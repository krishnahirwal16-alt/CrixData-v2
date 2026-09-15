from typing import Any, Dict, List

from database import Database
from utils import text


class CricketSearch:
    """
    Database-first cricket search service.

    Search order:
    1. Competition aliases
    2. Competition names
    3. Season names
    4. Team aliases/names
    5. Match/team/competition data

    This service does NOT call external providers.
    Therefore normal search uses zero API requests.
    """

    def __init__(self):
        self.database = Database()

    # =====================================================
    # MAIN SEARCH
    # =====================================================

    def search(self, query: str) -> Dict[str, Any]:
        query = text(query).strip()

        if not query:
            return {
                "ok": True,
                "query": "",
                "suggestions": [],
                "competitions": [],
                "seasons": [],
                "teams": [],
                "matches": [],
            }

        normalized = self._normalize(query)

        suggestions = (
            self.get_suggestions(normalized)
        )

        competitions = (
            self._search_competitions(
                normalized
            )
        )

        seasons = (
            self._search_seasons(
                normalized
            )
        )

        teams = (
            self._search_teams(
                normalized
            )
        )

        matches = (
            self._search_matches(
                normalized
            )
        )

        return {
            "ok": True,
            "query": query,
            "suggestions": suggestions,
            "competitions": competitions,
            "seasons": seasons,
            "teams": teams,
            "matches": matches,
        }

    # =====================================================
    # AUTOCOMPLETE
    # =====================================================

    def get_suggestions(
        self,
        query: str,
        limit: int = 12,
    ) -> List[Dict[str, Any]]:

        if not query:
            return []

        suggestions = []

        # ---------------------------------------------
        # Competition aliases
        # ---------------------------------------------

        competition_rows = self.database.execute(
            """
            SELECT
                c.id,
                c.canonical_name,
                c.short_name,
                c.gender,
                ca.alias
            FROM competition_aliases ca
            JOIN competitions c
                ON c.id = ca.competition_id
            WHERE ca.normalized_alias LIKE %s
            ORDER BY
                CASE
                    WHEN ca.normalized_alias = %s
                    THEN 0
                    WHEN ca.normalized_alias LIKE %s
                    THEN 1
                    ELSE 2
                END,
                c.canonical_name
            LIMIT %s;
            """,
            (
                query + "%",
                query,
                query + "%",
                limit,
            ),
            fetch=True,
        )

        for row in competition_rows:

            suggestions.append(
                {
                    "type": "competition",
                    "id": row[0],
                    "name": row[1],
                    "short_name": row[2],
                    "gender": row[3],
                    "matched_as": row[4],
                }
            )

        # ---------------------------------------------
        # Competition canonical names
        # ---------------------------------------------

        remaining = max(
            0,
            limit - len(suggestions),
        )

        if remaining:

            competition_rows = self.database.execute(
                """
                SELECT
                    id,
                    canonical_name,
                    short_name,
                    gender
                FROM competitions
                WHERE LOWER(canonical_name)
                      LIKE %s
                   OR LOWER(short_name)
                      LIKE %s
                ORDER BY canonical_name
                LIMIT %s;
                """,
                (
                    query + "%",
                    query + "%",
                    remaining,
                ),
                fetch=True,
            )

            existing_ids = {
                item["id"]
                for item in suggestions
                if item["type"] == "competition"
            }

            for row in competition_rows:

                if row[0] in existing_ids:
                    continue

                suggestions.append(
                    {
                        "type":
                            "competition",

                        "id":
                            row[0],

                        "name":
                            row[1],

                        "short_name":
                            row[2],

                        "gender":
                            row[3],
                    }
                )

        # ---------------------------------------------
        # Teams
        # ---------------------------------------------

        remaining = max(
            0,
            limit - len(suggestions),
        )

        if remaining:

            team_rows = self.database.execute(
                """
                SELECT
                    id,
                    name,
                    short_name,
                    gender
                FROM teams
                WHERE LOWER(name)
                      LIKE %s
                   OR LOWER(COALESCE(short_name, ''))
                      LIKE %s
                ORDER BY name
                LIMIT %s;
                """,
                (
                    query + "%",
                    query + "%",
                    remaining,
                ),
                fetch=True,
            )

            for row in team_rows:

                suggestions.append(
                    {
                        "type": "team",
                        "id": row[0],
                        "name": row[1],
                        "short_name": row[2],
                        "gender": row[3],
                    }
                )

        return suggestions[:limit]

    # =====================================================
    # COMPETITIONS
    # =====================================================

    def _search_competitions(
        self,
        query: str,
    ) -> List[Dict[str, Any]]:

        rows = self.database.execute(
            """
            SELECT DISTINCT
                c.id,
                c.canonical_name,
                c.short_name,
                c.gender,
                c.competition_type,
                c.country_name,
                c.country_code,
                c.logo_url
            FROM competitions c
            LEFT JOIN competition_aliases ca
                ON ca.competition_id = c.id
            WHERE
                c.is_active = TRUE
                AND (
                    LOWER(c.canonical_name)
                        LIKE %s
                    OR LOWER(
                        COALESCE(c.short_name, '')
                    )
                        LIKE %s
                    OR ca.normalized_alias
                        LIKE %s
                )
            ORDER BY
                CASE
                    WHEN LOWER(c.canonical_name)
                        = %s
                    THEN 0
                    WHEN LOWER(
                        COALESCE(c.short_name, '')
                    )
                        = %s
                    THEN 0
                    ELSE 1
                END,
                c.canonical_name
            LIMIT 50;
            """,
            (
                "%" + query + "%",
                "%" + query + "%",
                "%" + query + "%",
                query,
                query,
            ),
            fetch=True,
        )

        return [
            {
                "id": row[0],
                "name": row[1],
                "short_name": row[2],
                "gender": row[3],
                "competition_type": row[4],
                "country_name": row[5],
                "country_code": row[6],
                "logo_url": row[7],
            }
            for row in rows
        ]

    # =====================================================
    # SEASONS
    # =====================================================

    def _search_seasons(
        self,
        query: str,
    ) -> List[Dict[str, Any]]:

        rows = self.database.execute(
            """
            SELECT
                s.id,
                s.competition_id,
                c.canonical_name,
                c.short_name,
                s.season_name,
                s.provider_season_id
            FROM seasons s
            JOIN competitions c
                ON c.id = s.competition_id
            WHERE LOWER(s.season_name)
                  LIKE %s
               OR LOWER(c.canonical_name)
                  LIKE %s
               OR LOWER(
                    COALESCE(c.short_name, '')
                  )
                  LIKE %s
            ORDER BY
                s.season_name DESC
            LIMIT 100;
            """,
            (
                "%" + query + "%",
                "%" + query + "%",
                "%" + query + "%",
            ),
            fetch=True,
        )

        return [
            {
                "id": row[0],
                "competition_id": row[1],
                "competition_name": row[2],
                "competition_short_name": row[3],
                "season_name": row[4],
                "provider_season_id": row[5],
            }
            for row in rows
        ]

    # =====================================================
    # TEAMS
    # =====================================================

    def _search_teams(
        self,
        query: str,
    ) -> List[Dict[str, Any]]:

        rows = self.database.execute(
            """
            SELECT DISTINCT
                t.id,
                t.name,
                t.short_name,
                t.gender,
                t.country_name,
                t.country_code,
                t.logo_url
            FROM teams t
            LEFT JOIN team_aliases ta
                ON ta.team_id = t.id
            WHERE
                LOWER(t.name)
                    LIKE %s
                OR LOWER(
                    COALESCE(t.short_name, '')
                )
                    LIKE %s
                OR LOWER(
                    COALESCE(
                        ta.alias,
                        ''
                    )
                )
                    LIKE %s
            ORDER BY t.name
            LIMIT 100;
            """,
            (
                "%" + query + "%",
                "%" + query + "%",
                "%" + query + "%",
            ),
            fetch=True,
        )

        return [
            {
                "id": row[0],
                "name": row[1],
                "short_name": row[2],
                "gender": row[3],
                "country_name": row[4],
                "country_code": row[5],
                "logo_url": row[6],
            }
            for row in rows
        ]

    # =====================================================
    # MATCHES
    # =====================================================

    def _search_matches(
        self,
        query: str,
    ) -> List[Dict[str, Any]]:

        rows = self.database.execute(
            """
            SELECT
                m.id,
                m.provider_match_id,
                m.provider,
                m.match_status,
                m.start_time,
                m.team1_id,
                t1.name,
                t1.logo_url,
                m.team2_id,
                t2.name,
                t2.logo_url,
                m.competition_id,
                c.canonical_name,
                c.short_name,
                m.season_id,
                s.season_name,
                m.venue_id,
                v.name,
                v.city,
                v.country_name
            FROM matches m

            LEFT JOIN teams t1
                ON t1.id = m.team1_id

            LEFT JOIN teams t2
                ON t2.id = m.team2_id

            LEFT JOIN competitions c
                ON c.id = m.competition_id

            LEFT JOIN seasons s
                ON s.id = m.season_id

            LEFT JOIN venues v
                ON v.id = m.venue_id

            WHERE
                LOWER(
                    COALESCE(t1.name, '')
                )
                    LIKE %s

                OR LOWER(
                    COALESCE(t2.name, '')
                )
                    LIKE %s

                OR LOWER(
                    COALESCE(
                        c.canonical_name,
                        ''
                    )
                )
                    LIKE %s

                OR LOWER(
                    COALESCE(
                        c.short_name,
                        ''
                    )
                )
                    LIKE %s

                OR LOWER(
                    COALESCE(
                        s.season_name,
                        ''
                    )
                )
                    LIKE %s

                OR LOWER(
                    COALESCE(
                        v.name,
                        ''
                    )
                )
                    LIKE %s

            ORDER BY
                m.start_time DESC NULLS LAST

            LIMIT 200;
            """,
            (
                "%" + query + "%",
                "%" + query + "%",
                "%" + query + "%",
                "%" + query + "%",
                "%" + query + "%",
                "%" + query + "%",
            ),
            fetch=True,
        )

        results = []

        for row in rows:

            results.append(
                {
                    "id": row[0],
                    "provider_match_id": row[1],
                    "provider": row[2],
                    "status": row[3],
                    "start_time": (
                        row[4].isoformat()
                        if row[4]
                        else None
                    ),

                    "team1": {
                        "id": row[5],
                        "name": row[6],
                        "logo_url": row[7],
                    },

                    "team2": {
                        "id": row[8],
                        "name": row[9],
                        "logo_url": row[10],
                    },

                    "competition": {
                        "id": row[11],
                        "name": row[12],
                        "short_name": row[13],
                    },

                    "season": {
                        "id": row[14],
                        "name": row[15],
                    },

                    "venue": {
                        "id": row[16],
                        "name": row[17],
                        "city": row[18],
                        "country": row[19],
                    },
                }
            )

        return results

    # =====================================================
    # NORMALIZATION
    # =====================================================

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(
            value.lower().strip().split()
        )
