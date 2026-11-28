import GLib from 'gi://GLib';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as LoginManager from 'resource:///org/gnome/shell/misc/loginManager.js';

import {TimerEngine, DEFAULTS} from './lib/engine.js';
import {Clock} from './lib/clock.js';
import {IdleInhibitor} from './lib/idleInhibitor.js';
import {IdleRecovery} from './lib/idleRecovery.js';
import {BreakShield} from './ui/shield.js';
import {Indicator, BlockReminder} from './ui/indicator.js';

export default class BreakTimerExtension extends Extension {
    enable() {
        try {
            this._enable();
        } catch (error) {
            this.disable();
            throw error;
        }
    }

    _enable() {
        this._signals = [];
        this._settings = this.getSettings();
        this._clock = new Clock();
        this._loginManager = LoginManager.getLoginManager();
        this._sleeping = Boolean(this._loginManager.preparingForSleep);
        this._inhibitor = new IdleInhibitor();
        this._idleRecovery = new IdleRecovery(Main.screenShield);
        let saved = null;
        try {
            saved = JSON.parse(this._settings.get_string('saved-state'));
        } catch {
            // Empty or damaged snapshots start a fresh cycle; bans still apply.
        }
        const now = this._clock.now();
        try {
            this._engine = new TimerEngine(this._readConfig(), now, saved);
        } catch (error) {
            console.error(`Break Timer: 配置无效，使用默认值：${error.message}`);
            this._engine = new TimerEngine(DEFAULTS, now, saved);
        }
        this._shield = new BreakShield(() => this._resume(), () => this._lock());
        this._indicator = new Indicator(() => this.openPreferences());
        this._reminder = new BlockReminder();
        this._lastSave = 0;
        this._lastSignature = '';

        this._connect(Main.screenShield, 'active-changed', () => {
            this._sync();
            this._idleRecovery.screenActiveChanged();
        });
        this._connect(Main.screenShield, 'locked-changed', () => this._sync());
        this._connect(Main.sessionMode, 'updated', () => this._sync());
        this._connect(this._loginManager, 'prepare-for-sleep', (_manager, sleeping) => {
            this._sleeping = sleeping;
            this._sync();
            this._save();
        });
        this._connect(this._settings, 'changed', (_settings, key) => {
            if (key === 'saved-state')
                return;
            try {
                if (key !== 'inhibit-idle')
                    this._engine.configure(this._readConfig());
                this._sync();
            } catch (error) {
                Main.notify('Break Timer 配置未应用', error.message);
            }
        });
        this._sync();
        this._timer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 500, () => {
            this._guard(() => this._sync());
            return this._engine ? GLib.SOURCE_CONTINUE : GLib.SOURCE_REMOVE;
        });
    }

    _connect(object, signal, callback) {
        if (object)
            this._signals.push([object, object.connect(signal, (...args) =>
                this._guard(() => callback(...args)))]);
    }

    _guard(callback) {
        try {
            callback();
        } catch (error) {
            console.error(`Break Timer: ${error.stack ?? error}`);
            // A failed clock/UI update must not leave a permanent input grab.
            Main.extensionManager.disableExtension(this.uuid);
            Main.notify('Break Timer 已停用', '发生内部错误，已释放休息界面。详情见系统日志。');
        }
    }

    _readConfig() {
        return {
            workMs: this._settings.get_int('work-minutes') * 60_000,
            breakMs: this._settings.get_int('break-minutes') * 60_000,
            blockedRanges: this._settings.get_strv('blocked-ranges'),
            breakWarningMs: this._settings.get_int('break-warning-seconds') * 1000,
            blockWarningMs: this._settings.get_int('block-warning-seconds') * 1000,
        };
    }

    _systemLocked() {
        return this._sleeping || Main.screenShield?.locked || Main.screenShield?.active ||
            Main.sessionMode.isLocked || Main.sessionMode.currentMode === 'unlock-dialog';
    }

    _authenticating() {
        // GNOME leaves unlock-dialog after successful authentication, before
        // the unlock animation ends and screenShield.active becomes false.
        return this._sleeping || Main.sessionMode.isLocked ||
            Main.sessionMode.currentMode === 'unlock-dialog';
    }

    _sync() {
        const now = this._clock.now();
        const locked = this._systemLocked();
        const view = this._engine.tick(now, locked);
        this._view = view;
        this._shield.update(view, locked, this._authenticating());
        this._indicator.update(view, !locked);
        this._reminder.update(view, !locked);
        const inhibitIdle = this._settings.get_boolean('inhibit-idle');
        this._inhibitor.setWanted(inhibitIdle && !locked && view.state !== 'work');
        this._idleRecovery.setEnabled(!inhibitIdle && !this._sleeping && view.state !== 'work');
        const signature = `${view.state}:${view.away}:${this._engine.phase}`;
        if (signature !== this._lastSignature || now.boot - this._lastSave >= 30_000) {
            this._save();
            this._lastSave = now.boot;
            this._lastSignature = signature;
        }
    }

    _resume() {
        if (this._engine.resume(this._clock.now(), this._systemLocked())) {
            this._sync();
            this._save();
        }
    }

    _lock() {
        // GNOME owns authentication; never call deactivate() or change its
        // lock-enabled / suspend-lock-enabled settings.
        if (!Main.screenShield) {
            Main.notify('Break Timer', '当前会话不支持系统账户锁屏。');
            return;
        }
        Main.screenShield.lock(false);
        this._sync();
    }

    _save() {
        this._settings?.set_string('saved-state', JSON.stringify(this._engine.snapshot()));
    }

    disable() {
        if (this._timer) {
            GLib.Source.remove(this._timer);
            this._timer = null;
        }
        for (const [object, id] of this._signals ?? [])
            object.disconnect(id);
        this._signals = [];
        if (this._engine) {
            try {
                this._engine.tick(this._clock.now(), this._systemLocked());
                this._save();
            } catch (error) {
                console.warn(`Break Timer: 无法保存状态：${error.message}`);
            }
        }
        this._inhibitor?.destroy();
        this._idleRecovery?.destroy();
        this._shield?.destroy();
        this._reminder?.destroy();
        this._indicator?.destroy();
        this._shield = null;
        this._reminder = null;
        this._indicator = null;
        this._inhibitor = null;
        this._idleRecovery = null;
        this._engine = null;
        this._settings = null;
        this._clock = null;
        this._loginManager = null;
    }
}
