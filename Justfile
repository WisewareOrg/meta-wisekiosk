set dotenv-load := true

export py := if path_exists(justfile_directory() / ".venv/bin/python3") == "true" { justfile_directory() / ".venv/bin/python3" } else { "python3" }

machine := env('MACHINE', 'raspberrypi0-wifi')

config := env('KAS_CONFIG', 'kiosk-zero-w.yaml')

image-name := "core-image-base"

kiosk-host := env('KIOSK_HOST', '')

fleet-key := "kiosk-2026"

import 'justfiles/ota.just'
import 'justfiles/deploy.just'
import 'justfiles/device.just'
import 'justfiles/rotate.just'

[private]
default: help

[doc("Print this help message")]
help:
    @just --list

[group('build')]
[doc("Build the kiosk image using kas-container")]
build:
    tools/kas-run.sh build {{config}}

[group('build')]
[doc("Open a shell in the build environment")]
shell:
    tools/kas-run.sh shell {{config}}

[group('clean')]
[doc("Clean the build environment")]
clean:
    kas-container purge {{config}}

[group('clean')]
[doc("Remove all build artifacts and sources, and start fresh")]
spotless: clean
    rm -rf build/
    rm -rf sources/

[group('check')]
[script('bash')]
[doc("Run every check CI runs: prechecks, Markdown links, device identity, requirements, ADRs. CI passes --allow-partial")]
check *flags:
    rc=0
    {{py}} -m pytest --confcutdir=tests/prechecks tests/prechecks || rc=1
    {{py}} tools/doc-links.py || rc=1
    {{py}} tools/scrub-identity.py --check {{flags}} || rc=1
    uv run --locked check-reqs --root docs/requirements || rc=1
    uv run --locked check-adrs || rc=1
    exit $rc

[group('check')]
[script('bash')]
[doc("Run `just check`, then check docs against what the built image ships (skips if unbuilt)")]
verify:
    rc=0
    {{just_executable()}} check || rc=1
    {{py}} tools/doc-image.py check || rc=1
    exit $rc

[group('check')]
[doc("Install the pre-commit hook for this checkout")]
install-hooks:
    git config core.hooksPath .githooks
    @echo "core.hooksPath -> .githooks (pre-commit runs just check)"

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
