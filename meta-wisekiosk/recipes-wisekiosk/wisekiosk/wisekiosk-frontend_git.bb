SUMMARY = "WiseKiosk frontend: the static bundle the kiosk displays"
DESCRIPTION = "The Svelte bundle vite builds from the app's source, with its API client and config types generated at build, served from /srv/kiosk by wisekiosk-backend."

require wisekiosk-src.inc

LIC_FILES_CHKSUM = "file://LICENSE;md5=ff8f37ef1b2dd140232b20d67501377f"

# PV carries the app commit hash, which need not sort forward.
ERROR_QA:remove = "version-going-backwards"
WARN_QA:append = " version-going-backwards"

# `;dev=1`: every package in the shrinkwrap is a devDependency, so the closure is empty without it.
# The npmsw path is literal, not searched through FILESPATH. destsuffix puts node_modules beside
# the app's package.json, where node resolves imports by walking up.
SRC_URI += "npmsw://${THISDIR}/${BPN}/npm-shrinkwrap.json;dev=1;destsuffix=git/frontend"

# Fatal when the gitignored npm-shrinkwrap.json, written by tools/app-lockfile.py, or its .srcrev
# stamp is missing or stale for this SRCREV. mark_dependency makes a changed mtime on either file
# invalidate the cached parse, since neither is `require`d.
python () {
    import os
    shrinkwrap = os.path.join(d.getVar('THISDIR'), d.getVar('BPN'),
                               'npm-shrinkwrap.json')
    stamp = shrinkwrap + '.srcrev'
    bb.parse.mark_dependency(d, shrinkwrap)
    bb.parse.mark_dependency(d, stamp)
    recorded = open(stamp).read().strip() if os.path.exists(stamp) else None
    if not os.path.exists(shrinkwrap) or recorded != d.getVar('SRCREV'):
        bb.fatal("npm-shrinkwrap.json is missing or stale for this SRCREV: "
                 "run `just build`, or any other entry point that runs "
                 "tools/app-lockfile.py, before bitbake.")
}

# Build-host only, no `inherit npm`: npmsw places the closure and the output is the vite bundle.
DEPENDS = "nodejs-binary-native"

S = "${WORKDIR}/git"

do_compile() {
    cd ${S}/frontend
    # orval emits through prettier; fail when it does not resolve.
    node --input-type=module -e "await import('prettier')" || bbfatal "prettier not importable; orval would emit unformatted code"
    node node_modules/orval/dist/bin/orval.mjs
    node node_modules/json-schema-to-typescript/dist/src/cli.js --input src/config/schema.json --output src/config/types.ts --additionalProperties false
    node node_modules/vite/bin/vite.js build
}

do_install() {
    install -d ${D}/srv/kiosk
    cp -R --no-dereference --preserve=mode,timestamps ${S}/frontend/dist/. ${D}/srv/kiosk/

    # config.json is a symlink into /data; the backend serves this tree per request through
    # http.Dir, which follows it. kiosk-seed-config seeds it from the example installed below.
    ln -s /data/config/config.json ${D}/srv/kiosk/config.json

    install -D -m 0644 ${S}/deploy/config.example.json ${D}${datadir}/wisekiosk/config.example.json
}

FILES:${PN} = "/srv/kiosk"
FILES:${PN} += "${datadir}/wisekiosk"
