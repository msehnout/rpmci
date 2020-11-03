import logging


class Instance:
    """Instance represents a running OS be it a VM, container, physical machine, or anything else.

    The class is used to abstract away the underlying technology so that the tests can be executed in a unified way
    across all footprints.
    """
    def __init__(self, name: str, ip: str, port: int):
        logging.info(f"New instance {name} with SSH access at {ip}:{port}")
        self.ip = ip
        self.port = port