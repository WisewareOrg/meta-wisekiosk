# Kiosk build and deployment commands
#
# Convenience commands for building the kiosk image, managing RAUC OTA updates,
# and deploying to the device.
#
# Quick start:
#   just build              # Build the image (kas fetches sources/ on first run)
#   just kiosk-ota          # Build a bundle and install it on the device
#   just flash /dev/sdX     # Flash to SD card
#   just rauc-status <ip>   # Check device RAUC status

set dotenv-load := true

# Interpreter for every python recipe: the repo .venv python3 when present, else PATH python3.
export py := if path_exists(justfile_directory() / ".venv/bin/python3") == "true" { justfile_directory() / ".venv/bin/python3" } else { "python3" }

machine := env('MACHINE', 'raspberrypi0-wifi')

config := env('KAS_CONFIG', 'kiosk-zero-w.yaml')

image-name := "core-image-base"

# The device every host-defaulting recipe talks to, in ssh target form (`root@<addr>`); read from
# KIOSK_HOST or a local .env, empty when unset.
kiosk-host := env('KIOSK_HOST', '')

# === RAUC Configuration ===

rauc-bundle-dir := "build/bundles"

# Name of the key the fleet trusts: the `flash` keyring guard and the rotation recipes' old-key
# default. kiosk-zero-w.yaml repeats it; bitbake cannot read a just variable.
fleet-key := "kiosk-2026"

# Read only by `rauc-to-casync` in ota.just. The defaults are upstream development keys that no
# device trusts, present once `kas-container checkout` populates sources/; reviving casync means
# repointing RAUC_CERT/RAUC_KEY/RAUC_KEYRING at the fleet key.
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
    tools/kas-run.sh build {{config}}

# Open a shell in the build environment
[group('build')]
shell:
    tools/kas-run.sh shell {{config}}

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

[group('guards')]
[script('bash')]
[doc("Run repository guards: the invariants in tools/ci-guards.sh, self-tests included, and the device-identity scan")]
guards:
    rc=0
    tools/ci-guards.sh || rc=1
    tools/scrub-identity.py --check || rc=1
    if [ $rc -ne 0 ]; then echo; echo "guards FAILED"; fi
    exit $rc

[group('guards')]
[doc("Install the pre-commit hook for this checkout")]
install-hooks:
    git config core.hooksPath .githooks
    @echo "core.hooksPath -> .githooks (pre-commit runs tools/ci-guards.sh)"

# === Documentation checks ===

[group('check')]
[script('bash')]
[doc("Run every documentation check")]
verify:
    rc=0
    {{py}} tools/doc-links.py || rc=1
    {{py}} tools/doc-image.py check || rc=1
    if [ $rc -ne 0 ]; then echo; echo "verify FAILED"; fi
    exit $rc

[group('check')]
[doc("Check that every tracked Markdown cross-reference resolves")]
links:
    {{py}} tools/doc-links.py

[group('check')]
[doc("Check the requirements tree with wise-ci's check-reqs")]
reqs:
    uv run --locked check-reqs --root docs/requirements

[group('check')]
[doc("Check docs/decisions/ and every ADR citation with wise-ci's check-adrs")]
adrs:
    uv run --locked check-adrs

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
    tools/kas-run.sh build {{config}}:includes/cve-audit.yaml
    {{py}} tools/cve-delta.py snapshot

[group('provision')]
[doc("Provision a reachable device's /data from secrets.yaml")]
provision-device host=kiosk-host:
    tools/provision.sh device {{host}}

[group('provision')]
[doc("Provision a mounted /data partition on a fresh card")]
provision-card mountpoint:
    tools/provision.sh card {{mountpoint}}
