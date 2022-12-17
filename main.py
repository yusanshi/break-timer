#!/usr/bin/env python3

import logging
import os
import random
import subprocess
from datetime import datetime
from enum import Enum
from pathlib import Path
from time import sleep, time
import tempfile

from pathlib import Path
import stat

import psutil
import setproctitle

setproctitle.setproctitle(
    random.choice([p.name() for p in psutil.process_iter()]))

LOCKED_INTERVAL = 10 * 60
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


screensaver_full_path = subprocess.check_output('which xdg-screensaver',
                                                shell=True,
                                                text=True).strip()

with open(screensaver_full_path) as f:
    screensaver_text = f.read()


def lock():
    tmp = tempfile.NamedTemporaryFile()
    with open(tmp.name, 'w') as f:
        f.write(screensaver_text)
    subprocess.run(['bash', tmp.name, 'lock'])


def set_timer(start):
    file = Path(
        os.path.expanduser('~/.config/argos/auto-lock-indicator.1s.py'))
    with open(file, 'w') as f:
        f.write(f'''#!/usr/bin/env python3
from time import time

left = {start} + {UNLOCKED_INTERVAL} - time()
if left > {UNLOCKED_INTERVAL} / 2:
    if {SHOW_SECONDS}:
        print(f"{{int(left)}} s | iconName=system-lock-screen")
    else:
        print(f"{{int(left / 60)}} min | iconName=system-lock-screen")
else:
    print('| iconName=system-lock-screen')

''')

    file.chmod(file.stat().st_mode | stat.S_IEXEC)


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

    UNLOCKED_INTERVAL = 50 * 60

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

    if current == State.locked:
        logging.info('Locking')
        lock()
        if get_state() != State.locked:
            logging.info('Error: Locking failed')
