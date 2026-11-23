#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
mkdir -p dist
gnome-extensions pack --force --out-dir=dist --extra-source=lib --extra-source=ui --extra-source=icons .
printf '安装包：%s/dist/break-timer@local.shell-extension.zip\n' "$PWD"
