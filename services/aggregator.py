from datetime import datetime, timezone
from threading import Lock
from time import time
from typing import Any, Dict, List, Optional

from config import AppConfig
from models import Match
from services.base import CricketProvider
from services.cricketdata import CricketDataProvider
from services.highlightly import HighlightlyProvider
from utils import parse_datetime, text


class CricketAggregator:
    def __init__(self, config: AppConfig):
        self.config = config

        self.providers: List[CricketProvider] = [
            HighlightlyProvider(config),
            CricketDataProvider(config),
        ]

        self._cache: Optional[Dict[str, Any]] = None
        self._cache_time: float = 0
        self._lock = Lock()

    def get_feed(self) -> Dict[str, Any]:
        now = time()

        with self._lock:
            if (
                self._cache is not None
                and now - self._cache_time < self.config.cache_seconds
            ):
                return self._cache

            feed = self._build_feed()

            self._cache = feed
            self._cache_time = now

            return feed

    def get_match_details(self, match_id: str) -> Dict[str, Any]:
        match = self._find_match(match_id)

        if not match:
            return {
                "ok": False,
                "error": "Match not found",
                "match_id": match_id,
            }

        if match.provider == "highlightly":
            provider = self._get_provider("highlightly")

            if provider:
                details = provider.get_details(match)

                return {
                    "ok": True,
                    "match_id": match.id,
                    "provider": match.provider,
                    "details": details,
                }

        return {
            "ok": True,
            "match_id": match.id,
            "provider": match.provider,
            "details": match.raw,
        }

    def _build_feed(self) -> Dict[str, Any]:
        all_matches: List[Match] = []
        errors: List[Dict[str, str]] = []

        for provider in self.providers:
            try:
                matches = provider.get_matches()
                all_matches.extend(matches)

            except Exception as exc:
                errors.append(
                    {
                        "provider": provider.__class__.__name__,
                        "error": str(exc),
                    }
                )

        merged = self._merge_matches(all_matches)

        merged = [
            match
            for match in merged
            if self._is_valid_match(match)
        ]

        live = [
            match
            for match in merged
            if match.status == "live"
        ]

        upcoming = [
            match
            for match in merged
            if match.status == "upcoming"
        ]

        finished = [
            match
            for match in merged
            if match.status == "finished"
        ]

        live.sort(key=self._sort_key)
        upcoming.sort(key=self._sort_key)
        finished.sort(key=self._sort_key, reverse=True)

        return {
            "ok": True,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "timezone": self.config.timezone,
            "counts": {
                "live": len(live),
                "upcoming": len(upcoming),
                "finished": len(finished),
                "total": len(merged),
            },
            "live": [self._serialize(match) for match in live],
            "upcoming": [self._serialize(match) for match in upcoming],
            "finished": [self._serialize(match) for match in finished],
            "errors": errors,
        }

    def _merge_matches(self, matches: List[Match]) -> List[Match]:
        result: Dict[str, Match] = {}

        for match in matches:
            key = self._merge_key(match)

            if key not in result:
                result[key] = match
                continue

            result[key] = self._combine(result[key], match)

        return list(result.values())

    def _merge_key(self, match: Match) -> str:
        teams = sorted(
            [
                text(match.team1).lower(),
                text(match.team2).lower(),
            ]
        )

        competition = text(match.competition).lower()

        # Don't let vague "Other Cricket" prevent cross-provider merging.
        if competition == "other cricket":
            competition = ""

        start_bucket = ""

        dt = parse_datetime(match.start_time)

        if dt:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)

            timestamp = int(dt.timestamp())
            bucket = timestamp // (30 * 60)
            start_bucket = str(bucket)

        return "|".join(
            [
                teams[0],
                teams[1],
                competition,
                start_bucket,
            ]
        )

    def _combine(self, first: Match, second: Match) -> Match:
        # Prefer the provider with richer information.
        primary = first
        secondary = second

        if self._information_score(second) > self._information_score(first):
            primary = second
            secondary = first

        primary.provider_ids = list(
            dict.fromkeys(
                first.provider_ids + second.provider_ids
            )
        )

        if not primary.team1:
            primary.team1 = secondary.team1

        if not primary.team2:
            primary.team2 = secondary.team2

        if not primary.competition:
            primary.competition = secondary.competition

        if not primary.match_type:
            primary.match_type = secondary.match_type

        if not primary.team1_score:
            primary.team1_score = secondary.team1_score

        if not primary.team2_score:
            primary.team2_score = secondary.team2_score

        if not primary.status_text:
            primary.status_text = secondary.status_text

        if not primary.start_time:
            primary.start_time = secondary.start_time

        if not primary.venue:
            primary.venue = secondary.venue

        if not primary.details_url:
            primary.details_url = secondary.details_url

        # A live status from either provider should win over upcoming.
        statuses = {first.status, second.status}

        if "live" in statuses:
            primary.status = "live"
        elif "finished" in statuses:
            primary.status = "finished"
        else:
            primary.status = "upcoming"

        return primary

    def _information_score(self, match: Match) -> int:
        score = 0

        for value in (
            match.competition,
            match.match_type,
            match.team1,
            match.team2,
            match.team1_score,
            match.team2_score,
            match.status_text,
            match.start_time,
            match.venue,
        ):
            if text(value):
                score += 1

        return score

    def _is_valid_match(self, match: Match) -> bool:
        if not text(match.team1) or not text(match.team2):
            return False

        team1 = text(match.team1).lower()
        team2 = text(match.team2).lower()

        if team1 == team2:
            return False

        return True

    def _sort_key(self, match: Match):
        dt = parse_datetime(match.start_time)

        if dt is None:
            return datetime.max.replace(tzinfo=timezone.utc)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt

    def _serialize(self, match: Match) -> Dict[str, Any]:
        return {
            "id": match.id,
            "provider": match.provider,
            "provider_ids": match.provider_ids,
            "competition": match.competition,
            "match_type": match.match_type,
            "team1": match.team1,
            "team2": match.team2,
            "team1_score": match.team1_score,
            "team2_score": match.team2_score,
            "status": match.status,
            "status_text": match.status_text,
            "start_time": match.start_time,
            "venue": match.venue,
            "details_url": match.details_url,
        }

    def _find_match(self, match_id: str) -> Optional[Match]:
        feed = self.get_feed()

        for section in (
            "live",
            "upcoming",
            "finished",
        ):
            for item in feed.get(section, []):
                if item.get("id") == match_id:
                    return self._deserialize(item)

        return None

    def _deserialize(self, item: Dict[str, Any]) -> Match:
        return Match(
            id=text(item.get("id")),
            provider=text(item.get("provider")),
            provider_ids=item.get("provider_ids") or [],
            competition=text(item.get("competition")),
            match_type=text(item.get("match_type")),
            team1=text(item.get("team1")),
            team2=text(item.get("team2")),
            team1_score=text(item.get("team1_score")),
            team2_score=text(item.get("team2_score")),
            status=text(item.get("status")) or "upcoming",
            status_text=text(item.get("status_text")),
            start_time=item.get("start_time"),
            venue=text(item.get("venue")),
            details_url=text(item.get("details_url")),
        )

    def _get_provider(self, name: str) -> Optional[CricketProvider]:
        for provider in self.providers:
            if (
                provider.__class__.__name__.lower()
                == f"{name}provider".lower()
            ):
                return provider

        return None
