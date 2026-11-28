
# Reads: fleet-key, config

keys-root := justfile_directory() / "local/keys"

[group('rotate')]
[doc("Generate a new RAUC signing key (gitignored, never committed)")]
rotate-keygen name=fleet-key:
    tools/rauc-keygen.sh "{{keys-root}}/{{name}}"

[group('rotate')]
[doc("Install this host's SSH pubkey on a device")]
rotate-provision-ssh host=kiosk-host:
    tools/rauc-provision-ssh.sh "{{host}}"

[group('rotate')]
[doc("Build the transition and end-state bundles for a rotation; OLD_KEYDIR is the fleet-key directory")]
rotate-build name=fleet-key:
    OLD_KEYDIR="{{keys-root}}/{{fleet-key}}" tools/rauc-rotate-build.sh "{{keys-root}}/{{name}}" {{config}}

[group('rotate')]
[doc("Rotate the signing key on one device (transition then end-state)")]
rotate-run host name=fleet-key *flags:
    tools/rauc-rotate.sh "{{host}}" "{{keys-root}}/{{name}}" {{flags}}

[group('rotate')]
[doc("Verify a device trusts the new key (--empirical for the bundle test)")]
rotate-verify host name=fleet-key *flags:
    tools/rauc-rotate-verify.sh "{{host}}" "{{keys-root}}/{{name}}/signing.cert.pem" {{flags}}
