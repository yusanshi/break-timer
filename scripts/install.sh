#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
bash scripts/pack.sh
gnome-extensions install --force dist/break-timer@local.shell-extension.zip
printf '%s\n' '已安装 Break Timer。首次安装后请注销并重新登录，然后执行：' \
    '  gnome-extensions enable break-timer@local' \
    '设置：gnome-extensions prefs break-timer@local' \
    '启用后立即遵循当前封禁时段。'
