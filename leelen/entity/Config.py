from dataclasses import dataclass

from .BaseDaoBean import BaseDaoBean


@dataclass
class Config(BaseDaoBean):
    config_version: int = 0
    latest_time: int = 0

