from abc import ABC, abstractmethod
from typing import Any, Dict, List

from config import AppConfig
from models import Match


class CricketProvider(ABC):
    def __init__(self, config: AppConfig):
        self.config = config

    @abstractmethod
    def get_matches(self) -> List[Match]:
        raise NotImplementedError

    def get_details(self, match: Match) -> Dict[str, Any]:
        return {}
