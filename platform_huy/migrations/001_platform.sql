-- Companion tables for a separate local runtime; v0 tables remain unchanged.
CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY CHECK (version >= 1),
    applied_at TEXT NOT NULL
);

CREATE TABLE run_metadata (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    run_id TEXT NOT NULL UNIQUE,
    source_identity_json TEXT NOT NULL CHECK (json_valid(source_identity_json)),
    start_at TEXT NOT NULL,
    policy_version TEXT NOT NULL CHECK (policy_version = 'huy-demo-v1')
);

CREATE TABLE replay_checkpoint (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    tick_at TEXT,
    scan_watermark TEXT,
    version INTEGER NOT NULL CHECK (version >= 0)
);

CREATE TABLE tick_attempts (
    attempt_id TEXT PRIMARY KEY NOT NULL,
    tick_at TEXT NOT NULL UNIQUE,
    clock_version INTEGER NOT NULL CHECK (clock_version >= 0),
    status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'succeeded', 'failed')),
    a3_status TEXT NOT NULL CHECK (a3_status IN ('pending', 'completed', 'failed')),
    retry_count INTEGER NOT NULL CHECK (retry_count >= 0),
    errors_json TEXT NOT NULL CHECK (json_valid(errors_json)),
    started_wall_at TEXT NOT NULL,
    finished_wall_at TEXT
);

CREATE TABLE demo_clock (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    current_at TEXT,
    version INTEGER NOT NULL CHECK (version >= 0),
    current_attempt_id TEXT REFERENCES tick_attempts(attempt_id)
);

CREATE TABLE replay_commands (
    idempotency_key TEXT PRIMARY KEY NOT NULL,
    principal_id TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    attempt_id TEXT NOT NULL REFERENCES tick_attempts(attempt_id),
    result_json TEXT NOT NULL CHECK (json_valid(result_json))
);

CREATE TABLE tick_results (
    tick_at TEXT PRIMARY KEY NOT NULL,
    result_json TEXT NOT NULL CHECK (json_valid(result_json)),
    result_sha256 TEXT NOT NULL
);

CREATE TABLE a2_progress (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    tick_at TEXT NOT NULL,
    records_json TEXT NOT NULL CHECK (json_valid(records_json))
);

CREATE TABLE customer_messages (
    message_id TEXT PRIMARY KEY NOT NULL,
    contact_id TEXT NOT NULL REFERENCES contact_log(contact_id),
    order_id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    origin TEXT NOT NULL CHECK (origin IN ('text', 'voice_transcript')),
    created_at TEXT NOT NULL,
    received_at TEXT NOT NULL,
    body TEXT NOT NULL,
    request_code TEXT CHECK (request_code = 'late_compensation'),
    request_rule_version TEXT,
    recorded_by TEXT NOT NULL
);

CREATE TABLE execution_evidence (
    evidence_id TEXT PRIMARY KEY NOT NULL,
    order_id TEXT NOT NULL,
    contact_id TEXT REFERENCES contact_log(contact_id),
    message_id TEXT REFERENCES customer_messages(message_id),
    assessment_at TEXT NOT NULL,
    visible_at TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    sha256 TEXT NOT NULL,
    created_by TEXT NOT NULL
);

CREATE TABLE action_receipts (
    action_id TEXT PRIMARY KEY NOT NULL REFERENCES outbox(action_id),
    request_hash TEXT NOT NULL,
    principal_id TEXT NOT NULL,
    attested_source TEXT NOT NULL CHECK (attested_source IN ('a1', 'app', 'rule', 'cancel_reviewer')),
    evidence_id TEXT REFERENCES execution_evidence(evidence_id),
    decision_code TEXT NOT NULL,
    result_json TEXT NOT NULL CHECK (json_valid(result_json)),
    decided_at TEXT NOT NULL
);

CREATE TABLE voucher_ledger (
    voucher_ledger_id TEXT PRIMARY KEY NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    order_id TEXT NOT NULL UNIQUE,
    action_id TEXT NOT NULL UNIQUE REFERENCES outbox(action_id),
    contact_id TEXT NOT NULL REFERENCES contact_log(contact_id),
    face_value_vnd INTEGER NOT NULL CHECK (typeof(face_value_vnd) = 'integer' AND face_value_vnd = 10000),
    policy_version TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE eligibility_reviews (
    review_id TEXT PRIMARY KEY NOT NULL,
    order_id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision >= 1),
    state TEXT NOT NULL CHECK (state IN ('active', 'withdrawn')),
    source_identity_json TEXT NOT NULL CHECK (json_valid(source_identity_json)),
    evidence_as_of TEXT NOT NULL,
    material_fingerprints_json TEXT NOT NULL CHECK (json_valid(material_fingerprints_json)),
    decision_json TEXT NOT NULL CHECK (json_valid(decision_json)),
    evidence_refs_json TEXT NOT NULL CHECK (json_valid(evidence_refs_json)),
    reason TEXT NOT NULL,
    reviewed_by TEXT NOT NULL,
    reviewed_wall_at TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    request_hash TEXT NOT NULL,
    UNIQUE (order_id, revision)
);

CREATE TABLE cancel_requests (
    cancel_id TEXT PRIMARY KEY NOT NULL,
    request_action_id TEXT NOT NULL UNIQUE REFERENCES outbox(action_id),
    order_id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('awaiting_confirmation', 'awaiting_review', 'approved', 'rejected')),
    confirmation_id TEXT NOT NULL UNIQUE,
    version INTEGER NOT NULL CHECK (version >= 1),
    order_snapshot_sha256 TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    confirmed_at TEXT,
    reviewed_at TEXT,
    reviewed_by TEXT,
    review_reason TEXT
);

CREATE TABLE workflow_commands (
    idempotency_key TEXT PRIMARY KEY NOT NULL,
    request_hash TEXT NOT NULL,
    principal_id TEXT NOT NULL,
    cancel_id TEXT NOT NULL REFERENCES cancel_requests(cancel_id),
    result_json TEXT NOT NULL CHECK (json_valid(result_json)),
    created_at TEXT NOT NULL
);
