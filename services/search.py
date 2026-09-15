from typing import Any, Dict, List

from database import Database
from utils import text


class CricketSearch:
    """
    Database-first cricket search service.

    External cricket providers are NOT called here.

    Search sources:
    - competition canonical names
    - competition short names
    - competition aliases
    - seasons
    - team canonical names
    - team short names
    - team aliases
    - saved matches
    """

    def __init__(self):
        self.database = Database()

    # =====================================================
    # PUBLIC SEARCH
    # =====================================================

    def search(
        self,
        query: str,
    ) -> Dict[str, Any]:

        query = text(
            query
        ).strip()

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

        normalized = self._normalize(
            query
        )

        return {
            "ok": True,
            "query": query,

            "suggestions":
                self.get_suggestions(
                    normalized
                ),

            "competitions":
                self._search_competitions(
                    normalized
                ),

            "seasons":
                self._search_seasons(
                    normalized
                ),

            "teams":
                self._search_teams(
                    normalized
                ),

            "matches":
                self._search_matches(
                    normalized
                ),
        }

    # =====================================================
    # AUTOCOMPLETE / SUGGESTIONS
    # =====================================================

    def get_suggestions(
        self,
        query: str,
        limit: int = 12,
    ) -> List[Dict[str, Any]]:

        if not query:
            return []

        suggestions: List[
            Dict[str, Any]
        ] = []

        # -------------------------------------------------
        # Competition aliases
        # -------------------------------------------------

        competition_alias_rows = (
            self.database.execute(
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
        )

        for row in competition_alias_rows:

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

                    "matched_as":
                        row[4],
                }
            )

        # -------------------------------------------------
        # Competition names / short names
        # -------------------------------------------------

        remaining = max(
            0,
            limit - len(suggestions),
        )

        if remaining:

            competition_rows = (
                self.database.execute(
                    """
                    SELECT
                        id,
                        canonical_name,
                        short_name,
                        gender
                    FROM competitions
                    WHERE
                        is_active = TRUE
                        AND (
                            LOWER(canonical_name)
                                LIKE %s
                            OR LOWER(
                                COALESCE(
                                    short_name,
                                    ''
                                )
                            )
                                LIKE %s
                        )
                    ORDER BY
                        canonical_name
                    LIMIT %s;
                    """,
                    (
                        query + "%",
                        query + "%",
                        remaining,
                    ),
                    fetch=True,
                )
            )

            existing_competitions = {
                item["id"]
                for item in suggestions
                if item["type"]
                == "competition"
            }

            for row in competition_rows:

                if row[0] in existing_competitions:
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

        # -------------------------------------------------
        # Team names / short names
        # -------------------------------------------------

        remaining = max(
            0,
            limit - len(suggestions),
        )

        if remaining:

            team_rows = (
                self.database.execute(
                    """
                    SELECT
                        t.id,
                        t.canonical_name,
                        t.short_name,
                        t.gender
                    FROM teams t
                    WHERE
                        LOWER(t.canonical_name)
                            LIKE %s
                        OR LOWER(
                            COALESCE(
                                t.short_name,
                                ''
                            )
                        )
                            LIKE %s
                    ORDER BY
                        t.canonical_name
                    LIMIT %s;
                    """,
                    (
                        query + "%",
                        query + "%",
                        remaining,
                    ),
                    fetch=True,
                )
            )

            for row in team_rows:

                suggestions.append(
                    {
                        "type":
                            "team",

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

        # -------------------------------------------------
        # Team aliases
        # -------------------------------------------------

        remaining = max(
            0,
            limit - len(suggestions),
        )

        if remaining:

            team_alias_rows = (
                self.database.execute(
                    """
                    SELECT
                        t.id,
                        t.canonical_name,
                        t.short_name,
                        t.gender,
                        ta.alias
                    FROM team_aliases ta
                    JOIN teams t
                        ON t.id = ta.team_id
                    WHERE ta.normalized_alias LIKE %s
                    ORDER BY
                        CASE
                            WHEN ta.normalized_alias = %s
                                THEN 0
                            ELSE 1
                        END,
                        t.canonical_name
                    LIMIT %s;
                    """,
                    (
                        query + "%",
                        query,
                        remaining,
                    ),
                    fetch=True,
                )
            )

            for row in team_alias_rows:

                suggestions.append(
                    {
                        "type":
                            "team",

                        "id":
                            row[0],

                        "name":
                            row[1],

                        "short_name":
                            row[2],

                        "gender":
                            row[3],

                        "matched_as":
                            row[4],
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
                ON ca.competition_id =
                   c.id
            WHERE
                c.is_active = TRUE
                AND (
                    LOWER(
                        c.canonical_name
                    )
                        LIKE %s

                    OR LOWER(
                        COALESCE(
                            c.short_name,
                            ''
                        )
                    )
                        LIKE %s

                    OR ca.normalized_alias
                        LIKE %s
                )
            ORDER BY
                CASE
                    WHEN LOWER(
                        c.canonical_name
                    ) = %s
                        THEN 0

                    WHEN LOWER(
                        COALESCE(
                            c.short_name,
                            ''
                        )
                    ) = %s
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
                "id":
                    row[0],

                "name":
                    row[1],

                "short_name":
                    row[2],

                "gender":
                    row[3],

                "competition_type":
                    row[4],

                "country_name":
                    row[5],

                "country_code":
                    row[6],

                "logo_url":
                    row[7],
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
                s.provider_season_id,
                s.season_start,
                s.season_end,
                s.is_current
            FROM seasons s
            JOIN competitions c
                ON c.id = s.competition_id
            WHERE
                LOWER(
                    s.season_name
                )
                    LIKE %s

                OR LOWER(
                    c.canonical_name
                )
                    LIKE %s

                OR LOWER(
                    COALESCE(
                        c.short_name,
                        ''
                    )
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
                "id":
                    row[0],

                "competition_id":
                    row[1],

                "competition_name":
                    row[2],

                "competition_short_name":
                    row[3],

                "season_name":
                    row[4],

                "provider_season_id":
                    row[5],

                "season_start":
                    (
                        row[6].isoformat()
                        if row[6]
                        else None
                    ),

                "season_end":
                    (
                        row[7].isoformat()
                        if row[7]
                        else None
                    ),

                "is_current":
                    row[8],
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
                t.canonical_name,
                t.short_name,
                t.abbreviation,
                t.gender,
                t.country_name,
                t.country_code,
                t.logo_url,
                t.flag_url
            FROM teams t
            LEFT JOIN team_aliases ta
                ON ta.team_id = t.id
            WHERE
                LOWER(
                    t.canonical_name
                )
                    LIKE %s

                OR LOWER(
                    COALESCE(
                        t.short_name,
                        ''
                    )
                )
                    LIKE %s

                OR LOWER(
                    COALESCE(
                        t.abbreviation,
                        ''
                    )
                )
                    LIKE %s

                OR ta.normalized_alias
                    LIKE %s

            ORDER BY
                t.canonical_name

            LIMIT 100;
            """,
            (
                "%" + query + "%",
                "%" + query + "%",
                "%" + query + "%",
                "%" + query + "%",
            ),
            fetch=True,
        )

        return [
            {
                "id":
                    row[0],

                "name":
                    row[1],

                "short_name":
                    row[2],

                "abbreviation":
                    row[3],

                "gender":
                    row[4],

                "country_name":
                    row[5],

                "country_code":
                    row[6],

                "logo_url":
                    row[7],

                "flag_url":
                    row[8],
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
                m.status,
                m.status_text,
                m.result_text,
                m.start_time,

                m.home_team_id,
                home_team.canonical_name,
                home_team.short_name,
                home_team.logo_url,
                home_team.flag_url,

                m.away_team_id,
                away_team.canonical_name,
                away_team.short_name,
                away_team.logo_url,
                away_team.flag_url,

                m.competition_id,
                c.canonical_name,
                c.short_name,

                m.season_id,
                s.season_name,

                m.venue_id,
                v.canonical_name,
                v.city,
                v.region,
                v.country_name,
                v.country_code

            FROM matches m

            LEFT JOIN teams home_team
                ON home_team.id =
                   m.home_team_id

            LEFT JOIN teams away_team
                ON away_team.id =
                   m.away_team_id

            LEFT JOIN competitions c
                ON c.id =
                   m.competition_id

            LEFT JOIN seasons s
                ON s.id =
                   m.season_id

            LEFT JOIN venues v
                ON v.id =
                   m.venue_id

            WHERE

                LOWER(
                    COALESCE(
                        home_team.canonical_name,
                        ''
                    )
                )
                    LIKE %s

                OR LOWER(
                    COALESCE(
                        away_team.canonical_name,
                        ''
                    )
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
                        v.canonical_name,
                        ''
                    )
                )
                    LIKE %s

                OR LOWER(
                    COALESCE(
                        v.city,
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
                "%" + query + "%",
            ),
            fetch=True,
        )

        results = []

        for row in rows:

            results.append(
                {
                    "id":
                        row[0],

                    "provider_match_id":
                        row[1],

                    "provider":
                        row[2],

                    "status":
                        row[3],

                    "status_text":
                        row[4],

                    "result_text":
                        row[5],

                    "start_time":
                        (
                            row[6].isoformat()
                            if row[6]
                            else None
                        ),

                    "home_team":
                        {
                            "id":
                                row[7],

                            "name":
                                row[8],

                            "short_name":
                                row[9],

                            "logo_url":
                                row[10],

                            "flag_url":
                                row[11],
                        },

                    "away_team":
                        {
                            "id":
                                row[12],

                            "name":
                                row[13],

                            "short_name":
                                row[14],

                            "logo_url":
                                row[15],

                            "flag_url":
                                row[16],
                        },

                    "competition":
                        {
                            "id":
                                row[17],

                            "name":
                                row[18],

                            "short_name":
                                row[19],
                        },

                    "season":
                        {
                            "id":
                                row[20],

                            "name":
                                row[21],
                        },

                    "venue":
                        {
                            "id":
                                row[22],

                            "name":
                                row[23],

                            "city":
                                row[24],

                            "region":
                                row[25],

                            "country":
                                row[26],

                            "country_code":
                                row[27],
                        },
                }
            )

        return results

    # =====================================================
    # NORMALIZATION
    # =====================================================

    @staticmethod
    def _normalize(
        value: str,
    ) -> str:

        return " ".join(
            value.lower()
            .strip()
            .split()
        )
