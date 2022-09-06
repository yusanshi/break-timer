#!/usr/bin/env python3

import logging
import os
import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from subprocess import check_output
from time import sleep, time

import setproctitle

setproctitle.setproctitle(str(uuid.uuid4()))

UNLOCKED_INTERVAL = 40 * 60
LOCKED_INTERVAL = 10 * 60
SHOW_SECONDS = False


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
    os.system('xdg-screensaver lock')


def set_timer(start):
    with open(os.path.expanduser('~/.config/argos/auto-lock-indicator.1s.py'),
              'w') as f:
        f.write(f'''#!/usr/bin/env python3
from time import time

left = {start} + {UNLOCKED_INTERVAL} - time()
if left > 1200:
    if {SHOW_SECONDS}:
        print(f"{{int(left)}} s | iconName=system-lock-screen")
    else:
        print(f"{{int(left / 60)}} min | iconName=system-lock-screen")
else:
    print('| iconName=system-lock-screen')

''')


log_dir = Path(__file__).parent / 'log'
log_dir.mkdir(exist_ok=True)
log_file = log_dir / f'{datetime.now().replace(microsecond=0).isoformat()}.txt'


class MyLoggingHandler(logging.Handler):

    def emit(self, record):
        try:
            msg = self.format(record)
            print(msg)
            with open(log_file, 'a') as f:
                f.write(msg + '\n')
            self.flush()
        except Exception:
            self.handleError(record)


logging.basicConfig(level=logging.INFO,
                    format="[%(asctime)s] %(message)s",
                    handlers=[MyLoggingHandler()])

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
        set_timer(start)

    if current == State.locked:
        logging.info('Locking')
        lock()
