#!/usr/bin/env pythonw
# run `shell:startup` and put shortcut of this file into it

import subprocess
import sys
from datetime import datetime
from time import sleep


def run_silent(command):
    subprocess.run(command, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == '__main__':
    while True:
        sleep(1)
        now = datetime.now()
        combined = now.hour + now.minute / 60 + now.second / 3600
        intervals = [(0, 7)]
        if any([start <= combined <= end for start, end in intervals]):
            print(f'[{now}] Current time {combined:.4f} is in target interval')
            run_silent('shutdown /s')
            break
        else:
            print(f'[{now}] Current time {combined:.4f} not in target interval')
