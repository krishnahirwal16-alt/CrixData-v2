import logging
from typing import Any, Dict, List, Optional

import requests

from config import AppConfig
from database import Database
from seed_data import COMPETITIONS, normalize


logger = logging.getLogger(__name__)


class CricketSync:
    """
    Provider synchronization engine.

    Current responsibility:
    - Resolve CrixData competitions against Highlightly
    - Save provider competition IDs
    - Discover available seasons
    - Save provider season IDs

    Match/team/venue synchronization will be added after
    competition + season resolution is verified.
    """

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

        synced = []
        failed = []

        for competition in COMPETITIONS:

            try:
                result = (
                    self.sync_competition(
                        competition
                    )
                )

                if result:
                    synced.append(result)

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
            "synced":
                synced,
            "failed":
                failed,
            "synced_count":
                len(synced),
            "failed_count":
                len(failed),
        }

    # =====================================================
    # ONE COMPETITION
    # =====================================================

    def sync_competition(
        self,
        competition: Dict[str, Any],
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

        aliases = competition.get(
            "aliases"
        ) or []

        if not canonical_name:
            return None

        provider_league = (
            self._find_provider_league(
                canonical_name,
                aliases,
            )
        )

        if not provider_league:
            logger.warning(
                "No Highlightly league found for %s (%s)",
                canonical_name,
                gender,
            )

            return None

        provider_id = str(
            provider_league.get(
                "id"
            )
            or ""
        )

        provider_name = str(
            provider_league.get(
                "name"
            )
            or canonical_name
        )

        if not provider_id:
            return None

        competition_id = (
            self._get_local_competition_id(
                canonical_name,
                gender,
            )
        )

        if competition_id is None:
            logger.warning(
                "Local competition not found: %s (%s)",
                canonical_name,
                gender,
            )

            return None

        # ---------------------------------------------
        # Save provider competition mapping
        # ---------------------------------------------

        self._upsert_competition_source(
            competition_id=competition_id,
            provider="highlightly",
            provider_competition_id=provider_id,
            provider_name=provider_name,
            provider_logo_url=self._league_logo(
                provider_league
            ),
        )

        # ---------------------------------------------
        # Discover + save seasons
        # ---------------------------------------------

        seasons_saved = (
            self._sync_seasons(
                competition_id=competition_id,
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
                "highlightly",

            "provider_competition_id":
                provider_id,

            "provider_name":
                provider_name,

            "seasons_saved":
                seasons_saved,
        }

    # =====================================================
    # HIGHLIGHTLY LEAGUE SEARCH
    # =====================================================

    def _find_provider_league(
        self,
        canonical_name: str,
        aliases: List[str],
    ) -> Optional[Dict[str, Any]]:

        search_terms = []

        for value in [
            canonical_name,
            *aliases,
        ]:

            value = str(
                value or ""
            ).strip()

            if not value:
                continue

            if value.lower() not in [
                item.lower()
                for item in search_terms
            ]:
                search_terms.append(
                    value
                )

        candidates = []

        for term in search_terms:

            response = (
                self._get(
                    "/leagues",
                    {
                        "leagueName":
                            term,
                        "limit":
                            100,
                        "offset":
                            0,
                    },
                )
            )

            for league in self._extract_data(
                response
            ):

                if isinstance(
                    league,
                    dict,
                ):
                    candidates.append(
                        league
                    )

            # Exact match is enough.
            exact = (
                self._pick_exact_league(
                    candidates,
                    canonical_name,
                    term,
                )
            )

            if exact:
                return exact

        if not candidates:
            return None

        # Fallback: closest normalized match.
        target = normalize(
            canonical_name
        )

        for league in candidates:

            name = normalize(
                league.get(
                    "name"
                )
                or ""
            )

            if name == target:
                return league

        return candidates[0]

    # =====================================================
    # PICK EXACT LEAGUE
    # =====================================================

    def _pick_exact_league(
        self,
        candidates: List[Dict[str, Any]],
        canonical_name: str,
        search_term: str,
    ) -> Optional[Dict[str, Any]]:

        canonical_normalized = normalize(
            canonical_name
        )

        search_normalized = normalize(
            search_term
        )

        # Prefer exact canonical match.
        for league in candidates:

            name = normalize(
                league.get(
                    "name"
                )
                or ""
            )

            if name == canonical_normalized:
                return league

        # Then exact searched-name match.
        for league in candidates:

            name = normalize(
                league.get(
                    "name"
                )
                or ""
            )

            if name == search_normalized:
                return league

        return None

    # =====================================================
    # SEASONS
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
    # SEASON UPSERT
    # =====================================================

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
                "highlightly",
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
    ) -> Dict[str, Any]:

        url = (
            f"{self.base_url}"
            f"{path}"
        )

        response = (
            self.session.get(
                url,
                params=params,
                timeout=30,
            )
        )

        response.raise_for_status()

        payload = response.json()

        if not isinstance(
            payload,
            dict,
        ):
            return {}

        return payload

    # =====================================================
    # RESPONSE DATA
    # =====================================================

    @staticmethod
    def _extract_data(
        payload: Dict[str, Any],
    ) -> List[Dict[str, Any]]:

        data = payload.get(
            "data"
        )

        if isinstance(
            data,
            list,
        ):
            return data

        if isinstance(
            data,
            dict,
        ):
            return [data]

        # Some APIs return the list directly
        # under another wrapper.
        if isinstance(
            payload,
            list,
        ):
            return payload

        return []

    # =====================================================
    # LEAGUE LOGO
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
# MANUAL / LOCAL RUNNER
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
