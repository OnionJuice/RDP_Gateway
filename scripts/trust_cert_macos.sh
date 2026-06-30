#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CERT_FILE="${ROOT_DIR}/certs/localhost.pem"
LOGIN_KEYCHAIN="${HOME}/Library/Keychains/login.keychain-db"

if [[ ! -f "${LOGIN_KEYCHAIN}" ]]; then
  LOGIN_KEYCHAIN="${HOME}/Library/Keychains/login.keychain"
fi

if [[ ! -f "${CERT_FILE}" ]]; then
  echo "Missing certificate: ${CERT_FILE}" >&2
  echo "Run ./scripts/gen_cert.sh first." >&2
  exit 1
fi

security add-trusted-cert \
  -r trustRoot \
  -p ssl \
  -k "${LOGIN_KEYCHAIN}" \
  "${CERT_FILE}"

echo "Trusted ${CERT_FILE} in ${LOGIN_KEYCHAIN}"
