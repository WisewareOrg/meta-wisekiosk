# The app commit, pinned in exactly one place. wisekiosk-frontend and
# wisekiosk-backend are two halves of one repository and both require this file,
# so they build from the same SRCREV.

HOMEPAGE = "https://github.com/tjwise99/WiseKiosk"
LICENSE = "MIT"

SRC_URI = "git://github.com/tjwise99/WiseKiosk.git;protocol=https;branch=main"
SRCREV = "9ad6b27d0608fea1534bca1c274618756d9020cf"

# The app carries no release version; `+git` is poky's spelling for that, SRCPV
# being empty in 4.3 and later.
PV = "0.0+git"
