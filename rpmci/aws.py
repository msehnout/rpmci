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

    @contextlib.contextmanager
    def ephemeral_ec2_keypair(self, key_pair_name: str) -> Tuple[Path, Path]:
        logging.info("Creating ephemeral keypair in EC2")
        ec2 = self.session.resource("ec2")
        with rpmci.ssh.ssh_keys(self.cache_dir) as (private_key, public_key):
            with open(public_key, "rb") as pk:
                logging.info(f"Importing {key_pair_name} key pair to EC2")
                ec2.import_key_pair(KeyName=key_pair_name,
                                    PublicKeyMaterial=pk.read())
                self.priv_key_file = private_key
            try:
                yield private_key, public_key
            finally:
                logging.info(f"Deleting {key_pair_name} keypair from EC2")
                key_pair = ec2.KeyPair(key_pair_name)
                key_pair.delete()

    @contextlib.contextmanager
    def s3_repository(self, directory: str) -> str:
        """Upload RPMs to S3 and provide them."""
        logging.info("Uploading files to the bucket")
        s3 = self.session.resource("s3")
        # IMPORTANT NOTE: the bucket must have public access enabled and "static website" enabled
        bucket_name = self.bucket_name
        bucket = s3.Bucket(bucket_name)
        # "Directory" inside the bucket
        key = f"rpmci-repo-{self.test_id}"
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
            logging.info("Removing repo from S3")
            bucket.delete_objects(
                Delete={
                    "Objects": objects,
                    "Quiet": False
                }
            )

    @contextlib.contextmanager
    def ec2_security_group(self) -> str:
        """Create an ephemeral security group for the test run."""
        logging.info("Creating EC2 security group")
        ec2 = self.session.resource("ec2")
        name = f"rpmci-sg-{self.test_id}"
        sg = ec2.create_security_group(GroupName=name, Description="rpmci security group")
        sg.authorize_ingress(CidrIp="0.0.0.0/0", FromPort=22, ToPort=22, IpProtocol="tcp")
        self.sg_name = name
        try:
            yield name
        finally:
            # Remove the sg
            logging.info("Deleting security group")
            sg.delete()

    @contextlib.contextmanager
    def ec2_instance(self, user_data: str, instance_id: str) -> str:
        """Run an instance in EC2 and configure it using the cloud-init file."""
        logging.info("Running EC2 instance")
        ec2 = self.session.resource("ec2")
        instances = ec2.create_instances(ImageId="ami-02e7bb5cea59dbbd8",  # FIXME: dynamically find this id
                                         KeyName=f"rpmci-vm-{self.test_id}-{instance_id}",  # FIXME: generate this
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
            yield instance.public_ip_address
        finally:
            # Terminate
            logging.info("Terminating EC2 instance")
            instance.terminate()
            instance.wait_until_terminated()


def create_session(aws_cfg_path: str) -> boto3.session.Session:
    logging.info(f"Loading AWS config: {aws_cfg_path}")
    with open(aws_cfg_path, "r") as f:
        creds = json.load(f)

    logging.info("Creating AWS session")
    return boto3.session.Session(
        aws_access_key_id=creds["aws_access_key_id"],
        aws_secret_access_key=creds["aws_secret_access_key"],
        region_name=creds["region_name"]
    )


@contextlib.contextmanager
def ec2_keypair(ec2, cache_dir):
    # TODO: take as a parameter
    key_pair_name = "rpmci-runner-oct-26-local"
    with rpmci.ssh.ssh_keys(cache_dir) as (private_key, public_key):
        with open(public_key, "rb") as pk:
            logging.info(f"Importing {key_pair_name} key pair to EC2")
            ec2.import_key_pair(KeyName=key_pair_name,
                                PublicKeyMaterial=pk.read())
        try:
            yield private_key, public_key
        finally:
            logging.info(f"Deleting {key_pair_name} key pair from EC2")
            key_pair = ec2.KeyPair(key_pair_name)
            key_pair.delete()


@contextlib.contextmanager
def s3_repository(directory: str, aws_session: boto3.session.Session):
    """Upload RPMs to S3 and provide them."""
    logging.info("Obtaining S3 resource")
    s3 = aws_session.resource("s3")
    # IMPORTANT NOTE: the bucket must have public access enabled and "static website" enabled
    bucket_name = "msehnout"
    bucket = s3.Bucket(bucket_name)
    logging.info("Uploading files to the bucket")
    # "Directory" inside the bucket
    key = "aaabbb"
    objects = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            abspath = f"{root}/{file}"
            relpath = os.path.relpath(abspath, directory)  # relative to the cache directory
            logging.info(f"Uploading to S3: {relpath}")
            # NOTE: Skip this to speed up development and save money for bandwidth
            bucket.upload_file(Filename=abspath, Key=f"{key}/{relpath}", ExtraArgs={'ACL':'public-read'})
            objects += [{"Key": f"{key}/{relpath}"}]
    try:
        yield f"https://{bucket_name}.s3.{aws_session.region_name}.amazonaws.com/{key}/"
    finally:
        # Remove the repo
        logging.info("Removing repo from S3")
        bucket.delete_objects(
            Delete={
                "Objects": objects,
                "Quiet": False
            }
        )


@contextlib.contextmanager
def ec2_security_group(ec2):
    """Create an ephemeral security group for the test run."""
    logging.info("Creating EC2 security group")
    name = "rpmci-runner-sg"
    sg = ec2.create_security_group(GroupName=name, Description="rpmci security group test")
    sg.authorize_ingress(CidrIp="0.0.0.0/0", FromPort=22, ToPort=22, IpProtocol="tcp")
    try:
        yield name
    finally:
        # Remove the sg
        logging.info("Deleting security group")
        sg.delete()


@contextlib.contextmanager
def ec2_instance(ec2, security_group, user_data, priv_key_file):
    """Run an instance in EC2 and configure it using the cloud-init file."""
    logging.info("Running EC2 instance")
    instances = ec2.create_instances(ImageId="ami-02e7bb5cea59dbbd8",  # FIXME: dynamically find this id
                                     KeyName='rpmci-runner-test-1',  # FIXME: generate this
                                     MinCount=1,
                                     MaxCount=1,
                                     InstanceType='t2.micro',   # TODO: bigger machine for target because of disk images
                                     SecurityGroups=[security_group],
                                     UserData=user_data)
    instances[0].wait_until_running()
    instance = ec2.Instance(id=instances[0].id)
    for _ in range(20):
        # TODO: different log type
        cmd = [
            "ssh", f"admin@{instance.public_ip_address}",
            # TODO: refactor into the ssh module
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "ConnectTimeout=20",
            "-i", priv_key_file,
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
        yield instance.public_ip_address
    finally:
        # Terminate
        logging.info("Terminating EC2 instance")
        instance.terminate()
        instance.wait_until_terminated()


def prepare_vms(test_instance_ip, target_instance_ip, private_key):
    for instance in [test_instance_ip, target_instance_ip]:
        rpmci.ssh.ssh_run_command("admin", instance, 22, private_key,
                                  f"sudo sed -i 's|TESTVM|{test_instance_ip}|' /etc/ssh/ssh_config")
        rpmci.ssh.ssh_run_command("admin", instance, 22, private_key,
                                  f"sudo sed -i 's|TARGETVM|{target_instance_ip}|' /etc/ssh/ssh_config")


def run_test_2(config, cache_dir, aws_cfg_path):
    test_id = "test_id"
    aws_session = AWSSession("access key"
                             "secret key",
                             "bucket",
                             "eu-central-1",
                             cache_dir,
                             test_id)
    repodir = rpmci.rpm.copy_rpms_to_cache(config.rpms, cache_dir)
    with aws_session.ephemeral_ec2_keypair(test_id) as (private_key, public_key):
        with aws_session.s3_repository(repodir) as s3repo_url:
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
            with aws_session.ec2_security_group() as ec2sg:
                with aws_session.ec2_instance(user_data_str, "testvm") as test_instance_ip:
                    with aws_session.ec2_instance(user_data_str, "targetvm") as target_instance_ip:
                        prepare_vms(test_instance_ip, target_instance_ip, private_key)
                        # Install RPMs specified in the configuration
                        logging.info("Running dnf install in test VM")
                        rpmci.ssh.ssh_run_command("admin", test_instance_ip, 22, private_key,
                                                  f"sudo dnf install {config.test_rpm} -y")
                        logging.info("Running dnf install in target VM")
                        rpmci.ssh.ssh_run_command("admin", target_instance_ip, 22, private_key,
                                                  f"sudo dnf install {config.target_rpm} -y")
                        logging.info("Running rpmci-setup")
                        rpmci.ssh.ssh_run_command("admin", test_instance_ip, 22, private_key, config.rpmci_setup)
                        # Iterate over all files in the tests directory
                        logging.info(f"Running all integration tests in {config.tests_directory}")
                        rpmci.ssh.ssh_run_command("admin", test_instance_ip, 22, private_key,
                                                  "sudo find " + config.tests_directory + " -type f -exec sudo {} \\;")


def run_test(config, cache_dir, aws_cfg_path):
    # Load credentials
    aws_session = create_session(aws_cfg_path)
    ec2 = aws_session.resource("ec2")
    repodir = rpmci.rpm.copy_rpms_to_cache(config.rpms, cache_dir)
    # Upload the RPMs to S3
    with ec2_keypair(ec2, cache_dir) as (private_key, public_key):
        with s3_repository(repodir, aws_session) as s3repo_url:
            # Create cloud init
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
            with ec2_security_group(ec2) as ec2sg:
                with ec2_instance(ec2, ec2sg, user_data_str, private_key) as test_instance_ip:
                    with ec2_instance(ec2, ec2sg, user_data_str, private_key) as target_instance_ip:
                        logging.info("RUUUUUUN!")
                        # TODO: run setup and tests
                        for instance in [test_instance_ip, target_instance_ip]:
                            rpmci.ssh.ssh_run_command("admin", instance, 22, private_key,
                                                      f"sudo sed -i 's|TESTVM|{test_instance_ip}|' /etc/ssh/ssh_config")
                            rpmci.ssh.ssh_run_command("admin", instance, 22, private_key,
                                                      f"sudo sed -i 's|TARGETVM|{target_instance_ip}|' /etc/ssh/ssh_config")
                            # Install RPMs specified in the configuration
                            logging.info("Running dnf install in test VM")
                            rpmci.ssh.ssh_run_command("admin", test_instance_ip, 22, private_key,
                                                      f"sudo dnf install {config.test_rpm} -y")
                            logging.info("Running dnf install in target VM")
                            rpmci.ssh.ssh_run_command("admin", target_instance_ip, 22, private_key,
                                                      f"sudo dnf install {config.target_rpm} -y")
                            logging.info("Running rpmci-setup")
                            rpmci.ssh.ssh_run_command("admin", test_instance_ip, 22, private_key, config.rpmci_setup)
                            # Iterate over all files in the tests directory
                            logging.info(f"Running all integration tests in {config.tests_directory}")
                            rpmci.ssh.ssh_run_command("admin", test_instance_ip, 22, private_key,
                                                      "sudo find " + config.tests_directory + " -type f -exec sudo {} \\;")
