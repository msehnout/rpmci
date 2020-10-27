"""rpmci/virt_docker- Docker Virtualization

The `virt_docker` module implements the docker-based virtualization to execute
RPMci steering and target systems.
"""

# pylint: disable=invalid-name,too-few-public-methods

import contextlib
import subprocess

from . import util


class VirtDocker(contextlib.AbstractContextManager):
    """Docker Virtualization"""

    def __init__(
        self,
        exec_image,
    ):
        self._exec_image = exec_image

    def _image_acquire(self):
        # Pull the specified image and store it in the local image store.
        # Unfortunately, docker does not allow us to store it in our private
        # location, or tag it with our own tag, or somehow pin it. This means,
        # we cannot race-free tell whether we are the only user of that image,
        # nor can we reliably pin the image for the time we need it. Any racing
        # maintenance work will interfere.
        # We are unaware of any workarounds, hence, we simply pull the image
        # and leave it around. See `_image_release()` for more information.

        cmd = [
            "docker",
            "pull",
            self._exec_image,
        ]

        with util.manage_process(subprocess.Popen(cmd)) as proc:
            res = proc.wait()
            if res != 0:
                raise RuntimeError(f"Cannot pull specified docker image: {self._exec_image}: {res}")

    def _image_release(self):
        # This is the inverse operation to `_image_acquire()`. Unfortunately,
        # the docker CLI does not allow to fetch images under a custom name.
        # Therefore, we cannot release images that we fetched, because we
        # cannot know who else is using them.
        # Until docker gets an API for that, or until a workaround is found,
        # we simply never untag images for now.
        pass

    def __enter__(self):
        try:
            self._image_acquire()
            return self
        except:
            self._image_release()
            raise

    def __exit__(self, exc_type, exc_value, exc_tb):
        self._image_release()

    def run(self, args, *, privileged=False):
        """Run new container instance"""

        cmd = [
            "docker"
            "run"
            "--rm"
        ]

        if privileged:
            cmd += ["--privileged"]

        cmd += [self._exec_image]
        cmd += args

        with util.manage_process(subprocess.Popen(cmd)) as proc:
            return proc.wait()
