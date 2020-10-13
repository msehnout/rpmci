import contextlib
import logging
import os
import subprocess


@contextlib.contextmanager
def ssh_keys(dir):
    """Generate ephemeral SSH keys for use in the test."""
    logging.info("Generating SSH keys")
    # Generate the keys
    subprocess.run([
        "ssh-keygen",
        "-t", "rsa",
        "-N", "",
        "-f", f"{dir}/id_rsa"
    ], check=True)
    try:
        yield f"{dir}/id_rsa", f"{dir}/id_rsa.pub"
    finally:
        os.unlink(f"{dir}/id_rsa")
        os.unlink(f"{dir}/id_rsa.pub")
        pass


def ssh_run_command(user, host, port, privkey_file, command):
    cmd = [
        "ssh", f"{user}@{host}",
        # Don't show the host's key fingerprint
        "-o", "StrictHostKeyChecking=no",
        # Don't use the known-hosts file because the fingerprint changes with every run of this script
        "-o", "UserKnownHostsFile=/dev/null",
        "-p", str(port),
        "-i", privkey_file,
        command
    ]
    subprocess.run(cmd, check=True)
