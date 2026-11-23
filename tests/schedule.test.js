import test from 'node:test';
import assert from 'node:assert/strict';
import {parseRanges, scheduleAt, formatDuration, firstBlockBetween} from '../lib/schedule.js';

const wall = time => new Date(`2026-11-22T${time}+08:00`).getTime();

test('ranges reject invalid clocks and empty intervals', () => {
    for (const value of ['24:01-08:00', '12:60-13:00', 'abc', '8-9', '12:00-12:00', '24:00-08:00'])
        assert.throws(() => parseRanges([value]));
    assert.deepEqual(parseRanges(['0:00 ~ 8:00']), [[0, 480]]);
});

test('overlapping and adjacent intervals are merged', () => {
    const ranges = parseRanges(['12:00-13:00', '12:30-14:00', '14:00-15:00']);
    assert.deepEqual(ranges, [[720, 900]]);
    assert.equal(scheduleAt(ranges, wall('13:00:00')).active.end, wall('15:00:00'));
    assert.equal(scheduleAt(ranges, wall('15:00:00')).active, null);
});

test('overnight ranges do not unlock at midnight', () => {
    const ranges = parseRanges(['22:00-08:00']);
    const before = scheduleAt(ranges, wall('23:59:59'));
    assert.equal(before.active.end, new Date('2026-11-23T08:00:00+08:00').getTime());
    assert.equal(scheduleAt(ranges, wall('00:00:00')).active.end, wall('08:00:00'));
    assert.equal(scheduleAt(ranges, wall('08:00:00')).active, null);
});

test('split intervals merge across midnight and across a year boundary', () => {
    const ranges = parseRanges(['23:00-24:00', '00:00-08:00']);
    const info = scheduleAt(ranges, new Date('2026-12-31T23:30:00+08:00').getTime());
    assert.equal(info.active.end, new Date('2027-01-01T08:00:00+08:00').getTime());
});

test('full day coverage has no false midnight release', () => {
    const ranges = parseRanges(['00:00-12:00', '12:00-24:00']);
    assert.equal(scheduleAt(ranges, wall('12:00:00')).active.end, Infinity);
    assert.equal(formatDuration(Infinity), '全天');
});

test('empty schedule and future occurrence', () => {
    assert.deepEqual(scheduleAt([], wall('12:00:00')), {active: null, next: null});
    const ranges = parseRanges(['12:00-13:00']);
    assert.equal(scheduleAt(ranges, wall('11:57:00')).next.start, wall('12:00:00'));
    assert.equal(scheduleAt(ranges, wall('13:00:00')).next.start, wall('12:00:00') + 86400_000);
    assert.equal(firstBlockBetween(ranges, wall('11:59:00'), wall('13:01:00')), wall('12:00:00'));
});

test('countdown rounds up so 00:00 never appears before expiry', () => {
    assert.equal(formatDuration(1), '00:01');
    assert.equal(formatDuration(60_001), '01:01');
    assert.equal(formatDuration(8 * 3600_000), '8:00:00');
    assert.equal(formatDuration(-1000), '00:00');
});

test('calendar boundaries follow daylight saving transitions', () => {
    const previous = process.env.TZ;
    try {
        process.env.TZ = 'America/New_York';
        const ranges = parseRanges(['00:00-08:00']);
        const spring = new Date('2026-03-08T00:00:00-05:00').getTime();
        const autumn = new Date('2026-11-01T00:00:00-04:00').getTime();
        assert.equal(scheduleAt(ranges, spring).active.end - spring, 7 * 3600_000);
        assert.equal(scheduleAt(ranges, autumn).active.end - autumn, 9 * 3600_000);
    } finally {
        process.env.TZ = previous;
    }
});
