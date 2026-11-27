# Enables the ed25519 HostKey as the only one, so sshd_check_keys generates one key per slot
# instead of three. Runs after the recipe's own append, leaving sshd_config_readonly unchanged.
do_install:append() {
    sed -i 's|^#HostKey /etc/ssh/ssh_host_ed25519_key$|HostKey /etc/ssh/ssh_host_ed25519_key|' ${D}${sysconfdir}/ssh/sshd_config
    [ "$(grep -c '^HostKey ' ${D}${sysconfdir}/ssh/sshd_config)" = 1 ] || bbfatal "sshd_config must list exactly one HostKey"
}
