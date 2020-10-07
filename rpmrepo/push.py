"""rpmrepo - Push RPM Repository

This module implements the functions that push local RPM repository
snapshots to configured remote storage.
"""

# pylint: disable=duplicate-code,invalid-name,too-few-public-methods

import contextlib
import boto3
import os
import subprocess

from . import util


class Push(contextlib.AbstractContextManager):
    """Push RPM repository"""

    def __init__(
        self,
        cache,
        platform_id,
        snapshot_id,
        aws_access_key_id,
        aws_secret_access_key,
    ):
        self._aws_access_key_id = aws_access_key_id
        self._aws_secret_access_key = aws_secret_access_key
        self._cache = cache
        self._path_conf = os.path.join(cache, "conf")
        self._path_data = os.path.join(cache, "index/data")
        self._path_snapshot = os.path.join(cache, "index/snapshot")
        self._platform_id = platform_id
        self._snapshot_id = snapshot_id

    def __exit__(self, exc_type, exc_value, exc_tb):
        pass

    def _push_snapshot(self):
        s3c = boto3.client(
            "s3",
            aws_access_key_id=self._aws_access_key_id,
            aws_secret_access_key=self._aws_secret_access_key,
        )

        n_total = 0
        for _, _, entries in os.walk(self._path_snapshot):
            for entry in entries:
                n_total += 1

        i_total = 0
        for level, subdirs, entries in os.walk(self._path_snapshot):
            levelpath = os.path.relpath(level, self._path_snapshot)
            if levelpath == ".":
                snapshotpath = os.path.join(self._snapshot_id)
            else:
                snapshotpath = os.path.join(self._snapshot_id, levelpath)

            for entry in entries:
                i_total += 1

                with open(os.path.join(level, entry), "rb") as filp:
                    checksum = filp.read().decode()

                print(f"[{i_total}/{n_total}] '{snapshotpath}/{entry}' -> {checksum}")

                s3c.put_object(
                    ACL="public-read",
                    Body=b"",
                    Bucket="rpmci",
                    Key=f"data/ref/snapshot/{snapshotpath}/{entry}",
                    Metadata={"rpmci-checksum": checksum},
                )

    def push(self):
        """Run operation"""

        #
        # We require a repository to be imported and indexed before we can push
        # it out to remote storage.
        #

        assert os.access(os.path.join(self._path_conf, "index.ok"), os.R_OK)

        self._push_snapshot()
