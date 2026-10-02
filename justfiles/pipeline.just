# Bench pipeline provisioning and control -- docs/testing.md covers what each
# tier proves and how to run it.
#
# Required variables (set by importing Justfile):
#   py - the python3 interpreter every python recipe runs

[group('pipeline')]
[script('bash')]
[doc("Provision the pipeline's checkouts, ssh key, env file and units")]
pipeline-install driver_ref=env('PIPELINE_DRIVER_REF', 'main') \
                 pipeline_baseline_ref=env('PIPELINE_BASELINE_REF', 'origin/main') \
                 dl_dir=env('DL_DIR', (justfile_directory() / 'build/downloads')) \
                 sstate_dir=env('SSTATE_DIR', (justfile_directory() / 'build/sstate-cache')) \
                 target=env('PIPELINE_TARGET', ''):
    set -euo pipefail
    if [ -z "{{target}}" ]; then
        echo "pipeline-install: target not given -- pass target=<address> or set PIPELINE_TARGET" >&2
        exit 1
    fi
    TARGET="{{target}}"
    # Same lock file and fd as tools/pipeline/run.sh.
    PIPELINE_LOCK="$HOME/.config/wisekiosk/pipeline.lock"
    mkdir -p "$(dirname "$PIPELINE_LOCK")"
    exec 9>"$PIPELINE_LOCK"
    if ! flock -n 9; then
        echo "pipeline-install: pipeline lock held -- a run is in progress; refusing to touch the checkouts" >&2
        exit 1
    fi
    ROOT=$(readlink -f "{{justfile_directory()}}")
    mkdir -p "{{dl_dir}}" "{{sstate_dir}}"
    DL_DIR=$(readlink -f "{{dl_dir}}")
    SSTATE_DIR=$(readlink -f "{{sstate_dir}}")
    DRIVER="$HOME/wisekiosk-pipeline/driver"
    TREE="$HOME/wisekiosk-pipeline/tree"
    MAP=$(readlink -f "$ROOT/local/device-identity.md")
    KEYS=$(readlink -f "$ROOT/local/keys")
    ORIGIN_URL=$(git -C "$ROOT" remote get-url origin)

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

    for d in "$DRIVER" "$TREE"; do
        if [ -L "$d/local" ]; then
            echo "$d/local is a symlink -- refusing" >&2
            exit 1
        fi
        mkdir -p "$d/local"
        ln -sf "$MAP" "$d/local/device-identity.md"
    done
    # local/keys: an empty bind-mount target -- docs/testing.md §"Running it".
    # A non-empty keys dir fails rmdir and aborts the recipe.
    for p in "$DRIVER/local/keys" "$TREE/local/keys"; do
        [ -L "$p" ] && rm -- "$p"
        [ -d "$p" ] && rmdir -- "$p"
    done
    mkdir -p "$TREE/local/keys"

    # Seed hashserv.db once from the dev tree's -- docs/testing.md §"Running it".
    # sqlite3 online backup: copies the live WAL contents too.
    DEV_HASHSERV_DB="$ROOT/build/cache/hashserv.db"
    PIPELINE_HASHSERV_DB="$TREE/build/cache/hashserv.db"
    if [ -f "$DEV_HASHSERV_DB" ] && [ ! -f "$PIPELINE_HASHSERV_DB" ]; then
        mkdir -p "$TREE/build/cache"
        rm -f "$PIPELINE_HASHSERV_DB.tmp"
        {{py}} -c 'import sqlite3, sys; src = sqlite3.connect("file:" + sys.argv[1] + "?mode=ro", uri=True); dst = sqlite3.connect(sys.argv[2]); src.backup(dst); dst.close(); src.close()' \
            "$DEV_HASHSERV_DB" "$PIPELINE_HASHSERV_DB.tmp"
        mv -- "$PIPELINE_HASHSERV_DB.tmp" "$PIPELINE_HASHSERV_DB"
        echo "seeded the pipeline's hash-equivalence DB from the dev tree (sqlite3 online backup)"
    fi

    CONF_DIR="$HOME/.config/wisekiosk"
    mkdir -p "$CONF_DIR"
    SSH_DIR="$CONF_DIR/pipeline-ssh"
    # Read by systemd EnvironmentFile= and by pipeline-run's `.`.
    {
        printf 'PATH="%s"\n' "$PATH"
        printf 'DL_DIR="%s"\n' "$DL_DIR"
        printf 'SSTATE_DIR="%s"\n' "$SSTATE_DIR"
        printf 'PIPELINE_DRIVER="%s"\n' "$DRIVER"
        printf 'PIPELINE_TREE="%s"\n' "$TREE"
        printf 'PIPELINE_BASELINE_REF="{{pipeline_baseline_ref}}"\n'
        printf 'PIPELINE_SSH_DIR="%s"\n' "$SSH_DIR"
        printf 'PIPELINE_KEYS_DIR="%s"\n' "$KEYS"
        printf 'PIPELINE_TARGET="%s"\n' "$TARGET"
    } > "$CONF_DIR/pipeline.env"
    echo "wrote $CONF_DIR/pipeline.env"

    mkdir -p "$SSH_DIR"
    chmod 700 "$SSH_DIR"
    if [ ! -f "$SSH_DIR/id_ed25519" ]; then
        ssh-keygen -t ed25519 -N "" -C "wisekiosk-pipeline" -f "$SSH_DIR/id_ed25519" -q
        echo "generated $SSH_DIR/id_ed25519"
    fi
    touch "$SSH_DIR/known_hosts"

    # Host *: the testimage container dials TEST_TARGET_IP, a bare address.
    {
        printf 'Host *\n'
        printf '    User root\n'
        printf '    IdentityFile ~/.ssh/id_ed25519\n'
        printf '    StrictHostKeyChecking accept-new\n'
        printf '    UserKnownHostsFile ~/.ssh/known_hosts\n'
    } > "$SSH_DIR/config"
    echo "wrote $SSH_DIR/config"

    PUBKEY=$(cat "$SSH_DIR/id_ed25519.pub")
    SSH="ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10"
    $SSH "root@$TARGET" "mkdir -p ~/.ssh && chmod 700 ~/.ssh && touch ~/.ssh/authorized_keys && grep -qxF '$PUBKEY' ~/.ssh/authorized_keys || echo '$PUBKEY' >> ~/.ssh/authorized_keys"
    echo "installed the pipeline key on root@$TARGET"

    TARGET_HOSTNAME=$($SSH -i "$SSH_DIR/id_ed25519" "root@$TARGET" hostname)
    printf 'PIPELINE_TARGET_HOSTNAME="%s"\n' "$TARGET_HOSTNAME" >> "$CONF_DIR/pipeline.env"
    echo "recorded the target's hostname in $CONF_DIR/pipeline.env"

    mkdir -p "$HOME/.config/systemd/user"
    ln -sf "$DRIVER/tools/pipeline/wisekiosk-pipeline.service" "$HOME/.config/systemd/user/wisekiosk-pipeline.service"
    ln -sf "$DRIVER/tools/pipeline/wisekiosk-pipeline.timer" "$HOME/.config/systemd/user/wisekiosk-pipeline.timer"
    systemctl --user daemon-reload
    echo "symlinked the units into ~/.config/systemd/user/ and reloaded"

    if ! loginctl show-user "$(id -un)" -p Linger 2>/dev/null | grep -q '^Linger=yes$'; then
        loginctl enable-linger "$(id -un)"
        echo "enabled linger for $(id -un)"
    fi

    systemd-run --user --wait --pipe -p "EnvironmentFile=$CONF_DIR/pipeline.env" -- gh auth status
    systemd-run --user --wait --pipe -p "EnvironmentFile=$CONF_DIR/pipeline.env" -- git -C "$DRIVER" ls-remote origin HEAD
    echo "gh auth and git ls-remote both proved under systemd-run --user"
    echo "the timer is NOT enabled -- run 'just pipeline-on' when ready"

[group('pipeline')]
[script('bash')]
[doc("Print and clear any DISABLED reason, then enable the pipeline timer")]
pipeline-on:
    set -euo pipefail
    DISABLED="$HOME/wisekiosk-pipeline/driver/local/pipeline/DISABLED"
    if [ -f "$DISABLED" ]; then
        echo "clearing DISABLED:"
        cat "$DISABLED"
        rm -- "$DISABLED"
    fi
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

[group('pipeline')]
[script('bash')]
[doc("Run one pipeline job by hand: no args (queue head, or a missing baseline) | baseline [sha]")]
pipeline-run *args:
    set -a
    . "$HOME/.config/wisekiosk/pipeline.env"
    set +a
    "$HOME/wisekiosk-pipeline/driver/tools/pipeline/run.sh" {{args}}
