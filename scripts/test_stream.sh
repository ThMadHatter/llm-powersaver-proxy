#!/usr/bin/env bash
set -euo pipefail
: "${ROUTER_URL:=http://127.0.0.1:8080}"
: "${ROUTER_API_KEY:?Esporta ROUTER_API_KEY}"
curl -N --no-buffer   -H "Authorization: Bearer $ROUTER_API_KEY"   -H "Content-Type: application/json"   "$ROUTER_URL/api/chat"   -d '{"model":"llama3.2","messages":[{"role":"user","content":"Conta lentamente da 1 a 5"}],"stream":true}'
