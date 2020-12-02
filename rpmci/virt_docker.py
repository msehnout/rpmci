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
        exec_privileged,
    ):
        self._exec_image = exec_image
        self._exec_privileged = exec_privileged
        self._exec_ref = None

    def _image_acquire(self):
        # Pull the specified image and store it in the local image store.
        # Unfortunately, docker does not allow us to store it in our private
        # location, or tag it with our own tag, or somehow pin it. This means,
        # we cannot tell race-free whether we are the only user of that image,
        # nor can we reliably pin the image for the time we need it. Any racing
        # maintenance work will interfere.
        # We are unaware of any workarounds, hence, we simply pull the image
        # and leave it around.

        cmd = [
            "docker",
            "pull",
            "--quiet",
            self._exec_image,
        ]

        with util.manage_process(subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
        )) as proc:
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

    def _container_start(self):
        # Start a new adhoc container with the specified image. We require the
        # default entrypoint to stall the container (i.e., quite likely some
        # init implementation).
        # We remember the container ID so we can properly stop the container
        # when we no longer need it.

        cmd = [
            "docker",
            "container",
            "run",
            "--detach",
            "--rm",
        ]

        if self._exec_privileged:
            cmd += ["--privileged"]

        cmd += [self._exec_image]

        with util.manage_process(subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
        )) as proc:
            stdout, _stderr = proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError(f"Cannot run specified docker image: {self._exec_image}: {proc.returncode}")

        self._exec_ref = stdout.rstrip()

    def _container_stop(self):
        if self._exec_ref is None:
            return

        cmd = [
            "docker",
            "container",
            "stop",
            self._exec_ref,
        ]

        with util.manage_process(subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
        )) as proc:
            proc.wait()
            # We do not care whether the container was auto-cleaned or whether
            # this cleaned it up. Ignore the return code for now.

        self._exec_ref = None

    def __enter__(self):
        try:
            self._image_acquire()
            self._container_start()
            return self
        except:
            self._container_stop()
            self._image_release()
            raise

    def __exit__(self, exc_type, exc_value, exc_tb):
        self._container_stop()
        self._image_release()

    def run(self, args, stdin=None):
        """Execute command in container"""

        cmd = [
            "docker",
            "container",
            "exec",
        ]

        if self._exec_privileged:
            cmd += ["--privileged"]

        cmd += [self._exec_ref]
        cmd += args

        with util.manage_process(subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
        )) as proc:
            return proc.wait()
