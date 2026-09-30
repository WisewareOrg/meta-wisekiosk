# Kiosk build and deployment commands
#
# Convenience commands for building the kiosk image, managing RAUC OTA updates,
# and deploying to the device.
#
# Quick start:
#   just build              # Build the image (kas fetches sources/ on first run)
#   just build-with-history # Build with buildhistory, for `just artifact-diff`
#   just kiosk-ota          # Build a bundle and install it on the device
#   just flash /dev/sdX     # Flash to SD card
#   just rauc-status <ip>   # Check device RAUC status

set dotenv-load := true

# The interpreter every python recipe runs. A repo .venv holds PyYAML; nothing
# puts it on PATH, because neither `just` nor a git hook sources a startup file,
# so a bare `python3` resolves to a host one without it and the YAML guard
# fails on a tree that parses fine. Preferred, not required -- CI has no .venv
# and installs PyYAML into its own python3, which is the fallback.
py := if path_exists(justfile_directory() / ".venv/bin/python3") == "true" { justfile_directory() / ".venv/bin/python3" } else { "python3" }

# Default machine target
machine := env('MACHINE', 'raspberrypi0-wifi')

# Kas configuration
config := env('KAS_CONFIG', 'kiosk-zero-w.yaml')

# Image name for flash recipe
image-name := "core-image-base"

# The device every host-defaulting recipe talks to, in ssh target form. The
# address is site-specific and this repo is PUBLIC, so it is never committed:
# there is no in-tree default. Set it in the environment
# (`export KIOSK_HOST=root@<addr>`) or a local .env, and `just find <cidr>`
# learns the address of a board you just swapped in. A recipe run without it
# fails on an empty host rather than targeting a stale one.
kiosk-host := env('KIOSK_HOST', '')

# === RAUC Configuration ===

# Directory for RAUC bundles
rauc-bundle-dir := "build/bundles"

# The key the fleet trusts. Single source for the just side (the `flash` keyring
# guard, the rotation recipes' old-key default). kiosk-zero-w.yaml repeats the
# name because bitbake cannot read a just variable -- the ONE site this cannot
# cover; docs/rauc-key-rotation.md lists both under "Rotating to a new key".
fleet-key := "kiosk-2026"

# Consumed ONLY by `rauc-to-casync` in ota.just, which is disabled
# (RAUC_CASYNC_BUNDLE = "0"; chunker removed with #29). NOT the fleet signing
# path -- that is kiosk-zero-w.yaml's AUTONOMOS_RAUC_*, pointed at the fleet-key
# dir under local/keys. These name upstream's retired example keys, which no
# device trusts, and exist only after `kas-container checkout` populates
# sources/. Reviving casync means repointing RAUC_CERT/RAUC_KEY/RAUC_KEYRING at
# the fleet key: a dev-key-signed bundle installs nowhere.
rauc-cert := env('RAUC_CERT', 'sources/meta-autonomos/meta-autonomos-core/files/rauc-example-keys/development.cert.pem')
rauc-key := env('RAUC_KEY', 'sources/meta-autonomos/meta-autonomos-core/files/rauc-example-keys/development.key.pem')
rauc-keyring := env('RAUC_KEYRING', 'sources/meta-autonomos/meta-autonomos-core/files/rauc-example-keys/development.cert.pem')

# Import shared recipes
import 'justfiles/ota.just'
import 'justfiles/deploy.just'
import 'justfiles/device.just'
import 'justfiles/rotate.just'

default: help

# Print this help message
help:
    @just --list

# === Build ===

# Build the kiosk image using kas-container
[group('build')]
build:
    tools/write-build-rev.sh
    {{py}} tools/go-mods.py
    {{py}} tools/app-lockfile.py
    kas-container build {{config}}

[group('build')]
[doc("Build with buildhistory inherited, for artifact-diff")]
build-with-history:
    tools/write-build-rev.sh
    {{py}} tools/go-mods.py
    {{py}} tools/app-lockfile.py
    kas-container build {{config}}:includes/buildhistory.yaml

# Open a shell in the build environment
[group('build')]
shell:
    tools/write-build-rev.sh
    {{py}} tools/go-mods.py
    {{py}} tools/app-lockfile.py
    kas-container shell {{config}}

# === Clean ===

# Clean the build environment
[group('clean')]
clean:
    kas-container purge {{config}}

# Remove all build artifacts, sources, and start fresh
[group('clean')]
spotless: clean
    rm -rf build/
    rm -rf sources/

# === Repository guards ===

# Run the same checks CI runs. Fast, needs no build.
#
# Both run even when the first fails, matching `verify` and the pre-commit hook:
# two independent findings are worth more than the first one twice.
[group('guards')]
[script('bash')]
[doc("Run repository guards: secrets, template, shell syntax, YAML, gitleaks, IPs, service reachability, recovery wiring, trailing-; hooks, guard wiring, guard self-test, review-checklist taxonomy, CVE tools self-test, python interpreter, Go module generator self-test, config seed self-test, default-config path agreement, app lockfile self-test, device identity")]
guards:
    rc=0
    tools/ci-guards.sh || rc=1
    tools/scrub-identity.py --check || rc=1
    if [ $rc -ne 0 ]; then echo; echo "guards FAILED"; fi
    exit $rc

# Point git at .githooks so pre-commit runs the guards. Hooks are not carried by
# a clone, so this is per-checkout and has to be run once by hand.
[group('guards')]
[doc("Install the pre-commit hook for this checkout")]
install-hooks:
    git config core.hooksPath .githooks
    @echo "core.hooksPath -> .githooks (pre-commit runs tools/ci-guards.sh)"

# === Documentation checks ===

# Both checks run even when the first fails: two independent findings are worth
# more than the first one twice.
[group('check')]
[script('bash')]
[doc("Run every documentation check")]
verify:
    rc=0
    {{py}} tools/doc-links.py || rc=1
    {{py}} tools/doc-image.py check || rc=1
    if [ $rc -ne 0 ]; then echo; echo "verify FAILED"; fi
    exit $rc

# Cross-references in every tracked Markdown file: [text](path), #anchors, and
# section-name refs must resolve.
[group('check')]
[doc("Check that every tracked Markdown cross-reference resolves")]
links:
    {{py}} tools/doc-links.py

# What the prose says the image ships, against what it ships. Needs a populated
# build/ rootfs and is therefore local-only -- CI never builds, so wiring it
# into a required check would mean a permanently skipping gate.
[group('check')]
[doc("Check docs against what the built image ships (skips if unbuilt)")]
image:
    {{py}} tools/doc-image.py check

# === Image audit ===

[group('audit')]
[doc("Report the CVE findings from the last audit build (skips if unbuilt); --layer/--exclude/--min-cvss narrow the detail")]
cve *args:
    {{py}} tools/cve-report.py check {{args}}

[group('audit')]
[doc("Report the SBOM the last build emitted (skips if unbuilt)")]
sbom:
    {{py}} tools/sbom-report.py check

[group('audit')]
[doc("Second-source findings the CVE manifest does not carry (skips if unbuilt)")]
cve-scan:
    {{py}} tools/cve-scan.py check

[group('audit')]
[doc("Report what changed in the CVE picture since the previous audit build (skips if <2)")]
cve-delta:
    {{py}} tools/cve-delta.py check

[group('audit')]
[doc("Re-judge the kernel's CVE findings against the sources this config compiles (skips if unbuilt)")]
kernel-cve *args:
    {{py}} tools/kernel-cve.py check {{args}}

[group('audit')]
[doc("Report which pinned upstream repos have fallen behind their branch head (needs network)")]
currency:
    {{py}} tools/layer-currency.py check

[group('audit')]
[doc("Report where a PREFERRED_VERSION selects an older recipe than the pinned layer already ships (offline)")]
preferred-version:
    {{py}} tools/preferred-version.py check

[group('audit')]
[doc("Report which unpatched CVEs bumping one pin would plausibly close (offline; --fetch to update sources/)")]
gap repo *args:
    {{py}} tools/layer-currency.py gap {{repo}} {{args}}

[group('audit')]
[doc("Build with cve-check inherited: CVE manifest beside the image, snapshot in ~/.cache/wisekiosk")]
cve-build:
    tools/write-build-rev.sh
    {{py}} tools/go-mods.py
    {{py}} tools/app-lockfile.py
    kas-container build {{config}}:includes/cve-audit.yaml
    {{py}} tools/cve-delta.py snapshot

[group('audit')]
[doc("Report whether the buildhistory image dir differs between two refs (rc 1 = no change, rc 2 = could not tell)")]
artifact-diff base head *args:
    {{py}} tools/artifact-diff.py {{args}} {{base}} {{head}}

[group('audit')]
[script('bash')]
[doc("Build with testimage inherited; run the wisekiosk oeqa suite over ssh")]
testimage ssh_dir=env('PIPELINE_SSH_DIR', ''):
    if [ -z "{{ssh_dir}}" ] || [ -z "${TEST_TARGET_IP:-}" ]; then
        echo "testimage needs ssh_dir (or PIPELINE_SSH_DIR) and TEST_TARGET_IP set -- refusing" >&2
        exit 2
    fi
    tools/write-build-rev.sh
    {{py}} tools/go-mods.py
    {{py}} tools/app-lockfile.py
    # outside guard 10's regex (option before the subcommand)
    kas-container --ssh-dir {{ssh_dir}} --runtime-args "-e TEST_TARGET_IP=$TEST_TARGET_IP -e OEQA_JSON_RESULT_DIR=$OEQA_JSON_RESULT_DIR" build {{config}}:includes/testimage.yaml -c testimage

# Write per-site config to a device's /data. The image carries none of it.
[group('provision')]
[doc("Provision a reachable device's /data from secrets.yaml")]
provision-device host=kiosk-host:
    tools/provision.sh device {{host}}

# Before first boot: the wifi credentials are what let you reach the device, so
# the first write cannot come over the network.
[group('provision')]
[doc("Provision a mounted /data partition on a fresh card")]
provision-card mountpoint:
    tools/provision.sh card {{mountpoint}}

# === Pipeline (#119) ===
#
# The bench pipeline builds, artifact-diffs, OTAs, testimages, rolls back and
# reports on a systemd user timer -- see docs/testing.md "Running it". Every
# host artifact below is created ONLY by pipeline-install; nothing here is
# done to the host by hand.

# Idempotent: re-running updates the two checkouts to driver_ref and
# regenerates the env file and units, refusing nothing it can redo. Never
# touches the timer -- pipeline-on is the separate, deliberate step, gated on
# the falsifier pair passing (#119 decision 15).
[group('pipeline')]
[script('bash')]
[doc("Provision the pipeline's checkouts, ssh key, env file and units (idempotent; does not enable the timer)")]
pipeline-install driver_ref="main":
    set -euo pipefail
    ROOT="{{justfile_directory()}}"
    DRIVER="$HOME/wisekiosk-pipeline/driver"
    TREE="$HOME/wisekiosk-pipeline/tree"
    ORIGIN_URL=$(git -C "$ROOT" remote get-url origin)

    # Both checkouts are pure infrastructure -- nobody edits them by hand --
    # so a re-run force-syncs them to driver_ref rather than merging drift.
    if [ -d "$DRIVER/.git" ]; then
        git -C "$DRIVER" fetch origin
        git -C "$DRIVER" checkout -B "{{driver_ref}}" "origin/{{driver_ref}}"
    else
        git clone --branch "{{driver_ref}}" "$ORIGIN_URL" "$DRIVER"
    fi
    if [ -d "$TREE/.git" ]; then
        git -C "$TREE" fetch origin
    else
        git clone "$ORIGIN_URL" "$TREE"
    fi
    git -C "$TREE" checkout --detach "origin/{{driver_ref}}"
    echo "driver and tree at origin/{{driver_ref}}"

    # One source of truth for the site: local/ is gitignored, so a symlink
    # inside it is ignored too (#119 decision 7).
    for d in "$DRIVER" "$TREE"; do
        mkdir -p "$d/local"
        ln -sf "$ROOT/local/device-identity.md" "$d/local/device-identity.md"
    done

    CONF_DIR="$HOME/.config/wisekiosk"
    mkdir -p "$CONF_DIR"
    SSH_DIR="$CONF_DIR/pipeline-ssh"
    # printf, not a heredoc: `just` treats a flush-left line as ending the
    # recipe body, so a heredoc's own terminator can never be flush-left here.
    # Every value double-quoted: this file is both an EnvironmentFile= (which
    # accepts that quoting per systemd.exec(5)) and, for `just pipeline-run`,
    # a plain `. `-sourced shell file -- and PATH on this host has spaces in
    # it (WSL's /mnt/c/Program Files/...), which an unquoted value would
    # word-split under the latter.
    {
        printf 'PATH="%s"\n' "$PATH"
        printf 'KAS_BUILD_DIR="%s"\n' "$ROOT/build"
        printf 'PIPELINE_DRIVER="%s"\n' "$DRIVER"
        printf 'PIPELINE_TREE="%s"\n' "$TREE"
        printf 'PIPELINE_BASELINE_REF="origin/main"\n'
        printf 'PIPELINE_SSH_DIR="%s"\n' "$SSH_DIR"
    } > "$CONF_DIR/pipeline.env"
    echo "wrote $CONF_DIR/pipeline.env"

    # A dedicated bench-only key, never ~/.ssh (decision 8): mounted into the
    # kas-container for the testimage stage only, so untrusted build/test
    # code never touches the key that also pushes to GitHub.
    mkdir -p "$SSH_DIR"
    chmod 700 "$SSH_DIR"
    if [ ! -f "$SSH_DIR/id_ed25519" ]; then
        ssh-keygen -t ed25519 -N "" -C "wisekiosk-pipeline" -f "$SSH_DIR/id_ed25519" -q
        echo "generated $SSH_DIR/id_ed25519"
    fi
    touch "$SSH_DIR/known_hosts"

    # A catch-all Host block, not a bench-specific one: what the container
    # connects to is TEST_TARGET_IP, a bare address passed at run time, never
    # a literal "bench" alias -- and this ssh dir is mounted only for the
    # testimage stage, so "every Host" already means "only bench".
    {
        printf 'Host *\n'
        printf '    User root\n'
        printf '    IdentityFile ~/.ssh/id_ed25519\n'
        printf '    StrictHostKeyChecking accept-new\n'
        printf '    UserKnownHostsFile ~/.ssh/known_hosts\n'
    } > "$SSH_DIR/config"
    echo "wrote $SSH_DIR/config"

    BENCH=$({{py}} tools/pipeline/resolve-role.py --map "$ROOT/local/device-identity.md" bench)
    PUBKEY=$(cat "$SSH_DIR/id_ed25519.pub")
    SSH="ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10"
    $SSH "root@$BENCH" "mkdir -p ~/.ssh && chmod 700 ~/.ssh && touch ~/.ssh/authorized_keys && grep -qxF '$PUBKEY' ~/.ssh/authorized_keys || echo '$PUBKEY' >> ~/.ssh/authorized_keys"
    echo "installed the pipeline key on bench (root@$BENCH)"

    mkdir -p "$HOME/.config/systemd/user"
    ln -sf "$DRIVER/tools/pipeline/wisekiosk-pipeline.service" "$HOME/.config/systemd/user/wisekiosk-pipeline.service"
    ln -sf "$DRIVER/tools/pipeline/wisekiosk-pipeline.timer" "$HOME/.config/systemd/user/wisekiosk-pipeline.timer"
    systemctl --user daemon-reload
    echo "symlinked the units into ~/.config/systemd/user/ and reloaded"

    if ! loginctl show-user "$(id -un)" -p Linger 2>/dev/null | grep -q '^Linger=yes$'; then
        loginctl enable-linger "$(id -un)"
        echo "enabled linger for $(id -un)"
    fi

    # Proved under the same systemd --user context the timer itself runs
    # under -- not just this interactive shell's.
    systemd-run --user --wait --pipe -- gh auth status
    systemd-run --user --wait --pipe -- git -C "$DRIVER" ls-remote origin HEAD
    echo "gh auth and git ls-remote both proved under systemd-run --user"
    echo "the timer is NOT enabled -- run 'just pipeline-on' when ready"

[group('pipeline')]
[doc("Enable the pipeline timer")]
pipeline-on:
    systemctl --user enable --now wisekiosk-pipeline.timer

[group('pipeline')]
[doc("Disable the pipeline timer")]
pipeline-off:
    systemctl --user disable --now wisekiosk-pipeline.timer

[group('pipeline')]
[script('bash')]
[doc("Report the timer's state and any DISABLED reason")]
pipeline-status:
    systemctl --user status wisekiosk-pipeline.timer --no-pager || true
    echo
    DISABLED="$HOME/wisekiosk-pipeline/driver/local/pipeline/DISABLED"
    if [ -f "$DISABLED" ]; then
        echo "DISABLED:"
        cat "$DISABLED"
    else
        echo "no DISABLED file"
    fi

# Sources the env file pipeline-install wrote, then runs the driver's own
# run.sh -- the same invocation the timer makes, by hand.
[group('pipeline')]
[script('bash')]
[doc("Run one pipeline job by hand: no args (next candidate) | baseline [sha] | pr N")]
pipeline-run *args:
    set -a
    . "$HOME/.config/wisekiosk/pipeline.env"
    set +a
    "$HOME/wisekiosk-pipeline/driver/tools/pipeline/run.sh" {{args}}
