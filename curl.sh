#!/usr/bin/env zsh
set -x
set -e

curl http://localhost:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer local_no_key" \
  -d '{"model":"llama3","messages":[{"role":"user","content":"hello"}]}'