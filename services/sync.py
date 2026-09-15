import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from config import AppConfig
from database import Database
from seed_data import COMPETITIONS, normalize


logger = logging.getLogger(__name__)


class CricketSync:
    """
    Centralized Highlightly synchronization engine.

    Design goals:
    - Avoid alias-by-alias API requests.
    - Discover leagues in paginated batches.
    - Resolve CrixData competitions locally.
    - Save provider competition mappings.
    - Save provider seasons.
    - Respect API rate limits.
    - Keep this layer independent from the frontend.
    """

    PROVIDER_NAME = "highlightly"

    # Highlightly documents a maximum league limit of 100.
    LEAGUE_PAGE_SIZE = 100

    # Safety limit so a broken API response cannot cause
    # an endless pagination loop.
    MAX_LEAGUE_PAGES = 20

    # Small delay between API pages.
    REQUEST_DELAY_SECONDS = 0.35

    def __init__(
        self,
        config: AppConfig,
    ):
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
                "x-rapidapi-key":
                    self.api_key,
                "Accept":
                    "application/json",
            }
        )

    # =====================================================
    # PUBLIC ENTRY POINT
    # =====================================================

    def sync_selected_competitions(
        self,
    ) -> Dict[str, Any]:

        if not self.api_key:
            raise RuntimeError(
                "HIGHLIGHTLY_API_KEY is not configured."
            )

        # -------------------------------------------------
        # Fetch the provider league catalog once, in pages.
        # -------------------------------------------------

        leagues = self._get_all_provider_leagues()

        if not leagues:
            return {
                "ok": False,
                "synced": [],
                "failed": [
                    {
                        "error":
                            "No Highlightly leagues were returned."
                    }
                ],
                "synced_count": 0,
                "failed_count": len(COMPETITIONS),
                "provider_league_count": 0,
            }

        synced = []
        failed = []

        # -------------------------------------------------
        # Resolve all local competitions against the same
        # provider catalog. No alias-by-alias API calls.
        # -------------------------------------------------

        for competition in COMPETITIONS:

            try:

                result = (
                    self._sync_competition_from_catalog(
                        competition=competition,
                        provider_leagues=leagues,
                    )
                )

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
                                "No confident provider league match found.",
                        }
                    )

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
            "synced": synced,
            "failed": failed,
            "synced_count": len(synced),
            "failed_count": len(failed),
            "provider_league_count":
                len(leagues),
        }

    # =====================================================
    # PROVIDER LEAGUE CATALOG
    # =====================================================

    def _get_all_provider_leagues(
        self,
    ) -> List[Dict[str, Any]]:

        all_leagues = []

        offset = 0
        page_number = 0
        total_count = None

        while page_number < self.MAX_LEAGUE_PAGES:

            page_number += 1

            payload, headers = (
                self._get(
                    "/leagues",
                    {
                        "limit":
                            self.LEAGUE_PAGE_SIZE,
                        "offset":
                            offset,
                    },
                )
            )

            page_leagues = (
                self._extract_leagues(
                    payload
                )
            )

            if not page_leagues:
                break

            all_leagues.extend(
                page_leagues
            )

            pagination = (
                payload.get(
                    "pagination"
                )
                if isinstance(
                    payload,
                    dict,
                )
                else {}
            )

            if isinstance(
                pagination,
                dict,
            ):

                raw_total = pagination.get(
                    "totalCount"
                )

                try:
                    total_count = (
                        int(raw_total)
                        if raw_total is not None
                        else None
                    )
                except (
                    TypeError,
                    ValueError,
                ):
                    total_count = None

            # ---------------------------------------------
            # Rate-limit logging
            # ---------------------------------------------

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

            logger.info(
                "Highlightly leagues page=%s offset=%s received=%s remaining=%s limit=%s",
                page_number,
                offset,
                len(page_leagues),
                remaining,
                limit,
            )

            # ---------------------------------------------
            # Stop conditions
            # ---------------------------------------------

            if total_count is not None:

                if len(all_leagues) >= total_count:
                    break

            if (
                len(page_leagues)
                < self.LEAGUE_PAGE_SIZE
            ):
                break

            offset += (
                self.LEAGUE_PAGE_SIZE
            )

            if (
                self.REQUEST_DELAY_SECONDS
                > 0
            ):
                time.sleep(
                    self.REQUEST_DELAY_SECONDS
                )

        logger.info(
            "Highlightly league catalog loaded: %s leagues.",
            len(all_leagues),
        )

        return all_leagues

    # =====================================================
    # COMPETITION RESOLUTION
    # =====================================================

    def _sync_competition_from_catalog(
        self,
        competition: Dict[str, Any],
        provider_leagues:
            List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:

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
            str(item).strip()
            for item in (
                competition.get(
                    "aliases"
                )
                or []
            )
            if str(item).strip()
        ]

        provider_league = (
            self._choose_provider_league(
                canonical_name=
                    canonical_name,
                aliases=
                    aliases,
                gender=
                    gender,
                provider_leagues=
                    provider_leagues,
            )
        )

        if not provider_league:

            logger.warning(
                "No provider league match found for %s (%s).",
                canonical_name,
                gender,
            )

            return None

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
            return None

        competition_id = (
            self._get_local_competition_id(
                canonical_name=
                    canonical_name,
                gender=
                    gender,
            )
        )

        if competition_id is None:
            return None

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

        seasons_saved = (
            self._sync_seasons(
                competition_id=
                    competition_id,
                provider_league=
                    provider_league,
            )
        )

        return {
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
        }

    # =====================================================
    # LOCAL PROVIDER MATCHING
    # =====================================================

    def _choose_provider_league(
        self,
        canonical_name: str,
        aliases: List[str],
        gender: str,
        provider_leagues:
            List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:

        search_names = [
            canonical_name,
            *aliases,
        ]

        normalized_targets = []

        for value in search_names:

            key = normalize(
                value
            )

            if (
                key
                and key not in normalized_targets
            ):
                normalized_targets.append(
                    key
                )

        if not normalized_targets:
            return None

        best_candidate = None
        best_score = 0

        for league in provider_leagues:

            provider_name = normalize(
                league.get(
                    "name"
                )
                or ""
            )

            if not provider_name:
                continue

            score = (
                self._match_score(
                    provider_name=
                        provider_name,
                    target_names=
                        normalized_targets,
                )
            )

            if score <= 0:
                continue

            # ---------------------------------------------
            # Gender preference.
            #
            # Provider responses may not always expose
            # gender, so this is a preference, not a hard
            # requirement.
            # ---------------------------------------------

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

                    if "women" in provider_gender:
                        score += 8

                elif gender in (
                    "men",
                    "male",
                ):

                    if (
                        "men"
                        in provider_gender
                    ):
                        score += 8

            if score > best_score:

                best_score = score
                best_candidate = league

        return best_candidate

    @staticmethod
    def _match_score(
        provider_name: str,
        target_names: List[str],
    ) -> int:

        best = 0

        provider_tokens = set(
            provider_name.split()
        )

        for target in target_names:

            if not target:
                continue

            # Exact normalized match.
            if provider_name == target:
                best = max(
                    best,
                    100,
                )
                continue

            target_tokens = set(
                target.split()
            )

            if not target_tokens:
                continue

            # Provider contains target.
            if target in provider_name:
                best = max(
                    best,
                    85,
                )

            # Target contains provider name.
            if provider_name in target:
                best = max(
                    best,
                    80,
                )

            # Token overlap.
            overlap = len(
                provider_tokens
                & target_tokens
            )

            if overlap:

                ratio = (
                    overlap
                    / max(
                        len(
                            target_tokens
                        ),
                        1,
                    )
                )

                if ratio >= 0.75:
                    best = max(
                        best,
                        70,
                    )
                elif ratio >= 0.5:
                    best = max(
                        best,
                        55,
                    )

        return best

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
    # COMPETITION SOURCE UPSERT
    # =====================================================

    def _upsert_competition_source(
        self,
        competition_id: int,
        provider: str,
        provider_competition_id: str,
        provider_name: str,
        provider_logo_url:
            Optional[str],
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
    # SEASON SYNC
    # =====================================================

    def _sync_seasons(
        self,
        competition_id: int,
        provider_league:
            Dict[str, Any],
    ) -> int:

        saved = 0

        seasons = (
            provider_league.get(
                "seasons"
            )
            or []
        )

        for item in seasons:

            if not isinstance(
                item,
                dict,
            ):
                continue

            provider_season_id = (
                item.get(
                    "id"
                )
                or item.get(
                    "season"
                )
            )

            season_value = (
                item.get(
                    "season"
                )
                or item.get(
                    "name"
                )
            )

            if (
                provider_season_id
                is None
                and season_value
                is None
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
    # HTTP REQUEST
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
            timeout=30,
        )

        # -------------------------------------------------
        # Handle rate limiting explicitly.
        # -------------------------------------------------

        if response.status_code == 429:

            remaining = response.headers.get(
                "x-ratelimit-requests-remaining"
            )

            limit = response.headers.get(
                "x-ratelimit-requests-limit"
            )

            retry_after = response.headers.get(
                "Retry-After"
            )

            raise RuntimeError(
                "Highlightly rate limit reached "
                f"(remaining={remaining}, "
                f"limit={limit}, "
                f"retry_after={retry_after}). "
                "Do not repeatedly retry until the quota resets."
            )

        response.raise_for_status()

        payload = response.json()

        if not isinstance(
            payload,
            dict,
        ):
            return {}, dict(
                response.headers
            )

        return (
            payload,
            dict(
                response.headers
            ),
        )

    # =====================================================
    # RESPONSE HELPERS
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

        value = league.get(
            "logo"
        )

        if value:
            return str(
                value
            )

        return None


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
