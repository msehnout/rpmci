"""rpmci - Command Line Interface

The `cli` module provides a command-line interface to the rpmci package. It
provides the most basic way to execute and interact with the rpmci functions.
"""

# pylint: disable=invalid-name,too-few-public-methods

import argparse
import contextlib
import logging
import os
import yaml

import rpmci.qemu


class Configuration:
    """RPMCI configuration"""

    def __init__(self, yaml, config_directory):
        # Store the directory where the configuration file exists because the paths in there are relative to its
        # location.
        self.config_directory = config_directory
        self.rpms = f"{self.config_directory}/{yaml['rpms-directory']}"
        self.image = f"{self.config_directory}/{yaml['image']}"

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
            prog="rpmcli",
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
            help="Path to YAML config file to use",
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
            # Default: run test VMs
            cfg_abspath = os.path.abspath(self.args.config)
            logging.info(f"Using {cfg_abspath} as a configuration file")
            with open(self.args.config, 'r') as f:
                config = Configuration(yaml.load(f, Loader=yaml.SafeLoader), os.path.dirname(cfg_abspath))
                logging.info(config)

            rpmci.qemu.run_test(config, self.args.cache)

            ret = 0
        elif self.args.cmd == "dummy":
            ret = CliDummy(self).run()
        else:
            raise RuntimeError("Command mismatch")

        return ret
