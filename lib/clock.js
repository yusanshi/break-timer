import GLib from 'gi://GLib';

const decoder = new TextDecoder();
function readText(path) {
    const [ok, bytes] = GLib.file_get_contents(path);
    if (!ok)
        throw new Error(`无法读取 ${path}`);
    return decoder.decode(bytes).trim();
}

export class Clock {
    constructor() {
        this.bootId = readText('/proc/sys/kernel/random/boot_id');
    }

    now() {
        // /proc/uptime includes suspend and is unaffected by NTP/date changes.
        const boot = Number(readText('/proc/uptime').split(' ')[0]) * 1000;
        if (!Number.isFinite(boot))
            throw new Error('无法读取系统运行时间');
        return {wall: Date.now(), boot, bootId: this.bootId};
    }
}
