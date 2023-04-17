#!/usr/bin/env python3

import logging
import os
import stat
import subprocess

from enum import Enum
from pathlib import Path
from time import sleep, time

argos_file = Path(
    os.path.expanduser('~/.config/argos/auto-lock-non-strict.1s.py'))

LOCKED_INTERVAL = 8 * 60
UNLOCKED_INTERVAL = 50 * 60
SHOW_SECONDS = False


class State(Enum):
    unlocked = 1
    locked = 2
    unlockable = 3


def get_state():
    output = subprocess.check_output('ps -aux',
                                     stderr=subprocess.STDOUT,
                                     shell=True,
                                     text=True)
    return State.unlocked if '/usr/share/gnome-shell/extensions/ding@rastersoft.com/ding.js' in output else State.locked


def set_timer(start):
    with open(argos_file, 'w') as f:
        f.write(f'''#!/usr/bin/env python3
from time import time

left = {start} + {UNLOCKED_INTERVAL} - time()
if left > {UNLOCKED_INTERVAL} / 2:
    if {SHOW_SECONDS}:
        print(f"{{int(left)}} s")
    else:
        print(f"{{int(left / 60)}} min")
elif left > 0:
    print(' ')
elif int(time()) % 2 == 0:
    print(f"Break time | iconName=dialog-warning")
else:
    print(' ')

''')

    argos_file.chmod(argos_file.stat().st_mode | stat.S_IEXEC)


logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")

logging.info('Begin running')
current = State.unlockable

while True:
    sleep(1)
    """
    [unlocked] [locked] [unlockable] [unlocked] [locked] [unlockable] ...

                unlocked  locked  unlockable
    unlocked        -        ✓        x

    locked          x        -        ✓

    unlockable      ✓        x        -
    """

    actual = get_state()
    if int(time()) % 20 == 0:
        logging.info(f'{current = }, {actual = }')
    if current == State.unlocked:
        if time() - start > UNLOCKED_INTERVAL:
            logging.info('Unlocked -> Locked')
            start = time()
            current = State.locked
        elif actual == State.locked:
            if time() - start < UNLOCKED_INTERVAL / 2:
                # manually lock it in early time
                logging.info('Unlocked -> Unlockable')
                current = State.unlockable
            else:
                # manually lock it in late time, lock it!
                logging.info('Unlocked -> Locked')
                start = time()
                current = State.locked
    if current == State.locked and time() - start > LOCKED_INTERVAL:
        logging.info('Locked -> Unlockable')
        current = State.unlockable
    if current == State.unlockable and actual == State.unlocked:
        logging.info('Unlockable -> Unlocked')
        start = time()
        current = State.unlocked
        set_timer(start)
