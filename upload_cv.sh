#!/usr/bin/env bash
# Usage: upload_cv.sh <local_file> <spott_upload_url>
# PUTs raw CV bytes to a Spott signed upload URL; prints Spott's JSON response.
set -euo pipefail
f="$1"; url="$2"
magic=$(head -c 4 "$f" | od -An -c | tr -d ' \n')
case "$magic" in
  %PDF*) ct=application/pdf ;;
  PK*)   ct=application/vnd.openxmlformats-officedocument.wordprocessingml.document ;;
  *)     if head -c 8 "$f" | od -An -tx1 | grep -q 'd0 cf 11 e0'; then ct=application/msword; else ct=text/plain; fi ;;
esac
size=$(stat -c %s "$f")
if [ "$size" -gt 10485760 ]; then echo '{"error":"too_large","message":"CV over 10MB"}'; exit 0; fi
curl -sS --retry 3 -X PUT -H "Content-Type: $ct" --data-binary @"$f" "$url"; echo
