import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import Meta from 'gi://Meta';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import {formatDuration, formatTime} from '../lib/schedule.js';

export class Indicator {
    constructor(openPreferences) {
        this.button = new PanelMenu.Button(0.0, 'Break Timer');
        const box = new St.BoxLayout({style_class: 'panel-status-menu-box'});
        this._workIcon = new St.Icon({
            gicon: new Gio.FileIcon({file: Gio.File.new_for_uri(import.meta.url)
                .get_parent().get_parent().get_child('icons').get_child('sand-clock.png')}),
            style_class: 'system-status-icon break-timer-work-icon',
            y_align: Clutter.ActorAlign.CENTER,
        });
        this.label = new St.Label({
            style_class: 'break-timer-panel-label',
            y_align: Clutter.ActorAlign.CENTER,
            text: '工作',
        });
        box.add_child(this._workIcon);
        box.add_child(this.label);
        this.button.add_child(box);
        this._status = new PopupMenu.PopupMenuItem('', {reactive: false});
        this._next = new PopupMenu.PopupMenuItem('', {reactive: false});
        this.button.menu.addMenuItem(this._status);
        this.button.menu.addMenuItem(this._next);
        this.button.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        this.button.menu.addAction('设置…', openPreferences);
        Main.panel.addToStatusArea('break-timer', this.button, 0, 'right');
        this._panelBox = Main.panel._rightBox;
        this._positionLater = 0;
        this._knownChildren = new WeakSet(this._panelBox.get_children());
        this._childAddedId = this._panelBox.connect('child-added', (_box, child) => {
            // A peer may reorder by removing and reinserting its actor. Only
            // genuinely new actors get one positioning attempt, never retries.
            if (this._knownChildren.has(child))
                return;
            this._knownChildren.add(child);
            this._queuePosition();
        });
        this._queuePosition();
        this._blink = false;
    }

    _queuePosition() {
        if (this._positionLater || this._panelBox.get_first_child() === this.button.container)
            return;
        // Coalesce new indicators into one attempt before redraw. Do not watch
        // first-child: two extensions enforcing that slot can fight forever.
        this._positionLater = global.compositor.get_laters().add(Meta.LaterType.BEFORE_REDRAW, () => {
            this._positionLater = 0;
            const container = this.button.container;
            if (container.get_parent() === this._panelBox &&
                this._panelBox.get_first_child() !== container)
                this._panelBox.set_child_at_index(container, 0);
            return false;
        });
    }

    update(view, visible) {
        this.button.visible = visible;
        const names = {work: '工作', break: '休息', blocked: '封禁', ready: '可解除'};
        const status = view.state === 'ready' ? '休息完成' :
            `${names[view.state]} ${formatDuration(view.remaining)}`;
        this._workIcon.visible = view.state === 'work';
        this.label.text = view.state === 'work' && !view.breakWarning ? '工作' : status;
        this._status.label.text = view.away && view.state === 'work'
            ? `工作已暂停 · 剩余 ${formatDuration(view.remaining)}` : status;
        this._next.label.text = view.nextBlockAt === null ? '没有后续封禁时段' :
            `下次封禁 ${formatTime(view.nextBlockAt)}`;
        this._blink = view.breakWarning && !this._blink;
        if (view.breakWarning)
            this.label.add_style_class_name('break-timer-warning');
        else
            this.label.remove_style_class_name('break-timer-warning');
        this.label.opacity = this._blink ? 80 : 255;
        this.button.accessible_name = `Break Timer ${this._status.label.text}`;
    }

    destroy() {
        this._panelBox.disconnect(this._childAddedId);
        if (this._positionLater) {
            global.compositor.get_laters().remove(this._positionLater);
            this._positionLater = 0;
        }
        this.button.destroy();
    }
}

export class BlockReminder {
    constructor() {
        this.actor = new St.BoxLayout({
            name: 'break-timer-reminder',
            style_class: 'break-timer-reminder',
            orientation: Clutter.Orientation.VERTICAL,
            reactive: false,
            visible: false,
            width: 330,
        });
        this._title = new St.Label({text: '即将进入封禁时段', style_class: 'break-timer-reminder-title'});
        this._countdown = new St.Label({style_class: 'break-timer-reminder-time'});
        this._hint = new St.Label({text: '请保存工作，准备离开电脑'});
        for (const label of [this._title, this._countdown, this._hint])
            this.actor.add_child(label);
        Main.layoutManager.addTopChrome(this.actor, {trackFullscreen: false});
    }

    update(view, visible) {
        const monitor = Main.layoutManager.primaryMonitor;
        this.actor.visible = Boolean(visible && view.blockWarning && monitor);
        if (!this.actor.visible)
            return;
        Main.layoutManager.uiGroup.set_child_above_sibling(this.actor, null);
        const scale = St.ThemeContext.get_for_stage(global.stage).scale_factor;
        const width = Math.min(330 * scale, monitor.width - 24 * scale);
        this.actor.width = width;
        this.actor.set_position(monitor.x + monitor.width - width - 12 * scale,
            monitor.y + Main.layoutManager.panelBox.height + 12 * scale);
        this._countdown.text = `${formatDuration(view.nextBlockIn)} 后开始`;
    }

    destroy() {
        Main.layoutManager.removeChrome(this.actor);
        this.actor.destroy();
    }
}
