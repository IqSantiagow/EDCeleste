#!/usr/bin/env bash
# Sends the working copy (uncommitted changes included) to the EDCeleste runner on the VPS
# and prints the upload_id that start_mutation / start_e2e need.
#
#   bash mutation_testing/send_code.sh
#
# Needs two environment variables:
#   RUNNER_URL    e.g. http://100.101.102.103:8765   (the Tailscale address of the VPS)
#   RUNNER_TOKEN  the same token as in /etc/edceleste-runner.env on the VPS
#
# Why a script and not an MCP tool: the code would have to travel through the model's
# context. Here it goes straight from this machine to the VPS, and the model sees only the id.
set -euo pipefail
cd "$(dirname "$0")/.."

: "${RUNNER_URL:?Set RUNNER_URL, for example http://100.101.102.103:8765}"
: "${RUNNER_TOKEN:?Set RUNNER_TOKEN, the same token as on the VPS}"

# The list of files comes from git, so .venv, caches and everything in .gitignore stay at home.
# --ignore-failed-read: a tracked file that was deleted in the working copy is skipped.
git ls-files -z --cached --others --exclude-standard \
    | tar --null --ignore-failed-read -T - -czf - \
    | curl --silent --show-error --fail-with-body \
        -T - -H "Authorization: Bearer $RUNNER_TOKEN" \
        "$RUNNER_URL/upload"
echo
