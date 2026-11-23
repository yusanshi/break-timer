import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

function call(method, parameters, signature) {
    return new Promise((resolve, reject) => {
        Gio.DBus.session.call('org.gnome.SessionManager', '/org/gnome/SessionManager',
            'org.gnome.SessionManager', method, parameters,
            new GLib.VariantType(signature), Gio.DBusCallFlags.NONE, 5000, null,
            (connection, result) => {
                try {
                    resolve(connection.call_finish(result).deepUnpack());
                } catch (error) {
                    reject(error);
                }
            });
    });
}

// Inhibit only automatic idle, never explicit lock or suspend. A late reply
// after disable is still released; cancellation would lose the cookie.
export class IdleInhibitor {
    constructor() {
        this._wanted = false;
        this._cookie = null;
        this._pending = false;
        this._generation = 0;
    }

    setWanted(wanted) {
        if (wanted === this._wanted)
            return;
        this._wanted = wanted;
        this._generation++;
        this._sync();
    }

    async _sync() {
        if (this._pending)
            return;
        this._pending = true;
        const generation = this._generation;
        try {
            if (this._wanted && this._cookie === null) {
                [this._cookie] = await call('Inhibit', new GLib.Variant('(susu)',
                    ['break-timer@local', 0, 'Break Timer 休息界面', 8]), '(u)');
            } else if (!this._wanted && this._cookie !== null) {
                const cookie = this._cookie;
                this._cookie = null;
                await call('Uninhibit', new GLib.Variant('(u)', [cookie]), '()');
            }
        } catch (error) {
            console.warn(`Break Timer: 空闲抑制失败，保留系统锁屏策略：${error.message}`);
        } finally {
            this._pending = false;
            if (generation !== this._generation)
                this._sync();
        }
    }

    destroy() {
        this.setWanted(false);
    }
}
