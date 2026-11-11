import os
import sys
import subprocess
import unittest
import tempfile
import time
from pathlib import Path
from src.process_runner import run_worker


class ProcessRunnerTest(unittest.TestCase):
    def test_stdout_and_timeout(self):
        done = run_worker([sys.executable, '-c', 'print("ok")'], payload='', cwd=None, timeout=5, env=os.environ.copy())
        self.assertEqual(done.stdout.strip(), 'ok')
        with self.assertRaises(subprocess.TimeoutExpired):
            run_worker([sys.executable, '-c', 'import time; time.sleep(30)'], payload='', cwd=None, timeout=.3, env=os.environ.copy())

    def test_timeout_stops_spawned_child(self):
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder)/'child_finished'
            child = 'import pathlib,time; time.sleep(2); pathlib.Path(%r).write_text("alive")' % str(marker)
            parent = 'import subprocess,sys,time; subprocess.Popen([sys.executable,"-c",%r]); time.sleep(30)' % child
            with self.assertRaises(subprocess.TimeoutExpired):
                run_worker([sys.executable, '-c', parent], payload='', cwd=None, timeout=.8, env=os.environ.copy())
            time.sleep(2.5)
            self.assertFalse(marker.exists())
