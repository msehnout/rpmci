import contextlib
import logging
import os
import tempfile
import subprocess
import sys

from rpmci.rpm import serve_repository
from rpmci.cloudinit import write_metadata_file, write_userdata_file, create_cloudinit_iso


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
            with qemu_boot_image(config.image, cloudinit_file):
                # TODO: ssh into the machine
                logging.info("Time to SSH into the machine")
                sys.stdin.readline()
                pass
    pass


@contextlib.contextmanager
def ssh_keys(dir):
    """Generate ephemeral SSH keys for use in the test."""
    logging.info("Generating SSH keys")
    # Generate the keys
    subprocess.run([
        "ssh-keygen",
        "-t", "rsa",
        "-N", "\"\"",
        "-f", f"{dir}/id_rsa"
    ], check=True)
    try:
        yield f"{dir}/id_rsa", f"{dir}/id_rsa.pub"
    finally:
        os.unlink(f"{dir}/id_rsa")
        os.unlink(f"{dir}/id_rsa.pub")
        pass


@contextlib.contextmanager
def qemu_boot_image(image_file, cloudinit_file):
    """Run a single VM using qemu."""
    logging.info("Running a VM using qemu")
    with tempfile.TemporaryDirectory() as _dir:
        # run in background
        cmd = ["qemu-system-x86_64",
               "-enable-kvm",
               "-m", "2048",
               "-snapshot",
               "-cpu", "host",
               "-net", "nic,model=virtio", "-net", "user,hostfwd=tcp::2222-:22,hostfwd=tcp::4430-:443",
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
