#!/usr/bin/env python3

import uuid
import shutil
import subprocess
from pathlib import Path

source_file = str(Path(__file__).parent / 'run.py')
target_file = f'/tmp/{str(uuid.uuid4())}'
shutil.copyfile(source_file, target_file)

subprocess.Popen(['python', target_file])
