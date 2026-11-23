import {Clock} from '../lib/clock.js';
import {TimerEngine} from '../lib/engine.js';
import {parseRanges, scheduleAt} from '../lib/schedule.js';

const clock = new Clock();
const now = clock.now();
if (!(now.boot > 0) || !now.bootId)
    throw new Error('Linux boot clock failed');
const engine = new TimerEngine({blockedRanges: []}, now);
if (engine.tick(now).state !== 'work')
    throw new Error('GJS engine failed');
if (!scheduleAt(parseRanges(['00:00-24:00']), now.wall).active)
    throw new Error('GJS schedule failed');
print('GJS runtime and suspend-aware clock: OK');
