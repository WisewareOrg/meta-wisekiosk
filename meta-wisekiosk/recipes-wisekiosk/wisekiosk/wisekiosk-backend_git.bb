SUMMARY = "WiseKiosk backend: serves the frontend bundle and the API on :8080"
DESCRIPTION = "One origin for the page, its configuration and the API. The bundle is served from \
disk at request time rather than embedded, which is what lets /srv/kiosk/config.json be a symlink \
into /data and be picked up without a rebuild. The port and the two flags are the app's, not this \
layer's."

require wisekiosk-src.inc
require wisekiosk-backend-go-mods.inc

# scarthgap unpacks file:// SRC_URI straight into WORKDIR; go.bbclass redirects
# only the git entry, so this lands beside the checkout.
SRC_URI += "file://wisekiosk.service"

# The proxy tree wisekiosk-backend-go-mods.inc's SRC_URI entries unpack into,
# holding only the modules this unpack's own entries name -- a stale module
# from a previous SRCREV never lingers to be read by mistake.
do_unpack[cleandirs] += "${WORKDIR}/goproxy"

GO_IMPORT = "github.com/tjwise99/WiseKiosk"

LIC_FILES_CHKSUM = "file://src/${GO_IMPORT}/LICENSE;md5=4af5bdd6287d36bddd2161cdad4e1eb5"

# The go module is the backend/ subtree, one level below the import path the
# checkout lands at.
GO_WORKDIR = "${GO_IMPORT}/backend"
GO_INSTALL = "${GO_IMPORT}/backend/cmd"

inherit go-mod

# Any fetch at compile time fails the task.
export GOPROXY = "off"

# oapi-codegen generates internal/boundary/boundary.gen.go from the app's
# shared OpenAPI document and never reaches the binary go_do_compile produces
# below -- it is a build-time-only dependency, but its own module graph still
# has to resolve under GOPROXY=off above, so it runs against the goproxy tree
# unpacked from wisekiosk-backend-go-mods.inc's SRC_URI entries rather than
# DL_DIR directly. GOOS/GOARCH are forced to the build host on this one
# command because oapi-codegen is a host-native tool, not the cross-compiled
# target the rest of this recipe builds. Path is the app's own justfile
# codegen recipe, run from backend/.
do_compile() {
    ( cd ${S}/src/${GO_WORKDIR} && GOOS=${BUILD_GOOS} GOARCH=${BUILD_GOARCH} \
        GOFLAGS=-modcacherw GOPROXY=file://${WORKDIR}/goproxy GOSUMDB=off \
        ${GO} tool oapi-codegen -config oapi-codegen.yaml ../boundary/openapi.yaml )
    [ -s ${S}/src/${GO_WORKDIR}/internal/boundary/boundary.gen.go ] \
        || bbfatal "oapi-codegen produced no internal/boundary/boundary.gen.go"
    go_do_compile
}

CGO_ENABLED = "0"

# poky's arm defaults assume cgo, and Go refuses both without it: goarch.bbclass
# sets GO_DYNLINK:arm ?= "1" (shared Go runtime) and go.bbclass appends
# -buildmode=pie. The :arm suffix is required -- an override-suffixed value wins
# over the bare name.
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

# The account the service runs as, uid and gid both pinned at 10001: /data is
# slot-shared, so the numeric ids are what survive an A/B update. The group is
# created explicitly because useradd otherwise assigns a gid of its own.
inherit useradd

USERADD_PACKAGES = "${PN}"
GROUPADD_PARAM:${PN} = "-g 10001 kiosk"
USERADD_PARAM:${PN} = "-u 10001 -g kiosk -d /srv/kiosk -s /bin/false -r kiosk"
