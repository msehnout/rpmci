import logging
import subprocess


class SshKeys:
    def __init__(self, cache_dir):
        logging.info("Generating SSH keys")
        subprocess.run([
            "ssh-keygen",
            "-t", "rsa",
            "-N", "",
            "-f", f"{cache_dir}/id_rsa"
        ], check=True)
        self.private_key = f"{cache_dir}/id_rsa"
        self.public_key = f"{cache_dir}/id_rsa.pub"
        with open(self.private_key) as f:
            self.private_key_str = f.read()
        with open(self.public_key) as f:
            self.public_key_str = f.read()

    def __del__(self):
        #os.unlink(self.private_key)
        #os.unlink(self.public_key)
        pass


class SshCommand:
    def __init__(self, user, host, port, privkey_file, command, **options):
        opts = [["-o", f"{key}={value}"] for key, value in options.items()]
        flat_opts = [opt for sublist in opts for opt in sublist]
        self.cmd = ["ssh", f"{user}@{host}"]
        self.cmd += flat_opts
        self.cmd += [
            "-p", str(port),
            "-i", privkey_file,
            command
        ]

    def run(self) -> int:
        cmd = " ".join(self.cmd)
        logging.info(f"Running {cmd}")
        res = subprocess.run(self.cmd)
        return res.returncode
