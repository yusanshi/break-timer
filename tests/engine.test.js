import test from 'node:test';
import assert from 'node:assert/strict';
import {TimerEngine} from '../lib/engine.js';

const MIN = 60_000;
function fixture(config = {}, time = '2026-11-22T09:00:00+08:00') {
    const clock = {wall: new Date(time).getTime(), boot: 1_000_000, bootId: 'boot-a'};
    const engine = new TimerEngine({blockedRanges: [], ...config}, clock);
    const tick = (ms = 0, away = false) => {
        clock.wall += ms;
        clock.boot += ms;
        return engine.tick(clock, away);
    };
    return {clock, engine, tick};
}

test('50/10 cycle waits indefinitely for explicit resume', () => {
    const {engine, tick, clock} = fixture();
    assert.equal(tick().state, 'work');
    assert.equal(tick(49 * MIN).breakWarning, true);
    assert.equal(tick(MIN).state, 'break');
    assert.equal(engine.resume(clock), false);
    assert.equal(tick(10 * MIN).state, 'ready');
    assert.equal(tick(3 * 60 * MIN).state, 'ready');
    assert.equal(engine.resume(clock), true);
    assert.equal(tick().remaining, 50 * MIN);
});

test('late callbacks do not extend break deadlines', () => {
    const {tick} = fixture();
    assert.equal(tick(55 * MIN).remaining, 5 * MIN);
    assert.equal(tick(20 * MIN).state, 'ready');
});

test('short lock pauses, then resumes the remaining work', () => {
    const {tick} = fixture();
    tick(20 * MIN, true);
    assert.equal(tick(5 * MIN, true).remaining, 30 * MIN);
    assert.equal(tick(0, false).remaining, 30 * MIN);
    assert.equal(tick(MIN).remaining, 29 * MIN);
});

test('long lock earns rest but does not start a new cycle', () => {
    const {tick, engine, clock} = fixture();
    tick(20 * MIN, true);
    assert.equal(tick(10 * MIN, true).state, 'ready');
    assert.equal(engine.resume(clock, true), false);
    assert.equal(tick(0, false).canResume, true);
    assert.equal(engine.resume(clock), true);
    assert.equal(tick().remaining, 50 * MIN);
});

test('separate short locks do not accumulate into a full rest', () => {
    const {tick} = fixture();
    tick(MIN, true);
    tick(6 * MIN, false);
    tick(MIN, true);
    assert.equal(tick(6 * MIN, false).state, 'work');
    assert.equal(tick().remaining, 48 * MIN);
});

test('suspend during rest counts fully, while system authentication remains separate', () => {
    const {tick, engine, clock} = fixture();
    tick(50 * MIN);
    tick(2 * MIN, true);
    assert.equal(tick(30 * MIN, true).state, 'ready');
    assert.equal(engine.resume(clock, true), false);
    assert.equal(tick(0, false).canResume, true);
});

test('starts blocked inside default ban; exact end requires acknowledgement', () => {
    const {tick, engine, clock} = fixture({blockedRanges: ['00:00-08:00']}, '2026-11-22T07:59:00+08:00');
    assert.equal(tick().state, 'blocked');
    assert.equal(engine.resume(clock), false);
    assert.equal(tick(MIN).state, 'ready');
    assert.equal(engine.resume(clock), true);
});

test('ban interrupts work before work can expire', () => {
    const {tick, engine, clock} = fixture({blockedRanges: ['12:00-13:00']}, '2026-11-22T11:56:00+08:00');
    assert.equal(tick().blockWarning, false);
    assert.equal(tick(MIN).blockWarning, true);
    assert.equal(tick(3 * MIN).state, 'blocked');
    assert.equal(engine.resume(clock), false);
    assert.equal(tick(60 * MIN).state, 'ready');
});

test('overlapping break and ban both have to end', () => {
    const {tick} = fixture({workMs: MIN, breakMs: 20 * MIN, blockedRanges: ['12:00-12:05']}, '2026-11-22T11:58:00+08:00');
    assert.equal(tick(MIN).state, 'break');
    assert.equal(tick(MIN).state, 'blocked');
    assert.equal(tick(5 * MIN).state, 'break');
    assert.equal(tick(14 * MIN).state, 'ready');
});

test('ban boundary wins when clicking resume at the same time', () => {
    const {tick, engine, clock} = fixture({workMs: MIN, breakMs: MIN, blockedRanges: ['12:00-13:00']}, '2026-11-22T11:57:00+08:00');
    assert.equal(tick(2 * MIN).canResume, true);
    clock.wall += MIN;
    clock.boot += MIN;
    assert.equal(engine.resume(clock), false);
});

test('a missed entire ban still requires acknowledgement after return', () => {
    const {tick} = fixture({workMs: 4 * 60 * MIN, blockedRanges: ['12:00-13:00']}, '2026-11-22T11:59:00+08:00');
    assert.equal(tick(62 * MIN).state, 'ready');
});

test('wall clock correction does not shorten work or rest', () => {
    const {tick, engine, clock} = fixture();
    clock.wall += 5 * 60 * MIN;
    assert.equal(tick(MIN).remaining, 49 * MIN);
    tick(49 * MIN);
    clock.wall -= 10 * 60 * MIN;
    assert.equal(tick(MIN).remaining, 9 * MIN);
    assert.equal(engine.phase, 'break');
});

test('wall changes still reevaluate local ban immediately', () => {
    const {tick, clock} = fixture({blockedRanges: ['12:00-13:00']});
    clock.wall = new Date('2026-11-22T12:30:00+08:00').getTime();
    assert.equal(tick().state, 'blocked');
});

test('snapshot recovery retains elapsed rest on same boot', () => {
    const {tick, engine, clock} = fixture();
    tick(52 * MIN);
    const saved = JSON.parse(JSON.stringify(engine.snapshot()));
    clock.wall += 3 * MIN;
    clock.boot += 3 * MIN;
    const restored = new TimerEngine({blockedRanges: []}, clock, saved);
    assert.equal(restored.tick(clock).remaining, 5 * MIN);
});

test('snapshot retains long external lock across extension reload', () => {
    const {tick, engine, clock} = fixture();
    tick(20 * MIN, true);
    const saved = engine.snapshot();
    clock.wall += 15 * MIN;
    clock.boot += 15 * MIN;
    const restored = new TimerEngine({blockedRanges: []}, clock, saved);
    assert.equal(restored.tick(clock, false).state, 'ready');
});

test('reboot time counts as rest, short reboot preserves work remainder', () => {
    const {tick, engine, clock} = fixture();
    tick(20 * MIN);
    const saved = engine.snapshot();
    const reboot = {...clock, bootId: 'boot-b', boot: 1000, wall: clock.wall + 5 * MIN};
    const short = new TimerEngine({blockedRanges: []}, reboot, saved);
    assert.equal(short.tick(reboot).remaining, 30 * MIN);
    reboot.wall += 10 * MIN;
    const long = new TimerEngine({blockedRanges: []}, reboot, saved);
    assert.equal(long.tick(reboot).state, 'ready');
});

test('reboot during break translates boot deadline correctly', () => {
    const {tick, engine, clock} = fixture();
    tick(52 * MIN);
    const reboot = {...clock, bootId: 'boot-b', boot: 1000, wall: clock.wall + 3 * MIN};
    const restored = new TimerEngine({blockedRanges: []}, reboot, engine.snapshot());
    assert.equal(restored.tick(reboot).remaining, 5 * MIN);
});

test('configuration changes preserve current duration, apply on next cycle', () => {
    const {engine, tick, clock} = fixture();
    tick(10 * MIN);
    engine.configure({blockedRanges: [], workMs: 25 * MIN, breakMs: 5 * MIN});
    assert.equal(tick().remaining, 40 * MIN);
    assert.equal(tick(40 * MIN).remaining, 5 * MIN);
    tick(5 * MIN);
    engine.resume(clock);
    assert.equal(tick().remaining, 25 * MIN);
});

test('invalid configuration is rejected atomically and bad snapshots are ignored', () => {
    const {engine, clock} = fixture();
    assert.throws(() => engine.configure({blockedRanges: ['25:00-08:00']}));
    assert.equal(engine.tick(clock).state, 'work');
    for (const saved of [{}, {version: 1, phase: 'break', breakUntil: 'bad'}, null]) {
        const fresh = new TimerEngine({blockedRanges: []}, clock, saved);
        assert.equal(fresh.tick(clock).remaining, 50 * MIN);
    }
});
