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

import rpmci.qemu
import rpmci.aws


class Configuration:
    """RPMCI configuration"""

    def __init__(self, input_dict, config_directory):
        # Store the directory where the configuration file exists because the paths in there are relative to its
        # location.
        self.config_directory = config_directory
        self.rpms = f"{self.config_directory}/{input_dict['rpms-directory']}"
        self.image = f"{self.config_directory}/{input_dict['image']}"
        self.test_rpm = input_dict['test-rpm']
        self.target_rpm = input_dict['target-rpm']
        self.rpmci_setup = input_dict['rpmci-setup']
        self.tests_directory = input_dict['tests-directory']

    def __repr__(self):
        items = ','.join([f'{key}={value}' for key, value in self.__dict__.items()])
        return f'{type(self).__name__}({items})'

    def __str__(self):
        return self.__repr__()


class CliDummy:
    """Dummy Command"""

    def __init__(self, ctx):
        self._ctx = ctx

    # pylint: disable=no-self-use
    def run(self):
        """Run dummy command"""

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
            required=True,
        )
        self._parser.add_argument(
            "--config",
            help="Path to JSON config file to use",
            metavar="PATH",
            type=os.path.abspath,
            required=True,
        )

        cmd = self._parser.add_subparsers(
            dest="cmd",
            title="RPMci Commands",
        )

        cmd_dummy = cmd.add_parser(
            "dummy",
            add_help=True,
            allow_abbrev=False,
            argument_default=None,
            description="Dummy operation",
            help="Execute dummy functions",
            prog=f"{self._parser.prog} dummy",
        )
        cmd_dummy.add_argument(
            "--foobar",
            help="Path to foobar",
            metavar="PATH",
            type=os.path.abspath,
        )

        cmd_aws = cmd.add_parser(
            "aws",
            add_help=True,
            allow_abbrev=False,
            argument_default=None,
            description="Run rpmci in AWS",
            help="Run rpmci in AWS",
            prog=f"{self._parser.prog} aws",
        )
        cmd_aws.add_argument(
            "--credentials",
            help="Path to JSON config file specifying AWS credentials and region",
            metavar="PATH",
            type=os.path.abspath,
            required=False,
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

        cfg_abspath = os.path.abspath(self.args.config)
        logging.info(f"Using {cfg_abspath} as a configuration file")
        with open(self.args.config, 'r') as f:
            config = Configuration(json.load(f), os.path.dirname(cfg_abspath))
            logging.info(config)

        if not self.args.cmd:
            # Default: run test VMs
            rpmci.qemu.run_test(config, self.args.cache)

            ret = 0
        elif self.args.cmd == "dummy":
            ret = CliDummy(self).run()
        elif self.args.cmd == "aws":
            aws_cfg_abspath = os.path.abspath(self.args.credentials)
            rpmci.aws.run_test(config, self.args.cache, aws_cfg_abspath)
            ret = 0
        else:
            raise RuntimeError("Command mismatch")

        return ret
