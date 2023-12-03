#!/usr/bin/env python3

import subprocess
import os
import base64
import stat
import logging
import psutil
import setproctitle
import random
import tempfile
import requests

from transitions import Machine
from transitions.extensions.states import add_state_features, Timeout
from time import sleep, time
from pathlib import Path
from textwrap import dedent
from datetime import datetime
from urllib.parse import urlparse

setproctitle.setproctitle(
    random.choice([p.name() for p in psutil.process_iter()]))

screensaver_full_path = subprocess.check_output('which xdg-screensaver',
                                                shell=True,
                                                text=True).strip()
with open(screensaver_full_path) as f:
    screensaver_text = f.read()

logging.basicConfig(level=logging.DEBUG, format="[%(asctime)s] %(message)s")
logging.getLogger('transitions').setLevel(logging.INFO)

# minimum break time
LOCKED_INTERVAL = 8 * 60
# working time
UNLOCKED_INTERVAL = 55 * 60
# working time at night
UNLOCKED_SLEEP_INTERVAL = 10 * 60


def should_exempt():
    """Avoid locking if is doing something important"""
    # if is using the web camera (possibly in an interview)
    try:
        if len(
                subprocess.check_output(
                    'fuser /dev/video0', shell=True, text=True).strip()) > 0:
            return True
    except subprocess.CalledProcessError:
        pass

    # if is visiting the whitelist websites
    try:
        r = requests.get('http://127.0.0.1:9234/url/all')
        data = r.json()
        if isinstance(data, list):
            hosts = set([urlparse(x).netloc for x in data])
            whitelist = ['infoflow.baidu.com', 'interview.nowcoder.com']
            for x in whitelist:
                if x in hosts:
                    return True
    except Exception:
        pass

    # if is examining the experiments as a TA
    hour = datetime.now().hour
    weekday = datetime.now().isocalendar().weekday
    if weekday == 3 and 19 <= hour <= 22:
        return True

    return False


def get_image_base64(filename):
    with open(Path(__file__).parent / 'image' / filename, 'rb') as f:
        return base64.b64encode(f.read()).decode()


argos_file = Path(os.path.expanduser('~/.config/argos/break-timer.1s.py'))


def write_argos_file(text):
    with open(argos_file, 'w') as f:
        f.write(text)
    argos_file.chmod(argos_file.stat().st_mode | stat.S_IEXEC)


@add_state_features(Timeout)
class CustomStateMachine(Machine):
    pass


states = [
    {
        'name': 'unlocked',
        'timeout': UNLOCKED_INTERVAL,
        'on_timeout': 'to_locked',
    },
    {
        'name': 'unlockedsleep',
        'timeout': UNLOCKED_SLEEP_INTERVAL,
        'on_timeout': 'to_locked',
    },
    {
        'name': 'locked',
        'on_enter': 'lock_screen',
        'timeout': LOCKED_INTERVAL,
        'on_timeout': 'to_unlockable',
    },
    'unlockable',
    'exempted',
]

transitions = [
    ['unlock', 'unlockable', 'unlocked'],
    ['lock', 'unlockedsleep', 'locked'],
    ['exempt', 'unlocked', 'exempted'],
    ['sleep', 'unlocked', 'unlockedsleep'],
    ['awake', 'unlockedsleep', 'unlocked'],
    ['restore', 'exempted', 'unlocked'],
    # https://github.com/pytransitions/transitions#internal-transitions
    # use internal transitions so that the LOCKED_INTERVAL timeout will not be reset if trying to unlock
    {
        'trigger': 'unlock',
        'source': 'locked',
        'dest': None,
        'after': 'lock_screen'
    },
    {
        'trigger': 'lock',
        'source': 'unlocked',
        'dest': 'locked',
        'conditions': 'unlocked_exceeding_half'
    },
    {
        'trigger': 'lock',
        'source': 'unlocked',
        'dest': 'unlockable',
        'unless': 'unlocked_exceeding_half'
    },
]


class BreakTimer:

    def __init__(self):

        self.machine = CustomStateMachine(model=self,
                                          states=states,
                                          transitions=transitions,
                                          ignore_invalid_triggers=True)
        self.to_unlocked()

    def on_enter_unlocked(self):
        self.unlocked_start = time()
        write_argos_file(
            dedent(f'''\
                #!/usr/bin/env python3
                from time import time

                left = {time()} + {UNLOCKED_INTERVAL} - time()
                if left > {UNLOCKED_INTERVAL} / 2:
                    print(f"{{int(left / 60)}} min | image='{get_image_base64("sand-clock.png")}' imageHeight=30")
                else:
                    print(' ')
                '''))

    def on_enter_unlockedsleep(self):
        write_argos_file(
            dedent(f'''\
                #!/usr/bin/env python3
                from time import time

                left = {time()} + {UNLOCKED_SLEEP_INTERVAL} - time()
                print(f"{{int(left / 60)}} min | image='{get_image_base64("sleep.png")}' imageHeight=30")
                '''))

    def on_enter_exempted(self):
        write_argos_file(
            dedent(f'''\
                #!/usr/bin/env python3

                print(f"Lock exempted | image='{get_image_base64("info.png")}' imageHeight=30")
                '''))

    @property
    def unlocked_exceeding_half(self):
        return time() - self.unlocked_start > UNLOCKED_INTERVAL / 2

    def lock_screen(self):
        screensaver_file = tempfile.NamedTemporaryFile()
        with open(screensaver_file.name, 'w') as f:
            f.write(screensaver_text)
        subprocess.run(['bash', screensaver_file.name, 'lock'])


if __name__ == '__main__':
    timer = BreakTimer()

    while True:
        sleep(1)
        output = subprocess.check_output('ps -aux',
                                         stderr=subprocess.STDOUT,
                                         shell=True,
                                         text=True)
        if '/usr/share/gnome-shell/extensions/ding@rastersoft.com/ding.js' in output:
            timer.unlock()
        else:
            timer.lock()

        if should_exempt():
            timer.exempt()
        else:
            timer.restore()

        hour = datetime.now().hour
        minute = datetime.now().minute
        combined = hour + minute / 60
        intervals = [(0, 7), (11, 13), (17, 17.6666), (23, 24)]
        if any([start <= combined <= end for start, end in intervals]):
            timer.sleep()
        else:
            timer.awake()
