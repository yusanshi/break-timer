"""System-service fixtures on a PRIVATE bus. Never contacts the host system bus."""
import os
from pathlib import Path
from gi.repository import Gio, GLib

root = Path(os.environ['BREAK_TIMER_TEST_ROOT'])
assert str(root).startswith('/tmp/break-timer-integration.')
assert os.environ['DBUS_SYSTEM_BUS_ADDRESS'] == os.environ['DBUS_SESSION_BUS_ADDRESS']
bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
objects = []


def export(name, path, iface, properties, methods):
    xml = f'<node><interface name="{iface}">'
    for key, (sig, value) in properties.items():
        xml += f'<property name="{key}" type="{sig}" access="read"/>'
    for key, (insig, outsig, fn) in methods.items():
        xml += f'<method name="{key}">'
        for sig in insig:
            xml += f'<arg type="{sig}" direction="in"/>'
        for sig in outsig:
            xml += f'<arg type="{sig}" direction="out"/>'
        xml += '</method>'
    xml += '</interface></node>'
    info = Gio.DBusNodeInfo.new_for_xml(xml)

    def called(conn, sender, obj, interface, method, args, inv):
        try:
            insig, outsig, fn = methods[method]
            result = fn(*args.unpack())
            if isinstance(result, Gio.UnixFDList):
                inv.return_value_with_unix_fd_list(GLib.Variant('(h)', (0,)), result)
            else:
                inv.return_value(GLib.Variant('(' + ''.join(outsig) + ')', result or ()))
        except Exception as e:
            print(iface, method, str(e), flush=True)
            inv.return_dbus_error('org.breaktimer.TestError', str(e))

    def prop(conn, sender, obj, interface, key):
        sig, value = properties[key]
        return GLib.Variant(sig, value)

    objects.append(bus.register_object(path, info.interfaces[0], called, prop, None))
    bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus',
                  'org.freedesktop.DBus', 'RequestName',
                  GLib.Variant('(su)', (name, 0)), None,
                  Gio.DBusCallFlags.NONE, 3000, None)


def inhibit(*args):
    fd = os.open('/dev/null', os.O_RDONLY)
    fds = Gio.UnixFDList.new()
    fds.append(fd)
    os.close(fd)
    return fds

export('org.gnome.DisplayManager','/org/gnome/DisplayManager/Manager','org.gnome.DisplayManager.Manager',{'Version':('s','50.1')},{'RegisterSession':([],[],lambda:()),'RegisterDisplay':([],[],lambda:())})
export('org.freedesktop.login1','/org/freedesktop/login1','org.freedesktop.login1.Manager',{'LidClosed':('b',False),'PreparingForSleep':('b',False),'OnExternalPower':('b',True)}, {
 'GetSession':(['s'],['o'],lambda _:('/org/freedesktop/login1/session/test',)),
 'GetUser':(['u'],['o'],lambda _:('/org/freedesktop/login1/user/test',)),
 'Inhibit':(['s','s','s','s'],['h'],inhibit),
 'CanSuspend':([],['s'],lambda:('no',)),
 'CanHibernate':([],['s'],lambda:('no',)),
 'CanSuspendThenHibernate':([],['s'],lambda:('no',)),
 'ListSessions':([],['a(susso)'],lambda:([],)),
})
for path in ['/org/freedesktop/login1/session/test','/org/freedesktop/login1/session/auto']:
    export('org.freedesktop.login1',path,'org.freedesktop.login1.Session',{'Id':('s','test'),'Active':('b',True),'State':('s','active'),'Class':('s','user'),'Type':('s','wayland'),'LockedHint':('b',False)}, {'SetIdleHint':(['b'],[],lambda _:()),'SetLockedHint':(['b'],[],lambda _:())})
export('org.freedesktop.login1','/org/freedesktop/login1/user/test','org.freedesktop.login1.User',{'Sessions':('a(so)',[('test','/org/freedesktop/login1/session/test')])},{})
export('org.freedesktop.systemd1','/org/freedesktop/systemd1','org.freedesktop.systemd1.Manager',{'Virtualization':('s','')},{})
export('org.freedesktop.hostname1','/org/freedesktop/hostname1','org.freedesktop.hostname1',{'Chassis':('s','desktop')},{})
export('org.freedesktop.UPower','/org/freedesktop/UPower','org.freedesktop.UPower',{'DaemonVersion':('s','1.90.9'),'OnBattery':('b',False),'LidIsClosed':('b',False),'LidIsPresent':('b',False)}, {
 'EnumerateDevices':([],['ao'],lambda:([],)),
 'EnumerateKbdBacklights':([],['ao'],lambda:([],)),
 'GetDisplayDevice':([],['o'],lambda:('/org/freedesktop/UPower/devices/DisplayDevice',)),
 'GetCriticalAction':([],['s'],lambda:('PowerOff',)),
})
export('org.freedesktop.UPower','/org/freedesktop/UPower/devices/DisplayDevice','org.freedesktop.UPower.Device',{'Type':('u',0),'State':('u',0),'Percentage':('d',100.0),'WarningLevel':('u',1),'IsPresent':('b',False),'PowerSupply':('b',False),'Energy':('d',0.0),'EnergyFull':('d',0.0),'EnergyRate':('d',0.0),'TimeToEmpty':('x',0),'TimeToFull':('x',0),'IconName':('s','ac-adapter-symbolic')},{})
(root / 'fixtures-ready').touch()
GLib.MainLoop().run()
