from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from models import Match
from services.base import CricketProvider
from utils import http_get_json, lower, parse_datetime, text


class CricketDataProvider(CricketProvider):
    LIVE_STATES = {
        "live",
        "inprogress",
        "in progress",
        "started",
        "play",
        "in play",
    }

    FINISHED_STATES = {
        "result",
        "finished",
        "completed",
        "complete",
        "abandoned",
        "cancelled",
        "canceled",
        "no result",
    }

    def __init__(self, config):
        super().__init__(config)
        self.base_url = config.cricketdata_base_url.rstrip("/")

    def get_matches(self) -> List[Match]:
        if not self.config.cricketdata_api_key:
            return []

        matches: List[Match] = []

        # Primary feed
        try:
            data = http_get_json(
                f"{self.base_url}/cricScore",
                params={
                    "apikey": self.config.cricketdata_api_key,
                },
            )

            for item in self._extract_matches(data):
                match = self._normalize_match(item)

                if match:
                    matches.append(match)

        except Exception:
            pass

        # Secondary feed
        try:
            data = http_get_json(
                f"{self.base_url}/currentMatches",
                params={
                    "apikey": self.config.cricketdata_api_key,
                },
            )

            for item in self._extract_matches(data):
                match = self._normalize_match(item)

                if match:
                    matches.append(match)

        except Exception:
            pass

        return matches

    def get_details(self, match: Match) -> Dict[str, Any]:
        return {}

    def _extract_matches(self, data: Any) -> List[Dict[str, Any]]:
        if isinstance(data, list):
            return data

        if not isinstance(data, dict):
            return []

        value = data.get("data")

        if isinstance(value, list):
            return value

        for key in ("matches", "results"):
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
            or item.get("unique_id")
        )

        if not provider_id:
            provider_id = self._build_fallback_id(item)

        team1, team2 = self._get_teams(item)

        if not team1 and not team2:
            return None

        status_text = text(
            item.get("status")
            or item.get("matchStatus")
            or item.get("ms")
        )

        start_time = self._get_start_time(item)
        status = self._normalize_status(item, status_text, start_time)

        competition = text(
            item.get("name")
            or item.get("series")
            or item.get("seriesName")
            or item.get("competition")
        )

        match_type = text(
            item.get("matchType")
            or item.get("type")
            or item.get("format")
        )

        score1, score2 = self._get_scores(item)
        venue = self._get_venue(item)

        return Match(
            id=f"cricketdata:{provider_id}",
            provider="cricketdata",
            provider_ids=[provider_id],
            competition=competition or "Other Cricket",
            match_type=match_type,
            team1=team1,
            team2=team2,
            team1_score=score1,
            team2_score=score2,
            status=status,
            status_text=status_text,
            start_time=start_time,
            venue=venue,
            details_url="",
            raw=item,
        )

    def _normalize_status(
        self,
        item: Dict[str, Any],
        status_text: str,
        start_time: Optional[str],
    ) -> str:
        ms = lower(item.get("ms"))
        status = lower(status_text)

        if ms in self.FINISHED_STATES:
            return "finished"

        if ms in self.LIVE_STATES:
            return "live"

        if any(value in status for value in (
            "won by",
            "match tied",
            "no result",
            "abandoned",
            "cancelled",
            "canceled",
            "completed",
        )):
            return "finished"

        if any(value in status for value in (
            "live",
            "in progress",
            "inprogress",
            "innings break",
            "stumps",
            "lunch",
            "tea",
            "drinks",
        )):
            return "live"

        dt = parse_datetime(start_time)

        if dt:
            now = datetime.now(timezone.utc)

            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)

            if dt > now:
                return "upcoming"

        if self._has_score(item):
            return "live"

        return "upcoming"

    def _get_teams(self, item: Dict[str, Any]):
        teams = item.get("teams")

        if isinstance(teams, list):
            names = []

            for team in teams[:2]:
                if isinstance(team, dict):
                    names.append(
                        text(
                            team.get("name")
                            or team.get("teamName")
                        )
                    )
                else:
                    names.append(text(team))

            while len(names) < 2:
                names.append("")

            return names[0], names[1]

        team1 = text(
            item.get("team1")
            or item.get("teamA")
            or item.get("homeTeam")
            or self._nested_team_name(item.get("teamInfo"), 0)
        )

        team2 = text(
            item.get("team2")
            or item.get("teamB")
            or item.get("awayTeam")
            or self._nested_team_name(item.get("teamInfo"), 1)
        )

        return team1, team2

    def _nested_team_name(self, value: Any, index: int) -> str:
        if not isinstance(value, list):
            return ""

        if index >= len(value):
            return ""

        team = value[index]

        if isinstance(team, dict):
            return text(
                team.get("name")
                or team.get("teamName")
                or team.get("shortname")
            )

        return text(team)

    def _get_start_time(self, item: Dict[str, Any]) -> Optional[str]:
        for key in (
            "dateTimeGMT",
            "dateTime",
            "startTime",
            "start_time",
            "date",
        ):
            value = item.get(key)

            if value:
                return text(value)

        status = text(item.get("status"))

        # Example:
        # "Match starts at Sep 20, 10:00 GMT"
        if status.lower().startswith("match starts at"):
            return self._parse_start_from_status(status)

        return None

    def _parse_start_from_status(self, status: str) -> Optional[str]:
        raw = status[len("Match starts at"):].strip()

        formats = [
            "%b %d, %H:%M GMT",
            "%B %d, %H:%M GMT",
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(raw, fmt)

                now = datetime.now(timezone.utc)

                dt = dt.replace(
                    year=now.year,
                    tzinfo=timezone.utc,
                )

                if dt < now:
                    dt = dt.replace(year=now.year + 1)

                return dt.isoformat()
            except ValueError:
                continue

        return None

    def _get_scores(self, item: Dict[str, Any]):
        score1 = ""
        score2 = ""

        # Typical CricketData score list
        score = item.get("score")

        if isinstance(score, list):
            if len(score) > 0:
                score1 = self._score_text(score[0])

            if len(score) > 1:
                score2 = self._score_text(score[1])

        elif isinstance(score, dict):
            score1 = self._score_text(score.get("team1"))
            score2 = self._score_text(score.get("team2"))

        # Alternative fields
        if not score1:
            score1 = self._score_text(item.get("score1"))

        if not score2:
            score2 = self._score_text(item.get("score2"))

        return score1, score2

    def _score_text(self, value: Any) -> str:
        if isinstance(value, dict):
            runs = text(value.get("r"))
            wickets = text(value.get("w"))
            overs = text(value.get("o"))

            if runs and wickets and overs:
                return f"{runs}/{wickets} ({overs})"

            if runs and wickets:
                return f"{runs}/{wickets}"

            if runs:
                return runs

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

    def _has_score(self, item: Dict[str, Any]) -> bool:
        score = item.get("score")

        if isinstance(score, list):
            return len(score) > 0

        if isinstance(score, dict):
            return bool(score)

        return bool(
            item.get("score1")
            or item.get("score2")
        )

    def _build_fallback_id(self, item: Dict[str, Any]) -> str:
        team1, team2 = self._get_teams(item)

        start = self._get_start_time(item) or ""

        return "|".join(
            [
                team1,
                team2,
                start,
                text(item.get("series")),
            ]
        )
