# SCHEMA — Health Intelligence Platform

Version 1.0 | June 2026

Canonical reference for all database work. Read before touching any migration or query.

Claude Code: @-import this file in CLAUDE.md for every session involving the database.

## Migration Sequence

Ordering is determined by FK dependencies. Do not reorder.

```
001 — protocol_items          no FK to health_events — must precede it
002 — health_events           FK to protocol_items + users
003 — event_sources           FK to health_events
004 — health_markers          FK to health_events + users
005 — marker_aliases          standalone
006 — unknown_markers         standalone
007 — health_metrics          FK to users only; independent chain
008 — metric_type_aliases     standalone
009 — unknown_metric_types    standalone
010 — workout_metrics         FK to health_events + users
011 — derived_metrics         FK to users
012 — vendor_metrics          FK to users
013 — daily_metric_summaries  materialized view — last
014 — user_health_state       PLACEHOLDER — design after first data flowing
015 — hevy_exercise_templates FK to users (owner_user_id, nullable) — otherwise standalone
016 — exercise_region_tags    FK to hevy_exercise_templates (CASCADE) — app-owned annotation
017 — cbti_blocks             FK to users (CASCADE) — append-only titration block ledger
018 — cbti_prescriptions      FK to cbti_blocks (CASCADE) + self (superseded_by) — append-only window ledger
019 — cbti_isi                FK to cbti_blocks (SET NULL, nullable) — ISI outcome-measure administrations
020 — capability_observations FK to users (CASCADE) — append-only capability measurement ledger
021 — interpretation_rephrases  no FK — disposable plain-register overlay + promotion state
022 — marker_canonical_entries  FK to users (created_by_user_id, SET NULL, nullable) — runtime-mutable canonical marker map
025 — hevy_workouts            FK to users (CASCADE) — persisted Hevy workout headers (Q6 load lane)
026 — hevy_sets                FK to hevy_workouts (CASCADE) — per-set grain; exercise_template_id NOT an FK (#79/#81)
027 — load_events              FK to users (CASCADE) — derived per-session-window load; source_ref soft (no FK), source-neutral (Q6 gate 2)
```

**Alembic caveats** — autogenerate never produces these, always hand-written:

- Materialized views
- Partial indexes (WHERE ended_at IS NULL, WHERE source_ref IS NOT NULL)
- CHECK constraints on event_type
- Seed data inserts (marker_aliases)

Railway deploys auto-run alembic upgrade head. Commit migration files before pushing.

## Core Design Principles

- **Raw physiological signals only in health_metrics** — whitelisted canonical types; vendor composites rejected at ingest gate
- **Our derivations in derived_metrics** — RMSSD, RHR, sleep efficiency, TRIMP, zones all computed from raw; formula_version enables clean reprocessing
- **Vendor composites in vendor_metrics** — display only; never algorithm inputs; UI must label them explicitly as device-reported
- **Device agnostic** — source field abstracts hardware; connector normalisation layer translates vendor field names before data reaches schema; new integrations are integration problems, not schema problems
- **Provenance tracked** — event_sources table; one canonical event row, many source registrations; source authority hierarchy determines canonical
- **Lab markers normalised** — marker_aliases maps all raw lab names to canonical; unknown_markers catches misses at runtime for admin review
- **Wearable metric types normalised** — same pattern via metric_type_aliases and unknown_metric_types
- **Confidence tagged** — derived_metrics.confidence mirrors the platform's interpretive epistemology: high / moderate / low / guessing

## Table Definitions

### 001 — protocol_items

Point-in-time protocol state. One row per supplement/medication per active period. Paired event written to health_events for timeline narrative.

```sql
CREATE TABLE protocol_items (
    id              BIGSERIAL PRIMARY KEY,
    user_id         INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    item_type       VARCHAR(30) NOT NULL,        -- 'supplement' | 'medication' | 'intervention'
    item_name       VARCHAR(200) NOT NULL,
    brand           VARCHAR(200),
    dose            VARCHAR(100),
    frequency       VARCHAR(100),
    timing          VARCHAR(200),
    started_at      DATE NOT NULL,
    ended_at        DATE,                        -- NULL = currently active
    reason          TEXT,
    source          VARCHAR(100),               -- 'self' | 'physician' | 'dr_smith'
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Fast active-stack query
CREATE INDEX idx_protocol_items_active
    ON protocol_items (user_id, started_at)
    WHERE ended_at IS NULL;

-- Protocol changes in date range (confound window queries)
CREATE INDEX idx_protocol_items_range
    ON protocol_items (user_id, started_at, ended_at);
```

Key queries:

```sql
-- Active stack on a given date
SELECT * FROM protocol_items
WHERE user_id = $1
  AND started_at <= $2
  AND (ended_at IS NULL OR ended_at > $2);

-- Changes in confound window before lab panel
SELECT * FROM protocol_items
WHERE user_id = $1
  AND (started_at BETWEEN $window_start AND $panel_date
    OR (ended_at IS NOT NULL AND ended_at BETWEEN $window_start AND $panel_date));
```

### 002 — health_events

Unified health timeline spine. Every module writes events here. All other structured tables hang off this via event_id FK.

```sql
CREATE TABLE health_events (
    id               BIGSERIAL PRIMARY KEY,
    user_id          INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_type       VARCHAR(50) NOT NULL,
    event_date       TIMESTAMPTZ NOT NULL,
    source           VARCHAR(100),              -- 'polar' | 'samsung_health' | 'hevy' | 'manual'
    source_ref       VARCHAR(255),              -- external ID for event_sources dedup
    protocol_item_id BIGINT REFERENCES protocol_items(id),  -- set for supplement_add/remove events
    payload          JSONB DEFAULT '{}',
    notes            TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT event_type_valid CHECK (event_type IN (
        'lab_panel',
        'biomarker_single',     -- one-off reading outside a panel
        'readiness_score',      -- computed composite output
        'protocol_change',
        'supplement_add',
        'supplement_remove',
        'medication_add',
        'medication_remove',
        'imaging',              -- DEXA, MRI, X-ray — details in payload
        'injury',
        'wearable_daily',       -- ring/band daily summary spine entry
        'wearable_workout',     -- session from Hevy or device
        'manual_observation'
    ))
);

CREATE INDEX idx_health_events_user_date
    ON health_events (user_id, event_date DESC);

CREATE INDEX idx_health_events_user_type_date
    ON health_events (user_id, event_type, event_date DESC);

-- Imaging and other rich payload queries
CREATE INDEX idx_health_events_payload
    ON health_events USING GIN (payload);
```

### 003 — event_sources

Provenance registry. Decouples "real-world event happened once" from "multiple systems reported it." One health_events row per real event; one event_sources row per system that saw it.

```sql
CREATE TABLE event_sources (
    id           BIGSERIAL PRIMARY KEY,
    event_id     BIGINT NOT NULL REFERENCES health_events(id) ON DELETE CASCADE,
    source       VARCHAR(100) NOT NULL,
    source_ref   VARCHAR(255) NOT NULL,
    is_canonical BOOLEAN NOT NULL DEFAULT FALSE,
    raw_payload  JSONB,
    received_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_event_sources UNIQUE (source, source_ref)
);

CREATE INDEX idx_event_sources_event ON event_sources (event_id);
```

Ingest funnel (three stages):

```python
SOURCE_AUTHORITY = {
    # Higher index = higher authority (richer data, more trusted)
    'wearable_workout': ['health_connect', 'samsung_health', 'strava', 'polar', 'hevy'],
    'wearable_daily':   ['health_connect', 'samsung_health', 'polar'],
}

FUZZY_WINDOW_MINUTES = {
    'wearable_workout': 10,   # session start can drift across systems
    'hrv':              5,
}

# Stage 1: exact dup — same source + source_ref — skip entirely
# Stage 2: fuzzy time match — different source, same real event
#          → register new event_sources row
#          → authority check: does new source outrank canonical?
#          → if yes, upgrade canonical source and update health_events.payload
# Stage 3: new event — create health_events row + canonical event_sources row
```

### 004 — health_markers

Structured lab marker storage. One row per marker per panel. Hangs off lab_panel events.

```sql
CREATE TABLE health_markers (
    id                  BIGSERIAL PRIMARY KEY,
    user_id             INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_id            BIGINT NOT NULL REFERENCES health_events(id) ON DELETE CASCADE,
    marker_name         VARCHAR(100) NOT NULL,   -- canonical name from marker_aliases
    marker_display_name VARCHAR(150),
    marker_category     VARCHAR(50),             -- 'metabolic' | 'lipid' | 'hormonal' | 'thyroid' | ...
    value_numeric       NUMERIC,
    value_text          VARCHAR(100),            -- for qualitative: 'positive' | 'detected'
    unit                VARCHAR(30),
    reference_low       NUMERIC,                 -- lab's reference range at time of test
    reference_high      NUMERIC,
    flag                VARCHAR(10),             -- 'low' | 'normal' | 'high' | 'critical'
    measured_at         DATE NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Primary trending query: same marker across dates
CREATE INDEX idx_health_markers_trending
    ON health_markers (user_id, marker_name, measured_at DESC);

-- Category-level queries for interpretation layer
CREATE INDEX idx_health_markers_category
    ON health_markers (user_id, marker_category, measured_at DESC);
```

### 005 — marker_aliases

Maps raw lab report names to canonical marker names. Covers AU labs (Sonic/SNP/QML/Laverty) and US labs (Quest/LabCorp) plus common variants.

```sql
CREATE TABLE marker_aliases (
    id              SERIAL PRIMARY KEY,
    raw_name        VARCHAR(200) UNIQUE NOT NULL,
    canonical_name  VARCHAR(100) NOT NULL,       -- lowercase_snake_case
    display_name    VARCHAR(150),                -- what the user sees
    category        VARCHAR(50)                  -- drives interpretation layer grouping
);
```

Canonical name convention: lowercase_snake_case. Display name is title case. Category is the grouping key for the interpretation screen.

Seed categories and key aliases:

```sql
-- HAEMATOLOGY
('Haemoglobin', 'haemoglobin', 'Haemoglobin', 'haematology'),
('Hemoglobin',  'haemoglobin', 'Haemoglobin', 'haematology'),
('Hb',          'haemoglobin', 'Haemoglobin', 'haematology'),
('Haematocrit', 'haematocrit', 'Haematocrit', 'haematology'),
('Hematocrit',  'haematocrit', 'Haematocrit', 'haematology'),
('Hct',         'haematocrit', 'Haematocrit', 'haematology'),
('RBC', 'rbc', 'RBC', 'haematology'),
('Red Blood Cell Count', 'rbc', 'RBC', 'haematology'),
('WBC', 'wbc', 'WBC', 'haematology'),
('White Blood Cell Count', 'wbc', 'WBC', 'haematology'),
('Platelet Count', 'platelets', 'Platelets', 'haematology'),
('Platelets', 'platelets', 'Platelets', 'haematology'),
('MCV', 'mcv', 'MCV', 'haematology'),
('Neutrophils', 'neutrophils', 'Neutrophils', 'haematology'),
('Lymphocytes', 'lymphocytes', 'Lymphocytes', 'haematology'),
('Monocytes', 'monocytes', 'Monocytes', 'haematology'),
('Eosinophils', 'eosinophils', 'Eosinophils', 'haematology'),
('Basophils', 'basophils', 'Basophils', 'haematology'),
-- IRON STUDIES
('Ferritin', 'ferritin', 'Ferritin', 'iron'),
('Serum Ferritin', 'ferritin', 'Ferritin', 'iron'),
('Serum Iron', 'serum_iron', 'Serum Iron', 'iron'),
('Transferrin', 'transferrin', 'Transferrin', 'iron'),
('Transferrin Saturation', 'transferrin_sat', 'Transferrin Sat %', 'iron'),
('Iron Saturation', 'transferrin_sat', 'Transferrin Sat %', 'iron'),
('% Saturation', 'transferrin_sat', 'Transferrin Sat %', 'iron'),
('TIBC', 'tibc', 'TIBC', 'iron'),
('Total Iron Binding Capacity', 'tibc', 'TIBC', 'iron'),
-- GLUCOSE / METABOLIC
('HbA1c', 'hba1c', 'HbA1c', 'metabolic'),
('Hemoglobin A1c', 'hba1c', 'HbA1c', 'metabolic'),
('Haemoglobin A1c', 'hba1c', 'HbA1c', 'metabolic'),
('Glycated Haemoglobin', 'hba1c', 'HbA1c', 'metabolic'),
('A1C', 'hba1c', 'HbA1c', 'metabolic'),
('Glucose', 'glucose', 'Glucose', 'metabolic'),
('Fasting Glucose', 'glucose', 'Glucose', 'metabolic'),
('Plasma Glucose', 'glucose', 'Glucose', 'metabolic'),
('Insulin', 'insulin', 'Insulin', 'metabolic'),
('Fasting Insulin', 'insulin', 'Insulin', 'metabolic'),
('HOMA-IR', 'homa_ir', 'HOMA-IR', 'metabolic'),
('Uric Acid', 'uric_acid', 'Uric Acid', 'metabolic'),
('Urate', 'uric_acid', 'Uric Acid', 'metabolic'),
('C-Peptide', 'c_peptide', 'C-Peptide', 'metabolic'),
('Fasting C-Peptide', 'c_peptide', 'C-Peptide', 'metabolic'),
-- RENAL / ELECTROLYTES
('eGFR', 'egfr', 'eGFR', 'renal'),
('Estimated GFR', 'egfr', 'eGFR', 'renal'),
('Creatinine', 'creatinine', 'Creatinine', 'renal'),
('Serum Creatinine', 'creatinine', 'Creatinine', 'renal'),
('Urea', 'urea', 'Urea', 'renal'),
('BUN', 'urea', 'Urea', 'renal'),
('Blood Urea Nitrogen', 'urea', 'Urea', 'renal'),
('Sodium', 'sodium', 'Sodium', 'renal'),
('Potassium', 'potassium', 'Potassium', 'renal'),
('Chloride', 'chloride', 'Chloride', 'renal'),
('Bicarbonate', 'bicarbonate', 'Bicarbonate', 'renal'),
('Calcium', 'calcium', 'Calcium', 'renal'),
('Phosphate', 'phosphate', 'Phosphate', 'renal'),
('Phosphorus', 'phosphate', 'Phosphate', 'renal'),
-- MAGNESIUM (split — plasma vs RBC are different signals)
('Magnesium', 'magnesium_plasma', 'Magnesium (Plasma)', 'micronutrient'),
('Plasma Magnesium', 'magnesium_plasma', 'Magnesium (Plasma)', 'micronutrient'),
('Serum Magnesium', 'magnesium_plasma', 'Magnesium (Plasma)', 'micronutrient'),
('RBC Magnesium', 'magnesium_rbc', 'Magnesium (RBC)', 'micronutrient'),
('Red Cell Magnesium', 'magnesium_rbc', 'Magnesium (RBC)', 'micronutrient'),
('Intracellular Magnesium', 'magnesium_rbc', 'Magnesium (RBC)', 'micronutrient'),
-- LIVER FUNCTION
('ALT', 'alt', 'ALT', 'liver'),
('Alanine Aminotransferase', 'alt', 'ALT', 'liver'),
('SGPT', 'alt', 'ALT', 'liver'),
('AST', 'ast', 'AST', 'liver'),
('Aspartate Aminotransferase', 'ast', 'AST', 'liver'),
('SGOT', 'ast', 'AST', 'liver'),
('GGT', 'ggt', 'GGT', 'liver'),
('Gamma-Glutamyl Transferase', 'ggt', 'GGT', 'liver'),
('ALP', 'alp', 'ALP', 'liver'),
('Alkaline Phosphatase', 'alp', 'ALP', 'liver'),
('Bilirubin', 'bilirubin_total', 'Bilirubin (Total)', 'liver'),
('Total Bilirubin', 'bilirubin_total', 'Bilirubin (Total)', 'liver'),
('Bilirubin Direct', 'bilirubin_direct', 'Bilirubin (Direct)', 'liver'),
('Direct Bilirubin', 'bilirubin_direct', 'Bilirubin (Direct)', 'liver'),
('Conjugated Bilirubin', 'bilirubin_direct', 'Bilirubin (Direct)', 'liver'),
('Albumin', 'albumin', 'Albumin', 'liver'),
('Total Protein', 'total_protein', 'Total Protein', 'liver'),
('LDH', 'ldh', 'LDH', 'liver'),
('Lactate Dehydrogenase', 'ldh', 'LDH', 'liver'),
-- LIPIDS
('Total Cholesterol', 'cholesterol_total', 'Total Cholesterol', 'lipid'),
('Cholesterol', 'cholesterol_total', 'Total Cholesterol', 'lipid'),
('LDL Cholesterol', 'ldl', 'LDL', 'lipid'),
('LDL-C', 'ldl', 'LDL', 'lipid'),
('HDL Cholesterol', 'hdl', 'HDL', 'lipid'),
('HDL-C', 'hdl', 'HDL', 'lipid'),
('Triglycerides', 'triglycerides', 'Triglycerides', 'lipid'),
('TG', 'triglycerides', 'Triglycerides', 'lipid'),
('Non-HDL Cholesterol', 'non_hdl', 'Non-HDL Cholesterol', 'lipid'),
('ApoB', 'apob', 'ApoB', 'lipid'),
('Apolipoprotein B', 'apob', 'ApoB', 'lipid'),
('ApoA1', 'apoa1', 'ApoA1', 'lipid'),
('Lp(a)', 'lpa', 'Lp(a)', 'lipid'),
('Lipoprotein(a)', 'lpa', 'Lp(a)', 'lipid'),
('Oxidised LDL', 'oxldl', 'Oxidised LDL', 'lipid'),
-- INFLAMMATORY
('CRP', 'crp', 'CRP', 'inflammatory'),
('C-Reactive Protein', 'crp', 'CRP', 'inflammatory'),
('hsCRP', 'crp', 'CRP', 'inflammatory'),
('High Sensitivity CRP', 'crp', 'CRP', 'inflammatory'),
('ESR', 'esr', 'ESR', 'inflammatory'),
('Erythrocyte Sedimentation Rate', 'esr', 'ESR', 'inflammatory'),
('Fibrinogen', 'fibrinogen', 'Fibrinogen', 'inflammatory'),
('Homocysteine', 'homocysteine', 'Homocysteine', 'inflammatory'),
('Total Homocysteine', 'homocysteine', 'Homocysteine', 'inflammatory'),
-- THYROID
('TSH', 'tsh', 'TSH', 'thyroid'),
('Thyroid Stimulating Hormone', 'tsh', 'TSH', 'thyroid'),
('Free T4', 'free_t4', 'Free T4', 'thyroid'),
('FT4', 'free_t4', 'Free T4', 'thyroid'),
('Free Thyroxine', 'free_t4', 'Free T4', 'thyroid'),
('Free T3', 'free_t3', 'Free T3', 'thyroid'),
('FT3', 'free_t3', 'Free T3', 'thyroid'),
('Total T4', 'total_t4', 'Total T4', 'thyroid'),
('Total T3', 'total_t3', 'Total T3', 'thyroid'),
('TPO Antibodies', 'tpo_ab', 'TPO Antibodies', 'thyroid'),
('Thyroid Peroxidase Antibodies', 'tpo_ab', 'TPO Antibodies', 'thyroid'),
('Anti-TPO', 'tpo_ab', 'TPO Antibodies', 'thyroid'),
('Thyroglobulin Antibodies', 'tg_ab', 'Thyroglobulin Ab', 'thyroid'),
-- HORMONAL (TRT core panel + general)
('Total Testosterone', 'total_testosterone', 'Total Testosterone', 'hormonal'),
('Testosterone', 'total_testosterone', 'Total Testosterone', 'hormonal'),
('Free Testosterone', 'free_testosterone', 'Free Testosterone', 'hormonal'),
('Testosterone Free', 'free_testosterone', 'Free Testosterone', 'hormonal'),
('SHBG', 'shbg', 'SHBG', 'hormonal'),
('Sex Hormone Binding Globulin', 'shbg', 'SHBG', 'hormonal'),
('Oestradiol', 'oestradiol', 'Oestradiol', 'hormonal'),
('Estradiol', 'oestradiol', 'Oestradiol', 'hormonal'),
('E2', 'oestradiol', 'Oestradiol', 'hormonal'),
('LH', 'lh', 'LH', 'hormonal'),
('Luteinizing Hormone', 'lh', 'LH', 'hormonal'),
('Luteinising Hormone', 'lh', 'LH', 'hormonal'),
('FSH', 'fsh', 'FSH', 'hormonal'),
('Follicle Stimulating Hormone', 'fsh', 'FSH', 'hormonal'),
('Prolactin', 'prolactin', 'Prolactin', 'hormonal'),
('DHEAS', 'dheas', 'DHEA-S', 'hormonal'),
('DHEA-S', 'dheas', 'DHEA-S', 'hormonal'),
('Dehydroepiandrosterone Sulfate', 'dheas', 'DHEA-S', 'hormonal'),
('DHEA', 'dhea', 'DHEA', 'hormonal'),
('Progesterone', 'progesterone', 'Progesterone', 'hormonal'),
('Cortisol', 'cortisol', 'Cortisol', 'hormonal'),
('Morning Cortisol', 'cortisol', 'Cortisol', 'hormonal'),
('IGF-1', 'igf1', 'IGF-1', 'hormonal'),
('Insulin-Like Growth Factor 1', 'igf1', 'IGF-1', 'hormonal'),
('Somatomedin C', 'igf1', 'IGF-1', 'hormonal'),
('DHT', 'dht', 'DHT', 'hormonal'),
('Dihydrotestosterone', 'dht', 'DHT', 'hormonal'),
('PSA', 'psa_total', 'PSA (Total)', 'hormonal'),
('Total PSA', 'psa_total', 'PSA (Total)', 'hormonal'),
('Prostate Specific Antigen', 'psa_total', 'PSA (Total)', 'hormonal'),
('Free PSA', 'psa_free', 'PSA (Free)', 'hormonal'),
('AMH', 'amh', 'AMH', 'hormonal'),
('Anti-Mullerian Hormone', 'amh', 'AMH', 'hormonal'),
('Androstenedione', 'androstenedione', 'Androstenedione', 'hormonal'),
('Aldosterone', 'aldosterone', 'Aldosterone', 'hormonal'),
('Renin', 'renin', 'Renin', 'hormonal'),
-- VITAMINS / MICRONUTRIENTS
('Vitamin D', 'vitamin_d', 'Vitamin D', 'micronutrient'),
('25-OH Vitamin D', 'vitamin_d', 'Vitamin D', 'micronutrient'),
('25-Hydroxyvitamin D', 'vitamin_d', 'Vitamin D', 'micronutrient'),
('Calcidiol', 'vitamin_d', 'Vitamin D', 'micronutrient'),
('Vitamin B12', 'b12', 'Vitamin B12', 'micronutrient'),
('Cobalamin', 'b12', 'Vitamin B12', 'micronutrient'),
('Active B12', 'b12_active', 'Active B12', 'micronutrient'),
('Holotranscobalamin', 'b12_active', 'Active B12', 'micronutrient'),
('Folate', 'folate', 'Folate', 'micronutrient'),
('Folic Acid', 'folate', 'Folate', 'micronutrient'),
('RBC Folate', 'folate_rbc', 'Folate (RBC)', 'micronutrient'),
('Zinc', 'zinc', 'Zinc', 'micronutrient'),
('Plasma Zinc', 'zinc', 'Zinc', 'micronutrient'),
('Copper', 'copper', 'Copper', 'micronutrient'),
('Selenium', 'selenium', 'Selenium', 'micronutrient'),
('Vitamin A', 'vitamin_a', 'Vitamin A', 'micronutrient'),
('Retinol', 'vitamin_a', 'Vitamin A', 'micronutrient'),
('Vitamin E', 'vitamin_e', 'Vitamin E', 'micronutrient'),
('Alpha-Tocopherol', 'vitamin_e', 'Vitamin E', 'micronutrient'),
('Iodine', 'iodine', 'Iodine', 'micronutrient'),
('Methylmalonic Acid', 'mma', 'Methylmalonic Acid', 'micronutrient'),
('MMA', 'mma', 'Methylmalonic Acid', 'micronutrient'),
-- COAGULATION
('INR', 'inr', 'INR', 'coagulation'),
('PT', 'pt', 'Prothrombin Time', 'coagulation'),
('Prothrombin Time', 'pt', 'Prothrombin Time', 'coagulation'),
('APTT', 'aptt', 'APTT', 'coagulation'),
-- CARDIOVASCULAR
('NT-proBNP', 'nt_probnp', 'NT-proBNP', 'cardiovascular'),
('BNP', 'bnp', 'BNP', 'cardiovascular'),
('Troponin I', 'troponin', 'Troponin', 'cardiovascular'),
-- BONE
('PTH', 'pth', 'PTH', 'bone'),
('Parathyroid Hormone', 'pth', 'PTH', 'bone'),
('Osteocalcin', 'osteocalcin', 'Osteocalcin', 'bone'),
-- AUTOIMMUNE / GUT
('ANA', 'ana', 'ANA', 'autoimmune'),
('Rheumatoid Factor', 'rf', 'Rheumatoid Factor', 'autoimmune'),
('Calprotectin', 'calprotectin', 'Calprotectin', 'gut'),
('tTG-IgA', 'ttg_iga', 'tTG-IgA', 'gut'),
-- ONCOLOGY SCREENING (common panels)
('CEA', 'cea', 'CEA', 'oncology'),
('CA-125', 'ca125', 'CA-125', 'oncology'),
('CA 19-9', 'ca199', 'CA 19-9', 'oncology'),
('AFP', 'afp', 'AFP', 'oncology')
```

### 006 — unknown_markers

Runtime catch for unrecognised lab names. Admin reviews and promotes to marker_aliases. At commercial scale, shared across users — one resolution benefits all.

```sql
CREATE TABLE unknown_markers (
    id              SERIAL PRIMARY KEY,
    raw_name        VARCHAR(200) NOT NULL,
    seen_count      INT NOT NULL DEFAULT 1,
    first_seen      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    example_value   VARCHAR(100),
    example_unit    VARCHAR(30),
    resolved        BOOLEAN NOT NULL DEFAULT FALSE,
    canonical_name  VARCHAR(100),               -- filled when resolved
    UNIQUE (raw_name)
);
```

Ingest pipeline logic:

```python
async def resolve_marker_name(raw_name: str, value=None, unit=None) -> str | None:
    canonical = await db.fetchval(
        "SELECT canonical_name FROM marker_aliases WHERE raw_name = $1", raw_name
    )
    if canonical:
        return canonical
    await db.execute("""
        INSERT INTO unknown_markers (raw_name, example_value, example_unit)
        VALUES ($1, $2, $3)
        ON CONFLICT (raw_name) DO UPDATE
        SET seen_count = unknown_markers.seen_count + 1,
            last_seen = NOW()
    """, raw_name, str(value) if value else None, unit)
    return None  # caller stores with null canonical or skips
```

### 007 — health_metrics

Granular time-series for raw physiological measurements. Whitelist enforced — only CANONICAL_METRIC_TYPES accepted. Vendor composites are silently discarded at ingest gate (not even logged as unknown).

```sql
CREATE TABLE health_metrics (
    id              BIGSERIAL PRIMARY KEY,
    user_id         INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    metric_type     VARCHAR(50) NOT NULL,       -- must be in CANONICAL_METRIC_TYPES whitelist
    source          VARCHAR(100) NOT NULL,
    source_ref      VARCHAR(255),
    interval_start  TIMESTAMPTZ NOT NULL,
    interval_end    TIMESTAMPTZ,                -- NULL = instantaneous reading
    value_numeric   NUMERIC NOT NULL,
    unit            VARCHAR(30),
    user_timezone   VARCHAR(50),               -- from users.timezone at ingest; daily rollup boundary
    raw_payload     JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_health_metrics UNIQUE (user_id, source, source_ref)
);

-- Primary time-series query: user + type + date range
CREATE INDEX idx_health_metrics_series
    ON health_metrics (user_id, metric_type, interval_start DESC);

-- Fast dedup check on source_ref
CREATE INDEX idx_health_metrics_source_ref
    ON health_metrics (source, source_ref)
    WHERE source_ref IS NOT NULL;

-- Sleep staging query (source is load-bearing — stages not comparable across vendors)
CREATE INDEX idx_health_metrics_sleep_stages
    ON health_metrics (user_id, source, interval_start)
    WHERE metric_type = 'sleep_stage';
```

### 008 — metric_type_aliases

Maps vendor metric names to canonical metric types. Source is part of the unique key — the same raw name can mean different things across devices.

```sql
CREATE TABLE metric_type_aliases (
    id              SERIAL PRIMARY KEY,
    raw_name        VARCHAR(200) NOT NULL,
    source          VARCHAR(100) NOT NULL,      -- 'samsung_health' | 'garmin' | 'polar' | 'apple'
    canonical_name  VARCHAR(100) NOT NULL,      -- must be in CANONICAL_METRIC_TYPES
    display_name    VARCHAR(150),
    category        VARCHAR(50),
    UNIQUE (raw_name, source)
);
```

### 009 — unknown_metric_types

```sql
CREATE TABLE unknown_metric_types (
    id              SERIAL PRIMARY KEY,
    raw_name        VARCHAR(200) NOT NULL,
    source          VARCHAR(100) NOT NULL,
    seen_count      INT NOT NULL DEFAULT 1,
    first_seen      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    example_value   VARCHAR(100),
    example_unit    VARCHAR(30),
    resolved        BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (raw_name, source)
);
```

Note: Items in REJECTED_VENDOR_METRICS are discarded silently at the ingest gate — they never reach unknown_metric_types. Only genuinely unknown metric names (not recognised but not explicitly rejected) are logged here.

### 010 — workout_metrics

Session-level data. Four window loads are the only ACWR inputs — typed columns always populated where applicable. All modality-specific data lives in source_metrics JSONB so new integrations add keys without schema migration.

```sql
CREATE TABLE workout_metrics (
    id                  BIGSERIAL PRIMARY KEY,
    event_id            BIGINT NOT NULL REFERENCES health_events(id) ON DELETE CASCADE,
    user_id             INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    -- FOUR WINDOW LOADS — ACWR reads only these four columns
    -- Null = that window not applicable for this session type
    neuromuscular_load  NUMERIC,    -- velocity, accel/decel, sprints, heavy CNS demand
    mechanical_load     NUMERIC,    -- volume load (kg), player load, eccentric demand, contact
    metabolic_load      NUMERIC,    -- TRIMP, HR-based load, aerobic/anaerobic
    psychological_load  NUMERIC,    -- session RPE × duration minutes
    -- UNIVERSAL TYPED FIELDS — present across most sources; safe to query directly
    avg_hr              NUMERIC,
    max_hr              NUMERIC,
    session_rpe         NUMERIC,    -- 1–10; also feeds psychological_load
    duration_secs       INT,
    total_distance_m    NUMERIC,
    max_velocity_ms     NUMERIC,
    -- SOURCE METRICS — normalised to standard keys by connector before write
    -- New integrations add keys here; never new columns
    -- See connector normalisation contract below for key definitions
    source_metrics      JSONB DEFAULT '{}',
    source              VARCHAR(100),   -- 'polar' | 'hevy' | 'gametraka' | 'garmin' | 'manual'
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_workout_metrics_user
    ON workout_metrics (user_id, event_id DESC);

-- Covering index for ACWR query — avoids heap fetch on the four load columns
CREATE INDEX idx_workout_metrics_acwr
    ON workout_metrics (user_id, event_id DESC)
    INCLUDE (neuromuscular_load, mechanical_load, metabolic_load, psychological_load);

CREATE INDEX idx_workout_metrics_source_metrics
    ON workout_metrics USING GIN (source_metrics);
```

### 011 — derived_metrics

Our computed outputs. Derived from raw signals in health_metrics and workout_metrics. Never populated by device connectors. formula_version enables full reprocessing of historical raw data when algorithms improve.

```sql
CREATE TABLE derived_metrics (
    id                  BIGSERIAL PRIMARY KEY,
    user_id             INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    metric_type         VARCHAR(100) NOT NULL,
    derived_date        DATE NOT NULL,
    value_numeric       NUMERIC NOT NULL,
    confidence          VARCHAR(10) NOT NULL DEFAULT 'moderate'
                            CHECK (confidence IN ('high', 'moderate', 'low', 'guessing')),
    formula_version     VARCHAR(20) NOT NULL,        -- 'v1.0'; bump when algorithm changes
    source_event_ids    BIGINT[],                    -- raw event IDs that fed this derivation
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_derived_metric
        UNIQUE (user_id, metric_type, derived_date, formula_version)
);

CREATE INDEX idx_derived_metrics_trending
    ON derived_metrics (user_id, metric_type, derived_date DESC);
```

Derived metric catalogue:

```python
DERIVED_METRIC_DEFINITIONS = {
    # Cardiac
    'rhr_bpm':              {'confidence': 'high',     'from': 'heart_rate overnight min'},
    # HRV (from rr_interval series)
    'rmssd_ms':             {'confidence': 'moderate', 'from': 'rr_interval series'},
    'sdnn_ms':              {'confidence': 'moderate', 'from': 'rr_interval series'},
    'lnrmssd':              {'confidence': 'moderate', 'from': 'rr_interval series'},
    'lnrmssd_cv':           {'confidence': 'moderate', 'from': 'rr_interval 4–6 week window'},
    # Sleep (from sleep_stage epochs — source tag carried through)
    'sleep_tst_mins':       {'confidence': 'moderate', 'from': 'sleep_stage epochs'},
    'sleep_efficiency_pct': {'confidence': 'moderate', 'from': 'sleep_stage + sleep_tib'},
    'sleep_sws_mins':       {'confidence': 'low',      'from': 'sleep_stage deep epochs'},
    'sleep_rem_mins':       {'confidence': 'moderate', 'from': 'sleep_stage rem epochs'},
    'sleep_waso_mins':      {'confidence': 'moderate', 'from': 'sleep_stage wake epochs'},
    'sleep_sol_mins':       {'confidence': 'moderate', 'from': 'sleep_tib + first non-wake epoch'},
    # HR zones (from heart_rate series + user hrmax — our definitions, not vendor)
    'zone_1_secs':          {'confidence': 'high',     'from': 'heart_rate + measured hrmax'},
    'zone_2_secs':          {'confidence': 'high',     'from': 'heart_rate + measured hrmax'},
    'zone_3_secs':          {'confidence': 'high',     'from': 'heart_rate + measured hrmax'},
    'zone_4_secs':          {'confidence': 'high',     'from': 'heart_rate + measured hrmax'},
    'zone_5_secs':          {'confidence': 'high',     'from': 'heart_rate + measured hrmax'},
    'trimp':                {'confidence': 'moderate', 'from': 'heart_rate series + zones'},
    # Fitness
    'vo2max_estimate':      {'confidence': 'moderate', 'from': 'uth hr ratio; measured hrmax only'},
    # Load / ACWR
    'acwr_neuromuscular':   {'confidence': 'moderate', 'from': 'ewma neuromuscular_load 7/28d'},
    'acwr_mechanical':      {'confidence': 'moderate', 'from': 'ewma mechanical_load 7/28d'},
    'acwr_metabolic':       {'confidence': 'moderate', 'from': 'ewma metabolic_load 7/28d'},
    'acwr_psychological':   {'confidence': 'moderate', 'from': 'ewma psychological_load 7/28d'},
    # Composite
    'readiness_score':      {'confidence': 'moderate', 'from': 'composite — see Readiness Algorithm'},
}
```

### 012 — vendor_metrics

Vendor composite scores preserved for display and user calibration during platform adoption. Clearly segregated — never algorithm inputs.

```sql
CREATE TABLE vendor_metrics (
    id              BIGSERIAL PRIMARY KEY,
    user_id         INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source          VARCHAR(100) NOT NULL,          -- 'garmin' | 'samsung_health' | 'polar'
    metric_name     VARCHAR(100) NOT NULL,           -- 'body_battery' | 'energy_score' | 'stress_score'
    metric_date     DATE NOT NULL,
    value_numeric   NUMERIC,
    value_text      VARCHAR(100),
    raw_payload     JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_vendor_metric
        UNIQUE (user_id, source, metric_name, metric_date)
);

CREATE INDEX idx_vendor_metrics_lookup
    ON vendor_metrics (user_id, source, metric_name, metric_date DESC);
```

UI contract: Every vendor metric displayed must carry: "Reported by [Device] — not used in your readiness calculation."

Rationale for storing: Users arrive with established relationships to these metrics (e.g. years of Garmin Body Battery). Parallel display during adoption gives them an anchor for building trust in platform-derived metrics. The comparison also becomes the sales pitch — users see which metric better predicted how they actually felt.

### 013 — daily_metric_summaries (materialized view)

Derived from health_metrics. Never the primary store — always regenerable from raw. Refreshed nightly or on sync completion.

```sql
CREATE MATERIALIZED VIEW daily_metric_summaries AS
SELECT
    hm.user_id,
    hm.metric_type,
    DATE(hm.interval_start AT TIME ZONE hm.user_timezone) AS summary_date,
    SUM(hm.value_numeric)       AS total,
    AVG(hm.value_numeric)       AS avg,
    MIN(hm.value_numeric)       AS min,
    MAX(hm.value_numeric)       AS max,
    COUNT(*)                    AS reading_count,
    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY hm.value_numeric) AS p25,
    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY hm.value_numeric) AS p75
FROM health_metrics hm
GROUP BY hm.user_id, hm.metric_type,
         DATE(hm.interval_start AT TIME ZONE hm.user_timezone);

CREATE UNIQUE INDEX ON daily_metric_summaries (user_id, metric_type, summary_date);
```

### 014 — user_health_state (PLACEHOLDER)

Required for AI Tier 1 context (~800 tokens always-on). One row per user, updated on every relevant event write. Feeds: current protocol, active injuries, open flags, personal baselines (HRV mean, RHR).

Design deferred until two weeks of real data is flowing — query shape should reflect actual access patterns.

```python
# 014_create_user_health_state.py
# TODO: design after first 2 weeks of data
# Shape: one row per user, JSON or wide columns
# Updated by: supplement_add/remove events, injury events, derived_metrics writes
# Feeds: AI Tier 1 context assembly (~800 tokens)
def upgrade():
    pass
def downgrade():
    pass
```

### 015 — hevy_exercise_templates

Cache of Hevy exercise templates — global defaults + per-account customs — so provisioning resolves exercise title → id without a live Hevy call. Re-runnable per-user sync, upsert-only (Hevy templates cannot be deleted via API). owner_user_id NULL = Hevy default (global, shared across accounts); set = account custom, scoped to that user. Resolver prefers the default on title collision (#60) for a portable, account-independent vocabulary. Landed and proven; resolver dormant until context_builder activation.

```sql
CREATE TABLE hevy_exercise_templates (
    id                       VARCHAR(64) PRIMARY KEY,   -- Hevy template id: 8-char hex (default) or lowercase UUID (custom)
    title                    VARCHAR NOT NULL,
    type                     VARCHAR(50),               -- Hevy exercise type, e.g. weight_reps
    is_custom                BOOLEAN NOT NULL DEFAULT FALSE,
    owner_user_id            INT REFERENCES users(id) ON DELETE CASCADE,  -- NULL = Hevy default; set = account custom
    primary_muscle_group     VARCHAR(100),
    secondary_muscle_groups  JSON,                      -- landed as JSON (file convention elsewhere is JSONB)
    synced_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    laterality               VARCHAR(20),               -- bilateral|unilateral|alternating|NULL — app-owned; _upsert_template never assigns it
    adjudicated_at           TIMESTAMPTZ                -- three-state coverage (#76): NULL=unlooked; NOT NULL + tags=tagged; NOT NULL + 0 tags=no-pattern. App-owned; _upsert_template never assigns it
);

CREATE INDEX ix_hevy_exercise_templates_owner_user_id
    ON hevy_exercise_templates (owner_user_id);

CREATE INDEX ix_hevy_exercise_templates_title
    ON hevy_exercise_templates (title);
```

### 016 — exercise_region_tags

App-owned exercise→taxonomy-region annotation (DECISIONS_LOG #NEXT). A SEPARATE table from `hevy_exercise_templates` — that table is upsert-from-Hevy-sync (`_upsert_template`) and clobber-exposed on every resync; keeping tags here means a resync can never touch a row it does not write. Many-to-many by design (Suitcase Carry = carry + anti_lateral_flexion); `role` makes primacy explicit and reviewable. `region_key` is validated against `engine/taxonomy.py` at write time — fail-closed, an orphan key is refused. Plane/capacity are NOT stored (Region already carries them; region_key derives both). `source` follows the labs extract→confirm provenance model: `llm_proposed` then `human_confirmed` (with `confirmed_at`).

```sql
CREATE TABLE exercise_region_tags (
    hevy_exercise_template_id  VARCHAR(64) NOT NULL REFERENCES hevy_exercise_templates(id) ON DELETE CASCADE,
    region_key                 VARCHAR(100) NOT NULL,   -- validated vs engine/taxonomy.py Region.key
    role                       VARCHAR(20) NOT NULL DEFAULT 'primary',        -- primary | secondary
    taxonomy_version           VARCHAR(20) NOT NULL DEFAULT 'v0',             -- mirrors TAXONOMY_VERSION
    source                     VARCHAR(20) NOT NULL DEFAULT 'llm_proposed',   -- llm_proposed | human_confirmed
    confirmed_at               TIMESTAMPTZ,
    created_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (hevy_exercise_template_id, region_key)
);

CREATE INDEX ix_exercise_region_tags_region_key
    ON exercise_region_tags (region_key);
```

### 017 — cbti_blocks

CBT-I titration block ledger (DECISIONS_LOG #108). The module is block-structured, not a single arc: a block opens carrying the in-flight prescription (`decision='adopt'`) and closes (`decision='close'`); the ledger persists permanently after closure and is the baseline any later block titrates against. **Append-only** — the only permitted UPDATE is setting `closed_on` / `close_reason` / `exit_tst_min` / `exit_se_pct` at closure. This is a model+application invariant, not a DB trigger (the repo has no trigger precedent and the SQLite test path builds via `create_all`, not migrations). Read-only with respect to readiness in phase 1.

```sql
CREATE TABLE cbti_blocks (
    id            INTEGER PRIMARY KEY,
    user_id       INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    opened_on     DATE NOT NULL,
    closed_on     DATE,                    -- UPDATE-once at closure
    wake_anchor   VARCHAR(5) NOT NULL,     -- "05:00"
    open_reason   TEXT,
    close_reason  TEXT,                    -- UPDATE-once at closure
    exit_tst_min  INTEGER,                 -- UPDATE-once at closure
    exit_se_pct   FLOAT,                   -- UPDATE-once at closure
    notes         TEXT
);

CREATE INDEX ix_cbti_blocks_user_id ON cbti_blocks (user_id);
```

### 018 — cbti_prescriptions

One prescribed sleep window within a block (DECISIONS_LOG #107). Titration controls on total sleep time with sleep efficiency as a **floor** (≥85%), not SE as the target: `window_minutes` = rolling mean TST + buffer; exit on TST plateau with SE held ≥85%. **Append-only** — the only permitted UPDATEs are `effective_to` (when a successor takes over) and `superseded_by` (self-referential pointer to that successor); `basis_*` / `decision` / `rationale` are frozen at authorship. The `decision` domain is the one DB-enforced constraint (`ck_cbti_prescription_decision`). `excluded_nights` is reason-tagged JSON (`{"2026-04-02":"alcohol"}`) — recorded, not counted.

```sql
CREATE TABLE cbti_prescriptions (
    id                     INTEGER PRIMARY KEY,
    block_id               INT NOT NULL REFERENCES cbti_blocks(id) ON DELETE CASCADE,
    effective_from         DATE NOT NULL,
    effective_to           DATE,                    -- UPDATE-once when superseded
    prescribed_lights_out  VARCHAR(5) NOT NULL,     -- "22:36"
    wake_anchor            VARCHAR(5) NOT NULL,     -- "05:00"
    window_minutes         INTEGER NOT NULL,
    decision               VARCHAR(10) NOT NULL,    -- adopt|extend|hold|compress|close (CHECK ck_cbti_prescription_decision)
    basis_tst_min          INTEGER,
    basis_se_pct           FLOAT,
    basis_nights_n         INTEGER,
    -- basis provenance (migration c4e8a2019bd7). Recorded so a later reader can see
    -- what each decision rested on; none of these gate anything.
    basis_n_samsung        INTEGER,   -- basis nights whose adherence used Samsung bedtime (independent)
    basis_n_diary          INTEGER,   -- basis nights that fell back to diary lights_out
    basis_n_alcohol_unknown INTEGER,  -- basis nights admitted with alcohol unrecorded: assumed clean, not verified
    basis_tib_over_run_min FLOAT,     -- mean basis TIB minus prescribed window; instrumented, NOT gated (#114/#115)
    basis_window_start     DATE,
    basis_window_end       DATE,
    excluded_nights        JSON,                    -- reason-tagged: {"2026-04-02":"alcohol",...}
    rationale              TEXT,
    superseded_by          INT REFERENCES cbti_prescriptions(id) ON DELETE SET NULL,  -- UPDATE-once when superseded
    CONSTRAINT ck_cbti_prescription_decision
        CHECK (decision IN ('adopt','extend','hold','compress','close'))
);

CREATE INDEX ix_cbti_prescriptions_block_id ON cbti_prescriptions (block_id);
```

### 019 — cbti_isi

Insomnia Severity Index administrations (Morin) — the outcome measure a block is judged by (migration `d3f7a1908c62`). The **seven items are the record**; `total_reported` preserves what the administering tool returned, and the **canonical total is derived on read** (`sum(item_1..7)`), never stored — a total cannot be decomposed later, and item-level distinguishes a sleep change (items 1–3) from a distress change (items 6–7). `block_id` is **nullable** (a screening or between-block administration belongs to no block); unique on `(block_id, timepoint)`, and NULL `block_id`s do not collide so screenings are unconstrained. `timepoint` domain is DB-enforced (`ck_cbti_isi_timepoint`).

```sql
CREATE TABLE cbti_isi (
    id                INTEGER PRIMARY KEY,
    block_id          INT REFERENCES cbti_blocks(id) ON DELETE SET NULL,  -- nullable: screening has no block
    administered_at   TIMESTAMPTZ NOT NULL,
    timepoint         VARCHAR(10) NOT NULL,    -- baseline|mid|exit (CHECK ck_cbti_isi_timepoint)
    item_1            INTEGER NOT NULL,        -- ... item_2 .. item_7, all NOT NULL (the record)
    item_2            INTEGER NOT NULL,
    item_3            INTEGER NOT NULL,
    item_4            INTEGER NOT NULL,
    item_5            INTEGER NOT NULL,
    item_6            INTEGER NOT NULL,
    item_7            INTEGER NOT NULL,
    total_reported    INTEGER,                 -- what the tool returned; may differ from sum(items)
    instrument        VARCHAR(40) NOT NULL DEFAULT 'ISI',
    administered_via  VARCHAR(40),             -- e.g. 'QxMD'
    notes             TEXT,
    CONSTRAINT uq_cbti_isi_block_timepoint UNIQUE (block_id, timepoint),
    CONSTRAINT ck_cbti_isi_timepoint CHECK (timepoint IN ('baseline','mid','exit'))
);

CREATE INDEX ix_cbti_isi_block_id ON cbti_isi (block_id);
```

### 020 — capability_observations

Graded, timestamped capability **measurement** for the Adaptive Exposure Engine (migration `b6f3d92a4e17`, DECISIONS_LOG #161). Deliberately NOT a widening of `capability_state`: that table holds one row per `(user, region, side)`, is overwritten in place by `engine/adaptation.py::apply_response`, and its `status` is a 4-level ordinal — so it can only ever show today's label, cannot be regressed against dose, and has no trajectory. This table holds the history. `capability_state` is **unchanged** by this migration and nothing existing reads the new table.

**The two are different signals.** `capability_state.status` is the response-to-load **verdict**, self-reported through the education idiom and never a wearable metric — that invariant is unchanged and now stated explicitly on the model. A row here is a measured **quantity** and **may be device-derived** (GPS max velocity, deceleration counts). The wearable-metric invariant scopes to the verdict, not to measurement.

**Append-only.** No `updated_at` column and no UPDATE path anywhere — a correction is a new row, and supersession is resolved on read by `observed_on`, then `created_at`, then `id`. `observed_on` is the **measurement** date, not the insert date, so a backfilled battery lands on the day it happened; a backdated correction therefore supersedes its own date without displacing a later real measurement. No backfill was possible on first upgrade — `capability_state` carries no numeric value — so an empty table is the correct initial state.

`region_key` and `measure_key` are both validated against `engine/taxonomy.py` at write time (fail-closed, same guard as `exercise_region_tags`). Measures are **declared per region** on `Region.measures` and versioned with `TAXONOMY_VERSION`; a region with no declared measure is observation-ineligible, which is the correct default rather than a gap (7 of 31 regions are seeded). **`side` is validated against the MEASURE, not only the region** — sidedness is a property of the instrument: `deceleration_landing` is a per-side region, but a trunk-mounted GPS records one figure for the athlete and cannot attribute it to a leg, so `peak_decel_ms2` is `bilateral`-only.

**Boundary:** values, symmetry ratios, and trends are legal outputs; a clearance, "safe to return", severity grade, or return-to-sport verdict is not. Enforced by `backend/tests/test_capability_observations.py`, not by docstring — same construction as `injury_probes.py`.

```sql
CREATE TABLE capability_observations (
    id                INTEGER PRIMARY KEY,
    user_id           INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    region_key        VARCHAR(100) NOT NULL,   -- validated vs engine/taxonomy.py Region.key
    side              VARCHAR(20) NOT NULL DEFAULT 'bilateral',  -- bilateral | left | right
    observed_on       DATE NOT NULL,           -- MEASUREMENT date, not insert date
    measure_key       VARCHAR(60) NOT NULL,    -- validated vs the region's declared Measure set
    value             FLOAT NOT NULL,
    unit              VARCHAR(20) NOT NULL,    -- taken from the declared measure; mismatch refuses
    method            VARCHAR(30) NOT NULL,    -- baseline_battery | probe | session | manual
    source            VARCHAR(30) NOT NULL,    -- self_report | catapult | hevy | polar | manual
    confidence        VARCHAR(20) NOT NULL DEFAULT 'likely',   -- certain | likely | guessing
    context           JSON,                    -- {block, load, fatigue_state, notes, session_id}
    taxonomy_version  VARCHAR(20) NOT NULL DEFAULT 'v0',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
    -- NO updated_at, by construction. See "Append-only" above.
);

CREATE INDEX ix_capability_observations_user_id
    ON capability_observations (user_id);
CREATE INDEX ix_capability_obs_user_region_side_date
    ON capability_observations (user_id, region_key, side, observed_on);
CREATE INDEX ix_capability_obs_user_date
    ON capability_observations (user_id, observed_on);
```

**Seeded measures (v0)** — narrow first; broadening is additive and needs no schema change:

| region_key | measure_key | unit | sides |
|---|---|---|---|
| `hip_flexion_pc_length` | `aslr_deg` | deg | left / right |
| `single_leg_hop` | `hop_distance_cm` | cm | left / right |
| `ankle_df` | `knee_to_wall_cm` | cm | left / right |
| `frontal_single_leg_stability` | `stance_seconds` | s | left / right |
| `shoulder_mobility` | `er_rom_deg` | deg | left / right |
| `deceleration_landing` | `peak_decel_ms2` | m/s^2 | bilateral |
| `change_of_direction` | `cod_count` | count | bilateral |

_(`capability_state` and `fortification_profiles`, migration `d8e1f2a3b4c5`, predate this document's coverage and are not recorded here.)_

**daily_records diary columns** (migrations `e5f2a9c7b104`, `a7b3f1c8d240`, `b2d5f9e04a17`). Thirteen additive nullable AM-moment columns extend `daily_records` for the CBT-I sleep diary, sparse by design (captured only while an open `cbti_block` exists): `got_into_bed`, `lights_out`, `sleep_latency_min`, `waso_min`, `night_wakings_n`, `final_wake`, `out_of_bed`, `naps_min`, `diary_se_pct`, `diary_tst_min`, and — from `b2d5f9e04a17` — the waking-cause decomposition `wakings_nocturia_n`, `wakings_pain_n`, `wakings_spontaneous_n`. The three waking-cause counts decompose `night_wakings_n` by cause; they are **observational only** (the titration engine must not read them — `grep -rn 'wakings_' backend/cbti/` stays empty) and carry **no sum constraint** to `night_wakings_n` (recall is imperfect; consistency is surfaced, never enforced). Migration `f1a4c7e29b83` adds two nullable `Text` free-text columns, **`am_notes`** and **`pm_notes`** — uncaptured context that doesn't fit a structured field, captured through the AM and PM surfaces respectively. **Separate columns, not one:** the two surfaces submit independently, so a shared column's later write would clobber the earlier. Observational — read by no engine code, and not gated on an open block. `got_into_bed` (phase 2) is the moment you got into bed, **distinct** from `lights_out` (tried to sleep) — sleep efficiency is computed over the `lights_out`→`out_of_bed` window, so only `lights_out` was imported in phase 1 and the 53 historical rows carry `got_into_bed` NULL. `diary_se_pct` / `diary_tst_min` are frozen at AM capture (same contract as `naive_baseline`, never recomputed). `naps_min` is logged PM on date D but belongs to the night terminating on wake-date D+1 — stored at PM on D, the engine reads it from `(date - 1)`. _(The `daily_records` parent table itself predates this document's coverage; only the CBT-I additions are recorded here.)_

### 021 — interpretation_rephrases

Disposable plain-register overlay + its promotion state for interpretation increment 2 (migration `c3f1a8b2d9e4`, DECISIONS_LOG #202). One row is a generated plain-language rephrase of an interpretation presentation, keyed by the base text it was built from (`payload_hash` = sha256 of the serialiser's `addr\ttext`, from `interpretation/presentation.py::presentation_hash`) and the `register`. It is **both** the presentation cache (brief step 4) and the training-wheels promotion record (step 6) — one table, because a promotion must survive a Railway restart, which an in-memory cache would not. Expected at zero rows until the first plain-register request generates one.

**Never the record, always disposable.** The structured payload is the record (#202 clause 2); dropping any row is always safe — a missing row regenerates or renders the template. No `user_id` and no FK: the `payload_hash` is derived from one user's own readings, so a cross-user collision is vanishingly unlikely and, if it occurred, the base text (hence the valid rephrase) would be identical anyway.

**Promotion binds to the text, not the panel.** A new draw or an asset edit changes the base text → a new `payload_hash` → a new row at `ai_draft`. A stale `human_verified` can therefore never attach to changed text — regeneration is a fail-closed demotion, never a wrong promotion. The eligibility gate is **unconditional and server-side**: a plain-register request whose row is not `human_verified` renders the template regardless of the client's toggle (the toggle is a preference; the server decides). There is no auto-retire counter — retiring the gate after a few promoted panels is a later manual call.

```sql
CREATE TABLE interpretation_rephrases (
    id            INTEGER PRIMARY KEY,
    payload_hash  VARCHAR(64) NOT NULL,        -- sha256 of base text (addr+text), NOT of meta.generated_at
    register      VARCHAR(20) NOT NULL,        -- 'plain' (only the generated overlay is stored)
    text          TEXT NOT NULL,               -- the assembled plain-register presentation
    status        VARCHAR(20) NOT NULL DEFAULT 'ai_draft',   -- ai_draft | human_verified (#194 gate vocabulary)
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_interp_rephrase_payload_register UNIQUE (payload_hash, register)
);

CREATE INDEX ix_interpretation_rephrases_payload_hash
    ON interpretation_rephrases (payload_hash);
```

### 022 — marker_canonical_entries

The canonical marker map, runtime-mutable (migration `a7c3f19d5e28`, DECISIONS_LOG #220, fulfilling #50). Was a module-level dict loaded from `backend/reference/marker_canonical.json` at import; that file is now **only this table's migration seed**. The move exists because #50's "confirmation-populated" half is not buildable against a static repo file — a runtime bind cannot edit a file the app loaded at startup. Seeded at 70 rows (`source='seed'`), with the migration self-checking the inserted count against the JSON's entry count.

**`marker_name_raw` is the exact-string lookup key.** No fuzzy matching, no case folding, no normalisation (#50) — a near-match that silently binds is how two different analytes become one series, and the damage only surfaces much later as a trend that never happened. Rows are **global, not per-user**: canonical identity is a property of the marker, not of the reader.

**`unit_established` is legitimately nullable** (4 of the 70 seed rows) — a unitless marker (eGFR, a ratio) has no established unit. Null means NOT ESTABLISHED, which the over-collapse guard reads as "no unit claim to contradict", never as a mismatch.

**Read per request, not cached.** `labs.py::_canonical_map` queries on every confirm and every `/labs/canonical-map`. A cached dict would serve the pre-bind map to the very confirm the operator just bound for. At ~70 rows with rare confirms the freshness costs one indexed scan.

**`loinc` is dormant** (#50's B2B field, carried, never read). **`display_name` is column-only and unwired** — present so the queued display-name lane needs no second migration.

```sql
CREATE TABLE marker_canonical_entries (
    id                 INTEGER PRIMARY KEY,
    marker_name_raw    VARCHAR(100) NOT NULL,       -- exact-string lookup key
    marker_canonical   VARCHAR(100),                -- nullable: a declared-novel entry may bind later
    unit_established   VARCHAR(50),                 -- nullable: unitless markers, per §6
    loinc              VARCHAR(20),                 -- dormant, #50 B2B
    display_name       VARCHAR(100),                -- column only, unwired
    source             VARCHAR(10) NOT NULL,        -- 'seed' | 'bind'
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT uq_marker_canonical_entries_raw UNIQUE (marker_name_raw)
);

CREATE INDEX ix_marker_canonical_entries_marker_name_raw  ON marker_canonical_entries (marker_name_raw);
CREATE INDEX ix_marker_canonical_entries_marker_canonical ON marker_canonical_entries (marker_canonical);
```

**Writes.** `POST /labs/canonical/bind` is the only runtime writer (`source='bind'`). It refuses 409 on an already-mapped raw name (a mapped marker is not unmapped; binding it is a category error, not an update) and 422 on over-collapse — at bind time (the canonical already established at a different unit) and at backfill time (a historical `lab_results` row carrying a disagreeing unit). A bind promotes that marker's historical rows where `marker_canonical IS NULL`; a refused bind promotes **nothing**, since a half-migrated series is harder to see and harder to undo than a refusal.

### 023 — fortification_profiles.weekly_template

One additive nullable `JSON` column on the pre-existing `fortification_profiles` table (migration `b7c3e91f2a48`, DECISIONS_LOG #221). The parent table predates this document's coverage (see the note under 020); only this column is recorded here.

Holds the capacity-quota microcycle — how much of which capacity, how often, for how long:

```json
{"slots": [
  {"capacity": "ENDURANCE", "sessions_per_week": 2, "minutes": 30},
  {"capacity": "STABILITY", "sessions_per_week": 2, "minutes": 15},
  {"capacity": "POWER",     "sessions_per_week": 2, "minutes": 15},
  {"capacity": "STRENGTH",  "sessions_per_week": 3, "minutes": 45}
]}
```

**Sport-agnostic by construction.** A slot names a taxonomy `Capacity` and a dose — never a sport, a position, or an exercise. There is no `sport` column and the shape admits none. Sport-specificity is expressed through fields that already exist (`vehicle_bias`, `horizon`, `primary_target`), so two users with identical templates and different bias get different programmes.

**Validated at write, stored verbatim.** `engine/profile.py::validate_weekly_template` rejects (422) an unknown `capacity`, a duplicate capacity across slots, `sessions_per_week` outside 0-14, `minutes` outside 5-180, and any unknown field. Validation runs *before* the session is touched, so a refused template leaves no row. The value is **not canonicalised** — `PUT` then `GET` is byte-identical, so a slot written `"STABILITY"` reads back `"STABILITY"`; consumers resolve through `taxonomy.resolve_capacity`, which accepts the enum name or its value case-insensitively (open trade: Q105).

**NULL is a valid state, not a degraded one** — a user with no template behaves exactly as before this column existed. `upsert_profile` cannot write NULL back (the shared `is not None` guard, same as `hard_stops` / `live_signals` / every other field), so retirement is expressed as the empty-slot sentinel `{"slots": []}` rather than a clear.

```sql
ALTER TABLE fortification_profiles ADD COLUMN weekly_template JSON;
```

**Readers.** `select_next(..., capacity=)` filters the probe candidate set to one slot's capacity; `GET /engine/next?capacity=` passes it through. Nothing yet resolves *which* slot is due — the template is a declaration, and the consuming lane (weekly resolver) is `ROADMAP` NEXT. How a slot's `minutes` reaches the prescription is deliberately unresolved (Q106).

### 024 — user_knowledge_entries.schedule_item

No migration. `user_knowledge_entries.value` is `sa.JSON()` (Postgres `json`, not `jsonb`) and holds a different shape per `type`; this section records the shape for `type='schedule_item'` only. The parent table predates this document's coverage (see the note under 020). Shape declared and validated at DECISIONS_LOG #233.

**Ownership.** `schedule_item` owns **WHEN**. `fortification_profiles.weekly_template` (023) owns **HOW MUCH OF WHAT KIND**. Stores own facts; the resolver composes them. Any further axis resolves into an existing vocabulary rather than minting a store. `sessions_per_week` appears in both and means different things by design — here it is a calendar fact (*how often this commitment happens*), there a capacity quota (*how many doses of this capacity*).

```json
{
  "activity": "Rugby Training — Seniors (conditioning)",
  "days": ["tuesday"],
  "sessions_per_week": null,
  "hard": true,
  "expected_load": "moderate",
  "time_of_day": "evening",
  "time_range": "6:00pm - 7:30/8:00pm",
  "same_day_training": true,
  "same_day_note": "gym earlier the same day is fine if it is upper body",
  "duration_weeks": null,
  "season_end": "2026-09-05",
  "supersedes": null
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `activity` | str | yes | free text — the user's own naming |
| `days[]` | weekday names, lowercase | conditional | closed set: monday…sunday |
| `sessions_per_week` | int 1–14 | conditional | at least one of `days` / `sessions_per_week` must be present |
| `hard` | bool | yes | strict — a truthy string is refused |
| `expected_load` | `light` \| `moderate` \| `heavy` | on write | nullable **in store** for pre-validator rows |
| `time_of_day` | `morning` \| `afternoon` \| `evening` \| `unknown` | yes | |
| `time_range` | str | no | advisory display only, read by nothing |
| `same_day_training` | bool | yes | strict |
| `same_day_note` | str | no | the prose that was overloading the bool |
| `duration_weeks` | int \| null | yes | |
| `season_end` | date \| null | yes | |
| `supersedes` | int \| null | conditional | see the overlap rule below |
| any other key | — | — | **REFUSED** |

`distinct_from: [<id>, …]` is accepted at write and **never stored** — an acknowledgement token for one write, not a relationship.

**`hard` and `expected_load` are two axes, not one.** `hard` is a *scheduling* fact (immovable in the calendar); `expected_load` is a *cost* fact. Saturday rugby and Thursday set piece are both `hard`, and only one wants the day before scaled back. Conflating them was the original error.

**A multi-day row asserts uniform `expected_load`.** Where load differs by day, the row splits.

**Validated at write, stored verbatim.** `routers/knowledge.py::validate_schedule_item` refuses (422) an unknown key, a non-weekday in `days`, a truthy-string boolean, `sessions_per_week` outside 1–14, a missing required field, and an `expected_load` outside the closed set. Validation runs inside `upsert_knowledge_entry` — the shared write path for `POST /knowledge/entry`, the chat channel, and `routers/health.py` — *before* the session is touched, so a refused write leaves no row. Direct ORM construction is deliberately unvalidated: that is the backfill's path.

**The overlap rule — `supersedes` triggers on day overlap alone.** A write that lands on a day any active row of the same user already holds is refused **409**, regardless of `activity`, naming every overlapping row (id, activity, days, time_of_day). The retry must acknowledge *every* named row via `supersedes: <id>` (replaces it) or `distinct_from: [<id>, …]` (a separate commitment sharing a day). Matching on `activity` was considered and rejected: it is string equality over LLM-generated free text, so a near-miss fails **open** and produces the silent duplicate it was meant to prevent. This refuses more often, including on genuinely distinct same-day commitments — the failure moves from silent to visible, and the caller states which it is.

**Expiry precedence — nothing auto-flips `active`.** Three fields bound a row in time: `season_end` (a calendar fact about the commitment), `duration_weeks` (a duration from `added_at`), and `expires_at` (an absolute date on the row, for one-off overlays). A passed bound is a **badge** in the view and a prompt to the operator, never a state change (#228). Where more than one is set, the **earliest** governs the badge. They are not interchangeable and no validator derives one from another.

**Readers.** `context_builder.py` renders the weekly schedule table and the hard-commitment flags; `GET /knowledge/schedule` (`routers/knowledge.py`) returns active rows unmodified and interprets no shape — it is the calendar view's data source, and its shape-agnosticism is load-bearing. No `engine/` module reads this type. A day name the builder cannot place is now **reported** in THIS WEEK FLAGS rather than silently skipped; it was previously dropped by two separate mechanisms.

**Pre-existing rows were NOT backfilled in this run.** The validator is live at write; the 18 active rows carrying the legacy shape (prose in `same_day_training`, quota values in `days[]`, a `minimum_days` key, duplicate pairs, three stale-active rows) are untouched, because this session had no route to the production database. Validation is at write, so those rows read back unchanged and are not refused on read. The outstanding backfill, the five unperformed prod assertions, and the unexecuted live-row stop-condition are carried in `OPEN_QUESTIONS` Q116.

### 025 — hevy_workouts

Persisted Hevy workout headers — the append-only substrate the Q6 four-window strength-load lane is built on (DECISIONS_LOG #28/#32; persistence-first session). Keyed on the Hevy workout `id` (PK), so ingestion is a PK-upsert: a resync of the same 180-day window re-reads unchanged rows and cannot mint duplicates. `raw` keeps the untouched Hevy payload (JSONB on Postgres, generic JSON on the SQLite test engine) so a later transform version recomputes load from source without a re-fetch — the two-level store (`load_events` derive from this; corrections are recomputes, never migrations of computed history). `dedup_flag` / `dedup_partner_ids` are **sync-derived and recompute-safe** (re-derived each sync). `excluded_at` / `exclusion_reason` are the **operator-owned adjudication mark the sync path never writes** — mirrors the `hevy_exercise_templates.laterality` convention: a resync must not clobber an operator annotation. Load consumers filter `excluded_at IS NULL`. Dedup is flag-and-adjudicate, never auto-delete.

```sql
CREATE TABLE hevy_workouts (
    hevy_id            VARCHAR(64) PRIMARY KEY,        -- Hevy workout id (UUID string)
    user_id            INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    start_time         TIMESTAMPTZ,
    end_time           TIMESTAMPTZ,
    title              VARCHAR,
    raw                JSONB NOT NULL,                 -- full untouched Hevy workout object
    synced_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    dedup_flag         BOOLEAN NOT NULL DEFAULT FALSE, -- sync-derived (D-G); recompute-safe
    dedup_partner_ids  JSONB,                          -- sync-derived list of same-day similar workout ids
    excluded_at        TIMESTAMPTZ,                    -- operator-owned exclusion mark; sync NEVER assigns it
    exclusion_reason   VARCHAR
);

CREATE INDEX ix_hevy_workouts_user_id     ON hevy_workouts (user_id);
CREATE INDEX ix_hevy_workouts_start_time  ON hevy_workouts (start_time);
CREATE INDEX ix_hevy_workouts_user_start  ON hevy_workouts (user_id, start_time);
```

### 026 — hevy_sets

Per-set grain (weight_kg × reps, rpe, set type) the Tier-0 Mechanical/Neuromuscular transform reads. Synthetic integer PK; identity is the natural key `(workout_id, block_index, set_index)` — a re-ingest of the same workout replaces its sets in place. `block_index` is the exercise's position in the workout, `set_index` the set's position in the exercise. Keyed on `exercise_template_id` (#79), **NEVER** the logged title (a workout stores a title snapshot that drifts as Hevy renames templates). **Deliberately NOT an FK to `hevy_exercise_templates`:** a logged template id can be absent from the local catalogue (#79/#81) — exactly the default-template hole the usage-joined laterality audit exists to surface — and a hard FK would reject the ingest of the very rows the audit must find. The audit LEFT-joins. Set fields are the live-verified snake_case shape (`hevy_format.py`, #68).

```sql
CREATE TABLE hevy_sets (
    id                    SERIAL PRIMARY KEY,
    workout_id            VARCHAR(64) NOT NULL REFERENCES hevy_workouts(hevy_id) ON DELETE CASCADE,
    exercise_template_id  VARCHAR(64) NOT NULL,        -- keyed on id (#79); NO FK by design
    block_index           INT NOT NULL,                -- exercise position in workout
    set_index             INT NOT NULL,                -- set position in exercise
    type                  VARCHAR(20),                 -- normal|warmup|dropset|failure
    weight_kg             DOUBLE PRECISION,
    reps                  INT,
    duration_seconds      INT,
    distance_meters       DOUBLE PRECISION,
    rpe                   DOUBLE PRECISION,             -- half-point decimals preserved
    CONSTRAINT uq_hevy_set_position UNIQUE (workout_id, block_index, set_index)
);

CREATE INDEX ix_hevy_sets_workout_id            ON hevy_sets (workout_id);
CREATE INDEX ix_hevy_sets_exercise_template_id  ON hevy_sets (exercise_template_id);
```

### 027 — load_events

The **derived, recomputable** middle layer of the two-level load store (DECISIONS_LOG #28/#32, D-B/D-C/D-D; Q6 gate 2). The Tier-0 transform (`backend/load_events.py`) reads `hevy_workouts.raw` (source of truth, gate 1) and writes one **Mechanical** and one **Neuromuscular** row per session in window-native units (D-A); the daily `load_metrics` + Banister rollup (gate 3) reads these, never the raw payload. Per D-B a coefficient/routing correction is a **recompute, never a migration**: every constant is a REASONED-PRIOR (#32) tagged by `formula_version`, so the transform is delete-and-reinsert per `(user, formula_version)` — a re-run is idempotent on the `uq_load_event_session_window_version` natural key, and a new version's rows coexist beside the old until the rollup switches. **Source-neutral** (parallels the wearable ingestion contract #236): `(source, source_ref)` names the originating session generically with **NO hard FK** to `hevy_workouts` — the same store will later hold Metabolic (aerobic) and Psychological (sRPE) events whose `source_ref` points elsewhere, which a hard FK would reject. `user_id` **is** a hard FK (CASCADE). Rows orphaned by a hard-deleted or adjudicated-out (`excluded_at`, D-G) source session are cleared by the next recompute, which skips those sessions. `provenance` records the transform's **gaps** at row grain (RPE-banded vs reps-banded set counts, e1RM fit vs the 0.5 fallback, non-rep bridging contribution, laterality halving, and untagged-repeated templates surfaced-not-halved) — diagnostic, not consumed by load.

```sql
CREATE TABLE load_events (
    id               SERIAL PRIMARY KEY,
    user_id          INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source           VARCHAR(20) NOT NULL,        -- 'hevy'
    source_ref       VARCHAR(64) NOT NULL,        -- session id (soft ref; NO FK — source-neutral)
    window           VARCHAR(20) NOT NULL,        -- 'mechanical' | 'neuromuscular'
    occurred_at      TIMESTAMPTZ,                 -- session start; NULL if the source session is undated
    load             DOUBLE PRECISION NOT NULL,   -- window-native (D-A)
    unit             VARCHAR(20) NOT NULL,        -- 'kg_reps' | 'nm_au'
    formula_version  VARCHAR(20) NOT NULL,        -- 'tier0-v1'
    provenance       JSONB,                       -- gap-recording blob (diagnostic)
    computed_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_load_event_session_window_version UNIQUE (source, source_ref, window, formula_version)
);

CREATE INDEX ix_load_events_user_id           ON load_events (user_id);
CREATE INDEX ix_load_events_user_window       ON load_events (user_id, window);
CREATE INDEX ix_load_events_user_occurred     ON load_events (user_id, occurred_at);
CREATE INDEX ix_load_events_formula_version   ON load_events (formula_version);
```

## Canonical Metric Type Whitelist

```python
CANONICAL_METRIC_TYPES = {
    # Cardiac
    'heart_rate',           # bpm
    'rr_interval',          # ms — beat-to-beat; primary HRV source
    # Autonomic
    'respiratory_rate',     # breaths per minute
    'skin_temp',            # °C
    # Pulmonary
    'spo2',                 # %
    # Activity
    'steps',                # count in interval
    'distance',             # metres
    'gps_velocity',         # m/s — raw GPS
    # Sleep
    'sleep_stage',          # epoch: 'light' | 'deep' | 'rem' | 'wake'
    'sleep_tib',            # time in bed, minutes
    # Body
    'weight',               # kg
    'body_temp',            # °C
    # Strength (raw set-level, not aggregated)
    'set_weight_kg',
    'set_reps',
    'set_duration_secs',
    'set_distance_m',
    'set_rpe',
    # GPS / movement (raw instrument output)
    'accelerometer_load',   # triaxial composite — physics, not vendor score
    'gps_distance_m',
    'gps_speed_ms',
}

# Explicitly rejected at ingest gate — silently discarded, never logged as unknown
REJECTED_VENDOR_METRICS = {
    'energy_score', 'body_battery', 'stress_score', 'stress_level',
    'sleep_score', 'sleep_quality', 'training_load', 'training_status',
    'recovery_index', 'fitness_age', 'intensity_minutes', 'active_minutes',
    'readiness_score',      # ours, not theirs
    'vo2max_estimate',      # we derive; vendor estimates use age-predicted HRmax
    'hrv_status',           # garmin weekly trend — opaque composite
}
```

## Ingest Gate Logic

```python
async def ingest_metric(source, source_ref, user_id, raw_metric_name,
                         interval_start, interval_end, value, unit, raw):
    # Gate 1: explicit rejection — silent discard
    if raw_metric_name.lower() in REJECTED_VENDOR_METRICS:
        return
    # Gate 2: canonical lookup via metric_type_aliases
    canonical = await resolve_metric_type(source, raw_metric_name)
    if canonical:
        await store_raw_metric(user_id, canonical, source, source_ref,
                               interval_start, interval_end, value, unit, raw)
        return
    # Gate 3: unknown — log for review, do not store
    await log_unknown_metric_type(source, raw_metric_name, value, unit)
```

## Connector Normalisation Contract

Each connector maps vendor field names to platform-standard keys before writing. The schema never sees vendor-specific names. New integrations require only a new map — no migrations.

```python
# Standard source_metrics JSONB keys for workout_metrics
AEROBIC_KEYS = [
    'trimp', 'hrv_rmssd_ms', 'hrv_sdnn_ms', 'mean_rr_ms',
    'zone_1_secs', 'zone_2_secs', 'zone_3_secs', 'zone_4_secs', 'zone_5_secs'
    # Note: zones computed from raw HR against platform zone definitions — not vendor zones
]

STRENGTH_KEYS = [
    'volume_load_kg', 'sets_total', 'reps_total',
    'top_set_intensity_pct', 'muscle_groups'  # text array
]

GPS_CONTACT_KEYS = [
    'hsr_distance_m',       # high-speed running (>4 m/s)
    'sprint_distance_m',    # max velocity efforts
    'accel_count',          # acceleration events
    'decel_count',          # deceleration events (often more injurious)
    'accel_load',           # triaxial accelerometer composite (physics output)
    'impact_count',         # contact/collision events
    'metabolic_power_avg',  # GPS-derived from velocity changes
]

# Vendor → standard key maps
GAMETRAKA_MAP = {
    'PlayerLoad':       'accel_load',
    'TotalDistance':    None,               # → typed column total_distance_m
    'HSRDistance':      'hsr_distance_m',
    'SprintDistance':   'sprint_distance_m',
    'MaxVelocity':      None,               # → typed column max_velocity_ms
    'AccelEvents':      'accel_count',
    'DecelEvents':      'decel_count',
    'ImpactCount':      'impact_count',
    'MetabolicPower':   'metabolic_power_avg',
}

HEVY_MAP = {
    'volume_load':          'volume_load_kg',
    'sets':                 'sets_total',
    'reps':                 'reps_total',
    'top_intensity_pct':    'top_set_intensity_pct',
    'muscle_groups':        'muscle_groups',
}

# Future integrations follow the same pattern — new map, no migration
# CATAPULT_MAP, STATSPORTS_MAP, etc. all target the same standard keys
```

## HR Zone Computation

Zone boundaries are platform-defined. Never use vendor zone distributions — boundaries differ across Polar, Garmin, Apple, Samsung, making stored vendor zone data incomparable across sessions.

```python
# Platform zone definitions — applied uniformly across all sources
ZONE_BOUNDARIES_PCT_HRMAX = {
    'z1': (0.50, 0.60),
    'z2': (0.60, 0.70),
    'z3': (0.70, 0.80),
    'z4': (0.80, 0.90),
    'z5': (0.90, 1.00),
}

def compute_zones(hr_series: list[tuple], hrmax: int) -> dict:
    """
    hr_series: list of (timestamp, bpm) from health_metrics
    hrmax: measured from Polar H10 session — NEVER age-predicted
    returns: zone_N_secs dict + trimp
    """
```

Hard constraint: HRmax must be measured from Polar H10 session data. Age-predicted formulas (220 − age) are explicitly forbidden. One bad HRmax value propagates error into every zone calculation, TRIMP, and VO₂max estimate indefinitely.

## Sleep Stage Confidence

Sleep staging is accepted as input (no raw EEG alternative for consumer hardware) but confidence is systematically lower for deep sleep across all devices.

```python
SLEEP_STAGE_CONFIDENCE = {
    'wake':  'high',       # movement detection is reliable
    'rem':   'moderate',   # REM atonia + HR pattern = reasonable signal
    'light': 'moderate',   # default staging; better than deep
    'deep':  'low',        # no EEG proxy; worst accuracy across all devices and vendors
}
```

Cross-device staging is not comparable. Samsung Ring deep sleep ≠ Garmin deep sleep. Source tag is load-bearing in all sleep stage queries — always filter or group by source when comparing. If a user changes device mid-year, add a discontinuity marker to the trend UI.

## AI Context Bundle

Four targeted queries assembled per request. Not a single join. Cacheable per query. Aligns with Decision #17 (three-tier context model).

```python
async def build_ai_context(user_id, lookback_days=90,
                            confound_window_weeks=8, marker_history_count=5):
    # Query 1: timeline — recent events, lab markers aggregated onto parent event
    # Query 2: active protocol — current stack (protocol_items WHERE ended_at IS NULL)
    # Query 3: marker trends — last N readings per marker from health_markers
    # Query 4: recent confounds — protocol changes in window before last lab panel
    # Tier 1 always-on context comes from user_health_state (migration 014)
    # Tier 3 entry-point seeds are injected by the triggering UI component
```

## Known Gaps / Deferred

| Item | Reason deferred |
|------|-----------------|
| user_health_state (014) | Design after 2 weeks of real data; access patterns unknown |
| metric_type_aliases seed data | Needs systematic vendor API documentation review per integration |
| Overlap dedup for health_metrics intervals | Three-stage funnel covers exact dup; overlapping-interval detection for cross-source metrics (e.g. Health Connect re-broadcasting Polar HR) — implement when first confirmed duplicate observed |
| workout_metrics raw extraction spec | What to extract from R-R series before discarding raw; lock before any discard logic is implemented |
| Hevy resolver activation | Landed but dormant — title-resolution fires only after context_builder emits titles + byte-parity guard re-baseline |
| Hevy create-loop (app-originated exercises) | Recon gate: POST /v1/exercise_templates returns bare integer vs canonical UUID — decides clean upsert vs list-back |
