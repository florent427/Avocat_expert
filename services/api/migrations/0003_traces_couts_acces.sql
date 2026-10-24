-- 0003 — Traces d'exécution, coûts, quotas et journaux d'accès.
--
-- Les traces ne contiennent pas le texte des questions ni des documents
-- client : seulement des empreintes, des tailles et des métadonnées.

CREATE TABLE execution_trace (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id  uuid REFERENCES organization(id),
  user_id          uuid REFERENCES app_user(id),
  matter_id        uuid REFERENCES matter(id),
  operation        text NOT NULL,                 -- ex. 'answer', 'search'
  input_sha256     char(64) NOT NULL,
  input_length     integer NOT NULL,
  legal_as_of      date,
  routing          jsonb NOT NULL DEFAULT '{}'::jsonb,
  outcome          text NOT NULL CHECK (outcome IN ('OK', 'BLOCKED', 'PARTIAL', 'ERROR')),
  started_at       timestamptz NOT NULL,
  finished_at      timestamptz NOT NULL,
  CHECK (finished_at >= started_at)
);

CREATE TABLE execution_step (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  trace_id         uuid NOT NULL REFERENCES execution_trace(id),
  organization_id  uuid REFERENCES organization(id),
  position         integer NOT NULL,
  component        text NOT NULL,                 -- agent ou service
  component_version text NOT NULL,
  input_sha256     char(64),
  output_sha256    char(64),
  status           text NOT NULL CHECK (status IN ('OK', 'SKIPPED', 'BLOCKED', 'ERROR')),
  detail           jsonb NOT NULL DEFAULT '{}'::jsonb,
  started_at       timestamptz NOT NULL,
  finished_at      timestamptz NOT NULL,
  UNIQUE (trace_id, position)
);

-- Coûts : une ligne par appel à un fournisseur (modèle, embeddings...).
CREATE TABLE usage_record (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id      uuid REFERENCES organization(id),
  trace_id             uuid REFERENCES execution_trace(id),
  provider             text NOT NULL,
  model                text NOT NULL,
  input_tokens         integer NOT NULL DEFAULT 0 CHECK (input_tokens >= 0),
  output_tokens        integer NOT NULL DEFAULT 0 CHECK (output_tokens >= 0),
  cache_read_tokens    integer NOT NULL DEFAULT 0 CHECK (cache_read_tokens >= 0),
  cache_write_tokens   integer NOT NULL DEFAULT 0 CHECK (cache_write_tokens >= 0),
  call_count           integer NOT NULL DEFAULT 1 CHECK (call_count >= 0),
  duration_ms          integer NOT NULL CHECK (duration_ms >= 0),
  -- Montants en micro-euros (entiers) pour éviter les erreurs d'arrondi.
  estimated_cost_micro_eur bigint NOT NULL CHECK (estimated_cost_micro_eur >= 0),
  price_table_version  text NOT NULL,
  recorded_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX usage_record_org_time_idx ON usage_record (organization_id, recorded_at);

CREATE TABLE tenant_budget (
  organization_id        uuid PRIMARY KEY REFERENCES organization(id),
  period                 text NOT NULL DEFAULT 'MONTH' CHECK (period IN ('DAY', 'MONTH')),
  soft_limit_micro_eur   bigint NOT NULL CHECK (soft_limit_micro_eur >= 0),
  hard_limit_micro_eur   bigint NOT NULL CHECK (hard_limit_micro_eur >= soft_limit_micro_eur),
  degraded_mode          text NOT NULL DEFAULT 'EXTRACTIVE_ONLY' CHECK (degraded_mode IN ('EXTRACTIVE_ONLY', 'BLOCK')),
  updated_at             timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE billing_account (
  organization_id   uuid PRIMARY KEY REFERENCES organization(id),
  plan              text NOT NULL,
  billing_email     text NOT NULL,
  external_customer_ref text,                   -- référence chez le prestataire de paiement
  created_at        timestamptz NOT NULL DEFAULT now()
);

-- Journal d'accès : insertion seule.
CREATE TABLE access_log (
  id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  organization_id  uuid REFERENCES organization(id),
  user_id          uuid REFERENCES app_user(id),
  action           text NOT NULL,
  resource_type    text NOT NULL,
  resource_id      text,
  outcome          text NOT NULL CHECK (outcome IN ('ALLOWED', 'DENIED')),
  request_id       text,
  occurred_at      timestamptz NOT NULL DEFAULT now()
);

CREATE FUNCTION avx_forbid_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'table % en insertion seule', TG_TABLE_NAME;
END
$$;

CREATE TRIGGER access_log_append_only
  BEFORE UPDATE OR DELETE ON access_log
  FOR EACH ROW EXECUTE FUNCTION avx_forbid_mutation();

DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['execution_trace', 'execution_step', 'usage_record', 'access_log']
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (organization_id IS NULL OR organization_id = avx_current_tenant()) '
      'WITH CHECK (organization_id IS NULL OR organization_id = avx_current_tenant())', t);
  END LOOP;
  FOREACH t IN ARRAY ARRAY['tenant_budget', 'billing_account']
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (organization_id = avx_current_tenant()) '
      'WITH CHECK (organization_id = avx_current_tenant())', t);
  END LOOP;
END
$$;

-- Privilèges minimaux du rôle applicatif.
GRANT USAGE ON SCHEMA public TO avx_app;
GRANT SELECT ON legal_source, legal_document, provision, provision_version,
  provision_version_declared, legal_reference, court_decision, case_law_relation TO avx_app;
GRANT SELECT, INSERT, UPDATE ON matter, matter_document, matter_fact, legal_argument,
  report, report_claim, membership TO avx_app;
GRANT SELECT, INSERT ON citation_check, execution_trace, execution_step, usage_record, access_log TO avx_app;
GRANT SELECT ON organization, app_user, tenant_budget, billing_account TO avx_app;
