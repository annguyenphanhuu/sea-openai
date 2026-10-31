CREATE TABLE runtime_meta(schema_version INTEGER NOT NULL, boot_generation INTEGER NOT NULL);
INSERT INTO runtime_meta VALUES(1, 0);
CREATE TABLE sessions(
    id TEXT PRIMARY KEY, run_id TEXT NOT NULL, principal TEXT NOT NULL,
    order_id TEXT NOT NULL, open_key TEXT NOT NULL UNIQUE, data TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 0);
CREATE TABLE requests(
    id TEXT PRIMARY KEY, run_id TEXT NOT NULL, session_id TEXT NOT NULL REFERENCES sessions(id),
    principal TEXT NOT NULL, client_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
    payload TEXT NOT NULL, phase TEXT NOT NULL CHECK(phase IN ('processing','retry_wait','committed','failed_terminal')),
    base_version INTEGER NOT NULL, processing_attempts INTEGER NOT NULL DEFAULT 0,
    model_attempts INTEGER NOT NULL DEFAULT 0 CHECK(model_attempts BETWEEN 0 AND 1),
    next_at REAL NOT NULL DEFAULT 0, context TEXT, response TEXT, error TEXT,
    UNIQUE(run_id,principal,session_id,client_id));
CREATE TABLE events(
    id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id), sequence INTEGER NOT NULL,
    visibility TEXT NOT NULL, kind TEXT NOT NULL, content TEXT NOT NULL,
    UNIQUE(session_id, sequence));
CREATE TABLE evidence_bundles(ref TEXT PRIMARY KEY, request_id TEXT REFERENCES requests(id), data TEXT NOT NULL, trace TEXT NOT NULL);
CREATE TABLE pending_effects(
    id TEXT PRIMARY KEY, run_id TEXT NOT NULL, effect_key TEXT NOT NULL,
    session_id TEXT NOT NULL REFERENCES sessions(id), proposal TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1, state TEXT NOT NULL DEFAULT 'pending_delivery',
    outcome TEXT NOT NULL DEFAULT 'unknown', attempts INTEGER NOT NULL DEFAULT 0,
    lookups INTEGER NOT NULL DEFAULT 0, next_at REAL NOT NULL DEFAULT 0,
    session_version INTEGER NOT NULL, manual INTEGER NOT NULL DEFAULT 0,
    UNIQUE(run_id, effect_key));
CREATE TABLE effect_proposals(
    effect_id TEXT NOT NULL REFERENCES pending_effects(id), revision INTEGER NOT NULL,
    request_id TEXT NOT NULL REFERENCES requests(id), proposal TEXT NOT NULL,
    PRIMARY KEY(effect_id,revision));
CREATE TABLE effect_attempts(
    id TEXT PRIMARY KEY, effect_id TEXT NOT NULL REFERENCES pending_effects(id),
    revision INTEGER NOT NULL, kind TEXT NOT NULL, started_at REAL NOT NULL,
    deadline REAL NOT NULL, result TEXT);
CREATE TABLE receipts(
    effect_id TEXT NOT NULL REFERENCES pending_effects(id), revision INTEGER NOT NULL,
    data TEXT NOT NULL, PRIMARY KEY(effect_id,revision));
CREATE INDEX due_effects ON pending_effects(state,next_at);
CREATE INDEX retry_requests ON requests(phase,next_at);
