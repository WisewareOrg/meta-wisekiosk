#!/usr/bin/env bash
#   tools/replay/ca.sh <ca-dir> ca              -- mint the CA (once)
#   tools/replay/ca.sh <ca-dir> leaf <host>     -- mint <host>'s leaf, signed
#                                                   by <ca-dir>/ca.{crt,key}
set -euo pipefail

USAGE="usage: ca.sh <ca-dir> ca | ca.sh <ca-dir> leaf <host>"
CA_DIR=${1:?$USAGE}
MODE=${2:?$USAGE}

mint_ca() {
    local key="$CA_DIR/ca.key" cert="$CA_DIR/ca.crt"
    if [ -e "$key" ] || [ -e "$cert" ]; then
        echo "ca.sh: refusing to overwrite existing CA material in $CA_DIR" >&2
        echo "  ($key / $cert) -- rotate into a fresh directory instead" >&2
        exit 1
    fi
    mkdir -p "$CA_DIR"
    chmod 700 "$CA_DIR"
    openssl ecparam -name prime256v1 -genkey -noout -out "$key"
    openssl req -x509 -new -key "$key" -sha256 -days 3650 \
        -subj "/CN=WiseKiosk Replay CA/O=WiseKiosk/C=US" \
        -addext "keyUsage=critical,keyCertSign,cRLSign" -out "$cert"
    chmod 600 "$key"
    chmod 644 "$cert"
    echo "generated replay CA: $cert"
}

mint_leaf() {
    local host=${1:?$USAGE}
    local ca_key="$CA_DIR/ca.key" ca_cert="$CA_DIR/ca.crt"
    local leaf_dir="$CA_DIR/leaves"
    local key="$leaf_dir/$host.key" cert="$leaf_dir/$host.crt"
    if [ ! -f "$ca_key" ] || [ ! -f "$ca_cert" ]; then
        echo "ca.sh: no CA at $CA_DIR -- run 'ca.sh $CA_DIR ca' first" >&2
        exit 1
    fi
    if [ -e "$key" ] || [ -e "$cert" ]; then
        echo "ca.sh: refusing to overwrite existing leaf material for $host in $leaf_dir" >&2
        echo "  ($key / $cert) -- remove it first to rotate; the CA itself does not change" >&2
        exit 1
    fi
    mkdir -p "$leaf_dir"
    chmod 700 "$leaf_dir"
    local csr
    csr=$(mktemp)
    trap 'rm -f "$csr"' RETURN
    openssl ecparam -name prime256v1 -genkey -noout -out "$key"
    openssl req -new -key "$key" -subj "/CN=$host" \
        -addext "subjectAltName=DNS:$host" -addext "extendedKeyUsage=serverAuth" -out "$csr"
    openssl x509 -req -in "$csr" -CA "$ca_cert" -CAkey "$ca_key" -CAcreateserial \
        -days 365 -sha256 -copy_extensions=copy -out "$cert"
    chmod 600 "$key"
    chmod 644 "$cert"
    echo "generated replay leaf for $host: $cert"
}

case "$MODE" in
    ca) mint_ca ;;
    leaf) mint_leaf "${3:-}" ;;
    *) echo "ca.sh: unknown mode '$MODE' -- use 'ca' or 'leaf <host>'" >&2; exit 2 ;;
esac
