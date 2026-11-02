FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

# 52e8726d6782 (mainline v6.14) adds the `if (!sgl)` bounds check that turns
# running off the end of the brcmfmac SDIO scatterlist into -ENOMEM instead of a
# NULL deref. It was never backported to 6.6.y or 6.12.y, so no kernel bump
# delivers it -- that is why it is carried as a patch. Applies with zero fuzz and
# zero offset against 6.12.93.
#
# Hygiene for a real unguarded defect, explicitly NOT the fix for the crash
# diagnosed 2026-08-13 -- that was CPU instability at the top OPP, addressed by
# the kiosk-cpufreq recipe. Different fault class: this one faults near address 0
# with a resolvable PC.
SRC_URI += " file://brcmfmac-52e8726d6782.patch"

# #245: the soft-lockup detector, so a kernel looping with interrupts on panics
# with a stack trace into pstore before the 14s hardware watchdog fires,
# instead of a silent reset. CONFIG_HARDLOCKUP_DETECTOR and
# CONFIG_RCU_CPU_STALL_TIMEOUT are not selectable on this board (no CONFIG_SMP;
# see docs/issue_investigation/ota_install_reset/README.md's Batch 8 section).
SRC_URI += " file://lockup-detect.cfg"
