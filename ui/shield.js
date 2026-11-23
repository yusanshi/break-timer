import Clutter from 'gi://Clutter';
import Shell from 'gi://Shell';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {formatDuration, formatTime} from '../lib/schedule.js';

export class BreakShield {
    constructor(onResume, onLock) {
        this._onResume = onResume;
        this._onLock = onLock;
        this._grab = null;
        this._view = null;
        this._cards = [];
        this.actor = new St.Widget({
            name: 'break-timer-shield',
            style_class: 'break-timer-shield',
            reactive: true,
            can_focus: true,
            visible: false,
            constraints: new Clutter.BindConstraint({
                source: global.stage,
                coordinate: Clutter.BindCoordinate.ALL,
            }),
        });
        Main.layoutManager.uiGroup.add_child(this.actor);
        this.actor.connect('captured-event', (_actor, event) => this._capture(event));
        this._monitorId = Main.layoutManager.connect('monitors-changed', () => this._rebuild());
        this._rebuild();
    }

    _rebuild() {
        this.actor.destroy_all_children();
        this._cards = [];
        for (const monitor of Main.layoutManager.monitors) {
            const box = new St.BoxLayout({
                orientation: Clutter.Orientation.VERTICAL,
                style_class: 'break-timer-card',
                x_align: Clutter.ActorAlign.CENTER,
                y_align: Clutter.ActorAlign.CENTER,
            });
            const title = new St.Label({style_class: 'break-timer-title'});
            const countdown = new St.Label({style_class: 'break-timer-countdown'});
            const detail = new St.Label({style_class: 'break-timer-detail'});
            const resume = new St.Button({
                label: '结束休息，开始工作',
                style_class: 'break-timer-resume',
                can_focus: true,
                visible: false,
                x_align: Clutter.ActorAlign.CENTER,
            });
            resume.connect('clicked', () => this._onResume());
            const lock = new St.Button({
                label: '锁定账户 · Super+L',
                style_class: 'break-timer-lock',
                can_focus: true,
                visible: Boolean(Main.screenShield),
                x_align: Clutter.ActorAlign.CENTER,
            });
            lock.connect('clicked', () => this._onLock());
            for (const child of [title, countdown, detail, resume, lock])
                box.add_child(child);
            const bin = new St.Bin({
                x: monitor.x,
                y: monitor.y,
                width: monitor.width,
                height: monitor.height,
                child: box,
            });
            this.actor.add_child(bin);
            this._cards.push({title, countdown, detail, resume, lock});
        }
        if (this._view)
            this._render();
        if (this._grab)
            this.actor.grab_key_focus();
    }

    _capture(event) {
        const type = event.type();
        if (type !== Clutter.EventType.KEY_PRESS && type !== Clutter.EventType.KEY_RELEASE)
            return Clutter.EVENT_PROPAGATE;
        const key = event.get_key_symbol();
        if (type === Clutter.EventType.KEY_PRESS &&
            (key === Clutter.KEY_l || key === Clutter.KEY_L) &&
            (event.get_state() & (Clutter.ModifierType.SUPER_MASK | Clutter.ModifierType.MOD4_MASK))) {
            this._onLock();
            return Clutter.EVENT_STOP;
        }
        if (type === Clutter.EventType.KEY_PRESS &&
            (key === Clutter.KEY_Tab || key === Clutter.KEY_ISO_Left_Tab)) {
            const buttons = this._cards.flatMap(card => [card.resume, card.lock]).filter(b => b.visible);
            if (buttons.length === 0)
                return Clutter.EVENT_STOP;
            const current = buttons.indexOf(global.stage.key_focus);
            const backwards = Boolean(event.get_state() & Clutter.ModifierType.SHIFT_MASK);
            const next = (current + (backwards ? -1 : 1) + buttons.length) % buttons.length;
            buttons[next]?.grab_key_focus();
            return Clutter.EVENT_STOP;
        }
        // Keyboard activation is limited to deliberately focused buttons.
        if ([Clutter.KEY_Return, Clutter.KEY_KP_Enter, Clutter.KEY_space].includes(key) &&
            this._cards.some(card => global.stage.key_focus === card.lock ||
                (this._view.canResume && global.stage.key_focus === card.resume)))
            return Clutter.EVENT_PROPAGATE;
        return Clutter.EVENT_STOP;
    }

    _render() {
        const view = this._view;
        for (const card of this._cards) {
            card.title.text = view.state === 'blocked' ? '现在是封禁时段' :
                view.state === 'ready' ? '休息完成' : '离开屏幕，休息一下';
            card.countdown.text = view.state === 'ready' ? '可以继续了' : formatDuration(view.remaining);
            card.detail.text = view.state === 'blocked' && Number.isFinite(view.blockedUntil)
                ? `封禁至 ${formatTime(view.blockedUntil)}`
                : '';
            card.detail.visible = card.detail.text !== '';
            card.resume.visible = view.canResume;
        }
    }

    update(view, systemLocked, authenticating) {
        this._view = view;
        if (view.state === 'work') {
            this._release();
            this.actor.hide();
            return;
        }
        this._render();
        this.actor.show();
        if (systemLocked) {
            // Keep the curtain below the real lock screen. It remains present
            // throughout the unlock animation, without capturing authentication.
            Main.layoutManager.uiGroup.set_child_below_sibling(
                this.actor, Main.layoutManager.screenShieldGroup);
        } else {
            Main.layoutManager.uiGroup.set_child_above_sibling(this.actor, null);
        }
        if (authenticating) {
            this._release();
        } else if (!this._grab) {
            // Reacquire as soon as authentication ends, even if GNOME is
            // still animating its curtain. Otherwise applications could see
            // input between GNOME dropping its grab and active-changed.
            Main.overview.hide();
            Main.panel.closeCalendar();
            this._grab = Main.pushModal(this.actor, {actionMode: Shell.ActionMode.NONE});
            this.actor.grab_key_focus();
        }
    }

    _release() {
        if (this._grab) {
            Main.popModal(this._grab);
            this._grab = null;
        }
    }

    destroy() {
        this._release();
        Main.layoutManager.disconnect(this._monitorId);
        this.actor.destroy();
    }
}
