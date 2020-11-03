import json
import logging
from dataclasses import dataclass

import rpmci.aws

@dataclass
class Cfg:
    rpms: str
    test_rpm: str
    target_rpm: str
    rpmci_setup: str
    test_script: str


logging.basicConfig(level=logging.INFO)

cache_dir = "../rpmciconfig/cache/"
cfg = Cfg(rpms="../rpmciconfig/rpms",
    test_rpm="osbuild-composer-tests",
    target_rpm="osbuild-composer",
    test_script="/usr/libexec/tests/osbuild-composer/base_tests.sh",
    rpmci_setup="/usr/libexec/osbuild-composer-test/rpmci-setup")

with open("../rpmciconfig/aws.json", "r") as f:
    aws_creds = json.load(f)

aws = rpmci.aws.AWSSession(
    access_key_id=aws_creds["aws_access_key_id"],
    secret_access_key=aws_creds["aws_secret_access_key"],
    bucket_name="msehnout",
    region_name=aws_creds["region_name"],
    cache_dir="../rpmciconfig/cache/",
    test_id="manual-test-run-nov-3"
)

aws.run(cfg, cache_dir)