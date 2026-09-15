-- =========================================================
-- CrixData PostgreSQL Schema
-- =========================================================

CREATE TABLE IF NOT EXISTS competitions (
    id BIGSERIAL PRIMARY KEY,

    canonical_name VARCHAR(200) NOT NULL,
    short_name VARCHAR(100),

    gender VARCHAR(20),
    competition_type VARCHAR(50),

    country_name VARCHAR(100),
    country_code VARCHAR(20),

    logo_url TEXT,

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (canonical_name, gender)
);


-- =========================================================
-- COMPETITION ALIASES
-- IPL = ipl = Indian Premier League
-- CPL = Caribbean Premier League
-- =========================================================

CREATE TABLE IF NOT EXISTS competition_aliases (
    id BIGSERIAL PRIMARY KEY,

    competition_id BIGINT NOT NULL
        REFERENCES competitions(id)
        ON DELETE CASCADE,

    alias VARCHAR(200) NOT NULL,

    normalized_alias VARCHAR(200) NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (
        competition_id,
        normalized_alias
    )
);

CREATE INDEX IF NOT EXISTS idx_competition_alias_normalized
    ON competition_aliases(normalized_alias);


-- =========================================================
-- SEASONS
-- =========================================================

CREATE TABLE IF NOT EXISTS seasons (
    id BIGSERIAL PRIMARY KEY,

    competition_id BIGINT NOT NULL
        REFERENCES competitions(id)
        ON DELETE CASCADE,

    provider_season_id VARCHAR(100),

    season_name VARCHAR(100) NOT NULL,

    season_start DATE,
    season_end DATE,

    is_current BOOLEAN NOT NULL DEFAULT FALSE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (
        competition_id,
        season_name
    )
);

CREATE INDEX IF NOT EXISTS idx_seasons_competition
    ON seasons(competition_id);


-- =========================================================
-- TEAMS
-- =========================================================

CREATE TABLE IF NOT EXISTS teams (
    id BIGSERIAL PRIMARY KEY,

    canonical_name VARCHAR(200) NOT NULL,

    short_name VARCHAR(100),
    abbreviation VARCHAR(30),

    gender VARCHAR(20),

    country_name VARCHAR(100),
    country_code VARCHAR(20),

    logo_url TEXT,
    flag_url TEXT,

    provider_team_id VARCHAR(100),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_teams_provider_team
    ON teams(provider_team_id)
    WHERE provider_team_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_teams_name
    ON teams(canonical_name);


-- =========================================================
-- TEAM ALIASES
-- =========================================================

CREATE TABLE IF NOT EXISTS team_aliases (
    id BIGSERIAL PRIMARY KEY,

    team_id BIGINT NOT NULL
        REFERENCES teams(id)
        ON DELETE CASCADE,

    alias VARCHAR(200) NOT NULL,

    normalized_alias VARCHAR(200) NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (
        team_id,
        normalized_alias
    )
);

CREATE INDEX IF NOT EXISTS idx_team_alias_normalized
    ON team_aliases(normalized_alias);


-- =========================================================
-- VENUES
-- =========================================================

CREATE TABLE IF NOT EXISTS venues (
    id BIGSERIAL PRIMARY KEY,

    canonical_name VARCHAR(250) NOT NULL,

    city VARCHAR(150),
    region VARCHAR(150),
    country_name VARCHAR(100),
    country_code VARCHAR(20),

    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,

    provider_venue_id VARCHAR(100),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (
        canonical_name,
        city,
        country_name
    )
);

CREATE INDEX IF NOT EXISTS idx_venues_name
    ON venues(canonical_name);


-- =========================================================
-- MATCHES
-- =========================================================

CREATE TABLE IF NOT EXISTS matches (
    id BIGSERIAL PRIMARY KEY,

    competition_id BIGINT
        REFERENCES competitions(id)
        ON DELETE SET NULL,

    season_id BIGINT
        REFERENCES seasons(id)
        ON DELETE SET NULL,

    home_team_id BIGINT
        REFERENCES teams(id)
        ON DELETE SET NULL,

    away_team_id BIGINT
        REFERENCES teams(id)
        ON DELETE SET NULL,

    venue_id BIGINT
        REFERENCES venues(id)
        ON DELETE SET NULL,

    provider VARCHAR(50) NOT NULL,

    provider_match_id VARCHAR(150),

    format VARCHAR(50),

    round_name VARCHAR(150),

    match_number VARCHAR(100),

    gender VARCHAR(20),

    start_time TIMESTAMPTZ,

    status VARCHAR(30) NOT NULL DEFAULT 'upcoming',

    status_text TEXT,

    result_text TEXT,

    home_score TEXT,
    away_score TEXT,

    home_score_json JSONB,
    away_score_json JSONB,

    source_url TEXT,

    raw_json JSONB,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_matches_provider_match
    ON matches(provider, provider_match_id)
    WHERE provider_match_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_matches_competition_season
    ON matches(competition_id, season_id);

CREATE INDEX IF NOT EXISTS idx_matches_start_time
    ON matches(start_time);

CREATE INDEX IF NOT EXISTS idx_matches_status
    ON matches(status);

CREATE INDEX IF NOT EXISTS idx_matches_home_team
    ON matches(home_team_id);

CREATE INDEX IF NOT EXISTS idx_matches_away_team
    ON matches(away_team_id);


-- =========================================================
-- MATCH SCORES / INNINGS
-- =========================================================

CREATE TABLE IF NOT EXISTS match_scores (
    id BIGSERIAL PRIMARY KEY,

    match_id BIGINT NOT NULL
        REFERENCES matches(id)
        ON DELETE CASCADE,

    team_id BIGINT
        REFERENCES teams(id)
        ON DELETE SET NULL,

    innings_number INTEGER,

    runs INTEGER,
    wickets INTEGER,

    overs NUMERIC(6,2),

    score_text TEXT,

    score_json JSONB,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (
        match_id,
        team_id,
        innings_number
    )
);

CREATE INDEX IF NOT EXISTS idx_match_scores_match
    ON match_scores(match_id);


-- =========================================================
-- SEARCH
-- =========================================================

CREATE INDEX IF NOT EXISTS idx_competitions_canonical_name_lower
    ON competitions(LOWER(canonical_name));

CREATE INDEX IF NOT EXISTS idx_competitions_short_name_lower
    ON competitions(LOWER(short_name));

CREATE INDEX IF NOT EXISTS idx_teams_canonical_name_lower
    ON teams(LOWER(canonical_name));

CREATE INDEX IF NOT EXISTS idx_seasons_name_lower
    ON seasons(LOWER(season_name));


-- =========================================================
-- UPDATED_AT HELPER
-- =========================================================

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


DROP TRIGGER IF EXISTS competitions_updated_at
    ON competitions;

CREATE TRIGGER competitions_updated_at
BEFORE UPDATE ON competitions
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();


DROP TRIGGER IF EXISTS teams_updated_at
    ON teams;

CREATE TRIGGER teams_updated_at
BEFORE UPDATE ON teams
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();


DROP TRIGGER IF EXISTS matches_updated_at
    ON matches;

CREATE TRIGGER matches_updated_at
BEFORE UPDATE ON matches
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();


DROP TRIGGER IF EXISTS match_scores_updated_at
    ON match_scores;

CREATE TRIGGER match_scores_updated_at
BEFORE UPDATE ON match_scores
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();


-- =========================================================
-- PROVIDER MAPPINGS
-- =========================================================

CREATE TABLE IF NOT EXISTS competition_sources (
    id BIGSERIAL PRIMARY KEY,

    competition_id BIGINT NOT NULL
        REFERENCES competitions(id)
        ON DELETE CASCADE,

    provider VARCHAR(50) NOT NULL,

    provider_competition_id VARCHAR(150) NOT NULL,

    provider_name VARCHAR(200),

    provider_logo_url TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (
        provider,
        provider_competition_id
    ),

    UNIQUE (
        competition_id,
        provider
    )
);

CREATE INDEX IF NOT EXISTS idx_competition_sources_competition
    ON competition_sources(competition_id);

CREATE INDEX IF NOT EXISTS idx_competition_sources_provider
    ON competition_sources(provider);


-- =========================================================
-- SEASON PROVIDER MAPPINGS
-- =========================================================

CREATE TABLE IF NOT EXISTS season_sources (
    id BIGSERIAL PRIMARY KEY,

    season_id BIGINT NOT NULL
        REFERENCES seasons(id)
        ON DELETE CASCADE,

    provider VARCHAR(50) NOT NULL,

    provider_season_id VARCHAR(150) NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (
        provider,
        provider_season_id
    ),

    UNIQUE (
        season_id,
        provider
    )
);

CREATE INDEX IF NOT EXISTS idx_season_sources_season
    ON season_sources(season_id);


-- =========================================================
-- TEAM PROVIDER MAPPINGS
-- =========================================================

CREATE TABLE IF NOT EXISTS team_sources (
    id BIGSERIAL PRIMARY KEY,

    team_id BIGINT NOT NULL
        REFERENCES teams(id)
        ON DELETE CASCADE,

    provider VARCHAR(50) NOT NULL,

    provider_team_id VARCHAR(150) NOT NULL,

    provider_name VARCHAR(200),

    provider_logo_url TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (
        provider,
        provider_team_id
    ),

    UNIQUE (
        team_id,
        provider
    )
);

CREATE INDEX IF NOT EXISTS idx_team_sources_team
    ON team_sources(team_id);


-- =========================================================
-- UPDATED_AT TRIGGERS
-- =========================================================

DROP TRIGGER IF EXISTS competition_sources_updated_at
    ON competition_sources;

CREATE TRIGGER competition_sources_updated_at
BEFORE UPDATE ON competition_sources
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();


DROP TRIGGER IF EXISTS season_sources_updated_at
    ON season_sources;

CREATE TRIGGER season_sources_updated_at
BEFORE UPDATE ON season_sources
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();


DROP TRIGGER IF EXISTS team_sources_updated_at
    ON team_sources;

CREATE TRIGGER team_sources_updated_at
BEFORE UPDATE ON team_sources
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();
