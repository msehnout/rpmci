from dataclasses import dataclass


@dataclass
class RepoExistingUrl:
    name: str
    baseurl: str
