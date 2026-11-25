# One host key, so the first boot of a slot generates one key rather than the three sshd_check_keys
# makes for the defaults. This append runs after the recipe's own, so sshd_config_readonly (copied
# there) is unchanged.
do_install:append() {
    sed -i 's|^#HostKey /etc/ssh/ssh_host_ed25519_key$|HostKey /etc/ssh/ssh_host_ed25519_key|' ${D}${sysconfdir}/ssh/sshd_config
    [ "$(grep -c '^HostKey ' ${D}${sysconfdir}/ssh/sshd_config)" = 1 ] || bbfatal "sshd_config must list exactly one HostKey"
}
