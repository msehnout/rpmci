import logging
import subprocess

import yaml


def write_metadata_file(filename):
    """Write meta-data file for cloud-init."""
    logging.info("Writing meta-data file")
    with open(filename, "w") as f:
        print("instance-id: nocloud", file=f)
        print("local-hostname: vm", file=f)


def write_userdata_file(filename, pubkey_filename):
    """Write user-data file for cloud-init."""
    logging.info("Writing user-data file")
    with open(pubkey_filename, 'r') as f:
        pubkey_string = f.read()
    user_data = {
        "yum_repos": {
            "osbuild": {
                "name": "osbuild",
                "baseurl": "http://10.0.2.2:8000",
                "enabled": True,
                "gpgcheck": False,
            }
        },
        "user": "admin",
        "password": "foobar",
        "ssh_authorized_keys": [
            pubkey_string
        ],
        "ssh_pwauth": "True",
        "chpasswd": {
            "expire": False,
        },
        "sudo": "ALL=(ALL) NOPASSWD:ALL",
    }
    with open(filename, "w") as f:
        print("#cloud-config", file=f)
        yaml.dump(user_data, f, Dumper=yaml.SafeDumper)


def create_cloudinit_iso(userdata_file, metadata_file, cloudinit_file):
    """Take the user-data and meta-data files and generate cloud-init iso from them."""
    logging.info("Generating cloud-init ISO file")
    # Create an ISO that cloud-init can consume with userdata.
    subprocess.run(["genisoimage",
                    "-quiet",
                    "-input-charset", "utf-8",
                    "-output", cloudinit_file,
                    "-volid", "cidata",
                    "-joliet",
                    "-rock",
                    "-quiet",
                    "-graft-points",
                    userdata_file,
                    metadata_file],
                   check=True)