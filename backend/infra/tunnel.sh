#!/usr/bin/env bash
set -euo pipefail
: "${SSH_HOST:?请设置你自己的SSH_HOST}"
: "${SSH_USER:?请设置你自己的SSH_USER}"
project_dir="$(cd "$(dirname "$0")/.." && pwd)"
exec ssh -N -T \
  -i "${SSH_IDENTITY_FILE:-$project_dir/.local/id_ed25519}" \
  -o IdentitiesOnly=yes \
  -o "UserKnownHostsFile=${SSH_KNOWN_HOSTS_FILE:-$project_dir/.local/known_hosts}" \
  -o StrictHostKeyChecking=yes \
  -o BatchMode=yes \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -L 127.0.0.1:15432:127.0.0.1:15432 \
  -L 127.0.0.1:16379:127.0.0.1:16379 \
  -L 127.0.0.1:15673:127.0.0.1:15673 \
  "$SSH_USER@$SSH_HOST"
