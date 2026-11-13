#!/bin/sh
set -eu
# Only the anon JWT is passed to this container. JWT alphabet is JSON-safe.
case "${ANON_KEY:-}" in
  ''|*[!A-Za-z0-9_.-]*) echo 'Missing or invalid ANON_KEY' >&2; exit 1 ;;
esac
printf 'window.BASHKIR_PUBLIC_CONFIG={"url":location.origin,"key":"%s"};\n' "$ANON_KEY" > /usr/share/nginx/html/web/config.js
