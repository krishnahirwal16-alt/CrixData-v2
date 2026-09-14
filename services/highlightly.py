from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from models import Match
from services.base import CricketProvider
from utils import http_get_json, lower, parse_datetime, text


class HighlightlyProvider(CricketProvider):
    LIVE_STATES = {
        "in play",
        "stumps",
        "lunch",
        "innings break",
        "drinks",
        "timeout",
        "tea",
    }

    FINISHED_STATES = {
        "finished",
        "abandoned",
        "cancelled",
        "canceled",
        "no result",
    }

    UPCOMING_STATES = {
        "scheduled",
        "not started",
        "postponed",
    }

    KNOWN_LEAGUES = (
        "ipl",
        "wpl",
        "big bash",
        "bbl",
        "wbbl",
        "cpl",
        "women's caribbean premier league",
        "wcpl",
        "psl",
        "sa20",
        "lpl",
        "the hundred",
        "major league cricket",
        "mlc",
        "international league t20",
        "ilt20",
        "abu dhabi t10",
        "t10",
        "etpl",
    )

    INTERNATIONAL_MARKERS = (
        "india",
        "australia",
        "england",
        "pakistan",
        "south africa",
        "new zealand",
        "sri lanka",
        "west indies",
        "bangladesh",
        "afghanistan",
        "ireland",
        "zimbabwe",
        "scotland",
        "nepal",
        "namibia",
        "uganda",
        "usa",
        "united states",
        "united arab emirates",
        "uae",
        "oman",
        "canada",
        "netherlands",
    )

    INDIA_DOMESTIC_MARKERS = (
        "ranji",
        "vijay hazare",
        "syed mushtaq ali",
        "duleep",
        "irany",
        "irani",
        "deodhar",
        "maharaja trophy",
        "maruti suzuki",
        "bengal",
        "mumbai",
        "delhi",
        "karnataka",
        "tamil nadu",
        "kerala",
        "punjab",
        "gujarat",
        "rajasthan",
        "vidarbha",
        "baroda",
        "hyderabad",
        "andhra",
        "assam",
        "odisha",
        "jharkhand",
        "madhya pradesh",
        "uttar pradesh",
        "uttarakhand",
        "saurashtra",
        "goa",
    )

    def __init__(self, config):
        super().__init__(config)
        self.base_url = config.highlightly_base_url.rstrip("/")

    def get_matches(self) -> List[Match]:
        if not self.config.highlightly_api_key:
            return []

        today = datetime.now(timezone.utc).date()
        dates = [today, today + timedelta(days=1)]

        matches: List[Match] = []

        for match_date in dates:
            params = {
                "date": match_date.isoformat(),
                "timezone": self.config.timezone,
                "limit": 100,
                "offset": 0,
            }

            headers = {
                "x-rapidapi-key": self.config.highlightly_api_key,
            }

            try:
                data = http_get_json(
                    f"{self.base_url}/matches",
                    headers=headers,
                    params=params,
                )
            except Exception:
                continue

            for item in self._extract_matches(data):
                match = self._normalize_match(item)

                if match:
                    matches.append(match)

        return matches

    def get_details(self, match: Match) -> Dict[str, Any]:
        if not match.provider_ids:
            return {}

        provider_id = match.provider_ids[0]

        headers = {
            "x-rapidapi-key": self.config.highlightly_api_key,
        }

        try:
            return http_get_json(
                f"{self.base_url}/matches/{provider_id}",
                headers=headers,
            )
        except Exception as exc:
            return {
                "error": str(exc),
                "match_id": provider_id,
            }

    def _extract_matches(self, data: Any) -> List[Dict[str, Any]]:
        if isinstance(data, list):
            return data

        if not isinstance(data, dict):
            return []

        for key in ("data", "matches", "results"):
            value = data.get(key)

            if isinstance(value, list):
                return value

        return []

    def _normalize_match(self, item: Dict[str, Any]) -> Optional[Match]:
        if not isinstance(item, dict):
            return None

        provider_id = text(
            item.get("id")
            or item.get("matchId")
            or item.get("match_id")
        )

        if not provider_id:
            return None

        teams = item.get("teams") or {}

        if isinstance(teams, list):
            team1 = text(teams[0].get("name")) if len(teams) > 0 and isinstance(teams[0], dict) else text(teams[0]) if len(teams) > 0 else ""
            team2 = text(teams[1].get("name")) if len(teams) > 1 and isinstance(teams[1], dict) else text(teams[1]) if len(teams) > 1 else ""
        else:
            team1 = text(
                self._first_value(
                    teams,
                    "home",
                    "homeTeam",
                    "team1",
                    "1",
                )
            )
            team2 = text(
                self._first_value(
                    teams,
                    "away",
                    "awayTeam",
                    "team2",
                    "2",
                )
            )

        if not team1:
            team1 = text(item.get("homeTeam") or item.get("team1"))

        if not team2:
            team2 = text(item.get("awayTeam") or item.get("team2"))

        start_time = self._get_start_time(item)
        state_text = self._get_state_text(item)
        status = self._normalize_status(state_text, start_time)

        competition = self._get_competition(item)
        match_type = self._get_match_type(item)

        score1, score2 = self._get_scores(item)
        venue = self._get_venue(item)

        return Match(
            id=f"highlightly:{provider_id}",
            provider="highlightly",
            provider_ids=[provider_id],
            competition=competition,
            match_type=match_type,
            team1=team1,
            team2=team2,
            team1_score=score1,
            team2_score=score2,
            status=status,
            status_text=state_text,
            start_time=start_time,
            venue=venue,
            details_url=f"/api/matches/highlightly:{provider_id}/details",
            raw=item,
        )

    def _normalize_status(
        self,
        state_text: str,
        start_time: Optional[str],
    ) -> str:
        state = lower(state_text)

        if state in self.LIVE_STATES:
            return "live"

        if state in self.FINISHED_STATES:
            return "finished"

        if state in self.UPCOMING_STATES:
            return "upcoming"

        dt = parse_datetime(start_time)

        if dt:
            now = datetime.now(timezone.utc)

            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)

            if dt <= now:
                return "live"

        return "upcoming"

    def _get_state_text(self, item: Dict[str, Any]) -> str:
        state = item.get("state")

        if isinstance(state, dict):
            return text(
                state.get("description")
                or state.get("name")
                or state.get("state")
            )

        return text(
            item.get("status")
            or item.get("state")
            or item.get("statusText")
        )

    def _get_start_time(self, item: Dict[str, Any]) -> Optional[str]:
        for key in (
            "startTime",
            "start_time",
            "date",
            "startDate",
            "start_date",
        ):
            value = item.get(key)

            if value:
                return text(value)

        return None

    def _get_competition(self, item: Dict[str, Any]) -> str:
        league = item.get("league")

        candidates = []

        if isinstance(league, dict):
            candidates.extend(
                [
                    league.get("name"),
                    league.get("title"),
                    league.get("leagueName"),
                ]
            )
        else:
            candidates.append(league)

        candidates.extend(
            [
                item.get("competition"),
                item.get("tournament"),
                item.get("series"),
                item.get("competitionName"),
            ]
        )

        competition = next(
            (text(value) for value in candidates if text(value)),
            "",
        )

        return self._classify_competition(competition, item)

    def _classify_competition(
        self,
        competition: str,
        item: Dict[str, Any],
    ) -> str:
        comp = lower(competition)

        team_blob = " ".join(
            [
                lower(item.get("homeTeam")),
                lower(item.get("awayTeam")),
                lower(item.get("team1")),
                lower(item.get("team2")),
            ]
        )

        for league_name in self.KNOWN_LEAGUES:
            if league_name in comp:
                return competition

        if any(marker in team_blob for marker in self.INTERNATIONAL_MARKERS):
            return "International Cricket"

        if any(marker in comp for marker in self.INDIA_DOMESTIC_MARKERS):
            return "India Domestic"

        if "international" in comp:
            return "International Cricket"

        if competition:
            return competition

        return "Other Cricket"

    def _get_match_type(self, item: Dict[str, Any]) -> str:
        value = (
            item.get("matchType")
            or item.get("type")
            or item.get("format")
        )

        return text(value)

    def _get_scores(self, item: Dict[str, Any]):
        scores = item.get("scores")

        if not isinstance(scores, list):
            scores = item.get("score")

        score1 = ""
        score2 = ""

        if isinstance(scores, list):
            if len(scores) > 0:
                score1 = self._score_text(scores[0])

            if len(scores) > 1:
                score2 = self._score_text(scores[1])

        elif isinstance(scores, dict):
            score1 = self._score_text(scores.get("home"))
            score2 = self._score_text(scores.get("away"))

        return score1, score2

    def _score_text(self, value: Any) -> str:
        if isinstance(value, dict):
            runs = text(value.get("runs"))
            wickets = text(value.get("wickets"))
            overs = text(value.get("overs"))

            if runs and wickets and overs:
                return f"{runs}/{wickets} ({overs})"

            if runs and wickets:
                return f"{runs}/{wickets}"

            if runs:
                return runs

        return text(value)

    def _get_venue(self, item: Dict[str, Any]) -> str:
        venue = item.get("venue")

        if isinstance(venue, dict):
            return text(
                venue.get("name")
                or venue.get("title")
            )

        return text(
            venue
            or item.get("venueName")
            or item.get("ground")
        )

    @staticmethod
    def _first_value(data: Dict[str, Any], *keys):
        for key in keys:
            value = data.get(key)

            if value:
                if isinstance(value, dict):
                    return (
                        value.get("name")
                        or value.get("title")
                        or value.get("shortName")
                    )

                return value

        return ""
