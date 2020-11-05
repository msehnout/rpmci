import contextlib
import logging
import subprocess

from .ssh import ssh_run_command


class VirtQemu(contextlib.AbstractContextManager):
    """Qemu Virtualization"""
    def __init__(self, image, ssh_port, cloudinit_iso_file, private_key_file):
        self.image = image
        self.ssh_port = ssh_port
        self.cloudinit_iso_file = cloudinit_iso_file
        self.private_key_file = private_key_file
        self.vm_process = None

    def __enter__(self):
        cmd = ["qemu-system-x86_64",
               "-enable-kvm",
               "-m", "2048",
               "-snapshot",
               "-cpu", "host",
               "-net", "nic,model=virtio", "-net", f"user,hostfwd=tcp::{self.ssh_port}-:22",
               "-cdrom", self.cloudinit_iso_file,
               # "-nographic",
               self.image
               ]
        logging.info(f"running qemu command: {' '.join(cmd)}")
        self.vm_process = subprocess.Popen(cmd)  # , stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.vm_process.kill()

    def run(self, args):
        ssh_run_command("admin", "127.0.0.1", self.ssh_port, self.private_key_file, "".join(args))