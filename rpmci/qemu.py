import contextlib
import logging
import os
import tempfile
import time
import subprocess
import sys

from rpmci.rpm import serve_repository
from rpmci.cloudinit import write_metadata_file, write_userdata_file, create_cloudinit_iso
from rpmci.ssh import ssh_keys, ssh_run_command


def run_test(config, cache_dir):
    """Spawn VMs and run the tests inside of them."""
    logging.info("Running the test")
    # spawn HTTP server serving the RPMs from config
    with ssh_keys(cache_dir) as (private_key, public_key):
        # Create cloud-init configuration
        userdata_file = f"{cache_dir}/cloud-init/user-data"
        metadata_file = f"{cache_dir}/cloud-init/meta-data"
        cloudinit_file = f"{cache_dir}/cloud-init/cloudinit.iso"
        
        os.mkdir(f"{cache_dir}/cloud-init/")
        write_metadata_file(metadata_file)
        write_userdata_file(userdata_file, public_key)
        create_cloudinit_iso(userdata_file, metadata_file, cloudinit_file)

        with serve_repository(config.rpms, cache_dir):
            logging.info("Booting test VM")
            with qemu_boot_image(config.image, cloudinit_file, 2222):
                logging.info("Booting target VM")
                with qemu_boot_image(config.image, cloudinit_file, 2223):
                    logging.info("Time to SSH into the machine")
                    time.sleep(80)  # TODO: <- fix this
                    ssh_run_command("admin", "127.0.0.1", 2222, private_key,
                                    "sudo dnf install osbuild-composer-tests -y")
                    ssh_run_command("admin", "127.0.0.1", 2223, private_key,
                                    "sudo dnf install osbuild-composer -y")
                    # WARNING: I haven't implemented the forwarding from target to test yet, I just fake it by
                    # running composer directly on the test VM.
                    ssh_run_command("admin", "127.0.0.1", 2222, private_key,
                                    "sudo systemctl start osbuild-composer")
                    ssh_run_command("admin", "127.0.0.1", 2223, private_key,
                                    "sudo systemctl start osbuild-composer")
                    ssh_run_command("admin", "127.0.0.1", 2222, private_key,
                                    "sudo /usr/libexec/tests/osbuild-composer/osbuild-weldr-tests -test.v")
                    sys.stdin.readline()


@contextlib.contextmanager
def qemu_boot_image(image_file, cloudinit_file, sshport):
    """Run a single VM using qemu."""
    logging.info("Running a VM using qemu")
    with tempfile.TemporaryDirectory() as _dir:
        # run in background
        cmd = ["qemu-system-x86_64",
               "-enable-kvm",
               "-m", "2048",
               "-snapshot",
               "-cpu", "host",
               "-net", "nic,model=virtio", "-net", f"user,hostfwd=tcp::{sshport}-:22",
               "-cdrom", cloudinit_file,
               #"-nographic",
               image_file
               ]
        logging.info(f"running qemu command: {' '.join(cmd)}")
        vm = subprocess.Popen(cmd) #, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            yield None
        finally:
            vm.kill()
