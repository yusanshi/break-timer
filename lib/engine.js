import {parseRanges, scheduleAt, firstBlockBetween} from './schedule.js';

export const DEFAULTS = Object.freeze({
    workMs: 50 * 60_000,
    breakMs: 10 * 60_000,
    blockedRanges: ['00:00-08:00', '12:00-13:00', '18:00-19:00'],
    breakWarningMs: 60_000,
    blockWarningMs: 180_000,
});

// Pure state machine: no GNOME imports, wall clock for schedules and a
// suspend-aware monotonic clock (Linux boot time) for elapsed durations.
export class TimerEngine {
    constructor(config, clock, saved = null) {
        this.configure(config);
        this.phase = 'work';
        this.workRemaining = this.config.workMs;
        this.breakUntil = null;
        this.awaySince = null;
        this.lastBoot = clock.boot;
        this.lastWall = clock.wall;
        this.bootId = clock.bootId;
        if (this._validSnapshot(saved))
            this._restore(saved, clock);
    }

    configure(config) {
        const next = {...DEFAULTS, ...config};
        for (const key of ['workMs', 'breakMs']) {
            if (!Number.isFinite(next[key]) || next[key] <= 0)
                throw new Error(`无效时长：${key}`);
        }
        for (const key of ['breakWarningMs', 'blockWarningMs']) {
            if (!Number.isFinite(next[key]) || next[key] < 0)
                throw new Error(`无效提醒时长：${key}`);
        }
        const ranges = parseRanges(next.blockedRanges);
        this.config = next;
        this.ranges = ranges;
    }

    _validSnapshot(s) {
        return s?.version === 1 && ['work', 'break', 'ready'].includes(s.phase) &&
            typeof s.bootId === 'string' &&
            Number.isFinite(s.lastBoot) && s.lastBoot >= 0 &&
            Number.isFinite(s.lastWall) &&
            Number.isFinite(s.workRemaining) && s.workRemaining >= 0 &&
            (s.awaySince === null || (Number.isFinite(s.awaySince) && s.awaySince <= s.lastBoot)) &&
            (s.phase !== 'break' || Number.isFinite(s.breakUntil));
    }

    _restore(s, clock) {
        this.phase = s.phase;
        this.workRemaining = s.workRemaining;
        this.breakUntil = s.phase === 'break' ? s.breakUntil : null;
        this.awaySince = s.awaySince;
        this.lastWall = s.lastWall;
        if (s.bootId === clock.bootId && s.lastBoot <= clock.boot) {
            this.lastBoot = s.lastBoot;
            return;
        }
        // After a reboot the boot clock has a new origin. Time powered off
        // counts as rest, never as work. Backward wall changes grant no credit.
        const offline = Math.max(0, clock.wall - s.lastWall);
        if (this.phase === 'break') {
            const left = Math.max(0, s.breakUntil - s.lastBoot - offline);
            this.breakUntil = clock.boot + left;
        } else if (this.phase === 'work' && offline >= this.config.breakMs) {
            this.phase = 'ready';
        }
        this.awaySince = null;
        this.lastBoot = clock.boot;
    }

    tick(clock, away = false) {
        const elapsed = Math.max(0, clock.boot - this.lastBoot);
        const block = firstBlockBetween(this.ranges, this.lastWall, clock.wall);
        const schedule = scheduleAt(this.ranges, clock.wall);

        if (this.phase === 'work' && this.awaySince === null) {
            const beforeBlock = block === null ? Infinity :
                Math.max(0, Math.min(elapsed, block - this.lastWall));
            if (this.workRemaining <= elapsed && this.workRemaining <= beforeBlock) {
                this.breakUntil = this.lastBoot + this.workRemaining + this.config.breakMs;
                this.workRemaining = 0;
                this.phase = 'break';
            } else {
                this.workRemaining = Math.max(0, this.workRemaining - elapsed);
            }
        }
        if (this.phase === 'work' && this.awaySince !== null &&
            clock.boot - this.awaySince >= this.config.breakMs)
            this.phase = 'ready';

        if (this.phase === 'break' && clock.boot >= this.breakUntil) {
            this.phase = 'ready';
            this.breakUntil = null;
        }
        // A ban interrupts work. Its end requires explicit acknowledgement;
        // an already-running break must also finish before acknowledgement.
        if (this.phase === 'work' && (block !== null || schedule.active))
            this.phase = 'ready';

        if (away && this.awaySince === null)
            this.awaySince = clock.boot;
        else if (!away)
            this.awaySince = null;
        this.lastBoot = clock.boot;
        this.lastWall = clock.wall;
        return this.view(clock, schedule);
    }

    view(clock, schedule = scheduleAt(this.ranges, clock.wall)) {
        const state = schedule.active ? 'blocked' : this.phase;
        const breakRemaining = this.phase === 'break' ? Math.max(0, this.breakUntil - clock.boot) : 0;
        const blockRemaining = schedule.active ? schedule.active.end - clock.wall : 0;
        const nextBlockIn = schedule.next ? schedule.next.start - clock.wall : Infinity;
        return {
            state,
            away: this.awaySince !== null,
            remaining: state === 'work' ? this.workRemaining : Math.max(breakRemaining, blockRemaining),
            workRemaining: this.workRemaining,
            breakRemaining,
            blockedUntil: schedule.active?.end ?? null,
            nextBlockAt: schedule.next?.start ?? null,
            nextBlockIn,
            canResume: state === 'ready' && this.awaySince === null,
            breakWarning: state === 'work' && this.awaySince === null &&
                this.workRemaining <= this.config.breakWarningMs,
            blockWarning: !schedule.active && nextBlockIn <= this.config.blockWarningMs,
        };
    }

    resume(clock, away = false) {
        if (!this.tick(clock, away).canResume)
            return false;
        this.phase = 'work';
        this.workRemaining = this.config.workMs;
        this.breakUntil = null;
        return true;
    }

    snapshot() {
        return {
            version: 1,
            bootId: this.bootId,
            phase: this.phase,
            workRemaining: this.workRemaining,
            breakUntil: this.breakUntil,
            awaySince: this.awaySince,
            lastBoot: this.lastBoot,
            lastWall: this.lastWall,
        };
    }
}
