"""rpmrepo - Push RPM Repository

This module implements the functions that push local RPM repository
snapshots to configured remote storage.
"""

# pylint: disable=duplicate-code,invalid-name,too-few-public-methods

import contextlib
import boto3
import os
import subprocess
import sys

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

    def push_data_s3(self, storage, platform_id, aws_access_key_id, aws_secret_access_key):
        """Push data to S3"""

        assert os.access(os.path.join(self._path_conf, "index.ok"), os.R_OK)

        s3c = boto3.client(
            "s3",
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
        )

        s3args = {}
        if storage == "anon":
            s3args["ACL"] = "public-read"

        n_total = 0
        for _, _, entries in os.walk(self._path_data):
            for entry in entries:
                n_total += 1

        i_total = 0
        for level, _, entries in os.walk(self._path_data):
            levelpath = os.path.relpath(level, self._path_data)
            if levelpath == ".":
                path = platform_id
            else:
                path = os.path.join(platform_id, levelpath)

            for entry in entries:
                i_total += 1

                print(f"[{i_total}/{n_total}] 'data/{storage}/{path}/{entry}'")

                with open(os.path.join(level, entry), "rb") as filp:
                    s3c.upload_fileobj(
                        filp,
                        "rpmci",
                        f"data/{storage}/{path}/{entry}",
                        ExtraArgs=s3args,
                    )

    def push_data_psi(self, platform_id, os_app_cred_id, os_app_cred_secret):
        """Push data to PSI"""

        assert os.access(os.path.join(self._path_conf, "index.ok"), os.R_OK)

        cmd = [
            "swift",
            "upload",
            "rpmci",
            self._path_data,
            "--object-name", f"data/anon/{platform_id}",
        ]

        env = os.environ.copy()
        env["OS_AUTH_URL"] = "https://rhos-d.infra.prod.upshift.rdu2.redhat.com:13000/v3"
        env["OS_AUTH_TYPE"] = "v3applicationcredential"
        env["OS_APPLICATION_CREDENTIAL_ID"] = os_app_cred_id
        env["OS_APPLICATION_CREDENTIAL_SECRET"] = os_app_cred_secret

        sys.stdout.flush()
        proc = subprocess.Popen(cmd, env=env)
        res = proc.wait()
        assert res == 0

    def push_snapshot_s3(self, snapshot_id, aws_access_key_id, aws_secret_access_key):
        """Push snapshot to S3"""

        assert os.access(os.path.join(self._path_conf, "index.ok"), os.R_OK)

        s3c = boto3.client(
            "s3",
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
        )

        n_total = 0
        for _, _, entries in os.walk(self._path_snapshot):
            for entry in entries:
                n_total += 1

        i_total = 0
        for level, subdirs, entries in os.walk(self._path_snapshot):
            levelpath = os.path.relpath(level, self._path_snapshot)
            if levelpath == ".":
                path = os.path.join(snapshot_id)
            else:
                path = os.path.join(snapshot_id, levelpath)

            for entry in entries:
                i_total += 1

                with open(os.path.join(level, entry), "rb") as filp:
                    checksum = filp.read().decode()

                print(f"[{i_total}/{n_total}] '{path}/{entry}' -> {checksum}")

                s3c.put_object(
                    ACL="public-read",
                    Body=b"",
                    Bucket="rpmci",
                    Key=f"data/ref/snapshot/{path}/{entry}",
                    Metadata={"rpmci-checksum": checksum},
                )
