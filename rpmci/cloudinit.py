import base64
import logging
import pathlib
import subprocess

from pathlib import Path

import yaml


class CloudInit:
    def __init__(self):
        self.repos = {}
        self.users = []
        self.ssh_keypair = None
        self.ssh_configs = {}

    def add_repo(self, name: str, baseurl: str):
        self.repos[name] = {
            "name": name,
            "baseurl": baseurl,
            "enabled": True,
            "gpgcheck": False,
        }
        return self

    def add_user(self, username: str, password: str, ssh_pubkey: str):
        self.users += [{
            "user": username,
            "password": password,
            "ssh_authorized_keys": [ssh_pubkey],
            "ssh_pwauth": True,
            "chpasswd": {
                "expire": False,
            },
            "sudo": "ALL=(ALL) NOPASSWD:ALL",
        }]
        return self

    def add_ssh_key_pair(self, public_key: str, private_key: str):
        self.ssh_keypair = {
            "public_key": public_key,
            "private_key": private_key,
        }
        return self

    def add_ssh_config(self, host_alias: str, hostname: str, port: int, username: str):
        """Create new entry in /etc/ssh_config.

        Parameters
        ----------
        host_alias The name that the user can use to connect to this machine.
        hostname Domain name or IP address of the machine.
        port Port where the SSH daemon listens.
        username User with known password or SSH key.
        """
        self.ssh_configs[host_alias] = {
            "HostName": hostname,
            "Port": port,
            "User": username,
            "IdentityFile": "/etc/ssh/id_rsa",
            "StrictHostKeyChecking": "no",
        }
        return self

    def get_userdata_str(self):
        write_files = []
        user_data = {}
        if len(self.repos.keys()) > 0:
            user_data["yum_repos"] = self.repos
        if len(self.users) > 0:
            user_data["users"] = self.users
        if self.ssh_keypair is not None:
            write_files += [
                {
                    "path": "/etc/ssh/id_rsa.pub",
                    "encoding": "b64",
                    "content": base64.b64encode(self.ssh_keypair["public_key"].encode("utf-8")).decode("utf-8"),
                    "permissions": "0644",
                },
                {
                    "path": "/etc/ssh/id_rsa",
                    "encoding": "b64",
                    "content": base64.b64encode(self.ssh_keypair["private_key"].encode("utf-8")).decode("utf-8"),
                    "permissions": "0644",
                }
            ]
        if len(self.ssh_configs.keys()) > 0:
            ssh_config_content = ""
            for host, config in self.ssh_configs.items():
                ssh_config_content += f"Host {host}\n"
                for k,v in config.items():
                    ssh_config_content += f"    {k} {v}\n"
            write_files += [
                {
                    "path": "/etc/ssh/ssh_config",
                    "encoding": "b64",
                    "content": base64.b64encode(ssh_config_content.encode("utf-8")).decode("utf-8"),
                    "permissions": "0644",
                }
            ]
        if len(write_files) > 0:
            user_data["write_files"] = write_files

        user_data_str = yaml.dump(user_data, Dumper=yaml.SafeDumper)
        return f"#cloud-config\n{user_data_str}"

    @staticmethod
    def _write_userdata_file(filename: Path, content: str):
        """Write user-data file for cloud-init."""
        logging.info("Writing user-data file")
        with open(filename, "w") as f:
            f.write(content)

    @staticmethod
    def _write_metadata_file(filename: Path, vm_name: str):
        """Write meta-data file for cloud-init."""
        logging.info("Writing meta-data file")
        with open(filename, "w") as f:
            print("instance-id: nocloud", file=f)
            print(f"local-hostname: {vm_name}", file=f)

    def get_iso(self, cache_dir: Path, vm_name: str) -> Path:
        logging.info("Generating cloud-init ISO file")
        cloudinit_file = cache_dir.joinpath(f"{vm_name}.iso")
        userdata_file = cache_dir.joinpath("user-data")
        self._write_userdata_file(userdata_file, self.get_userdata_str())
        metadata_file = cache_dir.joinpath("meta-data")
        self._write_metadata_file(metadata_file, vm_name)
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
        return pathlib.Path(cloudinit_file)


def test_CloudInit_get_userdata_str():
    cloudinit = CloudInit()
    cloudinit.add_repo("osbuild", "osbuild.org")
    cloudinit.add_user("admin", "foobar", "abc")
    cloudinit.add_ssh_key_pair("pubkey", "privkey")
    cloudinit.add_ssh_config("target", "127.0.0.1", 2222, "admin")
    resulting_string = cloudinit.get_userdata_str()
    loaded_yaml = yaml.load(resulting_string, Loader=yaml.SafeLoader)
    assert loaded_yaml["users"][0]["user"] == "admin"
    generated_ssh_config = base64.b64decode(loaded_yaml["write_files"][2]["content"].encode("utf-8")).decode("utf-8")
    expected_ssh_config = """Host target
    HostName 127.0.0.1
    Port 2222
    User admin
    IdentityFile /etc/ssh/id_rsa
    StrictHostKeyChecking no
"""
    assert generated_ssh_config == expected_ssh_config
