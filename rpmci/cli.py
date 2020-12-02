"""rpmci - Command Line Interface

The `cli` module provides a command-line interface to the rpmci package. It
provides the most basic way to execute and interact with the rpmci functions.
"""

# pylint: disable=invalid-name,too-few-public-methods

import argparse
import contextlib
import json
import logging
import os
import pathlib
import sys

from . import virt_docker, virt_qemu, ssh, cloudinit, repo_local_http, repo_existing_url, virt_ec2
from .configuration import Conf


class CliRun:
    """Run Command"""

    def __init__(self, ctx):
        self._ctx = ctx
        self.cache = pathlib.Path(self._ctx.args.cache)
        self.ssh_keys = None
        self.rpm_repository = None

    def _serve_rpm_repository(self, options):
        provider = options["provider"]
        if provider == "local_http":
            return repo_local_http.RepoLocalHttp(
                self.cache,
                options["dir_with_rpms"],
                "rpmci",
                options["local_http"]["ip"],
                options["local_http"]["port"]
            )
        elif provider == "existing_url":
            return repo_existing_url.RepoExistingUrl(
                name="rpmci",
                baseurl=options["existing_url"]["baseurl"]
            )
        else:
            raise ValueError(f"Unknown RPM repo provider: {provider}")

    def _virtualize(self, options, target_options=None, credentials=None):
        """
        Parameters
        ----------
        options: Dict[Any, Any]
        target_options: Union[Dict[Any, Any], None] specify a way to reach the target machine
        """
        vtype = options["type"]
        if vtype == "docker":
            return virt_docker.VirtDocker(
                options["docker"]["image"],
                options["docker"].get("privileged", False),
            )
        elif vtype == "qemu":
            cloud_init = cloudinit.CloudInit() \
                .set_user("admin", "foobar", self.ssh_keys.public_key_str) \
                .add_repo(self.rpm_repository.name, self.rpm_repository.baseurl)
            if target_options is not None:
                vm_name = "steering"
                cloud_init\
                    .add_ssh_key_pair(self.ssh_keys.public_key_str, self.ssh_keys.private_key_str)\
                    .add_ssh_config("targetvm", "10.0.2.2", target_options["qemu"]["ssh_port"], "admin")
            else:
                vm_name = "target"
            return virt_qemu.VirtQemu(
                options["qemu"]["image"],
                options["qemu"]["ssh_port"],
                cloudinit_iso_file=cloud_init.get_iso(self.cache, vm_name),
                private_key_file=self.ssh_keys.private_key
            )
        elif vtype == "ec2":
            cloud_init = cloudinit.CloudInit() \
                .set_user("admin", "foobar", self.ssh_keys.public_key_str) \
                .add_repo(self.rpm_repository.name, self.rpm_repository.baseurl)
            userdata_str = cloud_init.get_userdata_str()
            return virt_ec2.VirtEC2(
                access_key_id=credentials["aws"]["access_key_id"],
                secret_access_key=credentials["aws"]["secret_access_key"],
                region_name=credentials["aws"]["region_name"],
                image_id=options["ec2"]["image_id"],
                instance_type=options["ec2"]["instance_type"],
                key_pair=self.ssh_keys,
                userdata_str=userdata_str,
            )
        else:
            raise ValueError(f"Unknown virtualization type: {vtype}")

    def run(self):
        """Run command"""

        if self._ctx.args.config is not None:
            with open(self._ctx.args.config, "r") as f:
                conf = Conf.load(f)
        else:
            conf = Conf.load(sys.stdin)

        self.ssh_keys = ssh.SshKeys(self.cache)

        if "rpm_repo" in conf.options:
            self.rpm_repository = self._serve_rpm_repository(
                conf.options["rpm_repo"]
            )

        steering = None
        credentials = conf.options.get("credentials")
        target = self._virtualize(conf.options["target"]["virtualization"], credentials=credentials)

        if "steering" in conf.options:
            steering = self._virtualize(
                conf.options["steering"]["virtualization"],
                conf.options["target"]["virtualization"],
                credentials=credentials
            )

        if "guest_features" in conf.options["target"]:
            stdin = json.dumps(conf.options["target"]["guest_features"])
        else:
            stdin = None

        #
        # Instantiate the target machine, followed by the steering machine, if
        # requested. Once the machines are up, we execute the test procedure:
        #
        #   * If rpms where specified, we install them into the respective
        #     image by providing our own temporary rpm repository.
        #
        #   * If an explicit `invoke` line was specified, we execute it. This
        #     is an easy way to just execute a single command in the respective
        #     machine, especially useful if the images already contain the
        #     custom configurations and/or RPMs.
        #
        #   * If a test-directory is specified, we iterate it and execute all
        #     binaries in it. We sort them in ascending alphabetical order, so
        #     their execution order is fixed.
        #
        res = 0
        with self.rpm_repository or contextlib.nullcontext():
            with target:
                with steering or contextlib.nullcontext():
                    if "rpm" in conf.options["target"]:
                        res = target.run(["sudo", "dnf", "install", conf.options["target"]["rpm"], "-y"])
                        if res != 0:
                            raise RuntimeError(f"Target RPM installation failed: {res}")

                    if "steering" in conf.options:
                        if "rpm" in conf.options["steering"]:
                            res = steering.run(["sudo", "dnf", "install", conf.options["steering"]["rpm"], "-y"])
                            if res != 0:
                                raise RuntimeError(f"Steering RPM installation failed: {res}")

                        if "invoke" in conf.options["steering"]:
                            res = steering.run(conf.options["steering"]["invoke"], stdin)
                            if res != 0:
                                raise RuntimeError(f"Steering invocation failed: {res}")

                    if "invoke" in conf.options["target"]:
                        res = target.run(conf.options["target"]["invoke"], stdin)
                        if res != 0:
                            raise RuntimeError(f"Target invocation failed: {res}")

                    if "test_invocation" in conf.options:
                        if conf.options["test_invocation"]["machine"] == "steering":
                            res = steering.run(conf.options["test_invocation"]["invoke"])
                            if res != 0:
                                logging.error(f"Running test in steering machine failed: {res}")
                        elif conf.options["test_invocation"]["machine"] == "target":
                            res = target.run(conf.options["test_invocation"]["invoke"])
                            if res != 0:
                                logging.error(f"Running test in target machine failed: {res}")

        return res


class Cli(contextlib.AbstractContextManager):
    """RPMci Command Line Interface"""

    EXITCODE_INVALID_COMMAND = 1

    def __init__(self, argv):
        self.args = None
        self._argv = argv
        self._parser = None

    def _parse_args(self):
        self._parser = argparse.ArgumentParser(
            add_help=True,
            allow_abbrev=False,
            argument_default=None,
            description="RPM Based Continuous Development",
            prog="rpmci",
        )
        self._parser.add_argument(
            "--cache",
            help="Path to cache-directory to use",
            metavar="PATH",
            type=os.path.abspath,
        )

        cmd = self._parser.add_subparsers(
            dest="cmd",
            title="RPMci Commands",
        )

        _cmd_run = cmd.add_parser(
            "run",
            add_help=True,
            allow_abbrev=False,
            argument_default=None,
            description="Run RPM CI",
            help="Run RPM CI with a given configuration",
            prog=f"{self._parser.prog} run",
        )
        _cmd_run.add_argument(
            "--config",
            help="Path to configuration file",
            metavar="PATH",
            type=os.path.abspath,
        )

        return self._parser.parse_args(self._argv[1:])

    def __enter__(self):
        self.args = self._parse_args()
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        pass

    def run(self):
        """Execute selected commands"""
        logging.basicConfig(level=logging.INFO)

        if not self.args.cmd:
            print("No subcommand specified", file=sys.stderr)
            self._parser.print_help(file=sys.stderr)
            ret = Cli.EXITCODE_INVALID_COMMAND
        elif self.args.cmd == "run":
            ret = CliRun(self).run()
        else:
            raise RuntimeError("Command mismatch")

        return ret
