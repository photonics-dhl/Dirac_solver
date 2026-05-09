-- Dirac Reference Database Schema
-- SQLite-based structured store for Octopus DFT calculation reference data

CREATE TABLE IF NOT EXISTS cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL UNIQUE,
    formula TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'dft_gs_3d',
    calculation_mode TEXT NOT NULL DEFAULT 'gs',
    species_mode TEXT NOT NULL,
    xc_functional TEXT,
    confidence_tier TEXT NOT NULL CHECK(confidence_tier IN ('A-ready', 'B-needs-evidence', 'C-pending')),
    description TEXT,
    source_url TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS energies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    quantity TEXT NOT NULL,
    value_hartree REAL NOT NULL,
    value_ev REAL,
    orbital_label TEXT,
    tolerance_relative REAL NOT NULL DEFAULT 0.03,
    source TEXT,
    nist_reference_hartree REAL,
    nist_match_percent REAL,
    verified INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS parameters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    param_name TEXT NOT NULL,
    param_value TEXT NOT NULL,
    unit TEXT,
    is_critical INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS provenance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    source_name TEXT NOT NULL,
    source_url TEXT,
    source_type TEXT NOT NULL,
    citation TEXT,
    doi TEXT,
    extraction_date TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS properties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    property_name TEXT NOT NULL,
    property_value TEXT NOT NULL,
    unit TEXT,
    methodology TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_cases_case_id ON cases(case_id);
CREATE INDEX IF NOT EXISTS idx_cases_formula ON cases(formula);
CREATE INDEX IF NOT EXISTS idx_cases_confidence ON cases(confidence_tier);
CREATE INDEX IF NOT EXISTS idx_energies_case_id ON energies(case_id);
CREATE INDEX IF NOT EXISTS idx_parameters_case_id ON parameters(case_id);
CREATE INDEX IF NOT EXISTS idx_provenance_case_id ON provenance(case_id);
CREATE INDEX IF NOT EXISTS idx_properties_case_id ON properties(case_id);

-- View: full case details with energies and parameters
CREATE VIEW IF NOT EXISTS v_case_summary AS
SELECT
    c.id,
    c.case_id,
    c.formula,
    c.category,
    c.calculation_mode,
    c.species_mode,
    c.xc_functional,
    c.confidence_tier,
    c.description,
    c.source_url,
    GROUP_CONCAT(DISTINCT e.quantity || '=' || e.value_hartree || 'Ha') AS energy_summary,
    GROUP_CONCAT(DISTINCT p.param_name || '=' || p.param_value) AS param_summary,
    c.updated_at
FROM cases c
LEFT JOIN energies e ON c.id = e.case_id
LEFT JOIN parameters p ON c.id = p.case_id
GROUP BY c.id;
