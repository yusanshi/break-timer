"""Regression for notification wakes with automatic locking disabled.

Runs native GNOME session, screen saver and power services on private buses.
Only hardware/login services are fixtures; monitor power states are measured.
"""
import json
import os
from pathlib import Path
import subprocess
import time
from gi.repository import Gio, GLib

root = Path(os.environ['BREAK_TIMER_TEST_ROOT'])
assert str(root).startswith('/tmp/break-timer-integration.')
assert os.environ['DBUS_SYSTEM_BUS_ADDRESS'] == os.environ['DBUS_SESSION_BUS_ADDRESS']
bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)


def call(name, path, iface, method, args, signature=None):
    return bus.call_sync(name, path, iface, method, args,
                         GLib.VariantType.new(signature) if signature else None,
                         Gio.DBusCallFlags.NONE, 5000, None).unpack()


def evaluate(code):
    ok, result = call('org.gnome.Shell', '/org/gnome/Shell', 'org.gnome.Shell',
                      'Eval', GLib.Variant('(s)', (code,)), '(bs)')
    if not ok:
        raise AssertionError(f'JS evaluation failed: {result}\n{code}')
    return json.loads(result) if result else None


def check(expression, label):
    result = evaluate(expression)
    if result is not True:
        raise AssertionError(f'{label}: {result!r}')
    print(f'PASS {label}', flush=True)


# Native gnome-session must finish initialization before Shell can enable us.
for attempt in range(50):
    try:
        call('org.gnome.SessionManager', '/org/gnome/SessionManager',
             'org.gnome.SessionManager', 'Initialized', None)
        break
    except GLib.Error:
        time.sleep(0.1)
deadline = time.monotonic() + 20
while True:
    try:
        if evaluate('true') is not True:
            raise AssertionError('Test driver is not ready')
        break
    except (GLib.Error, AssertionError):
        if time.monotonic() >= deadline:
            raise
        time.sleep(0.2)

evaluate("import('resource:///org/gnome/shell/ui/main.js').then(m => { globalThis.btMain = m; return true; })")
while True:
    ready = evaluate("Boolean(btMain.extensionManager.lookup('break-timer@local')?.stateObj?._engine)")
    if ready:
        break
    if time.monotonic() >= deadline:
        raise AssertionError('Extension failed to enable')
    time.sleep(0.2)
evaluate("globalThis.bt = btMain.extensionManager.lookup('break-timer@local').stateObj; true")
check("bt._view.state === 'work' && bt._indicator.button.visible", 'extension loads and panel shows work')
check("bt._shield._cards.length === 2", 'both virtual monitors have a curtain')

check('Boolean(btMain.screenShield)', 'native GNOME screen shield is available')
# These proxies exit if Shell is not ready, so start them only after it loads.
services = []
for entry in ['org.gnome.ScreenSaver', 'org.gnome.Shell.Notifications']:
    with open(root / (entry + '.log'), 'w') as out:
        services.append(subprocess.Popen(
            ['gjs', '-m', '/usr/share/gnome-shell/' + entry],
            stdout=out, stderr=subprocess.STDOUT))
time.sleep(0.7)
call('org.gnome.ScreenSaver', '/org/gnome/ScreenSaver',
     'org.gnome.ScreenSaver', 'GetActive', None)
with open(root / 'power.log', 'w') as out:
    power = subprocess.Popen(
        ['/usr/libexec/gsd-power', '--verbose'], stdout=out, stderr=subprocess.STDOUT,
        env=dict(os.environ, CANBERRA_DRIVER='null', G_MESSAGES_DEBUG='all',
                 WAYLAND_DISPLAY='wayland-0'))
with open(root / 'display-dbus.log', 'w') as out:
    monitor = subprocess.Popen(
        ['dbus-monitor', '--session',
         "interface='org.freedesktop.DBus.Properties',member='Set',path='/org/gnome/Mutter/DisplayConfig'"],
        stdout=out, stderr=subprocess.STDOUT)
start = time.monotonic()
rows = []


def sample(label):
    row = evaluate("""({
        idle: global.backend.get_core_idle_monitor().get_idletime(),
        state: bt._engine ? bt._view.state : 'disabled',
        extensionEngineActive: Boolean(bt._engine),
        active: btMain.screenShield.active,
        locked: btMain.screenShield.locked,
        mode: btMain.sessionMode.currentMode,
        recoveryWatch: bt._idleRecovery?._idleWatch ?? 0,
    })""")
    row['time'] = round(time.monotonic() - start, 3)
    row['label'] = label
    row['presence'] = call(
        'org.gnome.SessionManager', '/org/gnome/SessionManager/Presence',
        'org.freedesktop.DBus.Properties', 'Get',
        GLib.Variant('(ss)', ('org.gnome.SessionManager.Presence', 'status')))[0]
    row['display_power'] = call(
        'org.gnome.Mutter.DisplayConfig', '/org/gnome/Mutter/DisplayConfig',
        'org.freedesktop.DBus.Properties', 'Get',
        GLib.Variant('(ss)', ('org.gnome.Mutter.DisplayConfig', 'PowerSaveMode')))[0]
    text = (root / 'power.log').read_text()
    row['blank_requests'] = text.count('TESTSUITE: Blanked screen')
    row['unblank_requests'] = text.count('TESTSUITE: Unblanked screen')
    rows.append(row)
    (root / 'timeline.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    if power.poll() is not None:
        raise RuntimeError('Power manager exited')
    return row


def active_input():
    evaluate("""(async () => {
        const {default:Clutter}=await import('gi://Clutter');
        const {default:GLib}=await import('gi://GLib');
        globalThis.idleTestKeyboard??=global.stage.context.get_backend().get_default_seat().create_virtual_device(Clutter.InputDeviceType.KEYBOARD_DEVICE);
        idleTestKeyboard.notify_keyval(GLib.get_monotonic_time(),Clutter.KEY_Shift_L,Clutter.KeyState.PRESSED);
        idleTestKeyboard.notify_keyval(GLib.get_monotonic_time(),Clutter.KEY_Shift_L,Clutter.KeyState.RELEASED);
        return true;
    })()""")


def wait_for(predicate, label, timeout=45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        row = sample(label)
        if predicate(row):
            print('PASS', label, row, flush=True)
            return row
        time.sleep(0.25)
    raise AssertionError(f'{label}: {row}')


def wait_blank(label):
    return wait_for(lambda r: r['active'] and r['display_power'] == 3, label)


def notify(label):
    subprocess.run(['notify-send', '--app-name=Break Timer Idle Test', label,
                    'Single isolated notification'], check=True, timeout=5)
    return wait_for(lambda r: not r['active'] and r['display_power'] == 0,
                    label + ': notification wakes screen', 5)


def stays_on(label, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        row = sample(label)
        if row['display_power'] != 0 or row['active']:
            raise AssertionError(f'{label}: {row}')
        time.sleep(0.5)
    print('PASS', label, row, flush=True)


try:
    time.sleep(1)
    evaluate("""(async () => {
        const {default:Gio} = await import('gi://Gio');
        globalThis.idleSettings = new Gio.Settings({schema_id:'org.gnome.desktop.session'});
        btMain.overview.hide();
        btMain.messageTray.getSources().forEach(s => s.destroy());
        bt._settings.set_strv('blocked-ranges',['00:00-24:00']);
        bt._settings.set_strv('blocked-ranges',[]);
        return true;
    })()""")
    check("bt._view.state === 'ready' && !bt._settings.get_boolean('inhibit-idle')", 'ready screen uses default idle policy')
    active_input()
    wait_blank('initial automatic blank')

    first = notify('ready')
    check('bt._idleRecovery._idleWatch > 0', 'unattended wake rearms idle blanking')
    stays_on('notification does not immediately reblank', 15)
    after = wait_blank('ready screen blanks again without input')
    assert not after['locked']
    assert after['time'] - first['time'] >= 20
    check('bt._idleRecovery._idleWatch === 0 && bt._idleRecovery._activeWatch === 0', 'recovery watches are removed after use')

    # Ordinary input must cancel the extra watch; GNOME then handles idle itself.
    notify('real input')
    active_input()
    wait_for(lambda r: r['idle'] < 2000 and r['recoveryWatch'] == 0,
             'real input cancels recovery without starting work', 3)
    check("bt._view.state === 'ready'", 'waking screen does not acknowledge the break')
    wait_blank('normal input-driven idle cycle still blanks')

    # Apply a ban while asleep; ending the ban must not wake the monitor.
    evaluate("bt._settings.set_strv('blocked-ranges',['00:00-24:00']); true")
    notify('blocked')
    check("bt._view.state === 'blocked' && bt._idleRecovery._idleWatch > 0", 'ban also rearms idle blanking')
    wait_blank('ban screen blanks again')
    evaluate("bt._settings.set_strv('blocked-ranges',[]); true")
    check("bt._view.state === 'ready'", 'ban ended while screen remains asleep')
    assert sample('ban ended')['display_power'] == 3

    # Never-blank and opt-in inhibition take priority over an armed recovery.
    notify('never blank')
    evaluate("idleSettings.set_uint('idle-delay',0); true")
    check('bt._idleRecovery._idleWatch === 0', 'never-blank setting cancels pending recovery')
    stays_on('never-blank policy is respected', 35)
    evaluate("idleSettings.set_uint('idle-delay',20); true")
    wait_blank('restored system idle delay blanks again')

    notify('inhibition')
    evaluate("bt._settings.set_boolean('inhibit-idle',true); true")
    check('bt._idleRecovery._idleWatch === 0', 'enabling idle inhibition cancels pending recovery')
    stays_on('enabled inhibition keeps display on', 35)
    evaluate("bt._settings.set_boolean('inhibit-idle',false); true")
    wait_blank('disabling inhibition restores normal automatic blanking')

    # Negative control: removing the extension leaves the original GNOME bug.
    notify('disable cleanup')
    evaluate("globalThis.savedRecovery = bt._idleRecovery; btMain.extensionManager.disableExtension('break-timer@local'); true")
    check('!bt._engine && !bt._shield && !bt._idleRecovery && savedRecovery._idleWatch === 0 && savedRecovery._activeWatch === 0', 'disable cleans up pending recovery and overlay')
    stays_on('unmodified GNOME control does not reblank', 35)
    print('GNOME notification idle regression checks passed.', flush=True)
finally:
    for service in services:
        service.terminate()
        service.wait(timeout=5)
    monitor.terminate()
    monitor.wait(timeout=5)
    power.terminate()
    power.wait(timeout=5)

