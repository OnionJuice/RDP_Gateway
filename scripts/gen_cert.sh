#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CERT_DIR="${ROOT_DIR}/certs"
CERT_FILE="${CERT_DIR}/localhost.pem"
KEY_FILE="${CERT_DIR}/localhost-key.pem"
OPENSSL_CNF="${CERT_DIR}/localhost.cnf"

mkdir -p "${CERT_DIR}"

cat > "${OPENSSL_CNF}" <<'EOF'
[req]
default_bits = 2048
prompt = no
default_md = sha256
distinguished_name = dn
x509_extensions = v3_req

[dn]
CN = 127.0.0.1

[v3_req]
subjectAltName = @alt_names
keyUsage = critical,digitalSignature,keyEncipherment
extendedKeyUsage = serverAuth

[alt_names]
DNS.1 = localhost
IP.1 = 127.0.0.1
EOF

openssl req \
  -x509 \
  -nodes \
  -days 825 \
  -newkey rsa:2048 \
  -keyout "${KEY_FILE}" \
  -out "${CERT_FILE}" \
  -config "${OPENSSL_CNF}"

chmod 600 "${KEY_FILE}"
echo "Generated ${CERT_FILE} and ${KEY_FILE}"
