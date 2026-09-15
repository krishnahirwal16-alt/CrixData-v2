from database import Database


# =========================================================
# CrixData Competition Catalog
# =========================================================
#
# IMPORTANT:
# These are canonical names + aliases only.
# Provider league IDs and seasons will be discovered later
# from the provider sync layer.
#
# This file is intentionally centralized so that adding a
# new competition later does not require frontend changes.
# =========================================================

COMPETITIONS = [
    {
        "canonical_name": "Indian Premier League",
        "short_name": "IPL",
        "gender": "men",
        "competition_type": "league",
        "country_name": "India",
        "country_code": "IN",
        "aliases": [
            "IPL",
            "ipl",
            "Indian Premier League",
            "indian premier league",
        ],
    },
    {
        "canonical_name": "Women's Premier League",
        "short_name": "WPL",
        "gender": "women",
        "competition_type": "league",
        "country_name": "India",
        "country_code": "IN",
        "aliases": [
            "WPL",
            "wpl",
            "Women's Premier League",
            "Womens Premier League",
            "women premier league",
        ],
    },
    {
        "canonical_name": "Big Bash League",
        "short_name": "BBL",
        "gender": "men",
        "competition_type": "league",
        "country_name": "Australia",
        "country_code": "AU",
        "aliases": [
            "BBL",
            "bbl",
            "Big Bash",
            "Big Bash League",
        ],
    },
    {
        "canonical_name": "Women's Big Bash League",
        "short_name": "WBBL",
        "gender": "women",
        "competition_type": "league",
        "country_name": "Australia",
        "country_code": "AU",
        "aliases": [
            "WBBL",
            "wbbl",
            "Women's Big Bash",
            "Womens Big Bash",
            "Women's Big Bash League",
            "Womens Big Bash League",
        ],
    },
    {
        "canonical_name": "Caribbean Premier League",
        "short_name": "CPL",
        "gender": "men",
        "competition_type": "league",
        "country_name": "West Indies",
        "country_code": "WI",
        "aliases": [
            "CPL",
            "cpl",
            "Caribbean Premier League",
        ],
    },
    {
        "canonical_name": "Women's Caribbean Premier League",
        "short_name": "WCPL",
        "gender": "women",
        "competition_type": "league",
        "country_name": "West Indies",
        "country_code": "WI",
        "aliases": [
            "WCPL",
            "wcpl",
            "Women's Caribbean Premier League",
            "Womens Caribbean Premier League",
        ],
    },
    {
        "canonical_name": "Pakistan Super League",
        "short_name": "PSL",
        "gender": "men",
        "competition_type": "league",
        "country_name": "Pakistan",
        "country_code": "PK",
        "aliases": [
            "PSL",
            "psl",
            "Pakistan Super League",
        ],
    },
    {
        "canonical_name": "SA20",
        "short_name": "SA20",
        "gender": "men",
        "competition_type": "league",
        "country_name": "South Africa",
        "country_code": "ZA",
        "aliases": [
            "SA20",
            "sa20",
            "SA 20",
            "South Africa T20",
        ],
    },
    {
        "canonical_name": "Lanka Premier League",
        "short_name": "LPL",
        "gender": "men",
        "competition_type": "league",
        "country_name": "Sri Lanka",
        "country_code": "LK",
        "aliases": [
            "LPL",
            "lpl",
            "Lanka Premier League",
            "Sri Lanka Premier League",
        ],
    },
    {
        "canonical_name": "The Hundred",
        "short_name": "The Hundred Men",
        "gender": "men",
        "competition_type": "league",
        "country_name": "England",
        "country_code": "GB",
        "aliases": [
            "The Hundred",
            "Hundred",
            "The Hundred Men",
            "Hundred Men",
        ],
    },
    {
        "canonical_name": "The Hundred",
        "short_name": "The Hundred Women",
        "gender": "women",
        "competition_type": "league",
        "country_name": "England",
        "country_code": "GB",
        "aliases": [
            "The Hundred Women",
            "Hundred Women",
            "Women's Hundred",
            "Womens Hundred",
        ],
    },
    {
        "canonical_name": "Major League Cricket",
        "short_name": "MLC",
        "gender": "men",
        "competition_type": "league",
        "country_name": "United States",
        "country_code": "US",
        "aliases": [
            "MLC",
            "mlc",
            "Major League Cricket",
        ],
    },
    {
        "canonical_name": "International League T20",
        "short_name": "ILT20",
        "gender": "men",
        "competition_type": "league",
        "country_name": "United Arab Emirates",
        "country_code": "AE",
        "aliases": [
            "ILT20",
            "ilt20",
            "International League T20",
            "International League T20",
        ],
    },
    {
        "canonical_name": "Abu Dhabi T10",
        "short_name": "Abu Dhabi T10",
        "gender": "men",
        "competition_type": "t10",
        "country_name": "United Arab Emirates",
        "country_code": "AE",
        "aliases": [
            "Abu Dhabi T10",
            "Abu Dhabi T10 League",
            "T10 League",
            "T10",
        ],
    },
    {
        "canonical_name": "European T20 Premier League",
        "short_name": "ETPL",
        "gender": "men",
        "competition_type": "league",
        "country_name": "Europe",
        "country_code": None,
        "aliases": [
            "ETPL",
            "etpl",
            "European T20 Premier League",
        ],
    },
    {
        "canonical_name": "Major India Domestic Cricket",
        "short_name": "India Domestic",
        "gender": "men",
        "competition_type": "domestic",
        "country_name": "India",
        "country_code": "IN",
        "aliases": [
            "India Domestic",
            "Indian Domestic",
            "Major India Domestic",
            "Ranji Trophy",
            "Vijay Hazare Trophy",
            "Syed Mushtaq Ali Trophy",
            "Duleep Trophy",
            "Irani Cup",
        ],
    },
    {
        "canonical_name": "International Cricket",
        "short_name": "International Men",
        "gender": "men",
        "competition_type": "international",
        "country_name": None,
        "country_code": None,
        "aliases": [
            "International",
            "International Cricket",
            "International Men",
            "Men's International Cricket",
        ],
    },
    {
        "canonical_name": "International Cricket",
        "short_name": "International Women",
        "gender": "women",
        "competition_type": "international",
        "country_name": None,
        "country_code": None,
        "aliases": [
            "International Women",
            "Women's International Cricket",
            "Womens International Cricket",
        ],
    },
]


def normalize(value: str) -> str:
    """
    Creates a stable search key.

    Example:
        ' Indian Premier League '
        → 'indian premier league'
    """

    return " ".join(
        str(value)
        .strip()
        .lower()
        .split()
    )


def seed_competitions():
    """
    Insert competitions and aliases without creating duplicates.

    This function is safe to run more than once.
    """

    database = Database()

    connection = database.connect()

    try:
        with connection.cursor() as cursor:

            for competition in COMPETITIONS:

                cursor.execute(
                    """
                    INSERT INTO competitions (
                        canonical_name,
                        short_name,
                        gender,
                        competition_type,
                        country_name,
                        country_code,
                        is_active
                    )
                    VALUES (
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        TRUE
                    )
                    ON CONFLICT (
                        canonical_name,
                        gender
                    )
                    DO UPDATE SET
                        short_name =
                            EXCLUDED.short_name,
                        competition_type =
                            EXCLUDED.competition_type,
                        country_name =
                            EXCLUDED.country_name,
                        country_code =
                            EXCLUDED.country_code,
                        is_active = TRUE
                    RETURNING id;
                    """,
                    (
                        competition["canonical_name"],
                        competition["short_name"],
                        competition["gender"],
                        competition["competition_type"],
                        competition["country_name"],
                        competition["country_code"],
                    ),
                )

                row = cursor.fetchone()

                if not row:
                    continue

                competition_id = row[0]

                for alias in competition["aliases"]:

                    normalized_alias = normalize(
                        alias
                    )

                    cursor.execute(
                        """
                        INSERT INTO competition_aliases (
                            competition_id,
                            alias,
                            normalized_alias
                        )
                        VALUES (
                            %s,
                            %s,
                            %s
                        )
                        ON CONFLICT (
                            competition_id,
                            normalized_alias
                        )
                        DO NOTHING;
                        """,
                        (
                            competition_id,
                            alias,
                            normalized_alias,
                        ),
                    )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()

    return len(COMPETITIONS)


if __name__ == "__main__":
    count = seed_competitions()

    print(
        f"Seeded {count} CrixData competitions."
    )
