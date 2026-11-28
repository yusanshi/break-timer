#!/usr/bin/env bash
# Real GNOME Shell integration test. All settings, sockets and bus names are
# isolated under /tmp; the host desktop and system bus are never contacted.
set -euo pipefail
test_scripts=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cd "$test_scripts/.."
if [[ "${1:-}" != --inside ]]; then
    test_root=$(mktemp -d /tmp/break-timer-integration.XXXXXX)
    mkdir -p "$test_root"/{runtime,data,config,cache}
    chmod 700 "$test_root/runtime"
    cat > "$test_root/bus.conf" <<'EOF'
<busconfig>
  <type>session</type>
  <listen>unix:tmpdir=/tmp</listen>
  <policy context="default">
    <allow send_destination="*" eavesdrop="true"/>
    <allow eavesdrop="true"/>
    <allow own="*"/>
  </policy>
</busconfig>
EOF
    printf '测试产物：%s\n' "$test_root"
    export BREAK_TIMER_TEST_ROOT="$test_root"
    export XDG_RUNTIME_DIR="$test_root/runtime" XDG_DATA_HOME="$test_root/data"
    export XDG_CONFIG_HOME="$test_root/config" XDG_CACHE_HOME="$test_root/cache"
    export XDG_CONFIG_DIRS="$test_root/config"
    export XDG_DATA_DIRS=/usr/share
    export CANBERRA_DRIVER=null
    export GSETTINGS_BACKEND=keyfile GIO_USE_VFS=local GTK_A11Y=none
    export XDG_CURRENT_DESKTOP=GNOME GNOME_SHELL_SESSION_MODE=user
    unset DISPLAY WAYLAND_DISPLAY
    exec dbus-run-session --config-file="$test_root/bus.conf" -- bash "$test_scripts/idle-notification.sh" --inside
fi
[[ "$BREAK_TIMER_TEST_ROOT" == /tmp/break-timer-integration.* ]]
export DBUS_SYSTEM_BUS_ADDRESS="$DBUS_SESSION_BUS_ADDRESS"
extension_dir="$XDG_DATA_HOME/gnome-shell/extensions/break-timer@local"
mkdir -p "$extension_dir"
cp -r metadata.json extension.js prefs.js stylesheet.css lib ui icons schemas "$extension_dir/"
glib-compile-schemas --strict "$extension_dir/schemas"
driver_dir="$XDG_DATA_HOME/gnome-shell/extensions/break-timer-test-driver@local"
mkdir -p "$driver_dir"
cat > "$driver_dir/metadata.json" <<'EOF'
{"uuid":"break-timer-test-driver@local","name":"Isolated test driver","description":"Test only","shell-version":["50"],"session-modes":["user","unlock-dialog"]}
EOF
cat > "$driver_dir/extension.js" <<'EOF'
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
export default class TestDriver extends Extension {
    enable() { global.context.unsafe_mode = true; }
    disable() { global.context.unsafe_mode = false; }
}
EOF
gsettings set org.gnome.shell enabled-extensions "['break-timer-test-driver@local', 'break-timer@local']"
gsettings set org.gnome.shell disable-user-extensions false
gsettings set org.gnome.shell welcome-dialog-last-shown-version '50.1'
gsettings set org.gnome.desktop.screensaver lock-enabled false
gsettings set org.gnome.desktop.session idle-delay 20
gsettings set org.gnome.settings-daemon.plugins.power idle-dim true
gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-ac-type 'nothing'
gsettings set org.gnome.desktop.notifications show-banners true
gsettings set org.gnome.desktop.notifications show-in-lock-screen true
gsettings --schemadir "$extension_dir/schemas" set org.gnome.shell.extensions.break-timer blocked-ranges '[]'
python3 "$test_scripts/idle-system-fixtures.py" > "$BREAK_TIMER_TEST_ROOT/fixtures.log" 2>&1 &
gdm_pid=$!
for i in {1..50}; do
    if [[ -e "$BREAK_TIMER_TEST_ROOT/fixtures-ready" ]]; then break; fi
    sleep 0.1
done
mkdir -p "$XDG_CONFIG_HOME/gnome-session/sessions" "$XDG_CONFIG_HOME/autostart"
cat > "$XDG_CONFIG_HOME/gnome-session/sessions/break-timer-test.session" <<'EOF'
[GNOME Session]
Name=Break Timer Test
EOF
GNOME_SESSION_DEBUG=1 /usr/libexec/gnome-session-service --session=break-timer-test > "$BREAK_TIMER_TEST_ROOT/session.log" 2>&1 &
manager_pid=$!
gnome-shell --headless --wayland --no-x11 --virtual-monitor=1280x800 --virtual-monitor=1024x768 --debug-control > "$BREAK_TIMER_TEST_ROOT/shell.log" 2>&1 &
shell_pid=$!
trap 'kill "$shell_pid" "$gdm_pid" "$manager_pid" 2>/dev/null || true; wait "$shell_pid" 2>/dev/null || true' EXIT
if ! timeout 420s python3 "$test_scripts/idle-notification.py"; then
    tail -100 "$BREAK_TIMER_TEST_ROOT/shell.log"
    exit 1
fi
