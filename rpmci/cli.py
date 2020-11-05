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
import sys

from . import virt_docker


class Conf:
    """RPMCI configuration"""

    def __init__(self, options):
        self.options = options

    @staticmethod
    def _invalid_key(path, key):
        return RuntimeError(f"Invalid configuration key: {path}/{key}")

    @staticmethod
    def _invalid_value(path, key, value):
        return RuntimeError(f"Invalid configuration value: {path}/{key}: {value}")

    @staticmethod
    def _missing_key(path, key):
        return RuntimeError(f"Missing configuration key: {path}/{key}")

    # pylint: disable=too-many-branches
    @classmethod
    def _load_virtualization(cls, path, data):
        """Parse virtualization configuration"""

        conf = {}

        for key in data.keys():
            if key == "type":
                value = data[key]
                if value not in ["docker", "qemu", "ec2"]:
                    raise cls._invalid_value(path, key, value)
                conf[key] = value

            elif key == "docker":
                conf[key] = {}
                for subkey in data[key]:
                    if subkey == "arguments":
                        conf[key][subkey] = data[key][subkey]
                    elif subkey == "image":
                        conf[key][subkey] = data[key][subkey]
                    elif subkey == "privileged":
                        if not isinstance(data[key][subkey], bool):
                            raise cls._invalid_value(
                                f"{path}/docker",
                                subkey,
                                data[key][subkey],
                            )
                        conf[key][subkey] = data[key][subkey]
                    else:
                        raise cls._invalid_key(f"{path}/{key}", subkey)

                if "image" not in conf[key]:
                    raise cls._missing_key(f"{path}/{key}", "image")

            elif key == "qemu":
                conf[key] = {}
                for subkey in data[key]:
                    if subkey == "image":
                        conf[key][subkey] = data[key][subkey]
                    elif subkey == "ssh_port":
                        conf[key][subkey] = data[key][subkey]
                    else:
                        raise cls._invalid_key(f"{path}/{key}", subkey)

                for mandatory_subkey in ["image", "ssh_port"]:
                    if mandatory_subkey not in conf[key]:
                        raise cls._missing_key(f"{path}/{key}", mandatory_subkey)
            elif key == "ec2":
                pass
            else:
                raise cls._invalid_key(path, key)

        if "type" not in conf:
            raise cls._missing_key(path, "type")
        if conf["type"] not in conf:
            raise cls._missing_key(path, conf["type"])

        return conf

    @classmethod
    def _load_credentials(cls, path, data):
        conf = {}

        for key in data.keys():
            if key == "aws":
                conf[key] = {}
                for subkey in data[key].keys():
                    if subkey == "access-key-id":
                        conf[key][subkey] = data[key][subkey]
                    elif subkey == "secret-access-key":
                        conf[key][subkey] = data[key][subkey]
                    else:
                        raise cls._invalid_key(f"{path}/{key}", subkey)
            else:
                raise cls._invalid_key(path, key)

        if "virtualization" not in conf:
            raise cls._missing_key(path, "virtualization")

        return conf

    @classmethod
    def _load_steering(cls, path, data):
        conf = {}

        for key in data.keys():
            if key == "rpm":
                conf[key] = data[key]
            elif key == "tests":
                conf[key] = {}
                for subkey in data[key].keys():
                    if subkey == "directory":
                        conf[key][subkey] = data[key][subkey]
                    elif subkey == "provision":
                        conf[key][subkey] = data[key][subkey]
                    else:
                        raise cls._invalid_key(f"{path}/{key}", subkey)
            elif key == "virtualization":
                conf["virtualization"] = cls._load_virtualization(
                    f"{path}/virtualization",
                    data[key],
                )
            else:
                raise cls._invalid_key(path, key)

        if "virtualization" not in conf:
            raise cls._missing_key(path, "virtualization")

        return conf

    @classmethod
    def _load_target(cls, path, data):
        conf = {}

        for key in data.keys():
            if key == "invoke":
                if not (
                    isinstance(data[key], list) and
                    all(isinstance(entry, str) for entry in data[key])
                ):
                    raise cls._invalid_value(
                        path,
                        key,
                        data[key],
                    )
                conf[key] = data[key]
            elif key == "rpm":
                conf[key] = data[key]
            elif key == "virtualization":
                conf["virtualization"] = cls._load_virtualization(
                    f"{path}/virtualization",
                    data[key],
                )
            else:
                raise cls._invalid_key(path, key)

        if "virtualization" not in conf:
            raise cls._missing_key(path, "virtualization")

        return conf

    @classmethod
    def load(cls, filp):
        """Parse configuration"""

        conf = {}
        data = json.load(filp)
        path = ""

        for key in data.keys():
            if key == "credentials":
                conf[key] = cls._load_credentials(f"{path}/{key}", data[key])
            elif key == "steering":
                conf[key] = cls._load_steering(f"{path}/{key}", data[key])
            elif key == "target":
                conf[key] = cls._load_target(f"{path}/{key}", data[key])
            else:
                raise cls._invalid_key(path, key)

        if "target" not in conf:
            raise cls._missing_key(path, "target")

        return cls(conf)


class CliRun:
    """Run Command"""

    def __init__(self, ctx):
        self._ctx = ctx

    def _virtualize(self, options):
        vtype = options["type"]
        if vtype == "docker":
            return virt_docker.VirtDocker(
                options["docker"]["image"],
                options["docker"].get("privileged", False),
            )
        else:
            raise ValueError(f"Unknown virtualization type: {vtype}")

    def run(self):
        """Run command"""

        conf = Conf.load(sys.stdin)
        steering = None
        target = self._virtualize(conf.options["target"]["virtualization"])

        if "steering" in conf.options:
            steering = self._virtualize(
                conf.options["steering"]["virtualization"]
            )

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
        with target:
            with steering or contextlib.nullcontext():
                # XXX: Implement the `rpm` installation step.

                if "invoke" in conf.options["target"]:
                    res = target.run(conf.options["target"]["invoke"])
                    if res != 0:
                        raise RuntimeError(f"Target invocation failed: {res}")

                # XXX: Implement the `test` step.

        return 0


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
