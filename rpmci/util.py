"""rpmci/util - Utility Helpers

The `util` module provides basic utility helpers that extend the python
standard library. Each set of helpers is self-contained and documented as an
entity. They are meant to augment other libraries where they lack in features.
"""

# pylint: disable=invalid-name,too-few-public-methods

import contextlib
import signal
import subprocess


@contextlib.contextmanager
def manage_process(proc, *, timeout=0):
    """Context-manager for subprocesses

    This opens a context for the given process @proc. It yields the process
    object back to the caller. Once the context is exited, this manager takes
    care to terminate the process. By default, the process is forcibly
    terminated. If the timeout is set to anything but 0, a graceful termination
    is attempted for that period in blocking mode.
    """

    try:
        yield proc
    finally:
        if proc.poll() is None:
            if timeout == 0:
                proc.send_signal(signal.SIGKILL)
            else:
                try:
                    proc.terminate()
                    proc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    proc.send_signal(signal.SIGKILL)
