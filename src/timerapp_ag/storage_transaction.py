"""Cross-process lock and atomic durable JSON writes for the shared data file."""
from contextlib import contextmanager
import os
from pathlib import Path
import tempfile
import threading
import time

_mutex = threading.RLock()
_locks = {}

@contextmanager
def transaction(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _mutex:
        lock = _locks.setdefault(str(path), threading.RLock())
    with lock:
        handle = open(str(path) + '.sync-lock', 'a+b')
        try:
            if os.name == 'nt':
                import msvcrt
                handle.seek(0); handle.write(b'0'); handle.flush(); handle.seek(0)
                deadline = time.monotonic() + 10
                while True:
                    try:
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1); break
                    except OSError:
                        if time.monotonic() >= deadline: raise TimeoutError('Хранилище занято другим процессом')
                        time.sleep(.05)
            else:
                import fcntl
                deadline = time.monotonic() + 10
                while True:
                    try:
                        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB); break
                    except BlockingIOError:
                        if time.monotonic() >= deadline: raise TimeoutError('Хранилище занято другим процессом')
                        time.sleep(.05)
            yield
        finally:
            if os.name == 'nt':
                import msvcrt
                handle.seek(0)
                try: msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError: pass
            handle.close()


def atomic_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            handle.write(text); handle.flush(); os.fsync(handle.fileno())
        os.replace(name, path)
        if os.name != 'nt':
            fd = os.open(path.parent, os.O_RDONLY)
            try: os.fsync(fd)
            finally: os.close(fd)
    finally:
        if os.path.exists(name): os.unlink(name)
