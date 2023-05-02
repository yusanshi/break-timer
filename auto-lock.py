#!/usr/bin/env python3

import subprocess
import os
import base64
import stat

from transitions import Machine
from transitions.extensions.states import add_state_features, Timeout
from time import sleep, time
from pathlib import Path
import logging

logging.basicConfig(level=logging.DEBUG, format="[%(asctime)s] %(message)s")
logging.getLogger('transitions').setLevel(logging.INFO)

LOCKED_INTERVAL = 8 * 60
UNLOCKED_INTERVAL = 50 * 60
SHOW_SECONDS = False

argos_file = Path(os.path.expanduser('~/.config/argos/auto-lock.1s.py'))


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


def get_image_base64(filename):
    with open(Path(__file__).parent / 'image' / filename, 'rb') as f:
        return base64.b64encode(f.read()).decode()


class AutoLocker:

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
        with open(argos_file, 'w') as f:
            f.write(f'''#!/usr/bin/env python3
from time import time

left = {time()} + {UNLOCKED_INTERVAL} - time()
if left > {UNLOCKED_INTERVAL} / 2:
    if {SHOW_SECONDS}:
        print(f"{{int(left)}} s | image='{get_image_base64("sand-clock.png")}' imageHeight=30")
    else:
        print(f"{{int(left / 60)}} min | image='{get_image_base64("sand-clock.png")}' imageHeight=30")
else:
    print(' ')
    ''')

        argos_file.chmod(argos_file.stat().st_mode | stat.S_IEXEC)

    def on_enter_locked(self):
        self.locked_start = time()

    def on_enter_wait_lock(self):
        with open(argos_file, 'w') as f:
            f.write(f'''#!/usr/bin/env python3
if int(time()) % 2 == 0:
    print(f"Break time | image='{get_image_base64("error.png")}' imageHeight=30")
else:
    print(' ')
''')
        argos_file.chmod(argos_file.stat().st_mode | stat.S_IEXEC)

    @property
    def unlocked_exceeding_half(self):
        return time() - self.unlocked_start > UNLOCKED_INTERVAL / 2

    @property
    def fully_locked(self):
        return time() - self.locked_start > LOCKED_INTERVAL


locker = AutoLocker()

while True:
    sleep(1)
    output = subprocess.check_output('ps -aux',
                                     stderr=subprocess.STDOUT,
                                     shell=True,
                                     text=True)
    if '/usr/share/gnome-shell/extensions/ding@rastersoft.com/ding.js' in output:
        if locker.may_unlock():
            locker.unlock()
    else:
        if locker.may_lock():
            locker.lock()
