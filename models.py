from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Match:
    id: str
    provider: str
    provider_ids: List[str] = field(default_factory=list)

    competition: str = ""
    match_type: str = ""

    team1: str = ""
    team2: str = ""

    team1_score: str = ""
    team2_score: str = ""

    status: str = "upcoming"
    status_text: str = ""

    start_time: Optional[str] = None
    venue: str = ""

    details_url: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)
