# RAUC signing-key rotation.
#
# Replaces the key the devices trust with a fresh per-project key. The full flow, on the bench
# board first, then on every other board:
#
#   just rotate-keygen [name]                # new key, gitignored, never committed
#   just rotate-build [name]                 # transition + end-state bundles
#   just rotate-provision-ssh root@<host>    # once, if key auth is not set up
#   just rotate-run root@<bench> [name]      # the bench board first
#   just rotate-verify root@<bench> [name] --empirical build/rotation/transition.raucb build/rotation/new-signed.raucb
#   just rotate-run root@<host> [name]       # then every other board
#
# `name` selects a dir under the gitignored local/keys; the default is `fleet-key` in the root
# Justfile. docs/updates.md §"Rotating the signing key" covers the order.

keys-root := justfile_directory() / "local/keys"

[group('rotate')]
[doc("Generate a new RAUC signing key (gitignored, never committed)")]
rotate-keygen name=fleet-key:
    tools/rauc-keygen.sh "{{keys-root}}/{{name}}"

[group('rotate')]
[doc("Install this host's SSH pubkey on a device")]
rotate-provision-ssh host=kiosk-host:
    tools/rauc-provision-ssh.sh "{{host}}"

# `name` is the new key; OLD_KEYDIR is the `fleet-key` directory.
[group('rotate')]
[doc("Build the transition and end-state bundles for a rotation")]
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
