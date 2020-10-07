"""RPMrepo Main

This is the entrypoint of the rpmrepo executable. We simply import from the
rpmrepo module and execute the provided CLI entrypoint.
"""

import sys
from .cli import Cli as Main


if __name__ == "__main__":
    with Main(sys.argv) as global_main:
        sys.exit(global_main.run())
