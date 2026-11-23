// Daily schedules use local civil time. Durations are measured separately.
const DAY_MINUTES = 24 * 60;

function minutes(text, allowEndOfDay = false) {
    const match = /^(\d{1,2}):(\d{2})$/.exec(text.trim());
    if (!match)
        throw new Error(`无效时间：${text}，请使用 HH:MM`);
    const hour = Number(match[1]);
    const minute = Number(match[2]);
    if (hour === 24 && minute === 0 && allowEndOfDay)
        return DAY_MINUTES;
    if (hour > 23 || minute > 59)
        throw new Error(`时间超出范围：${text}`);
    return hour * 60 + minute;
}

export function parseRanges(values) {
    if (!Array.isArray(values))
        throw new Error('封禁时段必须是列表');
    const pieces = [];
    for (const value of values) {
        const parts = String(value).trim().split(/\s*[-~～–]\s*/);
        if (parts.length !== 2)
            throw new Error(`无效时段：${value}，请使用 HH:MM-HH:MM`);
        const start = minutes(parts[0]);
        const end = minutes(parts[1], true);
        if (start === end)
            throw new Error('开始和结束不能相同；全天请填写 00:00-24:00');
        if (start < end) {
            pieces.push([start, end]);
        } else {
            pieces.push([start, DAY_MINUTES]);
            if (end > 0)
                pieces.push([0, end]);
        }
    }
    pieces.sort((a, b) => a[0] - b[0]);
    const merged = [];
    for (const [start, end] of pieces) {
        const last = merged.at(-1);
        if (last && start <= last[1])
            last[1] = Math.max(last[1], end);
        else
            merged.push([start, end]);
    }
    return merged;
}

function localTime(day, offset, minute) {
    // Calendar arithmetic, rather than adding 24 hours, also handles DST.
    return new Date(day.getFullYear(), day.getMonth(), day.getDate() + offset,
        Math.floor(minute / 60), minute % 60).getTime();
}

export function scheduleAt(ranges, wallMs) {
    if (ranges.length === 0)
        return {active: null, next: null};
    if (ranges.length === 1 && ranges[0][0] === 0 && ranges[0][1] === DAY_MINUTES)
        return {active: {start: -Infinity, end: Infinity}, next: null};

    const day = new Date(wallMs);
    const intervals = [];
    for (let offset = -1; offset <= 2; offset++) {
        for (const [start, end] of ranges) {
            const a = localTime(day, offset, start);
            const b = localTime(day, offset, end);
            if (b <= a)
                continue;
            const previous = intervals.at(-1);
            if (previous && a <= previous.end)
                previous.end = Math.max(previous.end, b);
            else
                intervals.push({start: a, end: b});
        }
    }
    return {
        active: intervals.find(i => i.start <= wallMs && wallMs < i.end) ?? null,
        next: intervals.find(i => i.start > wallMs) ?? null,
    };
}

export function firstBlockBetween(ranges, fromWallMs, toWallMs) {
    if (toWallMs < fromWallMs)
        return scheduleAt(ranges, toWallMs).active ? toWallMs : null;
    const info = scheduleAt(ranges, fromWallMs);
    if (info.active)
        return fromWallMs;
    return info.next && info.next.start <= toWallMs ? info.next.start : null;
}

export function formatDuration(ms) {
    if (!Number.isFinite(ms))
        return '全天';
    const seconds = Math.max(0, Math.ceil(ms / 1000));
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor(seconds % 3600 / 60);
    const tail = `${String(minutes).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
    return hours ? `${hours}:${tail}` : tail;
}

export function formatTime(wallMs) {
    if (!Number.isFinite(wallMs))
        return '全天';
    const date = new Date(wallMs);
    return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
}
