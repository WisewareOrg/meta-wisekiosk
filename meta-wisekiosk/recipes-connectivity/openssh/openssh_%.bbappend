# Spike: list one host key, so first boot of a slot makes one key, not three.
do_install:append() {
    sed -i 's|^#HostKey /etc/ssh/ssh_host_ed25519_key|HostKey /etc/ssh/ssh_host_ed25519_key|' ${D}${sysconfdir}/ssh/sshd_config
}
