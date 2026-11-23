"""Exercise the installed extension inside a disposable GNOME Shell session."""
import json
import os
import subprocess
import time
from gi.repository import Gio, GLib

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


def screenshot(name):
    path = os.path.join(os.environ['BREAK_TIMER_TEST_ROOT'], name + '.png')
    success, _ = call('org.gnome.Shell.Screenshot', '/org/gnome/Shell/Screenshot',
                      'org.gnome.Shell.Screenshot', 'Screenshot',
                      GLib.Variant('(bbs)', (False, False, path)), '(bs)')
    assert success, 'Screenshot failed'


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

# Simulate extensions that load later and request the same leftmost slot.
evaluate("""(async () => {
    const PanelMenu = await import('resource:///org/gnome/shell/ui/panelMenu.js');
    const {default: St} = await import('gi://St');
    globalThis.btOtherIndicators = ['A', 'B'].map(name => {
        const button = new PanelMenu.Button(0, `Test extension ${name}`);
        button.add_child(new St.Label({text: name}));
        btMain.panel.addToStatusArea(`break-timer-test-${name}`, button, 0, 'right');
        return button;
    });
    return true;
})()""")
time.sleep(0.3)
check("btOtherIndicators.every(button => bt._indicator.button.container.get_transformed_position()[0] < button.container.get_transformed_position()[0])", 'indicator stays visually left of extensions loaded later')
evaluate("btMain.panel._rightBox.set_child_at_index(btOtherIndicators[0].container, 0); true")
time.sleep(0.3)
check("btOtherIndicators[0].container.get_transformed_position()[0] < bt._indicator.button.container.get_transformed_position()[0]", 'existing indicators can be reordered without a positioning fight')
evaluate("""(async () => {
    const PanelMenu = await import('resource:///org/gnome/shell/ui/panelMenu.js');
    const {default: St} = await import('gi://St');
    globalThis.btPeerMoves = 0;
    let moving = false;
    const box = btMain.panel._rightBox;
    const peer = btOtherIndicators[0].container;
    globalThis.btPeerListener = box.connect('notify::first-child', () => {
        if (moving || box.get_first_child() === peer) return;
        moving = true;
        try {
            box.remove_child(peer);
            box.insert_child_at_index(peer, 0);
            btPeerMoves++;
        } finally { moving = false; }
    });
    const late = new PanelMenu.Button(0, 'Test extension C');
    late.add_child(new St.Label({text: 'C'}));
    btOtherIndicators.push(late);
    btMain.panel.addToStatusArea('break-timer-test-C', late, 0, 'right');
    return true;
})()""")
time.sleep(0.3)
peer_moves = evaluate('btPeerMoves')
time.sleep(0.3)
check(f"btPeerMoves === {peer_moves} && btPeerMoves > 0 && bt._indicator._positionLater === 0", 'a peer enforcing first position settles without repeated redraws')
evaluate("btMain.panel._rightBox.disconnect(btPeerListener); true")
evaluate("btOtherIndicators.forEach(button => button.destroy()); true")

# Provide an isolated session-manager endpoint to test the real async D-Bus
# inhibitor, including the flag and release lifecycle.
evaluate("""(async () => {
    const {default: Gio} = await import('gi://Gio');
    globalThis.btCookies = new Set();
    globalThis.btCookieSequence = 0;
    globalThis.btSession = Gio.DBusExportedObject.wrapJSObject(
      '<node><interface name="org.gnome.SessionManager">' +
      '<method name="Inhibit"><arg type="s" direction="in"/><arg type="u" direction="in"/>' +
      '<arg type="s" direction="in"/><arg type="u" direction="in"/><arg type="u" direction="out"/></method>' +
      '<method name="Uninhibit"><arg type="u" direction="in"/></method>' +
      '<method name="IsInhibited"><arg type="u" direction="in"/><arg type="b" direction="out"/></method>' +
      '</interface></node>', {
        Inhibit(app, xid, reason, flags) {
            if (flags !== 8) throw new Error('Unexpected inhibition flags');
            btCookies.add(++btCookieSequence); return btCookieSequence;
        },
        Uninhibit(cookie) { btCookies.delete(cookie); },
        IsInhibited() { return btCookies.size > 0; },
      });
    btSession.export(Gio.DBus.session, '/org/gnome/SessionManager');
    globalThis.btSessionOwner = Gio.bus_own_name_on_connection(Gio.DBus.session,
        'org.gnome.SessionManager', Gio.BusNameOwnerFlags.NONE, null, null);
    return true;
})()""")
time.sleep(0.3)

evaluate("bt._engine.workRemaining = 59000; bt._sync(); true")
check("bt._view.breakWarning && bt._indicator.label.has_style_class_name('break-timer-warning')", 'last-minute warning')
evaluate("""(() => {
    const time = d => `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
    bt._settings.set_strv('blocked-ranges', [`${time(new Date(Date.now() + 120000))}-${time(new Date(Date.now() + 720000))}`]);
    bt._sync(); return true;
})()""")
check("bt._reminder.actor.visible && bt._view.blockWarning", 'three-minute floating ban countdown')
time.sleep(0.3)
screenshot('reminder')
evaluate("bt._engine.workRemaining = 0; bt._sync(); true")
time.sleep(0.3)
check("bt._view.state === 'break' && Boolean(bt._shield._grab) && btMain.actionMode === 0", 'break acquires modal input and disables shortcuts')
check("btCookies.size === 1", 'automatic idle inhibited while explicit lock remains available')
check("bt._shield._cards.every(c => !c.resume.visible)", 'cannot resume early')
evaluate("bt._resume(); true")
check("bt._view.state === 'break'", 'premature resume is rejected')
check("bt._reminder.actor.visible", 'ban reminder remains visible during a break')
screenshot('break')
evaluate("bt._settings.set_strv('blocked-ranges', []); true")

evaluate("""(async () => {
    const {default: Clutter} = await import('gi://Clutter');
    const {default: GLib} = await import('gi://GLib');
    globalThis.btKeyboard = global.stage.context.get_backend().get_default_seat().create_virtual_device(Clutter.InputDeviceType.KEYBOARD_DEVICE);
    globalThis.btPress = (...keys) => {
        for (const key of keys) btKeyboard.notify_keyval(GLib.get_monotonic_time(), key, Clutter.KeyState.PRESSED);
        for (const key of keys.toReversed()) btKeyboard.notify_keyval(GLib.get_monotonic_time(), key, Clutter.KeyState.RELEASED);
    };
    btPress(Clutter.KEY_Alt_L, Clutter.KEY_Tab);
    btPress(Clutter.KEY_Super_L);
    btPress(Clutter.KEY_Escape);
    return true;
})()""")
time.sleep(0.3)
check("bt._shield.actor.visible && Boolean(bt._shield._grab) && btMain.actionMode === 0 && !btMain.overview.visible", 'virtual Alt+Tab, Super and Escape cannot leave the curtain')
evaluate("""(async () => {
    const {default: Clutter} = await import('gi://Clutter');
    globalThis.btLockRequests = 0;
    globalThis.btOriginalLock = bt._shield._onLock;
    bt._shield._onLock = () => btLockRequests++;
    btPress(Clutter.KEY_Super_L, Clutter.KEY_l);
    return true;
})()""")
time.sleep(0.3)
check("btLockRequests === 1", 'virtual Super+L reaches the system-lock callback')
evaluate("bt._shield._onLock = btOriginalLock; true")

# Exercise the system session-mode handoff without authenticating or touching
# a real user's lock screen. GNOME's password UI is outside this test scope.
evaluate("""(async () => {
    const {default: Shell} = await import('gi://Shell');
    globalThis.btNativeGrab = btMain.pushModal(btMain.layoutManager.screenShieldGroup,
        {actionMode: Shell.ActionMode.LOCK_SCREEN});
    btMain.sessionMode.pushMode('unlock-dialog'); return true;
})()""")
time.sleep(0.3)
check("bt._view.away && !bt._shield._grab && !bt._indicator.button.visible", 'system lock receives input and hides panel item')
check("btCookies.size === 0", 'system lock releases idle inhibitor')
evaluate("""globalThis.btOriginalLocked = bt._systemLocked;
bt._systemLocked = () => true;
btMain.sessionMode.popMode('unlock-dialog');
btMain.popModal(btNativeGrab); true""")
check("bt._view.away && Boolean(bt._shield._grab) && btMain.actionMode === 0", 'input remains blocked throughout the native unlock animation')
evaluate("bt._systemLocked = btOriginalLocked; bt._sync(); true")
time.sleep(0.3)
check("Boolean(bt._shield._grab) && bt._view.state === 'break'", 'unfinished break reclaims input after system unlock')

evaluate("bt._engine.breakUntil = bt._clock.now().boot; bt._sync(); true")
check("bt._view.state === 'ready' && bt._shield._cards.every(c => c.resume.visible)", 'expired break waits for explicit acknowledgement')
screenshot('ready')
evaluate("bt._resume(); true")
time.sleep(0.2)
check("bt._view.state === 'work' && !bt._shield._grab && !bt._shield.actor.visible", 'acknowledgement starts work and releases input')
check("btCookies.size === 0", 'resume releases idle inhibitor')
evaluate("bt._loginManager.emit('prepare-for-sleep', true); true")
check("bt._view.away && bt._sleeping", 'sleep signal pauses work')
evaluate("bt._loginManager.emit('prepare-for-sleep', false); true")
check("!bt._view.away && !bt._sleeping", 'wake signal reconciles state')

evaluate("bt._settings.set_strv('blocked-ranges', ['00:00-24:00']); bt._sync(); true")
check("bt._view.state === 'blocked' && Boolean(bt._shield._grab)", 'configuration change activates ban immediately')
evaluate("bt._resume(); true")
check("bt._view.state === 'blocked'", 'ban rejects acknowledgement')
evaluate("bt._settings.set_strv('blocked-ranges', []); bt._sync(); true")
check("bt._view.state === 'ready'", 'ban end requires acknowledgement')

evaluate("btMain.extensionManager.disableExtension('break-timer@local'); true")
time.sleep(0.4)
check("!bt._timer && !bt._shield && btMain.modalCount === 0 && btCookies.size === 0", 'disable removes modal grab, timer, UI and inhibitor')
evaluate("btMain.extensionManager.enableExtension('break-timer@local'); true")
time.sleep(0.5)
evaluate("globalThis.bt = btMain.extensionManager.lookup('break-timer@local').stateObj; true")
check("bt._view.state === 'ready' && Boolean(bt._shield._grab)", 'reenable restores state without restarting work')

evaluate("bt._resume(); true")
environment = dict(os.environ, WAYLAND_DISPLAY='wayland-0', GDK_BACKEND='wayland',
                   GI_TYPELIB_PATH='/usr/lib/gnome-shell/girepository-1.0',
                   LD_LIBRARY_PATH='/usr/lib/gnome-shell')
subprocess.run(['gjs', '-m', 'tests/prefs-smoke.js'], env=environment, check=True, timeout=15)

evaluate("bt._engine.workRemaining = 0; bt._sync(); bt._clock.now = () => { throw new Error('Injected clock failure'); }; true")
time.sleep(0.8)
check("!bt._shield && !bt._timer && btMain.modalCount === 0 && btCookies.size === 0", 'runtime failure releases input instead of trapping the user')

print('GNOME Shell integration checks passed.', flush=True)
