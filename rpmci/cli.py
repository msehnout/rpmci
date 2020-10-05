"""rpmci - Command Line Interface

The `cli` module provides a command-line interface to the rpmci package. It
provides the most basic way to execute and interact with the rpmci functions.
"""

# pylint: disable=invalid-name,too-few-public-methods

import argparse
import contextlib
import os
import sys


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

        if not self.args.cmd:
            print("No subcommand specified", file=sys.stderr)
            self._parser.print_help(file=sys.stderr)
            ret = Cli.EXITCODE_INVALID_COMMAND
        elif self.args.cmd == "dummy":
            ret = CliDummy(self).run()
        else:
            raise RuntimeError("Command mismatch")

        return ret
