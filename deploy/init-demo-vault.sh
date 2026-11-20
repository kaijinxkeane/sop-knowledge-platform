#!/usr/bin/env bash
# DEVELOPMENT ONLY: create the vault git repo from demo-vault/ (fictional data).
# The real company vault is never created this way; company admins mount it (plan §10).
#
#   ./deploy/init-demo-vault.sh [target]     # default: deploy/data/vault
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
target="${1:-$repo_root/deploy/data/vault}"

if [ -e "$target/.git" ]; then
  echo "Vault already exists at $target (delete it to recreate)." >&2
  exit 1
fi

mkdir -p "$target"
cp -R "$repo_root/demo-vault/." "$target/"
cd "$target"
git init -q -b main
git config user.name "Demo Admin"
git config user.email "admin@demo.invalid"
git add -A
git commit -q -m "Seed demo vault (fictional data)"
echo "Demo vault ready at $target ($(git ls-files | wc -l | tr -d ' ') files, commit $(git rev-parse --short HEAD))"
