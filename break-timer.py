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

from transitions import Machine
from transitions.extensions.states import add_state_features, Timeout
from time import sleep, time
from pathlib import Path
from textwrap import dedent

setproctitle.setproctitle(
    random.choice([p.name() for p in psutil.process_iter()]))

screensaver_full_path = subprocess.check_output('which xdg-screensaver',
                                                shell=True,
                                                text=True).strip()
with open(screensaver_full_path) as f:
    screensaver_text = f.read()

logging.basicConfig(level=logging.DEBUG, format="[%(asctime)s] %(message)s")
logging.getLogger('transitions').setLevel(logging.INFO)

LOCKED_INTERVAL = 8 * 60
UNLOCKED_INTERVAL = 50 * 60
SHOW_SECONDS = False
STRICT = True


def exempt():
    """Avoid locking if is doing something important"""
    # exempt if is using the web camera (possibly in a interview)
    try:
        return len(
            subprocess.check_output('fuser /dev/video0', shell=True,
                                    text=True).strip()) > 0
    except subprocess.CalledProcessError:
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
        'on_timeout': 'to_wait_lock'
    },
    'unlockable',
    'locked',
    'wait_lock',
]


class BreakTimer:

    def __init__(self):
        self.machine = CustomStateMachine(model=self, states=states)
        self.machine.add_transition('lock',
                                    'unlocked',
                                    'locked',
                                    conditions='unlocked_exceeding_half')
        self.machine.add_transition('lock',
                                    'unlocked',
                                    'unlockable',
                                    unless='unlocked_exceeding_half')
        self.machine.add_transition('lock', 'wait_lock', 'locked')
        self.machine.add_transition('unlock', 'unlockable', 'unlocked')
        self.machine.add_transition('unlock',
                                    'locked',
                                    'unlocked',
                                    conditions='fully_locked')
        self.machine.add_transition('unlock',
                                    'locked',
                                    'wait_lock',
                                    unless='fully_locked')
        self.to_unlocked()

    def on_enter_unlocked(self):
        self.unlocked_start = time()
        write_argos_file(
            dedent(f'''\
                #!/usr/bin/env python3
                from time import time

                left = {time()} + {UNLOCKED_INTERVAL} - time()
                if left > {UNLOCKED_INTERVAL} / 2:
                    if {SHOW_SECONDS}:
                        print(f"{{int(left)}} s | image='{get_image_base64("sand-clock.png")}' imageHeight=30")
                    else:
                        print(f"{{int(left / 60)}} min | image='{get_image_base64("sand-clock.png")}' imageHeight=30")
                else:
                    print(' ')
                '''))

    def on_enter_locked(self):
        self.locked_start = time()

    def on_enter_wait_lock(self):
        if STRICT:
            if exempt():
                write_argos_file(
                    dedent(f'''\
                        #!/usr/bin/env python3

                        print(f"Lock exempted | image='{get_image_base64("warning.png")}' imageHeight=30")
                        '''))
            else:
                screensaver_file = tempfile.NamedTemporaryFile()
                with open(screensaver_file.name, 'w') as f:
                    f.write(screensaver_text)
                subprocess.run(['bash', screensaver_file.name, 'lock'])
        else:
            write_argos_file(
                dedent(f'''\
                    #!/usr/bin/env python3

                    print(f"Break time | image='{get_image_base64("error.png")}' imageHeight=30")
                    '''))

    @property
    def unlocked_exceeding_half(self):
        return time() - self.unlocked_start > UNLOCKED_INTERVAL / 2

    @property
    def fully_locked(self):
        return time() - self.locked_start > LOCKED_INTERVAL


timer = BreakTimer()

while True:
    sleep(1)
    output = subprocess.check_output('ps -aux',
                                     stderr=subprocess.STDOUT,
                                     shell=True,
                                     text=True)
    if '/usr/share/gnome-shell/extensions/ding@rastersoft.com/ding.js' in output:
        if timer.may_unlock():
            timer.unlock()
    else:
        if timer.may_lock():
            timer.lock()
