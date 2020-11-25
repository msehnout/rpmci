import contextlib
from dataclasses import dataclass


@dataclass
class RepoExistingUrl(contextlib.AbstractContextManager):
    name: str
    baseurl: str

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
