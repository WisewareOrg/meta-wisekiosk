# Pipeline provisioning and control: docs/testing.md §"Running it".
# Requires py from the root Justfile.

[group('pipeline')]
[doc("Provision the pipeline's checkouts and env file; install its ssh key on the target")]
pipeline-install dl_dir=env('DL_DIR', (justfile_directory() / 'build/downloads')) \
                 sstate_dir=env('SSTATE_DIR', (justfile_directory() / 'build/sstate-cache')) \
                 target=env('PIPELINE_TARGET', ''):
    DL_DIR={{dl_dir}} SSTATE_DIR={{sstate_dir}} PIPELINE_TARGET={{target}} tools/pipeline/install.sh

[group('pipeline')]
[script('bash')]
[doc("Print and clear any DISABLED reason, then enable the pipeline timer")]
pipeline-on:
    set -euo pipefail
    DRIVER="$HOME/wisekiosk-pipeline/driver"
    DISABLED="$DRIVER/local/pipeline/DISABLED"
    if [ -f "$DISABLED" ]; then
        echo "clearing DISABLED:"
        cat "$DISABLED"
        rm -- "$DISABLED"
    fi
    systemctl --user enable --now "$DRIVER/tools/pipeline/wisekiosk-pipeline.service" "$DRIVER/tools/pipeline/wisekiosk-pipeline.timer"

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
[doc("Run one pipeline job by hand: the queue head, or a missing baseline")]
pipeline-run:
    set -a
    . "$HOME/.config/wisekiosk/pipeline.env"
    set +a
    "$HOME/wisekiosk-pipeline/driver/tools/pipeline/run.sh"

[group('pipeline')]
[script('bash')]
[doc("Build and run <ref> from this checkout's own run.sh -- a dev tool: posts nothing, tags no baseline")]
pipeline-run-ref ref:
    set -a
    . "$HOME/.config/wisekiosk/pipeline.env"
    set +a
    tools/pipeline/run.sh {{ref}}

[group('pipeline')]
[script('bash')]
[doc("Record bench's current /data config as accepted -- the pre-job precondition compares against it")]
pipeline-accept-bench-config:
    set -a
    . "$HOME/.config/wisekiosk/pipeline.env"
    set +a
    "$HOME/wisekiosk-pipeline/driver/tools/pipeline/accept-bench-config.sh"

[group('pipeline')]
[doc("Live view of the merge queue and the current run; q quits")]
pipeline-watch:
    {{py}} tools/pipeline/watch.py
