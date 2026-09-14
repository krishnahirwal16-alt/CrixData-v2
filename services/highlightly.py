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
        "cancelled",
        "canceled",
        "abandoned",
    }

    UPCOMING_STATES = {
        "scheduled",
        "match delayed",
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
        "irani",
        "deodhar",
        "maharaja trophy",
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

        matches: List[Match] = []

        today = datetime.now(timezone.utc).date()

        dates = [
            today,
            today + timedelta(days=1),
        ]

        headers = {
            "x-rapidapi-key": self.config.highlightly_api_key,
        }

        for match_date in dates:

            params = {
                "date": match_date.isoformat(),
                "timezone": self.config.timezone,
                "limit": 100,
                "offset": 0,
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

        value = data.get("data")

        if isinstance(value, list):
            return value

        for key in (
            "matches",
            "results",
        ):
            value = data.get(key)

            if isinstance(value, list):
                return value

        return []

    def _normalize_match(
        self,
        item: Dict[str, Any],
    ) -> Optional[Match]:

        if not isinstance(item, dict):
            return None

        provider_id = text(
            item.get("id")
            or item.get("matchId")
            or item.get("match_id")
        )

        if not provider_id:
            return None

        team1 = self._team_name(
            item.get("homeTeam")
        )

        team2 = self._team_name(
            item.get("awayTeam")
        )

        if not team1:
            team1 = text(
                item.get("homeTeamName")
                or item.get("team1")
            )

        if not team2:
            team2 = text(
                item.get("awayTeamName")
                or item.get("team2")
            )

        if not team1 or not team2:
            return None

        state = item.get("state")

        if not isinstance(state, dict):
            state = {}

        state_description = text(
            state.get("description")
        )

        state_report = text(
            state.get("report")
        )

        start_time = self._get_start_time(item)

        status = self._normalize_status(
            state_description=state_description,
            start_time=start_time,
        )

        competition = self._get_competition(
            item
        )

        match_type = text(
            item.get("format")
            or item.get("matchType")
            or item.get("type")
        )

        score1, score2 = self._get_scores(
            state
        )

        venue = self._get_venue(
            item
        )

        status_text = (
            state_report
            or state_description
        )

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
            status_text=status_text,
            start_time=start_time,
            venue=venue,
            details_url=(
                f"/api/matches/"
                f"highlightly:{provider_id}"
                f"/details"
            ),
            raw=item,
        )

    def _normalize_status(
        self,
        state_description: str,
        start_time: Optional[str],
    ) -> str:

        state = lower(
            state_description
        )

        if state in self.LIVE_STATES:
            return "live"

        if state in self.FINISHED_STATES:
            return "finished"

        if state in self.UPCOMING_STATES:
            return "upcoming"

        # "No live coverage" does NOT mean live.
        if state == "no live coverage":
            return self._status_from_time(
                start_time
            )

        # Unknown state should never become
        # live merely because the start time is old.
        if state in {
            "",
            "unknown",
        }:
            return self._status_from_time(
                start_time
            )

        return self._status_from_time(
            start_time
        )

    def _status_from_time(
        self,
        start_time: Optional[str],
    ) -> str:

        dt = parse_datetime(
            start_time
        )

        if dt is None:
            return "upcoming"

        if dt.tzinfo is None:
            dt = dt.replace(
                tzinfo=timezone.utc
            )

        now = datetime.now(
            timezone.utc
        )

        # A future start is definitely upcoming.
        if dt > now:
            return "upcoming"

        # IMPORTANT:
        # Do NOT classify an old match as live.
        #
        # If the provider has not told us that the match
        # is live, treat an old/unknown match as finished.
        return "finished"

    def _team_name(
        self,
        team: Any,
    ) -> str:

        if isinstance(team, dict):
            return text(
                team.get("name")
                or team.get("displayName")
                or team.get("shortName")
                or team.get("abbreviation")
            )

        return text(team)

    def _get_start_time(
        self,
        item: Dict[str, Any],
    ) -> Optional[str]:

        for key in (
            "date",
            "startTime",
            "start_time",
            "startDate",
        ):

            value = item.get(key)

            if value:
                return text(value)

        return None

    def _get_competition(
        self,
        item: Dict[str, Any],
    ) -> str:

        league = item.get("league")

        competition = ""

        if isinstance(
            league,
            dict,
        ):
            competition = text(
                league.get("name")
                or league.get("title")
            )

        if not competition:
            competition = text(
                item.get("competition")
                or item.get("tournament")
                or item.get("series")
                or item.get("competitionName")
            )

        return self._classify_competition(
            competition,
            item,
        )

    def _classify_competition(
        self,
        competition: str,
        item: Dict[str, Any],
    ) -> str:

        comp = lower(
            competition
        )

        team1 = self._team_name(
            item.get("homeTeam")
        )

        team2 = self._team_name(
            item.get("awayTeam")
        )

        if not team1:
            team1 = text(
                item.get("homeTeamName")
            )

        if not team2:
            team2 = text(
                item.get("awayTeamName")
            )

        team_blob = (
            f"{lower(team1)} "
            f"{lower(team2)}"
        )

        # First: known leagues.
        for league_name in self.KNOWN_LEAGUES:

            if league_name in comp:
                return competition

        # Then: clearly international teams.
        if any(
            marker in team_blob
            for marker in self.INTERNATIONAL_MARKERS
        ):
            return "International Cricket"

        # Then: India domestic.
        if any(
            marker in comp
            for marker in self.INDIA_DOMESTIC_MARKERS
        ):
            return "India Domestic"

        if "international" in comp:
            return "International Cricket"

        if competition:
            return competition

        return "Other Cricket"

    def _get_scores(
        self,
        state: Dict[str, Any],
    ):

        teams = state.get(
            "teams"
        )

        if not isinstance(
            teams,
            dict,
        ):
            return "", ""

        home = teams.get(
            "home"
        )

        away = teams.get(
            "away"
        )

        score1 = self._team_score(
            home
        )

        score2 = self._team_score(
            away
        )

        return score1, score2

    def _team_score(
        self,
        team: Any,
    ) -> str:

        if not isinstance(
            team,
            dict,
        ):
            return ""

        return text(
            team.get("score")
        )

    def _get_venue(
        self,
        item: Dict[str, Any],
    ) -> str:

        venue = item.get(
            "venue"
        )

        if isinstance(
            venue,
            dict,
        ):
            name = text(
                venue.get("name")
            )

            city = text(
                venue.get("city")
            )

            if name and city:
                return f"{name}, {city}"

            return name or city

        return text(
            venue
            or item.get("venueName")
            or item.get("ground")
        )
