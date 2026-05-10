#!/usr/bin/env bash
# Generate a self-signed cert so phones can hit the server over HTTPS
# (required for getUserMedia outside of localhost).
set -e
cd "$(dirname "$0")"
openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout key.pem -out cert.pem -days 365 \
  -subj "/CN=ROOMBA" \
  -addext "subjectAltName=DNS:ROOMBA,DNS:localhost,IP:127.0.0.1"
echo "wrote cert.pem and key.pem"
