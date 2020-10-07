"""rpmrepo - Push RPM Repository

This module implements the functions that push local RPM repository
snapshots to configured remote storage.
"""

# pylint: disable=duplicate-code,invalid-name,too-few-public-methods

import contextlib
import os
import subprocess

from . import util


class Push(contextlib.AbstractContextManager):
    """Push RPM repository"""

    def __init__(self, cache):
        self._cache = cache
        self._path_conf = os.path.join(cache, "conf")
        self._path_data = os.path.join(cache, "index/data")
        self._path_snapshot = os.path.join(cache, "index/snapshot")

    def __exit__(self, exc_type, exc_value, exc_tb):
        pass

    def push(self):
        """Run operation"""

        #
        # We require a repository to be imported and indexed before we can push
        # it out to remote storage.
        #

        assert os.access(os.path.join(self._path_conf, "index.ok"), os.R_OK)
