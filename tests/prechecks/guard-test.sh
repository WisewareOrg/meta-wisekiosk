#!/usr/bin/env bash
# Self-test for .claude/hooks/guard.sh, run by `just check` and by CI.
#
# The payloads contain the patterns the guard blocks, so they live in this file and not in a Bash
# tool call. Every rule has must-block and must-allow cases, and every input shape the guard
# normalises (heredoc body, sudo prefix, ...) has its own pair.
#
# Identity and sysfs are fixtures, never this machine and never the real map:
#   - the fixture addresses are RFC 5737 documentation addresses;
#   - the fixture prod hostname ends in `0-wifi`, like the Yocto MACHINE name, so it also appears
#     inside legitimate build paths.
set -uo pipefail

G="$(cd "$(dirname "$0")/../.." && pwd)/.claude/hooks/guard.sh"
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT

cat > "$T/device-identity.md" <<'FIXTURE'
# fixture identity map
```identity
prod.address    = 198.51.100.7
bench.address   = 198.51.100.14
bench.hostname  = fixture-bench
public.prod.hostname = fixture-board0-wifi
```
FIXTURE

mkdir -p "$T/sys/block/sdz" "$T/sys/block/sdy"
echo 0 > "$T/sys/block/sdz/removable"   # a fixed disk
echo 1 > "$T/sys/block/sdy/removable"   # a card reader

# A /dev fixture: `/dev/disk/by-id/...` is a symlink to a disk node, which needs a real symlink.
mkdir -p "$T/dev/disk/by-id"
: > "$T/dev/sdz"
ln -s ../../sdz "$T/dev/disk/by-id/fixture-fixed-disk"

export KIOSK_IDENTITY_FILE="$T/device-identity.md"
export KIOSK_SYSFS_ROOT="$T/sys"
export KIOSK_DEV_ROOT="$T/dev"

# Grant fixtures: the expiring prod grant, written with the real unix time. KIOSK_PROD_AUTH_FILE is
# set per case, except in the worktree case.
NOW=$(date +%s)
GRANT_VALID="$T/prod-auth-valid"
GRANT_EXPIRED="$T/prod-auth-expired"
GRANT_MISSING_KEY="$T/prod-auth-missing-key"
GRANT_NON_INTEGER="$T/prod-auth-non-integer"
GRANT_NONE="$T/prod-auth-none"   # deliberately never created -- "no grant"
# Exported globally like KIOSK_IDENTITY_FILE: a case without its own KIOSK_PROD_AUTH_FILE prefix
# does not resolve to this checkout's local/prod-auth.
export KIOSK_PROD_AUTH_FILE="$GRANT_NONE"
printf 'expires=%s\n' "$((NOW + 3600))" > "$GRANT_VALID"
printf 'expires=%s\n' "$((NOW - 3600))" > "$GRANT_EXPIRED"
printf 'notexpires=%s\n' "$((NOW + 3600))" > "$GRANT_MISSING_KEY"
printf 'expires=notanumber\n' > "$GRANT_NON_INTEGER"

pass=0; fail=0
# Extra environment for the guard under test, as `env` arguments. The worktree block uses it to
# unset the identity-file override, which an assignment prefix cannot express.
TENV=()
t() { # $1=label $2=expect $3=payload
  out=$(printf '%s' "$3" | env ${TENV+"${TENV[@]}"} "$G" 2>&1); rc=$?
  got=$([ $rc -eq 2 ] && echo BLOCK || echo ALLOW)
  if [ "$got" = "$2" ]; then r="ok  "; pass=$((pass+1)); else r="FAIL"; fail=$((fail+1)); fi
  printf '%s expected=%-5s got=%-5s  %s\n' "$r" "$2" "$got" "$1"
  [ "$got" = "$2" ] || printf '        %s\n' "$out" | head -n 3
}
# jq-constructed, not printf: a payload containing a double quote breaks hand-built JSON.
b() { jq -nc --arg c "$1" '{tool_name:"Bash",tool_input:{command:$c}}'; }
e() { jq -nc --arg f "$1" '{tool_name:"Edit",tool_input:{file_path:$f}}'; }

PROD='198.51.100.7'; BENCH='198.51.100.14'; PHOST='fixture-board0-wifi'
# Assembled, so no line in this file is itself the banned spelling.
KILLPAT='pk''ill'; GREPPAT='pg''rep'

echo "--- must BLOCK: rule 1, destructive op aimed at PROD ---"
t "prod OTA by address"   BLOCK "$(b "just kiosk-ota host=root@$PROD")"
t "prod reboot by name"   BLOCK "$(b "just kiosk-reboot host=root@$PHOST")"
t "prod rauc install"     BLOCK "$(b "ssh root@$PROD rauc install /data/update.raucb")"
t "prod bare reboot"      BLOCK "$(b "ssh root@$PROD reboot")"
t "prod reprovision"      BLOCK "$(b "tools/provision.sh device root@$PROD")"
t "prod direct install tool" BLOCK "$(b "tools/kiosk-install.sh root@$PROD")"
t "prod direct install tool, quoted" BLOCK "$(b "\"tools/kiosk-install.sh\" root@$PROD b.raucb")"
t "prod direct install tool, ./"     BLOCK "$(b "cd tools && ./kiosk-install.sh root@$PROD b.raucb")"
t "prod direct install tool, //"     BLOCK "$(b "tools//kiosk-install.sh root@$PROD b.raucb")"
t "bench direct install tool"        ALLOW "$(b "tools/kiosk-install.sh root@$BENCH b.raucb")"
# The hostname in ssh-target position, with no `user@`: `-l root <host>` and bare `ssh <host> <cmd>`.
t "prod ssh, no user@"    BLOCK "$(b "ssh $PHOST reboot")"
t "prod ssh -l root"      BLOCK "$(b "ssh -l root $PHOST reboot")"
t "prod host= no user@"   BLOCK "$(b "just kiosk-ota host=$PHOST")"
# A heredoc body is kept when the opener names a shell (bash -s).
t "prod OTA in heredoc"   BLOCK "$(b "$(printf "tools/kiosk-ssh.sh root@%s 'bash -s' <<'EOF'\nrauc install /data/update.raucb\nreboot\nEOF" "$PROD")")"
# A power verb behind `sudo`.
t "prod sudo reboot"      BLOCK "$(b "ssh root@$PROD 'sudo reboot'")"
t "prod sudo reboot bare" BLOCK "$(b "ssh root@$PROD sudo reboot")"
t "prod shutdown -r"      BLOCK "$(b "ssh root@$PROD 'shutdown -r now'")"
t "prod local sudo reboot" BLOCK "$(b "ssh root@$PROD uptime && sudo reboot")"
# An assignment after the privilege word: `env VAR=V <cmd>`.
t "prod sudo VAR= reboot" BLOCK "$(b "ssh root@$PROD uptime && sudo LC_ALL=C reboot")"
t "prod env VAR= reboot"  BLOCK "$(b "ssh root@$PROD uptime && env LC_ALL=C reboot")"
# A wrapper option with a separate value.
t "prod sudo -u root"     BLOCK "$(b "ssh root@$PROD uptime && sudo -u root reboot")"
t "prod ssh sudo -u root" BLOCK "$(b "ssh root@$PROD sudo -u root reboot")"
# `systemctl halt` and `systemctl kexec`.
t "prod systemctl halt"   BLOCK "$(b "ssh root@$PROD systemctl halt")"
t "prod systemctl kexec"  BLOCK "$(b "ssh root@$PROD systemctl kexec")"

echo "--- must BLOCK: rule 2, image write to a non-removable device ---"
t "flash to fixed disk"   BLOCK "$(b 'just flash /dev/sdz')"
t "dd to nvme"            BLOCK "$(b 'dd if=core-image.wic of=/dev/nvme0n1 bs=4M')"
t "dd to virtio disk"     BLOCK "$(b 'dd if=core-image.wic of=/dev/vda bs=4M')"
t "bmaptool to fixed"     BLOCK "$(b 'bmaptool copy core-image.wic.bz2 /dev/sdz')"
t "dd to fixed partition" BLOCK "$(b 'dd if=x.img of=/dev/sdz1')"
# A power-off or writer verb behind `sudo`.
t "sudo bmaptool"         BLOCK "$(b 'sudo bmaptool copy core-image.wic.bz2 /dev/sdz')"
t "sudo dd, quoted of="   BLOCK "$(b "sudo dd if=x.wic of='/dev/sdz' bs=4M")"
t "device via variable"   BLOCK "$(b "D=/dev/sdz; sudo dd if=x.wic of=\$D")"
t "provision-fresh-card"  BLOCK "$(b 'just provision-fresh-card /dev/sdz')"
t "redirect to disk"      BLOCK "$(b 'cat core-image.wic > /dev/sdz')"
t "tee to disk"           BLOCK "$(b 'cat core-image.wic | sudo tee /dev/sdz > /dev/null')"
t "wipefs a disk"         BLOCK "$(b 'sudo wipefs -a /dev/sdz')"
t "mkfs a partition"      BLOCK "$(b 'sudo mkfs.vfat /dev/sdz1')"
t "by-id path"            BLOCK "$(b 'sudo dd if=x.wic of=/dev/disk/by-id/fixture-fixed-disk bs=4M')"
# The same prefixes on a writer with no `of=`: only the command-position anchor is measured.
t "sudo VAR= wipefs"      BLOCK "$(b 'sudo LC_ALL=C wipefs -a /dev/sdz')"
t "env VAR= sudo wipefs"  BLOCK "$(b 'env KIOSK=1 sudo wipefs -a /dev/sdz')"
t "sudo -u root bmaptool" BLOCK "$(b 'sudo -u root bmaptool copy core-image.wic.bz2 /dev/sdz')"

echo "--- must BLOCK: rules 3-7 ---"
t "ssh + suppress"        BLOCK "$(b "ssh root@$BENCH uptime 2>/dev/null")"
t "array form + suppress" BLOCK "$(b "ssh=(ssh -o BatchMode=yes root@$BENCH)
timeout 60 \"\${ssh[@]}\" uptime 2>/dev/null")"
t "disable sshd"          BLOCK "$(b "ssh root@$BENCH systemctl disable sshd")"
t "mask wpa_supplicant"   BLOCK "$(b 'systemctl mask wpa_supplicant.service')"
t "stop networkd"         BLOCK "$(b 'systemctl stop systemd-networkd')"
t "write cmdline.txt"     BLOCK "$(b 'echo x > /boot/cmdline.txt')"
t "cp INTO /boot"         BLOCK "$(b 'cp /data/uImage /boot/uImage')"
t "mv INTO /boot"         BLOCK "$(b 'mv new.dtb /boot/overlay.dtb')"
t "rm from /boot"         BLOCK "$(b 'rm /boot/cmdline.txt')"
t "tee into /boot"        BLOCK "$(b 'echo x | tee /boot/config.txt')"
t "sed -i on /boot"       BLOCK "$(b 'sed -i s/a/b/ /boot/cmdline.txt')"
t "fw_setenv"             BLOCK "$(b 'fw_setenv bootdelay 0')"
# /boot writers behind `sudo`, `doas` and a `VAR=1 ` assignment.
t "sudo sed -i on /boot"  BLOCK "$(b 'sudo sed -i s/a/b/ /boot/cmdline.txt')"
t "sudo rm from /boot"    BLOCK "$(b 'sudo rm /boot/cmdline.txt')"
t "sudo truncate /boot"   BLOCK "$(b 'sudo truncate -s0 /boot/config.txt')"
t "sudo dd into /boot"    BLOCK "$(b 'sudo dd if=k.img of=/boot/uImage')"
t "sudo cp INTO /boot"    BLOCK "$(b 'sudo cp /data/uImage /boot/uImage')"
t "sudo mv INTO /boot"    BLOCK "$(b 'sudo mv new.dtb /boot/overlay.dtb')"
t "pipe to sudo tee"      BLOCK "$(b 'echo x | sudo tee /boot/config.txt')"
t "sudo fw_setenv"        BLOCK "$(b 'sudo fw_setenv bootdelay 0')"
t "doas sed on /boot"     BLOCK "$(b 'doas sed -i s/a/b/ /boot/cmdline.txt')"
t "assignment + sed"      BLOCK "$(b 'FOO=1 sed -i s/a/b/ /boot/cmdline.txt')"
# An assignment after the privilege word.
t "env VAR= rm /boot"     BLOCK "$(b 'env LC_ALL=C rm /boot/cmdline.txt')"
t "sudo VAR= sed /boot"   BLOCK "$(b 'sudo LC_ALL=C sed -i s/a/b/ /boot/cmdline.txt')"
t "env VAR= sudo rm"      BLOCK "$(b 'env KIOSK=1 sudo rm /boot/cmdline.txt')"
t "sudo -u root rm /boot" BLOCK "$(b 'sudo -u root rm /boot/cmdline.txt')"
t "nice -n 5 tee /boot"   BLOCK "$(b 'nice -n 5 tee /boot/config.txt')"
t "timeout 60 rm /boot"   BLOCK "$(b 'timeout 60 rm /boot/cmdline.txt')"
t "exit-echo after pipe"  BLOCK "$(b 'just verify | tail -50 ; echo "exit=$?"')"
t "kiosk-ssh + suppress"  BLOCK "$(b "tools/kiosk-ssh.sh root@$BENCH uptime 2>/dev/null")"
t "pkill bare -f"         BLOCK "$(b "$KILLPAT -f doseresp.sh")"
t "pgrep after &&"        BLOCK "$(b "cd /tmp && $GREPPAT -f nettest")"
t "pkill combined -af"    BLOCK "$(b "$KILLPAT -af foo")"
# `sudo pkill -f`; the -f matches the harness's own command line.
t "sudo pkill bare -f"    BLOCK "$(b "sudo $KILLPAT -f doseresp.sh")"
t "env pgrep bare -f"     BLOCK "$(b "env $GREPPAT -f nettest")"
t "env VAR= pkill -f"     BLOCK "$(b "env LC_ALL=C $KILLPAT -f doseresp.sh")"
t "sudo -u root pkill -f" BLOCK "$(b "sudo -u root $KILLPAT -f doseresp.sh")"
# Lifeline and /boot rules inside a heredoc body a shell reads.
t "lifeline in heredoc"   BLOCK "$(b "$(printf "ssh root@%s bash <<'EOF'\nsystemctl disable sshd\nEOF" "$BENCH")")"
t "/boot in heredoc"      BLOCK "$(b "$(printf "bash <<'EOF'\necho x > /boot/cmdline.txt\nEOF")")"

echo "--- must ALLOW: the legal variants ---"
t "bench OTA by address"  ALLOW "$(b "just kiosk-ota host=root@$BENCH")"
t "bench OTA by name"     ALLOW "$(b 'just kiosk-ota host=root@fixture-bench')"
# The prod hostname appears inside a bundle path aimed at the BENCH board; `/` is not a token
# separator, so those occurrences are not bare hostname tokens.
t "MACHINE name in paths" ALLOW "$(b "just kiosk-install host=root@$BENCH bundle=build/tmp-$PHOST/deploy/images/$PHOST/update-bundle-$PHOST.raucb")"
t "MACHINE= assignment"   ALLOW "$(b "MACHINE=$PHOST just build")"
t "MACHINE name, ls path" ALLOW "$(b "ls build/tmp-$PHOST/deploy/images/$PHOST/")"
echo "--- must ALLOW: observing PROD is not destroying it ---"
t "prod kiosk-status"     ALLOW "$(b "just kiosk-status root@$PROD")"
t "prod screenshot"       ALLOW "$(b "just screenshot root@$PROD")"
t "prod backup"           ALLOW "$(b "just kiosk-backup host=root@$PROD")"
t "prod preflight"        ALLOW "$(b "just kiosk-preflight host=root@$PROD")"
# Reading the soak log for reboot events is allowed.
t "prod grep for reboot"  ALLOW "$(b "ssh root@$PROD 'grep -c reboot /var/log/messages'")"
t "prod status | grep"    ALLOW "$(b "just kiosk-status root@$PROD | grep reboot")"
# After the sudo prefix the verb is the real command word, not an argument of grep.
t "prod sudo grep reboot" ALLOW "$(b "ssh root@$PROD 'sudo grep -c reboot /var/log/messages'")"
# An option's separate value is not accepted mid-prefix: `sudo -n grep -c reboot` is a read.
t "prod env grep reboot"  ALLOW "$(b "ssh root@$PROD 'env LC_ALL=C grep -c reboot /var/log/messages'")"
t "prod local env grep"   ALLOW "$(b "ssh root@$PROD uptime && env LC_ALL=C grep -c reboot /tmp/soak.log")"
t "prod sudo -n grep"     ALLOW "$(b "ssh root@$PROD uptime && sudo -n grep -c reboot /tmp/soak.log")"
t "prod ssh sudo -u grep" ALLOW "$(b "ssh root@$PROD sudo -u root grep -c reboot /var/log/messages")"
# Rule 1 applies to PROD only; bench is the reboot target.
t "bench systemctl halt"  ALLOW "$(b "ssh root@$BENCH systemctl halt")"
t "bench env VAR= OTA"    ALLOW "$(b "env LC_ALL=C just kiosk-ota host=root@$BENCH")"
t "bench sudo -u reboot"  ALLOW "$(b "ssh root@$BENCH sudo -u root reboot")"
echo "--- must ALLOW: rule 2's legal targets ---"
t "flash to card reader"  ALLOW "$(b 'just flash /dev/sdy')"
t "dd to removable part"  ALLOW "$(b 'dd if=x.img of=/dev/sdy1')"
t "flash to mmcblk"       ALLOW "$(b 'just flash /dev/mmcblk0')"
t "README placeholder"    ALLOW "$(b 'just flash /dev/sdX')"
t "sudo bmaptool to card" ALLOW "$(b 'sudo bmaptool copy core-image.wic.bz2 /dev/sdy')"
t "fresh card to reader"  ALLOW "$(b 'just provision-fresh-card /dev/sdy')"
t "lsblk names a disk"    ALLOW "$(b 'lsblk -o NAME,SIZE,RM,MODEL /dev/sdz')"
t "2>/dev/null, no disk"  ALLOW "$(b 'ls /nonexistent 2>/dev/null')"
echo "--- must ALLOW: rules 3-7 ---"
t "ssh, no suppress"      ALLOW "$(b "ssh root@$BENCH uptime")"
t "UserKnownHosts"        ALLOW "$(b "ssh -o UserKnownHostsFile=/dev/null root@$BENCH uptime")"
t "local suppress only"   ALLOW "$(b 'grep foo bar 2>/dev/null')"
t "local supp + ssh else" ALLOW "$(b "tail -n 5 /tmp/out 2>/dev/null
ssh=(ssh -o BatchMode=yes root@$BENCH)
timeout 60 \"\${ssh[@]}\" uptime")"
t "mask logind"           ALLOW "$(b 'systemctl mask systemd-logind.service')"
t "mask resolved"         ALLOW "$(b 'systemctl mask systemd-resolved.service')"
t "mask zram"             ALLOW "$(b 'systemctl mask zram.service')"
t "sshd is-active"        ALLOW "$(b 'systemctl is-active sshd')"
t "read /boot"            ALLOW "$(b 'cat /boot/cmdline.txt')"
t "ls /boot"              ALLOW "$(b 'ls -l /boot/')"
t "cp FROM /boot"         ALLOW "$(b 'cp /boot/uImage /data/uImage-known-good')"
t "cat FROM /boot"        ALLOW "$(b 'cat /boot/uImage > /data/uImage-A')"
# "a-r-m" contains "rm"; /boot/ counts only at the start of a path.
t "arm/boot in a path"    ALLOW "$(b 'ls build/work-shared/kernel-source/arch/arm/boot/dts/overlays/')"
# A prefix before a read of /boot stays a read.
t "sudo read /boot"       ALLOW "$(b 'sudo cat /boot/cmdline.txt')"
t "sudo ls /boot"         ALLOW "$(b 'sudo ls -l /boot/')"
t "sudo cp FROM /boot"    ALLOW "$(b 'sudo cp /boot/uImage /data/uImage-known-good')"
# Any number of wrapper words, assignments and options before a read of /boot stays a read.
t "sudo cat /boot"        ALLOW "$(b 'sudo cat /boot/config.txt')"
t "env VAR= cat /boot"    ALLOW "$(b 'env LC_ALL=C cat /boot/config.txt')"
t "sudo -u root ls /boot" ALLOW "$(b 'sudo -u root ls -l /boot/')"
t "sudo -u root sysctl"   ALLOW "$(b 'sudo -u root systemctl is-active sshd')"
t "slot rootfs boot"      ALLOW "$(b 'cd /mnt/root/boot && cat /data/uImage-arm1 > uImage')"
t "rauc mark-good"        ALLOW "$(b 'rauc status mark-good booted')"
t "fw_setenv mentioned"   ALLOW "$(b 'echo "re-arm via rauc, not fw_setenv"')"
t "pipe, no exit echo"    ALLOW "$(b 'just verify | tail -50')"
t "heredoc body mentions" ALLOW "$(b "$(printf 'git commit -F - <<EOF\nnote: fw_setenv is refused by the guard\nEOF')")"
# A heredoc whose opener names a file, not an interpreter, is data.
t "doc heredoc mentions"  ALLOW "$(b "$(printf "cat > docs/note.md <<'EOF'\nrauc install on prod is refused, as is a reboot there\nEOF")")"
t "script heredoc, data"  ALLOW "$(b "$(printf "cat > tools/example.sh <<'EOF'\nfw_setenv bootdelay 0\nEOF")")"
t "known_hosts edit"      ALLOW "$(b "ssh-keygen -R $BENCH 2>/dev/null")"
t "read .ssh, suppressed" ALLOW "$(b "cat ~/.ssh/known_hosts 2>/dev/null | grep -c $BENCH")"
t "pgrep -x -f exact"     ALLOW "$(b "$GREPPAT -x -f '/bin/bash /tmp/x.sh'")"
t "pkill -x by name"      ALLOW "$(b "$KILLPAT -x surf")"
t "pkill in an echo"      ALLOW "$(b "echo 'do not use $KILLPAT -f here'")"
t "edit outside the repo" ALLOW "$(e /home/tjwise/elsewhere/NOTES.md)"

echo "--- escape hatch: authorized /boot write ---"
# The marker is read from the command text, not the environment: the hook runs before the command
# does. The payload is a redirect, which has no command-position anchor, so an ALLOW comes only
# from the marker check.
t "hatch in command text" ALLOW "$(b 'KIOSK_ALLOW_BOOT_WRITE=1 cat /data/cmdline.txt > /boot/cmdline.txt')"
printf '%s' "$(b 'cat /data/cmdline.txt > /boot/cmdline.txt')" > "$T/hatch.json"
KIOSK_ALLOW_BOOT_WRITE=1 "$G" < "$T/hatch.json" > /dev/null 2>&1
rc=$?
if [ $rc -eq 2 ]; then r="ok  "; pass=$((pass+1)); else r="FAIL"; fail=$((fail+1)); fi
printf '%s expected=BLOCK got=%-5s  hatch in ENVIRONMENT only\n' "$r" "$([ $rc -eq 2 ] && echo BLOCK || echo ALLOW)"

echo "--- worktree: the map lives in the PRIMARY tree only ---"
# `local/` is gitignored, so a linked worktree has none; the map resolves through
# `git rev-parse --git-common-dir` to the primary tree. The case uses a real `git worktree`, with
# the GIT_* variables git exports to hooks unset for the fixture and for the guard.
GITUNSET=(-u GIT_DIR -u GIT_INDEX_FILE -u GIT_WORK_TREE -u GIT_OBJECT_DIRECTORY
          -u GIT_COMMON_DIR -u GIT_PREFIX -u GIT_NAMESPACE
          -u GIT_ALTERNATE_OBJECT_DIRECTORIES)
if env "${GITUNSET[@]}" git -c init.defaultBranch=main init -q "$T/primary" \
   && env "${GITUNSET[@]}" git -C "$T/primary" -c user.email=guard@test -c user.name=guard \
        commit -q --allow-empty -m init \
   && env "${GITUNSET[@]}" git -C "$T/primary" worktree add -q "$T/wt" -b guard-test-wt; then
    mkdir -p "$T/primary/local"
    cp "$T/device-identity.md" "$T/primary/local/device-identity.md"
    # -u on both: the block tests the default resolution path, not the exported overrides.
    TENV=("${GITUNSET[@]}" -u KIOSK_IDENTITY_FILE -u KIOSK_PROD_AUTH_FILE "CLAUDE_PROJECT_DIR=$T/wt")
    t "worktree prod OTA"     BLOCK "$(b "just kiosk-ota host=root@$PROD")"
    t "worktree prod reboot"  BLOCK "$(b "ssh root@$PROD reboot")"
    t "worktree prod suppress" BLOCK "$(b "ssh root@$PROD uptime 2>/dev/null")"
    t "worktree bench OTA"    ALLOW "$(b "just kiosk-ota host=root@$BENCH")"
    # local/prod-auth resolves from the primary tree like local/device-identity.md.
    printf 'expires=%s\n' "$((NOW + 3600))" > "$T/primary/local/prod-auth"
    t "worktree grant: prod OTA allowed" ALLOW "$(b "just kiosk-ota host=root@$PROD")"
    printf 'expires=%s\n' "$((NOW - 3600))" > "$T/primary/local/prod-auth"
    t "worktree grant: expired still blocks" BLOCK "$(b "just kiosk-ota host=root@$PROD")"
    TENV=()
else
    fail=$((fail+1))
    printf 'FAIL expected=BLOCK got=-      git worktree fixture could not be built -- worktree resolution NOT measured\n'
fi

echo "--- fail-open: no identity map (a fresh clone, or CI) ---"
# With no identity map the prod rules do not fire; the other rules still do.
KIOSK_IDENTITY_FILE="$T/does-not-exist.md" t "prod op, no map" ALLOW "$(b "just kiosk-ota host=root@$PROD")"
KIOSK_IDENTITY_FILE="$T/does-not-exist.md" t "boot write, no map" BLOCK "$(b 'echo x > /boot/cmdline.txt')"
# The missing map is reported on stderr.
printf '%s' "$(b "just kiosk-ota host=root@$PROD")" > "$T/nomap.json"
notice=$(KIOSK_IDENTITY_FILE="$T/does-not-exist.md" "$G" < "$T/nomap.json" 2>&1 > /dev/null)
case "$notice" in
    *INERT*) r="ok  "; pass=$((pass+1)) ;;
    *)       r="FAIL"; fail=$((fail+1)) ;;
esac
printf '%s expected=NOTICE                   no-map fail-open announces itself on stderr\n' "$r"

echo "--- no grant -- in-scope verbs still block ---"
KIOSK_PROD_AUTH_FILE="$GRANT_NONE" t "no grant: kiosk-ota"   BLOCK "$(b "just kiosk-ota host=root@$PROD")"
KIOSK_PROD_AUTH_FILE="$GRANT_NONE" t "no grant: bare reboot" BLOCK "$(b "ssh root@$PROD reboot")"

echo "--- an expired grant blocks ---"
KIOSK_PROD_AUTH_FILE="$GRANT_EXPIRED" t "expired grant: kiosk-ota"   BLOCK "$(b "just kiosk-ota host=root@$PROD")"
KIOSK_PROD_AUTH_FILE="$GRANT_EXPIRED" t "expired grant: bare reboot" BLOCK "$(b "ssh root@$PROD reboot")"

echo "--- the expiry boundary -- exactly now blocks ---"
# grant_valid() requires `expires` strictly greater than `date +%s`, so expires == now is expired.
# The test samples the second before writing the grant and after the guard returns, and retries
# unless the two agree.
GRANT_BOUNDARY="$T/prod-auth-boundary"
attempt=0
while :; do
    prepass=$pass; prefail=$fail
    before=$(date +%s)
    printf 'expires=%s\n' "$before" > "$GRANT_BOUNDARY"
    KIOSK_PROD_AUTH_FILE="$GRANT_BOUNDARY" t "expiry boundary: expires == now blocks" BLOCK "$(b "just kiosk-ota host=root@$PROD")"
    after=$(date +%s)
    attempt=$((attempt+1))
    [ "$before" = "$after" ] && break
    # The second ticked over mid-call: discard the recorded result and retry.
    pass=$prepass; fail=$prefail
    if [ "$attempt" -ge 20 ]; then
        fail=$((fail+1))
        printf 'FAIL expected=BLOCK got=-      could not pin the expiry boundary in 20 attempts (clock too unstable)\n'
        break
    fi
done

echo "--- a malformed grant blocks, whatever shape the defect takes ---"
KIOSK_PROD_AUTH_FILE="$GRANT_MISSING_KEY"  t "malformed grant: missing key"          BLOCK "$(b "just kiosk-ota host=root@$PROD")"
KIOSK_PROD_AUTH_FILE="$GRANT_NON_INTEGER"  t "malformed grant: non-integer"          BLOCK "$(b "just kiosk-ota host=root@$PROD")"

echo "--- a valid grant allows every in-scope verb ---"
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "grant: kiosk-ota"               ALLOW "$(b "just kiosk-ota host=root@$PROD")"
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "grant: direct install tool"     ALLOW "$(b "tools/kiosk-install.sh root@$PROD")"
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "grant: kiosk-install"           ALLOW "$(b "just kiosk-install host=root@$PROD")"
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "grant: rauc install literal"    ALLOW "$(b "ssh root@$PROD rauc install /data/update.raucb")"
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "grant: kiosk-reboot"            ALLOW "$(b "just kiosk-reboot host=root@$PHOST")"
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "grant: systemctl reboot"        ALLOW "$(b "ssh root@$PROD systemctl reboot")"
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "grant: ssh bare reboot"         ALLOW "$(b "ssh root@$PROD reboot")"
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "grant: kiosk-rollback"          ALLOW "$(b "just kiosk-rollback host=root@$PROD")"
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "grant: provision-device recipe" ALLOW "$(b "just provision-device host=root@$PROD")"
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "grant: provision.sh device"     ALLOW "$(b "tools/provision.sh device root@$PROD")"

echo "--- a valid grant does not widen scope beyond the listed verbs ---"
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "grant: flash to fixed disk still blocked (RULE 2 unaffected)" BLOCK "$(b 'sudo bmaptool copy core-image.wic.bz2 /dev/sdz')"
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "grant: rauc-rotate still blocked"     BLOCK "$(b "tools/rauc-rotate.sh root@$PROD local/keys/fleet-key")"
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "grant: systemctl poweroff still blocked" BLOCK "$(b "ssh root@$PROD systemctl poweroff")"
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "grant: systemctl halt still blocked"     BLOCK "$(b "ssh root@$PROD systemctl halt")"
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "grant: shutdown -r still blocked"        BLOCK "$(b "ssh root@$PROD 'shutdown -r now'")"
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "grant: systemctl kexec still blocked"    BLOCK "$(b "ssh root@$PROD systemctl kexec")"

echo "--- a grant-scoped verb chained with an always-blocked verb still blocks ---"
# always_blocked and grant_scoped are each computed over the whole command line, not per ssh
# invocation or per `&&` segment.
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "grant: chained OTA + poweroff still blocks" BLOCK "$(b "just kiosk-ota host=root@$PROD && ssh root@$PROD poweroff")"
# A power verb followed by a closing quote ends at VERBEND, and `reboot -p/--halt/--poweroff` is
# always blocked although `reboot` alone is grant-scoped.
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "grant: rauc install && poweroff still blocks" BLOCK "$(b "ssh root@$PROD 'rauc install /data/update.raucb && poweroff'")"
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "grant: rauc install ; halt still blocks"      BLOCK "$(b "ssh root@$PROD 'rauc install /data/update.raucb; halt'")"
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "grant: reboot -p still blocks"                BLOCK "$(b "ssh root@$PROD reboot -p")"
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "grant: reboot --halt still blocks"            BLOCK "$(b "ssh root@$PROD reboot --halt")"
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "grant: reboot --poweroff still blocks"        BLOCK "$(b "ssh root@$PROD reboot --poweroff")"

echo "--- power-off and kexec spellings block with or without a grant ---"
# Power-off and kexec spellings, each proven with and without a grant.
KIOSK_PROD_AUTH_FILE="$GRANT_NONE"  t "no grant: /sbin/poweroff blocks"        BLOCK "$(b "ssh root@$PROD /sbin/poweroff")"
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "grant: /sbin/poweroff still blocks"     BLOCK "$(b "ssh root@$PROD /sbin/poweroff")"
KIOSK_PROD_AUTH_FILE="$GRANT_NONE"  t "no grant: kexec -e blocks"              BLOCK "$(b "ssh root@$PROD kexec -e")"
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "grant: kexec -e still blocks"           BLOCK "$(b "ssh root@$PROD kexec -e")"
KIOSK_PROD_AUTH_FILE="$GRANT_NONE"  t "no grant: systemctl --force poweroff blocks"    BLOCK "$(b "ssh root@$PROD systemctl --force poweroff")"
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "grant: systemctl --force poweroff still blocks" BLOCK "$(b "ssh root@$PROD systemctl --force poweroff")"

echo "--- prod log reads that only mention a power verb are allowed ---"
# Reads of prod logs that mention power verbs stay allowed, with and without a grant.
KIOSK_PROD_AUTH_FILE="$GRANT_NONE"  t "no grant: journalctl | grep 'reboot -p' allowed"  ALLOW "$(b "ssh root@$PROD \"journalctl -b -1 | grep -c 'reboot -p'\"")"
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "grant: journalctl | grep 'reboot -p' allowed"     ALLOW "$(b "ssh root@$PROD \"journalctl -b -1 | grep -c 'reboot -p'\"")"
# `--halt` here is grep's own argument, not a command.
KIOSK_PROD_AUTH_FILE="$GRANT_NONE"  t "no grant: grep ... --halt nonsense flag allowed" ALLOW "$(b "ssh root@$PROD \"grep reboot /var/log/messages --halt\"")"
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "grant: grep ... --halt nonsense flag allowed"    ALLOW "$(b "ssh root@$PROD \"grep reboot /var/log/messages --halt\"")"
# Workaround for an -E alternation whose last branch is a power or reboot verb: two -e patterns.
KIOSK_PROD_AUTH_FILE="$GRANT_NONE"  t "no grant: grep -e panic -e poweroff (workaround) allowed" ALLOW "$(b "ssh root@$PROD \"grep -e panic -e poweroff /var/log/messages\"")"
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "grant: grep -e panic -e poweroff (workaround) allowed"    ALLOW "$(b "ssh root@$PROD \"grep -e panic -e poweroff /var/log/messages\"")"
# Workaround: the power or reboot word is not the last branch of the alternation.
KIOSK_PROD_AUTH_FILE="$GRANT_NONE"  t "no grant: grep -cE halt|oom (reordered, workaround) allowed" ALLOW "$(b "ssh root@$PROD \"grep -cE 'halt|oom' /var/log/messages\"")"
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "grant: grep -cE halt|oom (reordered, workaround) allowed"    ALLOW "$(b "ssh root@$PROD \"grep -cE 'halt|oom' /var/log/messages\"")"
KIOSK_PROD_AUTH_FILE="$GRANT_NONE"  t "no grant: last -x | grep -e reboot -e shutdown (workaround) allowed" ALLOW "$(b "ssh root@$PROD \"last -x | grep -e reboot -e shutdown\"")"
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "grant: last -x | grep -e reboot -e shutdown (workaround) allowed"    ALLOW "$(b "ssh root@$PROD \"last -x | grep -e reboot -e shutdown\"")"
KIOSK_PROD_AUTH_FILE="$GRANT_NONE"  t "no grant: grep -c -e oom -e halt (workaround) allowed" ALLOW "$(b "ssh root@$PROD \"grep -c -e oom -e halt /var/log/messages\"")"
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "grant: grep -c -e oom -e halt (workaround) allowed"    ALLOW "$(b "ssh root@$PROD \"grep -c -e oom -e halt /var/log/messages\"")"

echo "--- the documented residual: an -E alternation ending in a power verb blocks ---"
# An -E alternation, or piped grep -E, whose last branch is a power-off or reboot verb has a bare
# `|` before the verb, which CMDPOS reads as a command separator, and a closing quote after it,
# which VERBEND accepts. The guard blocks it; the -e and reordered forms above are the workarounds.
KIOSK_PROD_AUTH_FILE="$GRANT_NONE"  t "documented residual: grep -cE oom|halt blocks"             BLOCK "$(b "ssh root@$PROD \"grep -cE 'oom|halt' /var/log/messages\"")"
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "documented residual (grant present): grep -cE oom|halt blocks" BLOCK "$(b "ssh root@$PROD \"grep -cE 'oom|halt' /var/log/messages\"")"
KIOSK_PROD_AUTH_FILE="$GRANT_NONE"  t "documented residual: last -x | grep reboot|shutdown blocks"             BLOCK "$(b "ssh root@$PROD \"last -x | grep -E 'reboot|shutdown'\"")"
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "documented residual (grant present): last -x | grep reboot|shutdown blocks" BLOCK "$(b "ssh root@$PROD \"last -x | grep -E 'reboot|shutdown'\"")"
KIOSK_PROD_AUTH_FILE="$GRANT_NONE"  t "documented residual: grep -cE panic|poweroff blocks" BLOCK "$(b "ssh root@$PROD \"grep -cE 'panic|poweroff' /var/log/messages\"")"

echo "--- further power-off/halt spellings block regardless of grant ---"
KIOSK_PROD_AUTH_FILE="$GRANT_NONE"  t "no grant: sh -c poweroff blocks"                    BLOCK "$(b "ssh root@$PROD sh -c poweroff")"
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "grant: sh -c poweroff still blocks"                 BLOCK "$(b "ssh root@$PROD sh -c poweroff")"
KIOSK_PROD_AUTH_FILE="$GRANT_NONE"  t "no grant: init 0 blocks"                            BLOCK "$(b "ssh root@$PROD init 0")"
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "grant: init 0 still blocks"                         BLOCK "$(b "ssh root@$PROD init 0")"
KIOSK_PROD_AUTH_FILE="$GRANT_NONE"  t "no grant: telinit 0 blocks"                         BLOCK "$(b "ssh root@$PROD telinit 0")"
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "grant: telinit 0 still blocks"                      BLOCK "$(b "ssh root@$PROD telinit 0")"
KIOSK_PROD_AUTH_FILE="$GRANT_NONE"  t "no grant: systemctl start poweroff.target blocks"   BLOCK "$(b "ssh root@$PROD systemctl start poweroff.target")"
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "grant: systemctl start poweroff.target still blocks" BLOCK "$(b "ssh root@$PROD systemctl start poweroff.target")"
KIOSK_PROD_AUTH_FILE="$GRANT_NONE"  t "no grant: systemctl isolate halt.target blocks"     BLOCK "$(b "ssh root@$PROD systemctl isolate halt.target")"
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "grant: systemctl isolate halt.target still blocks"  BLOCK "$(b "ssh root@$PROD systemctl isolate halt.target")"

echo "--- bypass probes -- a grant-scoped verb chained with a power verb, wrapped every way a hand-typed command actually gets wrapped ---"
# A grant-scoped verb and an always-blocked verb on one line, with a redirect, comment, second
# pipeline stage, trailing operator, wrapping shell, subshell parens or embedded newline around
# the power verb.
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "grant: chained + piped to tee still blocks"      BLOCK "$(b "ssh root@$PROD 'rauc install /data/update.raucb && poweroff' 2>&1 | tee log")"
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "grant: chained + > out still blocks"             BLOCK "$(b "ssh root@$PROD 'rauc install /data/update.raucb && poweroff' > out")"
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "grant: chained + trailing comment still blocks"  BLOCK "$(b "ssh root@$PROD 'rauc install /data/update.raucb && poweroff' # go")"
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "grant: chained + || true still blocks"           BLOCK "$(b "ssh root@$PROD 'rauc install /data/update.raucb && poweroff' || true")"
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "grant: chained + ; echo done still blocks"       BLOCK "$(b "ssh root@$PROD 'rauc install /data/update.raucb && poweroff' ; echo done")"
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "grant: chained + && echo ok still blocks"        BLOCK "$(b "ssh root@$PROD 'rauc install /data/update.raucb && poweroff' && echo ok")"
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "grant: timeout-wrapped, stdin redirected, still blocks" BLOCK "$(b "timeout 60 ssh root@$PROD 'rauc install /data/update.raucb; halt' </dev/null")"
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "grant: sh -c wrapping the remote command still blocks"  BLOCK "$(b "ssh root@$PROD \"sh -c 'rauc install /data/update.raucb; poweroff'\"")"
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "grant: sh -c wrapping + trailing 2>&1 still blocks"     BLOCK "$(b "ssh root@$PROD \"sh -c 'rauc install /data/update.raucb; poweroff'\" 2>&1")"
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "grant: subshell parens still blocks"             BLOCK "$(b "ssh root@$PROD '(rauc install /data/update.raucb; poweroff)'")"
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "grant: chained OTA + reboot -p, trailing 2>&1 still blocks" BLOCK "$(b "ssh root@$PROD 'rauc install /data/update.raucb && reboot -p' 2>&1")"
KIOSK_PROD_AUTH_FILE="$GRANT_VALID" t "grant: literal embedded newline still blocks" BLOCK "$(b "$(printf "ssh root@%s 'rauc install /data/update.raucb\npoweroff'\necho done" "$PROD")")"

echo "--- bare chained/multi-line power verbs block with no grant at all ---"
# No grant-scoped verb: an innocuous command chained before the always-blocked verb, or a
# literal newline between them.
KIOSK_PROD_AUTH_FILE="$GRANT_NONE" t "no grant: uptime ; poweroff, trailing 2>&1 blocks"  BLOCK "$(b "ssh root@$PROD 'uptime; poweroff' 2>&1")"
KIOSK_PROD_AUTH_FILE="$GRANT_NONE" t "no grant: uptime ; init 0, trailing 2>&1 blocks"    BLOCK "$(b "ssh root@$PROD 'uptime; init 0' 2>&1")"
KIOSK_PROD_AUTH_FILE="$GRANT_NONE" t "no grant: uptime ; /sbin/halt, trailing 2>&1 blocks" BLOCK "$(b "ssh root@$PROD 'uptime; /sbin/halt' 2>&1")"
KIOSK_PROD_AUTH_FILE="$GRANT_NONE" t "no grant: uptime, embedded newline, halt blocks"    BLOCK "$(b "$(printf "ssh root@%s 'uptime\nhalt' 2>&1" "$PROD")")"

echo "--- bench is unaffected by grant state either way ---"
KIOSK_PROD_AUTH_FILE="$GRANT_VALID"   t "grant present: bench OTA still allowed" ALLOW "$(b "just kiosk-ota host=root@$BENCH")"
KIOSK_PROD_AUTH_FILE="$GRANT_EXPIRED" t "grant expired: bench OTA still allowed" ALLOW "$(b "just kiosk-ota host=root@$BENCH")"

echo "--- revoking the grant (the file goes away) blocks again ---"
# Once the grant file is gone, the verb it allowed blocks again.
GRANT_REVOKABLE="$T/prod-auth-revokable"
printf 'expires=%s\n' "$((NOW + 3600))" > "$GRANT_REVOKABLE"
KIOSK_PROD_AUTH_FILE="$GRANT_REVOKABLE" t "revoke: allowed before" ALLOW "$(b "just kiosk-ota host=root@$PROD")"
rm -f "$GRANT_REVOKABLE"
KIOSK_PROD_AUTH_FILE="$GRANT_REVOKABLE" t "revoke: blocked after (grant file removed)" BLOCK "$(b "just kiosk-ota host=root@$PROD")"

echo
printf 'pass=%s fail=%s\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
