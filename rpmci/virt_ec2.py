import contextlib
import logging
import random
import string
import time
from typing import Union, Any

import boto3

from rpmci.ssh import SshKeys, SshCommand


class VirtEC2(contextlib.AbstractContextManager):
    def __init__(self, access_key_id: str,
                 secret_access_key: str,
                 region_name: str,
                 image_id: str,
                 key_pair: SshKeys,
                 userdata_str: str
                 ):
        logging.info("Creating AWS session")
        self.session: boto3.Session = boto3.session.Session(
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=region_name
        )
        self.ec2 = self.session.resource("ec2")
        self.key_pair: SshKeys = key_pair
        self.userdata_str: str = userdata_str
        # TODO: well known test_id would be better
        self.test_id: Union[str, None] = ''.join(random.choice(string.ascii_lowercase) for i in range(7))
        self.sg_name: Union[str, None] = None
        self.security_group: Union[Any, None] = None
        self.ec2_keypair_name: Union[str, None] = None
        self.image_id: str = image_id
        self.instance: Union[Any, None] = None

    def __enter__(self):
        self._create_ec2_keypair()
        self._create_ec2_security_group()
        self._create_ec2_instance()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._delete_ec2_instance()
        self._delete_ec2_security_group()
        self._delete_ec2_keypair()

    def run(self, args) -> int:
        return SshCommand("admin", f"{self.instance.public_ip_address}", 22, self.key_pair.private_key, " ".join(args),
                          StrictHostKeyChecking="no", UserKnownHostsFile="/dev/null").run()

    def _create_ec2_keypair(self):
        self.ec2_keypair_name = f"rpmci-keypair-{self.test_id}"
        with open(self.key_pair.public_key, "rb") as pk:
            self._log_aws_create_artifact(f"keypair {self.ec2_keypair_name}")
            self.ec2.import_key_pair(KeyName=self.ec2_keypair_name,
                                     PublicKeyMaterial=pk.read())

    def _delete_ec2_keypair(self):
        self._log_aws_delete_artifact(f"keypair {self.ec2_keypair_name}")
        key_pair = self.ec2.KeyPair(self.ec2_keypair_name)
        key_pair.delete()

    def _create_ec2_security_group(self):
        """Create an ephemeral security group for the test run."""
        self.sg_name = f"rpmci-sg-{self.test_id}"
        self._log_aws_create_artifact(f"EC2 security group {self.sg_name}")
        ec2 = self.session.resource("ec2")
        self.security_group = ec2.create_security_group(GroupName=self.sg_name, Description="rpmci security group")
        self.security_group.authorize_ingress(CidrIp="0.0.0.0/0", FromPort=22, ToPort=22, IpProtocol="tcp")

    def _delete_ec2_security_group(self):
        self._log_aws_delete_artifact(f"EC2 security group {self.sg_name}")
        self.security_group.delete()

    def _create_ec2_instance(self):
        """Run an instance in EC2 and configure it using the cloud-init file."""
        self._log_aws_create_artifact("EC2 instance")
        instances = self.ec2.create_instances(ImageId=self.image_id,  # ami-0911ed36164460ba6
                                              KeyName=self.ec2_keypair_name,
                                              MinCount=1,
                                              MaxCount=1,
                                              InstanceType='t2.small',  # TODO: make this configurable
                                              # TODO: bigger machine for target because of disk images
                                              SecurityGroups=[self.sg_name],
                                              UserData=self.userdata_str)
        instances[0].wait_until_running()
        self.instance = self.ec2.Instance(id=instances[0].id)
        for _ in range(20):
            ssh_cmd = SshCommand(user="admin",
                                 host=f"{self.instance.public_ip_address}",
                                 port=22,
                                 privkey_file=self.key_pair.private_key,
                                 command="systemctl is-system-running",
                                 StrictHostKeyChecking="no",
                                 UserKnownHostsFile="/dev/null",
                                 ConnectTimeout="20"
                                 )
            return_code = ssh_cmd.run()
            if return_code == 0:
                logging.info("SSH success")
                break
            time.sleep(20)
        else:
            raise RuntimeError("Failed to boot AWS instance")

    def _delete_ec2_instance(self):
        self._log_aws_delete_artifact("EC2 instance")
        self.instance.terminate()
        self.instance.wait_until_terminated()

    @staticmethod
    def _log_aws_create_artifact(msg: str):
        """Inform the user about creating an artifact in AWS which could potentially cost money if leaked.

        The leak can occur really easily e.g. when Jenkins running rpmci kills the job while still running. If killed
        using SIGKILL the cleanup code won't run at all and the user needs to do the cleanup manually.
        """
        logging.info(f"🚀 Creating artifact in AWS: {msg}")

    @staticmethod
    def _log_aws_delete_artifact(msg: str):
        """Inform the user that an artifact has been successfully deleted from AWS."""
        logging.info(f"🧹 Deleting artifact in AWS: {msg}")