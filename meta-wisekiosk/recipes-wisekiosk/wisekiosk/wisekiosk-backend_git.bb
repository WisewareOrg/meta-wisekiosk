SUMMARY = "WiseKiosk backend: serves the frontend bundle and the API on :8080"
DESCRIPTION = "The Go server that serves the frontend bundle from /srv/kiosk at request time, its configuration, and the API on :8080."

require wisekiosk-src.inc
require wisekiosk-backend-go-mods.inc

# PV carries the app commit hash, which need not sort forward.
ERROR_QA:remove = "version-going-backwards"
WARN_QA:append = " version-going-backwards"

# Fatal when the gitignored wisekiosk-backend-go-mods.inc, written by tools/go-mods.py, is
# missing or stale for this SRCREV.
python () {
    if d.getVar('WISEKIOSK_GOMODS_SRCREV') != d.getVar('SRCREV'):
        bb.fatal("wisekiosk-backend-go-mods.inc is missing or stale for this "
                 "SRCREV: run `just build`, or any other entry point that "
                 "runs tools/go-mods.py, before bitbake.")
}

# scarthgap unpacks file:// SRC_URI into WORKDIR; go.bbclass redirects only the git entry.
SRC_URI += "file://wisekiosk.service"

# The proxy tree wisekiosk-backend-go-mods.inc's SRC_URI entries unpack into; cleaned on each
# unpack so it holds only this SRCREV's modules.
do_unpack[cleandirs] += "${WORKDIR}/goproxy"

GO_IMPORT = "github.com/WisewareOrg/WiseKiosk"

LIC_FILES_CHKSUM = "file://src/${GO_IMPORT}/LICENSE;md5=ff8f37ef1b2dd140232b20d67501377f"

# The go module is the backend/ subtree of the checkout.
GO_WORKDIR = "${GO_IMPORT}/backend"
GO_INSTALL = "${GO_IMPORT}/backend/cmd"

inherit go-mod

# Any fetch at compile time fails the task.
export GOPROXY = "off"

# Generates internal/boundary/boundary.gen.go with oapi-codegen (the app's go:generate directive)
# before go_do_compile. It runs against the goproxy tree under GOPROXY=off. ${GO} is go-cross's
# wrapper, which forces the target GOOS/GOARCH, so this calls the unwrapped host go it execs.
do_compile() {
    ( cd ${S}/src/${GO_WORKDIR}/internal/boundary && GOOS=${BUILD_GOOS} GOARCH=${BUILD_GOARCH} \
        GOFLAGS=-modcacherw GOPROXY=file://${WORKDIR}/goproxy GOSUMDB=off \
        ${STAGING_LIBDIR_NATIVE}/${TARGET_SYS}/go/bin/go \
        tool oapi-codegen -config ../../oapi-codegen.yaml ../../../boundary/openapi.yaml )
    [ -s ${S}/src/${GO_WORKDIR}/internal/boundary/boundary.gen.go ] \
        || bbfatal "oapi-codegen produced no internal/boundary/boundary.gen.go"
    go_do_compile
}

CGO_ENABLED = "0"

# Without cgo Go refuses both poky arm defaults: GO_DYNLINK:arm ?= "1" and go.bbclass's
# -buildmode=pie. The :arm suffix is required; an override-suffixed value wins over the bare name.
GO_DYNLINK:arm = ""
GOBUILDFLAGS:remove = "-buildmode=pie"

inherit systemd

SYSTEMD_SERVICE:${PN} = "wisekiosk.service"
SYSTEMD_AUTO_ENABLE = "enable"

# `go install ./cmd` names the binary after its directory.
do_install:append() {
    mv ${D}${bindir}/cmd ${D}${bindir}/wisekiosk

    install -d ${D}${systemd_system_unitdir}
    install -m 0644 ${WORKDIR}/wisekiosk.service ${D}${systemd_system_unitdir}/wisekiosk.service
}

FILES:${PN} += "${systemd_system_unitdir}/wisekiosk.service"

# TLS anchors for the app's upstream calls.
RDEPENDS:${PN} += "ca-certificates"

# The service account, uid and gid pinned at 10001 because /data is shared by both slots.
# The group is created explicitly; useradd otherwise assigns its own gid.
inherit useradd

USERADD_PACKAGES = "${PN}"
GROUPADD_PARAM:${PN} = "-g 10001 kiosk"
USERADD_PARAM:${PN} = "-u 10001 -g kiosk -d /srv/kiosk -s /bin/false -r kiosk"
