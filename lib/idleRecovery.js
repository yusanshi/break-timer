import Gio from 'gi://Gio';
import Meta from 'gi://Meta';

import {PresenceStatus} from 'resource:///org/gnome/shell/misc/gnomeSession.js';

// With automatic locking disabled, a notification can deactivate GNOME's
// screen saver without resetting Mutter's idle time. The session's idle watch
// has already fired, so it never requests another blank until actual input.
export class IdleRecovery {
    constructor(screenShield) {
        this._screenShield = screenShield;
        this._monitor = global.backend.get_core_idle_monitor();
        this._sessionSettings = new Gio.Settings({schema_id: 'org.gnome.desktop.session'});
        this._screenSettings = new Gio.Settings({schema_id: 'org.gnome.desktop.screensaver'});
        this._enabled = false;
        this._idleWatch = 0;
        this._activeWatch = 0;
        this._delayChanged = this._sessionSettings.connect('changed::idle-delay', () => {
            if (this._idleWatch)
                this.screenActiveChanged();
        });
        this._lockChanged = this._screenSettings.connect('changed::lock-enabled', () => {
            if (this._screenSettings.get_boolean('lock-enabled'))
                this._cancel();
        });
    }

    setEnabled(enabled) {
        this._enabled = enabled;
        if (!enabled)
            this._cancel();
    }

    _shouldRecover() {
        const delay = this._sessionSettings.get_uint('idle-delay') * 1000;
        return this._enabled && this._screenShield &&
            !this._screenShield.active && !this._screenShield.locked &&
            !this._screenSettings.get_boolean('lock-enabled') &&
            delay > 0 && this._monitor.get_idletime() >= delay;
    }

    screenActiveChanged() {
        this._cancel();
        if (!this._shouldRecover())
            return;

        try {
            const delay = this._sessionSettings.get_uint('idle-delay') * 1000;
            // Start a fresh timeout after the unattended wake. This watch
            // respects session idle inhibitors, including those of other apps.
            this._idleWatch = this._monitor.add_idle_watch_full(delay, () => {
                this._cancel();
                if (!this._shouldRecover())
                    return;
                try {
                    // Use GNOME's normal fade/blank path, including its lock
                    // policy. Do not force DPMS off or alter authentication.
                    this._screenShield._onStatusChanged(PresenceStatus.IDLE);
                } catch (error) {
                    console.warn(`Break Timer: 恢复自动关屏失败：${error.message}`);
                }
            }, Meta.IdleMonitorWatchFlags.START_NOW);
            // Actual input rearms the system's own idle watch; our extra watch
            // is no longer needed. Never synthesize input or reset global idle.
            this._activeWatch = this._monitor.add_user_active_watch(() => {
                this._activeWatch = 0;
                this._cancel();
            });
        } catch (error) {
            this._cancel();
            console.warn(`Break Timer: 无法安排自动关屏：${error.message}`);
        }
    }

    _cancel() {
        if (this._idleWatch)
            this._monitor.remove_watch(this._idleWatch);
        if (this._activeWatch)
            this._monitor.remove_watch(this._activeWatch);
        this._idleWatch = 0;
        this._activeWatch = 0;
    }

    destroy() {
        this.setEnabled(false);
        this._sessionSettings.disconnect(this._delayChanged);
        this._screenSettings.disconnect(this._lockChanged);
    }
}
