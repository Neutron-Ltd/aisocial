#!/usr/bin/env bash
# Fetch upstream ComfyUI at a pinned commit into ./ComfyUI (git-ignored).
#
# ComfyUI is a separate project licensed under GPL-3.0 and is not part of
# this repository. Override the defaults with environment variables:
#   COMFYUI_REPO  (default: https://github.com/comfyanonymous/ComfyUI.git)
#   COMFYUI_REF   (default: 529c80255f3f2370c39780c62a9454d95344014d, v0.19.3)
#   COMFYUI_DIR   (default: <repo>/ComfyUI)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="${COMFYUI_REPO:-https://github.com/comfyanonymous/ComfyUI.git}"
REF="${COMFYUI_REF:-529c80255f3f2370c39780c62a9454d95344014d}"
DIR="${COMFYUI_DIR:-$ROOT/ComfyUI}"

if [[ ! "$REF" =~ ^[A-Za-z0-9._/-]+$ ]]; then
  echo "COMFYUI_REF contains invalid characters: $REF" >&2
  exit 2
fi

if [[ -e "$DIR" && ! -d "$DIR/.git" ]]; then
  echo "$DIR already exists and is not a git checkout; leaving it untouched." >&2
  exit 1
fi

if [[ ! -d "$DIR/.git" ]]; then
  git init -q "$DIR"
  git -C "$DIR" remote add origin "$REPO"
fi

git -C "$DIR" fetch --depth 1 origin "$REF"
git -C "$DIR" checkout -q --detach FETCH_HEAD
echo "ComfyUI checked out at $(git -C "$DIR" rev-parse --short HEAD) in $DIR"
echo "Next: python3 -m venv .venv && . .venv/bin/activate && pip install -r \"$DIR/requirements.txt\""
