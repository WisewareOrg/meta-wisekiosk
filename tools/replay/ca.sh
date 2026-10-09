#!/usr/bin/env bash
# Mint the replay proxy's CA and per-host leaf certificates, both ECDSA
# P-256, under a gitignored local/ directory. Convention matches
# tools/rauc-keygen.sh: refuses to overwrite existing key material (rotation
# is a fresh leaf, never a clobber), 600 on every key, 644 on every cert --
# mode 0644 so wisekiosk's User=kiosk can read the CA cert once it reaches
# bench.
#
#   tools/replay/ca.sh <ca-dir> ca              -- mint the CA (once)
#   tools/replay/ca.sh <ca-dir> leaf <host>     -- mint <host>'s leaf, signed
#                                                   by <ca-dir>/ca.{crt,key}
#
# The leaf's SAN carries <host> as a DNS name -- Go's net/http verifies SAN,
# never the CN, so a leaf without it fails TLS against the real client.
set -euo pipefail

CA_DIR=${1:?usage: ca.sh <ca-dir> ca | ca.sh <ca-dir> leaf <host>}
MODE=${2:?usage: ca.sh <ca-dir> ca | ca.sh <ca-dir> leaf <host>}

mint_ca() {
    local key="$CA_DIR/ca.key" cert="$CA_DIR/ca.crt"
    if [ -e "$key" ] || [ -e "$cert" ]; then
        echo "ca.sh: refusing to overwrite existing CA material in $CA_DIR" >&2
        echo "  ($key / $cert) -- rotate into a fresh directory instead" >&2
        exit 1
    fi
    mkdir -p "$CA_DIR"
    chmod 700 "$CA_DIR"
    openssl ecparam -name prime256v1 -genkey -noout -out "$key" 2>/dev/null
    openssl req -x509 -new -key "$key" -sha256 -days 3650 \
        -subj "/CN=WiseKiosk Replay CA/O=WiseKiosk/C=US" -out "$cert" >/dev/null 2>&1
    chmod 600 "$key"
    chmod 644 "$cert"
    echo "generated replay CA: $cert"
}

mint_leaf() {
    local host=${1:?usage: ca.sh <ca-dir> leaf <host>}
    local ca_key="$CA_DIR/ca.key" ca_cert="$CA_DIR/ca.crt"
    local leaf_dir="$CA_DIR/leaves"
    local key="$leaf_dir/$host.key" cert="$leaf_dir/$host.crt"
    if [ ! -f "$ca_key" ] || [ ! -f "$ca_cert" ]; then
        echo "ca.sh: no CA at $CA_DIR -- run 'ca.sh $CA_DIR ca' first" >&2
        exit 1
    fi
    if [ -e "$key" ] || [ -e "$cert" ]; then
        echo "ca.sh: refusing to overwrite existing leaf material for $host in $leaf_dir" >&2
        echo "  ($key / $cert) -- rotate into a fresh CA directory instead" >&2
        exit 1
    fi
    mkdir -p "$leaf_dir"
    chmod 700 "$leaf_dir"
    local csr
    csr=$(mktemp)
    trap 'rm -f "$csr"' RETURN
    openssl ecparam -name prime256v1 -genkey -noout -out "$key" 2>/dev/null
    openssl req -new -key "$key" -subj "/CN=$host" \
        -addext "subjectAltName=DNS:$host" -out "$csr" >/dev/null 2>&1
    openssl x509 -req -in "$csr" -CA "$ca_cert" -CAkey "$ca_key" -CAcreateserial \
        -days 365 -sha256 -copy_extensions=copy -out "$cert" >/dev/null 2>&1
    chmod 600 "$key"
    chmod 644 "$cert"
    echo "generated replay leaf for $host: $cert"
}

case "$MODE" in
    ca) mint_ca ;;
    leaf) mint_leaf "${3:-}" ;;
    *) echo "ca.sh: unknown mode '$MODE' -- use 'ca' or 'leaf <host>'" >&2; exit 2 ;;
esac
