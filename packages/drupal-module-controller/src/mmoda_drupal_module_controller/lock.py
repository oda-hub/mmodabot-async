import fcntl
import os
from contextlib import contextmanager

LOCK_FILE = "/tmp/drush.lock"


@contextmanager
def drush_lock():
    fd = os.open(LOCK_FILE, os.O_CREAT | os.O_RDWR)

    try:
        # blocking lock (wait until available)
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)