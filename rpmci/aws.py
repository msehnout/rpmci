import subprocess
import time

import boto3
import contextlib
import json
import logging
import os

from pathlib import Path
from typing import Union, Tuple

import rpmci.cloudinit
import rpmci.rpm
import rpmci.ssh

from rpmci.instance import Instance


def _log_aws_create_artifact(msg: str):
    """Inform the user about creating an artifact in AWS which could potentially cost money if leaked.

    The leak can occur really easily e.g. when Jenkins running rpmci kills the job while still running. If killed
    using SIGKILL the cleanup code won't run at all and the user needs to do the cleanup manually.
    """
    logging.info(f"🚀 Creating artifact in AWS: {msg}")


def _log_aws_delete_artifact(msg: str):
    """Inform the user that an artifact has been successfully deleted from AWS."""
    logging.info(f"🧹 Deleting artifact in AWS: {msg}")


class AWSSession:
    def __init__(self, access_key_id: str, secret_access_key: str, bucket_name: str, region_name: str, cache_dir: str,
                 test_id: str):
        """

        Parameters
        ----------
        access_key_id
        secret_access_key
        region_name
        bucket_name
        cache_dir
        test_id is a string used when creating CI artifacts, this is provided by the caller
        """
        logging.info("Creating AWS session")
        self.session: boto3.Session = boto3.session.Session(
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=region_name
        )
        self.cache_dir: str = cache_dir
        self.bucket_name: str = bucket_name
        self.test_id: str = test_id
        self.priv_key_file: Union[Path, None] = None
        self.sg_name: Union[str, None] = None
        self.ec2_keypair_name: Union[str, None] = None

    @contextlib.contextmanager
    def _ephemeral_ec2_keypair(self) -> Tuple[Path, Path]:
        """Create a new SSH keypair locally and upload it to AWS EC2 for usage in the VMs."""
        self.ec2_keypair_name = f"rpmci-keypair-{self.test_id}"
        ec2 = self.session.resource("ec2")
        with rpmci.ssh.ssh_keys(self.cache_dir) as (private_key, public_key):
            with open(public_key, "rb") as pk:
                _log_aws_create_artifact(f"keypair {self.ec2_keypair_name}")
                ec2.import_key_pair(KeyName=self.ec2_keypair_name,
                                    PublicKeyMaterial=pk.read())
                self.priv_key_file = private_key
            try:
                yield private_key, public_key
            finally:
                _log_aws_delete_artifact(f"keypair {self.ec2_keypair_name}")
                key_pair = ec2.KeyPair(self.ec2_keypair_name)
                key_pair.delete()

    @contextlib.contextmanager
    def _s3_repository(self, directory: str) -> str:
        """Upload RPMs to S3 and provide them using the S3 built-in file serving functionality."""
        logging.info(f"Uploading files to the {self.bucket_name} bucket")
        s3 = self.session.resource("s3")
        # IMPORTANT NOTE: the bucket must have public access enabled and "static website" enabled
        bucket_name = self.bucket_name
        bucket = s3.Bucket(bucket_name)
        # "Directory" inside the bucket
        key = f"rpmci-repo-{self.test_id}"
        _log_aws_create_artifact(f"RPM repository in {key} S3 bucket")
        objects = []
        for root, dirs, files in os.walk(directory):
            for file in files:
                abspath = f"{root}/{file}"
                relpath = os.path.relpath(abspath, directory)  # relative to the cache directory
                logging.info(f"Uploading to S3: {relpath}")
                # NOTE: Skip this to speed up development and save money for bandwidth
                bucket.upload_file(Filename=abspath, Key=f"{key}/{relpath}", ExtraArgs={'ACL': 'public-read'})
                objects += [{"Key": f"{key}/{relpath}"}]
        try:
            yield f"https://{bucket_name}.s3.{self.session.region_name}.amazonaws.com/{key}/"
        finally:
            # Remove the repo
            _log_aws_delete_artifact(f"RPM repository in {key} S3 bucket")
            bucket.delete_objects(
                Delete={
                    "Objects": objects,
                    "Quiet": False
                }
            )

    @contextlib.contextmanager
    def _ec2_security_group(self) -> str:
        """Create an ephemeral security group for the test run."""
        name = f"rpmci-sg-{self.test_id}"
        _log_aws_create_artifact(f"EC2 security group {name}")
        ec2 = self.session.resource("ec2")
        sg = ec2.create_security_group(GroupName=name, Description="rpmci security group")
        sg.authorize_ingress(CidrIp="0.0.0.0/0", FromPort=22, ToPort=22, IpProtocol="tcp")
        self.sg_name = name
        try:
            yield name
        finally:
            _log_aws_delete_artifact(f"EC2 security group {name}")
            sg.delete()

    @contextlib.contextmanager
    def _ec2_instance(self, user_data: str, instance_id: str) -> Instance:
        """Run an instance in EC2 and configure it using the cloud-init file."""
        _log_aws_create_artifact("EC2 instance")
        ec2 = self.session.resource("ec2")
        instances = ec2.create_instances(ImageId="ami-02e7bb5cea59dbbd8",  # FIXME: dynamically find this id
                                         KeyName=self.ec2_keypair_name,
                                         MinCount=1,
                                         MaxCount=1,
                                         InstanceType='t2.micro', # TODO: make this configurable
                                         # TODO: bigger machine for target because of disk images
                                         SecurityGroups=[self.sg_name],
                                         UserData=user_data)
        instances[0].wait_until_running()
        instance = ec2.Instance(id=instances[0].id)
        for _ in range(20):
            cmd = [
                "ssh", f"admin@{instance.public_ip_address}",
                # TODO: refactor into the ssh module
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                "-o", "ConnectTimeout=20",
                "-i", self.priv_key_file,
                "systemctl is-system-running"
            ]
            logging.info(f"SSH attempt: admin@{instance.public_ip_address}")
            sp = subprocess.run(cmd)
            if sp.returncode == 0:
                logging.info("SSH success")
                break
            time.sleep(20)
        else:
            raise RuntimeError("Failed to boot AWS instance")
        try:
            yield Instance(instance_id, instance.public_ip_address, 22)
        finally:
            _log_aws_delete_artifact("EC2 instance")
            instance.terminate()
            instance.wait_until_terminated()

    @staticmethod
    def _prepare_vms(test_instance_ip, target_instance_ip, private_key):
        """Well, this is just an unfortunate hack to enable the ssh_configs work in EC2.

        The problem here is that the ssh_config comes as part of the cloud-init configuration and we simply don't know
        the IP ahead of time. So `sed` for rescue :o).

        If we drop the configuration in target VM, we can actually generate a correct ssh_config for the test VM and
        drop this hack completely.
        """
        for instance in [test_instance_ip, target_instance_ip]:
            rpmci.ssh.ssh_run_command("admin", instance, 22, private_key,
                                      f"sudo sed -i 's|TESTVM|{test_instance_ip}|' /etc/ssh/ssh_config")
            rpmci.ssh.ssh_run_command("admin", instance, 22, private_key,
                                      f"sudo sed -i 's|TARGETVM|{target_instance_ip}|' /etc/ssh/ssh_config")

    def run(self, config, cache_dir):
        logging.info("Running rpmci in AWS")
        test_id = "test_id"
        repodir = rpmci.rpm.copy_rpms_to_cache(config.rpms, cache_dir)
        with self._ephemeral_ec2_keypair() as (private_key, public_key):
            with self._s3_repository(repodir) as s3repo_url:
                user_data_str = rpmci.cloudinit.write_userdata_str(public_key, private_key, s3repo_url, {
                    "testvm": {
                        # TODO: change from ip to hostname
                        # TODO: generate domain name of the machines ahead of their creation
                        # TODO: Or fill it in with dummy data and then run sed to replace it once it boots
                        "ip": "TESTVM",
                        "port": "22"
                    },
                    "targetvm": {
                        "ip": "TARGETVM",
                        "port": "22"
                    }
                })
                with self._ec2_security_group() as ec2sg:
                    with self._ec2_instance(user_data_str, "testvm") as test_instance:
                        with self._ec2_instance(user_data_str, "targetvm") as target_instance:
                            AWSSession._prepare_vms(test_instance.ip, target_instance.ip, private_key)
                            # Install RPMs specified in the configuration
                            logging.info("Running dnf install in test VM")
                            rpmci.ssh.ssh_run_command("admin", test_instance.ip, 22, private_key,
                                                      f"sudo dnf install {config.test_rpm} -y")
                            logging.info("Running dnf install in target VM")
                            rpmci.ssh.ssh_run_command("admin", target_instance.ip, 22, private_key,
                                                      f"sudo dnf install {config.target_rpm} -y")
                            logging.info("Running rpmci-setup")
                            rpmci.ssh.ssh_run_command("admin", test_instance.ip, 22, private_key, config.rpmci_setup)
                            # Iterate over all files in the tests directory
                            logging.info(f"Running integration test {config.test_script}")
                            # TODO: we need to change this because the test cases will not simply work in the target <-
                            # TODO: -> test scenario
                            rpmci.ssh.ssh_run_command("admin", test_instance.ip, 22, private_key,
                                                      f"sudo {config.test_script}")

