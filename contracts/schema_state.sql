-- Apply only to a separate runtime state database, never to a release database.
-- Timestamps use UTC ISO 8601 with a fixed microsecond precision and a Z suffix.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS contact_log (
    contact_id TEXT PRIMARY KEY NOT NULL,
    order_id TEXT NOT NULL,
    channel TEXT NOT NULL CHECK (channel IN ('chat', 'web_voice')),
    initiated_by TEXT NOT NULL CHECK (initiated_by IN ('A1', 'customer', 'human')),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'active', 'completed', 'failed', 'transferred')),
    requested_at TEXT NOT NULL,
    opened_at TEXT,
    closed_at TEXT,
    guard_checked_at TEXT,
    provider_session_id TEXT,
    turn_count INTEGER NOT NULL DEFAULT 0 CHECK (turn_count >= 0),
    abusive_turn_count INTEGER NOT NULL DEFAULT 0 CHECK (abusive_turn_count >= 0),
    summary TEXT
);

CREATE TABLE IF NOT EXISTS outbox (
    action_id TEXT PRIMARY KEY NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    order_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN (
        'open_chat', 'start_web_voice', 'request_cancel',
        'cancel_order', 'handoff_human', 'grant_late_xu'
    )),
    actor TEXT NOT NULL CHECK (actor IN ('A1', 'A2', 'A3', 'human')),
    contact_id TEXT REFERENCES contact_log(contact_id),
    confirmation_id TEXT,
    evidence_refs_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(evidence_refs_json)),
    requested_at TEXT NOT NULL,
    available_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'claimed', 'succeeded', 'failed', 'blocked')),
    claimed_at TEXT,
    completed_at TEXT,
    error_code TEXT
);
CREATE INDEX IF NOT EXISTS outbox_ready ON outbox(status, available_at);

-- This ledger is reserved for late compensation; UNIQUE(order_id) prevents re-grants.
-- Only the future platform executor may insert financial effects.
CREATE TABLE IF NOT EXISTS ledger_new (
    ledger_id TEXT PRIMARY KEY NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    order_id TEXT NOT NULL UNIQUE,
    action_id TEXT NOT NULL UNIQUE REFERENCES outbox(action_id),
    contact_id TEXT NOT NULL REFERENCES contact_log(contact_id),
    amount_xu INTEGER NOT NULL CHECK (
        typeof(amount_xu) = 'integer'
        AND amount_xu BETWEEN 10000 AND 1000000
        AND amount_xu % 1000 = 0
    ),
    reason_code TEXT NOT NULL DEFAULT 'late_delivery' CHECK (reason_code = 'late_delivery'),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS guard_heartbeat (
    tick_at TEXT PRIMARY KEY NOT NULL,
    recorded_at TEXT NOT NULL,
    proactive_contact_allowed INTEGER NOT NULL
        CHECK (proactive_contact_allowed IN (0, 1)),
    reason_codes_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(reason_codes_json))
);

CREATE TABLE IF NOT EXISTS feed_health (
    feed TEXT NOT NULL,
    tick_at TEXT NOT NULL REFERENCES guard_heartbeat(tick_at),
    status TEXT NOT NULL CHECK (status IN ('healthy', 'degraded', 'blocked', 'unknown')),
    last_ingested_at TEXT,
    checked_at TEXT NOT NULL,
    reason_codes_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(reason_codes_json)),
    PRIMARY KEY (feed, tick_at)
);

CREATE TABLE IF NOT EXISTS incidents (
    incident_id TEXT PRIMARY KEY NOT NULL,
    feed TEXT,
    order_id TEXT,
    detected_at TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
    summary TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(evidence_json)),
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'resolved')),
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS supervisor_questions (
    question_id TEXT PRIMARY KEY NOT NULL,
    order_id TEXT,
    asked_by TEXT NOT NULL DEFAULT 'A2' CHECK (asked_by = 'A2'),
    question_text TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(evidence_json)),
    asked_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'answered')),
    answer_text TEXT,
    answered_at TEXT,
    answered_by TEXT
);

-- Authorization and monotonic A3 tightening belong to the future platform gate.
CREATE TABLE IF NOT EXISTS controls (
    control_key TEXT NOT NULL,
    scope TEXT NOT NULL DEFAULT 'global',
    value_json TEXT NOT NULL CHECK (json_valid(value_json)),
    updated_at TEXT NOT NULL,
    updated_by TEXT NOT NULL CHECK (updated_by IN ('A3', 'human')),
    reason_code TEXT NOT NULL,
    PRIMARY KEY (control_key, scope)
);
