import base64
import logging
import subprocess

import yaml


def write_metadata_file(filename):
    """Write meta-data file for cloud-init."""
    logging.info("Writing meta-data file")
    with open(filename, "w") as f:
        print("instance-id: nocloud", file=f)
        print("local-hostname: vm", file=f)


def userdata(pubkey_filename, privkey_filename, repo_baseurl, vm_dict):
    logging.info("Generating user-data")
    with open(pubkey_filename, 'r') as f:
        pubkey_string = f.read()
    with open(privkey_filename, 'r') as f:
        privkey_string = f.read()
    user_data = {
        "yum_repos": {
            "osbuild": {
                "name": "osbuild",
                "baseurl": repo_baseurl,
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
        "write_files": [
            {
                "path": "/etc/ssh/id_rsa.pub",
                "encoding": "b64",
                "content": base64.b64encode(pubkey_string.encode("utf-8")).decode("utf-8"),
                "permissions": "0644",
            },
            {
                "path": "/etc/ssh/id_rsa",
                "encoding": "b64",
                "content": base64.b64encode(privkey_string.encode("utf-8")).decode("utf-8"),
                "permissions": "0644",
            },
            {
                "path": "/etc/ssh/ssh_config",
                "encoding": "b64",
                "content": base64.b64encode(f"""Host testvm
         HostName {vm_dict["testvm"]["ip"]}
         User admin
         Port {vm_dict["testvm"]["port"]}
         IdentityFile /etc/ssh/id_rsa
         StrictHostKeyChecking no
    Host targetvm
         HostName {vm_dict["targetvm"]["ip"]}
         User admin
         Port {vm_dict["targetvm"]["port"]}
         IdentityFile /etc/ssh/id_rsa
         StrictHostKeyChecking no
                    """.encode("utf-8")).decode("utf-8"),
                "permissions": "0644",
            }
        ]
    }
    return user_data


def write_userdata_file(filename, pubkey_filename, privkey_filename, repo_baseurl, vm_dict):
    """Write user-data file for cloud-init."""
    user_data = userdata(pubkey_filename, privkey_filename, repo_baseurl, vm_dict)
    logging.info("Writing user-data file")
    with open(filename, "w") as f:
        print("#cloud-config", file=f)
        yaml.dump(user_data, f, Dumper=yaml.SafeDumper)


def write_userdata_str(pubkey_filename, privkey_filename, repo_baseurl, vm_dict):
    """Write user-data to a string."""
    user_data = userdata(pubkey_filename, privkey_filename, repo_baseurl, vm_dict)
    userdatastr = yaml.dump(user_data, Dumper=yaml.SafeDumper)
    return f"#cloud-config\n{userdatastr}"


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