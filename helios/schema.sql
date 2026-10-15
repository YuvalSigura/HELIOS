CREATE TABLE IF NOT EXISTS organizations (
  id INTEGER PRIMARY KEY, slug TEXT UNIQUE NOT NULL, name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
  id SERIAL PRIMARY KEY, org_id INTEGER NOT NULL REFERENCES organizations(id),
  email TEXT UNIQUE NOT NULL, pass_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('analyst','manager','reviewer'))
);
CREATE TABLE IF NOT EXISTS connectors (
  id INTEGER PRIMARY KEY, org_id INTEGER NOT NULL REFERENCES organizations(id),
  name TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active'
);
CREATE TABLE IF NOT EXISTS reports (
  id SERIAL PRIMARY KEY, owner_org_id INTEGER NOT NULL REFERENCES organizations(id),
  title TEXT NOT NULL, summary TEXT NOT NULL,
  connector_id INTEGER NOT NULL REFERENCES connectors(id),
  cloned_from INTEGER REFERENCES reports(id)
);
CREATE TABLE IF NOT EXISTS report_shares (
  report_id INTEGER NOT NULL REFERENCES reports(id),
  grantee_org_id INTEGER NOT NULL REFERENCES organizations(id),
  PRIMARY KEY(report_id, grantee_org_id)
);
CREATE TABLE IF NOT EXISTS report_notes (
  id SERIAL PRIMARY KEY, report_id INTEGER NOT NULL REFERENCES reports(id),
  visibility TEXT NOT NULL CHECK (visibility IN ('public','internal')),
  body TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS data_rows (
  id SERIAL PRIMARY KEY, connector_id INTEGER NOT NULL REFERENCES connectors(id),
  period TEXT NOT NULL, department TEXT NOT NULL, amount INTEGER NOT NULL,
  reference TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS exports (
  id UUID PRIMARY KEY, requested_by INTEGER NOT NULL REFERENCES users(id),
  requester_org_id INTEGER NOT NULL REFERENCES organizations(id),
  report_id INTEGER NOT NULL REFERENCES reports(id),
  state TEXT NOT NULL CHECK(state IN ('queued','running','done','failed')),
  object_key TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS audit_events (
  id BIGSERIAL PRIMARY KEY, happened_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  kind TEXT NOT NULL, actor_id INTEGER REFERENCES users(id),
  owner_org_id INTEGER REFERENCES organizations(id),
  details JSONB NOT NULL DEFAULT '{}'::jsonb
);
-- Markers are operator-only truth; never queried by target web or worker.
CREATE TABLE IF NOT EXISTS oracle_markers (
  kind TEXT PRIMARY KEY, value TEXT NOT NULL
);
