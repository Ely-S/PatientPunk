PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ══════════════════════════════════════════════════════
-- LAYER 1: Raw social media data
-- ══════════════════════════════════════════════════════

CREATE TABLE users (
    user_id          TEXT PRIMARY KEY,
    source_subreddit TEXT NOT NULL,
    scraped_at       INTEGER NOT NULL
);

CREATE TABLE posts (
    post_id    TEXT PRIMARY KEY,
    title      TEXT, 
    parent_id  TEXT REFERENCES posts(post_id),
    user_id    TEXT NOT NULL REFERENCES users(user_id),
    body_text  TEXT NOT NULL,
    flair   TEXT,
    post_date  INTEGER,
    scraped_at INTEGER NOT NULL,
    metadata   TEXT                 -- JSON: score, upvotes, flair, etc.
);

CREATE INDEX idx_posts_user ON posts(user_id);
CREATE INDEX idx_posts_date ON posts(post_date);
CREATE INDEX idx_posts_parent ON posts(parent_id);

-- ══════════════════════════════════════════════════════
-- LAYER 2: Configuration
-- ══════════════════════════════════════════════════════

CREATE TABLE treatment (
    id              INTEGER PRIMARY KEY,
    canonical_name  TEXT NOT NULL COLLATE NOCASE UNIQUE,
    treatment_class TEXT,
    aliases         TEXT,   -- JSON array: ["LDN", "Revia"]
    notes           TEXT
);

CREATE INDEX idx_treatment_canonical ON treatment(canonical_name);

CREATE TABLE extraction_runs (
    run_id  INTEGER PRIMARY KEY,
    run_at  INTEGER NOT NULL,
    commit_hash TEXT NOT NULL,
    extraction_type TEXT NOT NULL,
    config  TEXT NOT NULL   -- JSON: models, prompt, version, temperature, etc.
);

-- ══════════════════════════════════════════════════════
-- LAYER 3: Extracted data
-- ══════════════════════════════════════════════════════

CREATE TABLE user_profiles (
    user_id    TEXT NOT NULL REFERENCES users(user_id),
    run_id     INTEGER NOT NULL REFERENCES extraction_runs(run_id),
    age_bucket TEXT,
    sex        TEXT,
    location   TEXT,
    PRIMARY KEY (user_id, run_id)
);

CREATE TABLE conditions (
    condition_id   INTEGER PRIMARY KEY,
    run_id         INTEGER NOT NULL REFERENCES extraction_runs(run_id),
    user_id        TEXT NOT NULL REFERENCES users(user_id),
    post_id        TEXT REFERENCES posts(post_id),
    condition_type TEXT NOT NULL CHECK (condition_type IN ('illness', 'symptom')),
    condition_name TEXT NOT NULL,
    diagnosed_at   TEXT,
    resolved_at    TEXT,
    severity       TEXT
);

CREATE INDEX idx_cond_user ON conditions(user_id);
CREATE INDEX idx_cond_name ON conditions(condition_name COLLATE NOCASE);
CREATE INDEX idx_cond_run  ON conditions(run_id);

CREATE TABLE treatment_reports (
    report_id       INTEGER PRIMARY KEY,
    run_id          INTEGER NOT NULL REFERENCES extraction_runs(run_id),
    post_id         TEXT NOT NULL REFERENCES posts(post_id),
    user_id         TEXT REFERENCES users(user_id),
    drug_id         INTEGER NOT NULL REFERENCES treatment(id),
    sentiment       TEXT NOT NULL,
    signal_strength TEXT NOT NULL,
    side_effects    TEXT              -- JSON array of lowercase symptom strings, or NULL/[] if none
);

CREATE INDEX idx_tr_post ON treatment_reports(post_id);
CREATE INDEX idx_tr_drug ON treatment_reports(drug_id);
CREATE INDEX idx_tr_user ON treatment_reports(user_id);
CREATE INDEX idx_tr_run  ON treatment_reports(run_id);

-- One row per dose the author states they took, per treatment report.
-- Written by src/run_dose_pipeline.py after the sentiment pipeline; amounts are
-- stored as stated (a range keeps low and high) with the sentence they came from.
CREATE TABLE report_doses (
    dose_id   INTEGER PRIMARY KEY,
    report_id INTEGER NOT NULL REFERENCES treatment_reports(report_id),
    run_id    INTEGER NOT NULL REFERENCES extraction_runs(run_id),
    ordinal   INTEGER NOT NULL,
    low       REAL NOT NULL,
    high      REAL NOT NULL,
    unit      TEXT,                   -- as the author wrote it (mg, mL, IU, drops, capsules...); NULL for a bare number
    route     TEXT,
    outcome   TEXT CHECK (outcome IN ('positive', 'negative', 'neutral', 'unclear')),
    quote     TEXT
);
CREATE INDEX idx_rd_report ON report_doses(report_id);
-- Runs append; nothing is deleted. Each report's rows from its most recent dose run:
CREATE VIEW IF NOT EXISTS report_doses_latest AS
    SELECT d.* FROM report_doses d
    WHERE d.run_id = (SELECT MAX(run_id) FROM report_doses WHERE report_id = d.report_id);

-- One row per effect the author says the drug had on them, per treatment report.
-- Written by src/run_effects_pipeline.py after the dose step; an effect the author ties
-- to a stated dose points at that report_doses row.
CREATE TABLE report_effects (
    effect_id   INTEGER PRIMARY KEY,
    report_id   INTEGER NOT NULL REFERENCES treatment_reports(report_id),
    run_id      INTEGER NOT NULL REFERENCES extraction_runs(run_id),
    ordinal     INTEGER NOT NULL,
    domain      TEXT NOT NULL,       -- one of the run's domain list, recorded in extraction_runs.config
    symptom     TEXT NOT NULL,       -- the author's own words for what changed
    direction   TEXT NOT NULL CHECK (direction IN ('improved', 'worsened', 'no_change', 'mixed')),
    attribution TEXT NOT NULL CHECK (attribution IN ('target', 'stack', 'unclear', 'other compound')),
    quote       TEXT NOT NULL,       -- verbatim sentence from the post
    dose_id     INTEGER REFERENCES report_doses(dose_id)  -- NULL unless the author ties the effect to a stated dose
);
CREATE INDEX idx_re_report ON report_effects(report_id);
-- Runs append; nothing is deleted. Each report's rows from its most recent effects run:
CREATE VIEW IF NOT EXISTS report_effects_latest AS
    SELECT e.* FROM report_effects e
    WHERE e.run_id = (SELECT MAX(run_id) FROM report_effects WHERE report_id = e.report_id);

-- ══════════════════════════════════════════════════════
-- Extracted variables (EAV)
-- ══════════════════════════════════════════════════════
-- One row per non-empty extracted cell from records.csv, including the
-- inductively-discovered variables.  load_extractions() maps a fixed set of
-- demographic/condition columns into user_profiles/conditions; this table keeps
-- the FULL wide variable matrix queryable.  Loaded by db.load_variables().
-- (The wide, one-column-per-variable `unified` table that load_db.py also builds
--  is data-driven -- created by pandas to_sql(), not declared here.)
CREATE TABLE variables (
    variable_id INTEGER PRIMARY KEY,
    run_id  INTEGER NOT NULL REFERENCES extraction_runs(run_id),
    user_id TEXT NOT NULL REFERENCES users(user_id),
    post_id TEXT,                 -- no FK: user-history records have no single post
    field   TEXT NOT NULL,
    value   TEXT NOT NULL         -- raw cell text; multi-values keep " | "
);

CREATE INDEX idx_var_user  ON variables(user_id);
CREATE INDEX idx_var_field ON variables(field);
CREATE INDEX idx_var_run   ON variables(run_id);
