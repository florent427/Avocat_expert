-- 0002 — Organisations, utilisateurs, dossiers et pièces (données client).
--
-- Isolation multi-tenant : chaque table client porte organization_id et est
-- protégée par Row Level Security (FORCE), sur la base du paramètre de
-- session `app.tenant_id` positionné par le serveur après authentification.
-- L'application se connecte avec le rôle avx_app (ni propriétaire, ni BYPASSRLS).

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'avx_app') THEN
    CREATE ROLE avx_app NOLOGIN;
  END IF;
END
$$;

-- Fonction utilitaire : tenant courant, NULL si non positionné (=> aucune ligne visible).
CREATE FUNCTION avx_current_tenant() RETURNS uuid
LANGUAGE sql STABLE AS $$
  SELECT nullif(current_setting('app.tenant_id', true), '')::uuid
$$;

CREATE TABLE organization (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name           text NOT NULL,
  -- Liste explicite des sous-traitants autorisés à recevoir des documents
  -- client (ex. fournisseur de modèles). Vide = aucun envoi externe.
  authorized_processors text[] NOT NULL DEFAULT '{}',
  data_retention_days   integer NOT NULL DEFAULT 365 CHECK (data_retention_days > 0),
  created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE app_user (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  oidc_issuer    text NOT NULL,
  oidc_subject   text NOT NULL,
  email          text NOT NULL,
  display_name   text,
  mfa_required   boolean NOT NULL DEFAULT true,
  created_at     timestamptz NOT NULL DEFAULT now(),
  deactivated_at timestamptz,
  UNIQUE (oidc_issuer, oidc_subject)
);

CREATE TABLE membership (
  organization_id uuid NOT NULL REFERENCES organization(id),
  user_id         uuid NOT NULL REFERENCES app_user(id),
  role            text NOT NULL CHECK (role IN ('OWNER', 'ADMIN', 'LAWYER', 'ASSISTANT', 'READER', 'AUDITOR')),
  created_at      timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (organization_id, user_id)
);

CREATE TABLE matter (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id  uuid NOT NULL REFERENCES organization(id),
  reference        text NOT NULL,
  title            text NOT NULL,
  -- Date d'appréciation du droit par défaut pour le dossier.
  legal_as_of      date,
  territory        text,
  status           text NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'CLOSED', 'ARCHIVED')),
  created_by       uuid NOT NULL REFERENCES app_user(id),
  created_at       timestamptz NOT NULL DEFAULT now(),
  closed_at        timestamptz,
  UNIQUE (organization_id, reference)
);

CREATE TABLE matter_document (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id  uuid NOT NULL REFERENCES organization(id),
  matter_id        uuid NOT NULL REFERENCES matter(id),
  filename         text NOT NULL,
  media_type       text NOT NULL,
  size_bytes       bigint NOT NULL CHECK (size_bytes >= 0),
  sha256           char(64) NOT NULL,
  storage_key      text NOT NULL,              -- clé objet S3 (bucket chiffré KMS)
  scan_status      text NOT NULL DEFAULT 'PENDING' CHECK (scan_status IN ('PENDING', 'CLEAN', 'REJECTED')),
  piece_number     text,                       -- numérotation de bordereau
  uploaded_by      uuid NOT NULL REFERENCES app_user(id),
  uploaded_at      timestamptz NOT NULL DEFAULT now(),
  erased_at        timestamptz                 -- effacement RGPD / fin de conservation
);

CREATE TABLE matter_fact (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id    uuid NOT NULL REFERENCES organization(id),
  matter_id          uuid NOT NULL REFERENCES matter(id),
  kind               text NOT NULL CHECK (kind IN ('FAIT', 'EVENEMENT', 'HYPOTHESE')),
  occurred_on        date,
  occurred_on_precision text CHECK (occurred_on_precision IN ('JOUR', 'MOIS', 'ANNEE', 'INCONNUE')),
  description        text NOT NULL,
  source_document_id uuid REFERENCES matter_document(id),
  source_locator     text,                     -- page, paragraphe...
  established        boolean NOT NULL DEFAULT false,
  created_at         timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE legal_argument (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id  uuid NOT NULL REFERENCES organization(id),
  matter_id        uuid NOT NULL REFERENCES matter(id),
  stance           text NOT NULL CHECK (stance IN ('FAVORABLE', 'CONTRAIRE', 'NEUTRE')),
  summary          text NOT NULL,
  created_by_agent text,
  validated_by     uuid REFERENCES app_user(id),
  validated_at     timestamptz,
  created_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE report (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id  uuid NOT NULL REFERENCES organization(id),
  matter_id        uuid REFERENCES matter(id),
  title            text NOT NULL,
  legal_as_of      date NOT NULL,
  status           text NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT', 'BLOCKED', 'PENDING_REVIEW', 'VALIDATED')),
  created_at       timestamptz NOT NULL DEFAULT now(),
  validated_by     uuid REFERENCES app_user(id),
  validated_at     timestamptz
);

-- Affirmation d'un rapport, typée (fait / hypothèse / droit applicable /
-- interprétation / recommandation) et rattachée à ses vérifications.
CREATE TABLE report_claim (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id  uuid NOT NULL REFERENCES organization(id),
  report_id        uuid NOT NULL REFERENCES report(id),
  position         integer NOT NULL,
  kind             text NOT NULL CHECK (kind IN ('FAIT', 'HYPOTHESE', 'DROIT_APPLICABLE', 'INTERPRETATION', 'RECOMMANDATION')),
  statement        text NOT NULL,
  support_status   text NOT NULL CHECK (support_status IN ('FONDEE', 'INCERTAINE', 'BLOQUEE')),
  argument_id      uuid REFERENCES legal_argument(id),
  UNIQUE (report_id, position)
);

-- Vérification d'une citation (résultat du moteur déterministe lexverif).
CREATE TABLE citation_check (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id       uuid REFERENCES organization(id),   -- NULL pour une recherche hors dossier
  claim_id              uuid REFERENCES report_claim(id),
  cited_official_id     text NOT NULL,
  provision_version_id  uuid REFERENCES provision_version(id),
  quote_sha256          char(64) NOT NULL,
  legal_as_of           date NOT NULL,
  territory             text,
  verdict               text NOT NULL CHECK (verdict IN ('CONFORME', 'INCERTAIN', 'NON_CONFORME')),
  checks                jsonb NOT NULL,
  engine_version        text NOT NULL,
  contract_version      text NOT NULL,
  checked_at            timestamptz NOT NULL DEFAULT now()
);

DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['matter', 'matter_document', 'matter_fact', 'legal_argument', 'report', 'report_claim']
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (organization_id = avx_current_tenant()) '
      'WITH CHECK (organization_id = avx_current_tenant())', t);
  END LOOP;
END
$$;

-- citation_check : lignes du tenant, ou lignes sans tenant (recherche publique).
ALTER TABLE citation_check ENABLE ROW LEVEL SECURITY;
ALTER TABLE citation_check FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON citation_check
  USING (organization_id IS NULL OR organization_id = avx_current_tenant())
  WITH CHECK (organization_id IS NULL OR organization_id = avx_current_tenant());

-- membership : visible uniquement pour l'organisation courante.
ALTER TABLE membership ENABLE ROW LEVEL SECURITY;
ALTER TABLE membership FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON membership
  USING (organization_id = avx_current_tenant())
  WITH CHECK (organization_id = avx_current_tenant());

-- organization : seule l'organisation courante est visible.
ALTER TABLE organization ENABLE ROW LEVEL SECURITY;
ALTER TABLE organization FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON organization USING (id = avx_current_tenant());

-- app_user : seuls les membres de l'organisation courante sont visibles.
ALTER TABLE app_user ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_user FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_members ON app_user USING (
  EXISTS (SELECT 1 FROM membership m WHERE m.user_id = app_user.id)
);

-- Résolution du principal après validation du jeton OIDC (avant que le
-- tenant ne soit connu). SECURITY DEFINER, périmètre strictement limité.
CREATE FUNCTION avx_resolve_principal(p_issuer text, p_subject text)
RETURNS TABLE (user_id uuid, organization_id uuid, role text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
  SELECT u.id, m.organization_id, m.role
  FROM app_user u
  JOIN membership m ON m.user_id = u.id
  WHERE u.oidc_issuer = p_issuer
    AND u.oidc_subject = p_subject
    AND u.deactivated_at IS NULL
$$;
REVOKE ALL ON FUNCTION avx_resolve_principal(text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION avx_resolve_principal(text, text) TO avx_app;
