import logging
from typing import Any, Dict, List, Optional, Tuple

import requests

from config import AppConfig
from database import Database
from seed_data import COMPETITIONS, normalize


logger = logging.getLogger(__name__)


class CricketSync:
    """
    Centralized provider synchronization engine.

    Phase 1:
    - Resolve selected CrixData competitions
    - Save provider competition IDs
    - Save provider seasons

    Design:
    - Provider API is queried only when sync is explicitly run.
    - No frontend dependency.
    - Duplicate database rows are avoided.
    - Rate-limit failures stop the sync cleanly.
    """

    PROVIDER_NAME = "highlightly"

    # Keep one provider request per selected competition.
    # We try the canonical name first, then at most ONE alias
    # only when the canonical search finds nothing.
    MAX_LOOKUPS_PER_COMPETITION = 2

    REQUEST_TIMEOUT = 30

    def __init__(self, config: AppConfig):
        self.config = config
        self.database = Database()

        self.base_url = (
            self.config.highlightly_base_url
            .rstrip("/")
        )

        self.api_key = (
            self.config.highlightly_api_key
        )

        self.session = requests.Session()

        self.session.headers.update(
            {
                "x-rapidapi-key": self.api_key,
                "Accept": "application/json",
            }
        )

    # =====================================================
    # PUBLIC ENTRY POINT
    # =====================================================

    def sync_selected_competitions(self) -> Dict[str, Any]:
        if not self.api_key:
            raise RuntimeError(
                "HIGHLIGHTLY_API_KEY is not configured."
            )

        synced = []
        failed = []

        total_requests = 0
        rate_limited = False

        for competition in COMPETITIONS:

            try:
                result, requests_used = (
                    self.sync_competition(
                        competition
                    )
                )

                total_requests += requests_used

                if result:
                    synced.append(result)
                else:
                    failed.append(
                        {
                            "competition":
                                competition.get(
                                    "canonical_name"
                                ),
                            "gender":
                                competition.get(
                                    "gender"
                                ),
                            "error":
                                "Provider league not confidently resolved.",
                        }
                    )

            except RateLimitError as exc:

                rate_limited = True

                failed.append(
                    {
                        "competition":
                            competition.get(
                                "canonical_name"
                            ),
                        "gender":
                            competition.get(
                                "gender"
                            ),
                        "error":
                            str(exc),
                    }
                )

                # Do NOT continue hammering the provider.
                break

            except Exception as exc:

                logger.exception(
                    "Competition sync failed: %s",
                    competition.get(
                        "canonical_name"
                    ),
                )

                failed.append(
                    {
                        "competition":
                            competition.get(
                                "canonical_name"
                            ),
                        "gender":
                            competition.get(
                                "gender"
                            ),
                        "error":
                            str(exc),
                    }
                )

        return {
            "ok": True,
            "provider": self.PROVIDER_NAME,
            "synced": synced,
            "failed": failed,
            "synced_count": len(synced),
            "failed_count": len(failed),
            "api_requests_used": total_requests,
            "rate_limited": rate_limited,
        }

    # =====================================================
    # ONE COMPETITION
    # =====================================================

    def sync_competition(
        self,
        competition: Dict[str, Any],
    ) -> Tuple[Optional[Dict[str, Any]], int]:

        canonical_name = str(
            competition.get(
                "canonical_name"
            )
            or ""
        ).strip()

        gender = str(
            competition.get(
                "gender"
            )
            or ""
        ).strip().lower()

        aliases = [
            str(alias).strip()
            for alias in (
                competition.get(
                    "aliases"
                )
                or []
            )
            if str(alias).strip()
        ]

        if not canonical_name:
            return None, 0

        competition_id = (
            self._get_local_competition_id(
                canonical_name,
                gender,
            )
        )

        if competition_id is None:
            return None, 0

        # ---------------------------------------------
        # Search canonical name first.
        # ---------------------------------------------

        search_terms = [
            canonical_name
        ]

        # ---------------------------------------------
        # At most ONE fallback alias.
        # Prefer the short name first.
        # ---------------------------------------------

        short_name = str(
            competition.get(
                "short_name"
            )
            or ""
        ).strip()

        if (
            short_name
            and normalize(short_name)
            != normalize(canonical_name)
        ):
            search_terms.append(
                short_name
            )

        if len(search_terms) < 2:
            for alias in aliases:

                if (
                    normalize(alias)
                    != normalize(canonical_name)
                ):
                    search_terms.append(
                        alias
                    )

                if len(search_terms) >= 2:
                    break

        search_terms = search_terms[
            :self.MAX_LOOKUPS_PER_COMPETITION
        ]

        provider_league = None
        requests_used = 0

        for term in search_terms:

            provider_league = (
                self._find_provider_league(
                    term,
                    gender,
                )
            )

            requests_used += 1

            if provider_league:
                break

        if not provider_league:
            return None, requests_used

        provider_id = str(
            provider_league.get(
                "id"
            )
            or ""
        ).strip()

        provider_name = str(
            provider_league.get(
                "name"
            )
            or canonical_name
        ).strip()

        if not provider_id:
            return None, requests_used

        # ---------------------------------------------
        # Save competition → provider mapping.
        # ---------------------------------------------

        self._upsert_competition_source(
            competition_id=
                competition_id,
            provider=
                self.PROVIDER_NAME,
            provider_competition_id=
                provider_id,
            provider_name=
                provider_name,
            provider_logo_url=
                self._league_logo(
                    provider_league
                ),
        )

        # ---------------------------------------------
        # Save seasons.
        # ---------------------------------------------

        seasons_saved = (
            self._sync_seasons(
                competition_id=
                    competition_id,
                provider_league=
                    provider_league,
            )
        )

        return (
            {
                "competition_id":
                    competition_id,

                "canonical_name":
                    canonical_name,

                "gender":
                    gender,

                "provider":
                    self.PROVIDER_NAME,

                "provider_competition_id":
                    provider_id,

                "provider_name":
                    provider_name,

                "seasons_saved":
                    seasons_saved,
            },
            requests_used,
        )

    # =====================================================
    # PROVIDER LEAGUE SEARCH
    # =====================================================

    def _find_provider_league(
        self,
        search_term: str,
        gender: str,
    ) -> Optional[Dict[str, Any]]:

        payload, _headers = self._get(
            "/leagues",
            {
                "leagueName":
                    search_term,
                "limit":
                    100,
                "offset":
                    0,
            },
        )

        leagues = (
            self._extract_leagues(
                payload
            )
        )

        if not leagues:
            return None

        return self._choose_best_league(
            leagues,
            search_term,
            gender,
        )

    # =====================================================
    # BEST PROVIDER LEAGUE
    # =====================================================

    def _choose_best_league(
        self,
        leagues: List[Dict[str, Any]],
        search_term: str,
        gender: str,
    ) -> Optional[Dict[str, Any]]:

        target = normalize(
            search_term
        )

        best = None
        best_score = 0

        for league in leagues:

            provider_name = normalize(
                league.get(
                    "name"
                )
                or ""
            )

            if not provider_name:
                continue

            score = self._name_score(
                provider_name,
                target,
            )

            provider_gender = normalize(
                str(
                    league.get(
                        "gender"
                    )
                    or ""
                )
            )

            if provider_gender:

                if gender in (
                    "women",
                    "female",
                ):
                    if (
                        "women"
                        in provider_gender
                        or "female"
                        in provider_gender
                    ):
                        score += 20

                elif gender in (
                    "men",
                    "male",
                ):
                    if (
                        "men"
                        in provider_gender
                        or "male"
                        in provider_gender
                    ):
                        score += 20

            if score > best_score:

                best_score = score
                best = league

        # Require a reasonably strong name match.
        if best_score < 60:
            return None

        return best

    # =====================================================
    # NAME MATCH
    # =====================================================

    @staticmethod
    def _name_score(
        provider_name: str,
        target: str,
    ) -> int:

        if provider_name == target:
            return 100

        if (
            provider_name in target
            or target in provider_name
        ):
            return 85

        provider_tokens = set(
            provider_name.split()
        )

        target_tokens = set(
            target.split()
        )

        if not provider_tokens or not target_tokens:
            return 0

        overlap = len(
            provider_tokens
            & target_tokens
        )

        ratio = (
            overlap
            / max(
                len(target_tokens),
                1,
            )
        )

        if ratio >= 0.75:
            return 75

        if ratio >= 0.50:
            return 60

        return 0

    # =====================================================
    # LOCAL COMPETITION
    # =====================================================

    def _get_local_competition_id(
        self,
        canonical_name: str,
        gender: str,
    ) -> Optional[int]:

        result = self.database.execute(
            """
            SELECT id
            FROM competitions
            WHERE canonical_name = %s
              AND gender = %s
            LIMIT 1;
            """,
            (
                canonical_name,
                gender,
            ),
            fetch=True,
        )

        if not result:
            return None

        return int(
            result[0][0]
        )

    # =====================================================
    # COMPETITION SOURCE
    # =====================================================

    def _upsert_competition_source(
        self,
        competition_id: int,
        provider: str,
        provider_competition_id: str,
        provider_name: str,
        provider_logo_url: Optional[str],
    ):

        self.database.execute(
            """
            INSERT INTO competition_sources (
                competition_id,
                provider,
                provider_competition_id,
                provider_name,
                provider_logo_url
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s
            )
            ON CONFLICT (
                competition_id,
                provider
            )
            DO UPDATE SET
                provider_competition_id =
                    EXCLUDED.provider_competition_id,
                provider_name =
                    EXCLUDED.provider_name,
                provider_logo_url =
                    EXCLUDED.provider_logo_url,
                updated_at =
                    NOW();
            """,
            (
                competition_id,
                provider,
                provider_competition_id,
                provider_name,
                provider_logo_url,
            ),
        )

    # =====================================================
    # SEASONS
    # =====================================================

    def _sync_seasons(
        self,
        competition_id: int,
        provider_league: Dict[str, Any],
    ) -> int:

        seasons = (
            provider_league.get(
                "seasons"
            )
            or []
        )

        saved = 0

        for item in seasons:

            if not isinstance(
                item,
                dict,
            ):
                continue

            provider_season_id = (
                item.get("id")
                or item.get("season")
            )

            season_value = (
                item.get("season")
                or item.get("name")
            )

            if (
                provider_season_id is None
                and season_value is None
            ):
                continue

            season_name = str(
                season_value
                or provider_season_id
            ).strip()

            provider_season_id = str(
                provider_season_id
                or season_name
            )

            season_id = (
                self._upsert_season(
                    competition_id=
                        competition_id,
                    season_name=
                        season_name,
                    provider_season_id=
                        provider_season_id,
                )
            )

            if season_id is not None:
                saved += 1

        return saved

    def _upsert_season(
        self,
        competition_id: int,
        season_name: str,
        provider_season_id: str,
    ) -> Optional[int]:

        result = self.database.execute(
            """
            INSERT INTO seasons (
                competition_id,
                provider_season_id,
                season_name
            )
            VALUES (
                %s,
                %s,
                %s
            )
            ON CONFLICT (
                competition_id,
                season_name
            )
            DO UPDATE SET
                provider_season_id =
                    EXCLUDED.provider_season_id
            RETURNING id;
            """,
            (
                competition_id,
                provider_season_id,
                season_name,
            ),
            fetch=True,
        )

        if not result:
            return None

        season_id = int(
            result[0][0]
        )

        self.database.execute(
            """
            INSERT INTO season_sources (
                season_id,
                provider,
                provider_season_id
            )
            VALUES (
                %s,
                %s,
                %s
            )
            ON CONFLICT (
                season_id,
                provider
            )
            DO UPDATE SET
                provider_season_id =
                    EXCLUDED.provider_season_id,
                updated_at =
                    NOW();
            """,
            (
                season_id,
                self.PROVIDER_NAME,
                provider_season_id,
            ),
        )

        return season_id

    # =====================================================
    # HTTP
    # =====================================================

    def _get(
        self,
        path: str,
        params: Dict[str, Any],
    ) -> Tuple[
        Dict[str, Any],
        Dict[str, Any],
    ]:

        url = (
            f"{self.base_url}"
            f"{path}"
        )

        response = self.session.get(
            url,
            params=params,
            timeout=self.REQUEST_TIMEOUT,
        )

        headers = dict(
            response.headers
        )

        # ---------------------------------------------
        # Rate limit
        # ---------------------------------------------

        if response.status_code == 429:

            remaining = (
                headers.get(
                    "x-ratelimit-requests-remaining"
                )
            )

            limit = (
                headers.get(
                    "x-ratelimit-requests-limit"
                )
            )

            retry_after = (
                headers.get(
                    "Retry-After"
                )
            )

            raise RateLimitError(
                "Highlightly rate limit reached "
                f"(remaining={remaining}, "
                f"limit={limit}, "
                f"retry_after={retry_after}). "
                "Stop now and retry only after the quota resets."
            )

        response.raise_for_status()

        payload = response.json()

        if not isinstance(
            payload,
            dict,
        ):
            return {}, headers

        return payload, headers

    # =====================================================
    # RESPONSE PARSER
    # =====================================================

    @staticmethod
    def _extract_leagues(
        payload: Dict[str, Any],
    ) -> List[Dict[str, Any]]:

        if not isinstance(
            payload,
            dict,
        ):
            return []

        data = payload.get(
            "data"
        )

        if not isinstance(
            data,
            list,
        ):
            return []

        return [
            item
            for item in data
            if isinstance(
                item,
                dict,
            )
        ]

    # =====================================================
    # LOGO
    # =====================================================

    @staticmethod
    def _league_logo(
        league: Dict[str, Any],
    ) -> Optional[str]:

        logo = league.get(
            "logo"
        )

        if logo:
            return str(
                logo
            )

        return None


class RateLimitError(Exception):
    """Provider API rate-limit exception."""


# =========================================================
# MANUAL RUNNER
# =========================================================

def run_sync():

    config = (
        AppConfig.from_env()
    )

    sync = CricketSync(
        config
    )

    return (
        sync.sync_selected_competitions()
    )


if __name__ == "__main__":

    logging.basicConfig(
        level=logging.INFO,
    )

    result = run_sync()

    print(result)
