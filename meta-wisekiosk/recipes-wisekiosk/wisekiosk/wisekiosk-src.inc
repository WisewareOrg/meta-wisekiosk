# The app commit, pinned once; wisekiosk-frontend and wisekiosk-backend both require this file.

HOMEPAGE = "https://github.com/WisewareOrg/WiseKiosk"
LICENSE = "MIT"

SRC_URI = "git://github.com/WisewareOrg/WiseKiosk.git;protocol=https;branch=main"
SRCREV = "c21efa0743bdfee7749c63ec512bff87c9ffb1f5"

# The app carries no release version; `+git` is poky's spelling.
PV = "0.0+git"
