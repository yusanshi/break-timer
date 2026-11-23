import Adw from 'gi://Adw';
import Gio from 'gi://Gio';

import {ExtensionPreferences} from 'resource:///org/gnome/Shell/Extensions/js/extensions/prefs.js';
import {parseRanges} from './lib/schedule.js';

export default class BreakTimerPreferences extends ExtensionPreferences {
    fillPreferencesWindow(window) {
        const settings = this.getSettings();
        window._settings = settings;
        window.set_default_size(640, 760);
        const page = new Adw.PreferencesPage({title: 'Break Timer', icon_name: 'alarm-symbolic'});
        window.add(page);

        const cycles = new Adw.PreferencesGroup({
            title: '工作与休息',
            description: '时长修改从下一轮工作或下一次休息开始生效。',
        });
        page.add(cycles);
        this._spin(cycles, settings, 'work-minutes', '工作时长（分钟）', 1, 1440);
        this._spin(cycles, settings, 'break-minutes', '休息时长（分钟）', 1, 1440);

        const schedule = new Adw.PreferencesGroup({
            title: '每日封禁时段',
            description: '按本地时间每天重复，多个时段用逗号分隔。支持跨午夜，如 22:00-08:00；留空则关闭每日封禁。',
        });
        page.add(schedule);
        const ranges = new Adw.EntryRow({
            title: '时段 · HH:MM-HH:MM',
            text: settings.get_strv('blocked-ranges').join(', '),
            show_apply_button: true,
        });
        schedule.add(ranges);
        ranges.connect('apply', () => {
            try {
                const values = ranges.text.split(/[,，;；\n]+/).map(s => s.trim()).filter(Boolean);
                parseRanges(values);
                settings.set_strv('blocked-ranges', values);
                ranges.remove_css_class('error');
                window.add_toast(new Adw.Toast({title: '封禁时段已应用'}));
            } catch (error) {
                ranges.add_css_class('error');
                window.add_toast(new Adw.Toast({title: error.message, timeout: 6}));
            }
        });

        const warnings = new Adw.PreferencesGroup({title: '提前提醒', description: '设为 0 可关闭对应提醒。'});
        page.add(warnings);
        this._spin(warnings, settings, 'break-warning-seconds', '休息前顶栏闪烁（秒）', 0, 3600);
        this._spin(warnings, settings, 'block-warning-seconds', '封禁前右上角倒计时（秒）', 0, 3600);

        const behavior = new Adw.PreferencesGroup({title: '锁屏与休眠'});
        page.add(behavior);
        for (const [title, subtitle] of [
            ['短暂离开暂停工作计时', '锁屏或休眠满一个休息周期，回来后即可手动开始新一轮工作。'],
            ['休眠时间计入休息', '休息或封禁结束后，等待你点击“结束休息，开始工作”。'],
            ['保留账户锁屏', '休息期间可使用 Super+L。系统锁屏或休眠唤醒的认证沿用系统设置。'],
            ['封禁时段优先', '工作会被封禁中断；已经开始的休息也必须结束后才能解除。'],
        ])
            behavior.add(new Adw.ActionRow({title, subtitle}));
    }

    _spin(group, settings, key, title, min, max) {
        const row = Adw.SpinRow.new_with_range(min, max, 1);
        row.title = title;
        settings.bind(key, row, 'value', Gio.SettingsBindFlags.DEFAULT);
        group.add(row);
    }
}
