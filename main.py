#!/usr/bin/env python3

from enum import Enum
from time import sleep, time
from datetime import datetime
from subprocess import check_output
from pathlib import Path
import os
import logging

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    handlers=[
        logging.FileHandler(
            Path(__file__).parent / 'log' /
            f'{datetime.now().replace(microsecond=0).isoformat()}.txt'),
        logging.StreamHandler()
    ])

UNLOCKED_INTERVAL = 40 * 60
LOCKED_INTERVAL = 10 * 60
SHOW_SECONDS = True


class State(Enum):
    unlocked = 1
    locked = 2
    unlockable = 3


def get_state():
    output = check_output('gnome-screensaver-command -q',
                          shell=True,
                          text=True)
    return State.unlocked if 'is inactive' in output else State.locked


def lock():
    check_output('xdg-screensaver lock', shell=True)


def set_indicator(start):
    with open(os.path.expanduser('~/.config/argos/auto-lock-indicator.1s.py'),
              'w') as f:
        f.write(f'''#!/usr/bin/env python3
from time import time
left = {start} + {UNLOCKED_INTERVAL} - time()
if {SHOW_SECONDS}:
    print(f"{{int(left)}} s | iconName=system-lock-screen")
else:
    print(f"{{int(left / 60)}} min | iconName=system-lock-screen")
''')


current = State.unlockable
logging.info('Begin running')

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
    if int(time()) % 10 == 0:
        logging.info(f'{current = }, {actual = }')
    if current == State.unlocked and (time() - start > UNLOCKED_INTERVAL
                                      or actual == State.locked):
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
        set_indicator(start)

    if current == State.locked:
        logging.info('Locking')
        lock()
