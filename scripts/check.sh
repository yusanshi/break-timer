#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
while IFS= read -r -d '' source; do
    node --check "$source"
done < <(find lib ui tests -name '*.js' -print0)
node --check extension.js
node --check prefs.js
glib-compile-schemas --strict --dry-run schemas
TZ=Asia/Shanghai node --test --test-isolation=none tests/*.test.js
gjs -m tests/gjs-smoke.js
