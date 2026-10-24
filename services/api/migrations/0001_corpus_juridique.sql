-- 0001 — Corpus juridique (données publiques, non rattachées à un tenant).
--
-- Principes :
--  * temps juridique (valid_from / valid_to, intervalle semi-ouvert [début, fin))
--    distinct du temps d'acquisition (sys_from / sys_to) : modèle bitemporel ;
--  * aucune version historique n'est écrasée : les lignes sont en insertion
--    seule ; une correction ferme la période système de la ligne précédente
--    (sys_to) et insère une nouvelle ligne ;
--  * chaque ligne conserve la provenance (source, fichier, empreinte, lot d'ingestion).

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS vector;

-- Configuration de recherche plein texte française insensible aux accents.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_ts_config WHERE cfgname = 'avx_fr') THEN
    CREATE TEXT SEARCH CONFIGURATION avx_fr (COPY = french);
    ALTER TEXT SEARCH CONFIGURATION avx_fr
      ALTER MAPPING FOR hword, hword_part, word WITH unaccent, french_stem;
  END IF;
END
$$;

CREATE TABLE legal_source (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code            text NOT NULL UNIQUE,          -- ex. 'DILA_LEGI'
  name            text NOT NULL,
  publisher       text NOT NULL,
  access_method   text NOT NULL CHECK (access_method IN ('BULK_DUMP', 'API', 'LICENSED_FEED')),
  base_url        text NOT NULL,
  licence_name    text NOT NULL,
  licence_url     text,
  licence_notes   text,
  created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE ingestion_run (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id          uuid NOT NULL REFERENCES legal_source(id),
  connector_version  text NOT NULL,
  archive_name       text NOT NULL,
  archive_sha256     char(64),
  started_at         timestamptz NOT NULL DEFAULT now(),
  finished_at        timestamptz,
  status             text NOT NULL DEFAULT 'RUNNING' CHECK (status IN ('RUNNING', 'SUCCEEDED', 'FAILED')),
  stats              jsonb NOT NULL DEFAULT '{}'::jsonb,
  error              text
);

-- Texte juridique (code, loi, décret...) identifié par son identifiant officiel.
CREATE TABLE legal_document (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id          uuid NOT NULL REFERENCES legal_source(id),
  official_id        text NOT NULL UNIQUE,       -- ex. LEGITEXT000006072050
  nature             text NOT NULL,              -- ex. CODE, LOI, DECRET
  title              text NOT NULL,
  short_title        text,
  -- Champ territorial : NULL = non renseigné par la source (ne jamais présumer).
  territorial_scope  text[],
  created_at         timestamptz NOT NULL DEFAULT now()
);

-- Disposition logique (ex. « article L5422-1 du code du travail »).
-- Limite connue : la clé (document, numéro) ne suit pas les renumérotations ;
-- les liens de transfert sont conservés dans legal_reference.
CREATE TABLE provision (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id   uuid NOT NULL REFERENCES legal_document(id),
  kind          text NOT NULL DEFAULT 'ARTICLE' CHECK (kind IN ('ARTICLE', 'ANNEXE', 'SECTION', 'AUTRE')),
  number        text NOT NULL,                   -- tel que publié : 'L5422-1'
  created_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (document_id, kind, number)
);

-- Version d'une disposition : unité de citation.
CREATE TABLE provision_version (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  provision_id          uuid NOT NULL REFERENCES provision(id),
  official_id           text NOT NULL,           -- ex. LEGIARTI000048590547
  source_status         text NOT NULL,           -- ETAT brut (VIGUEUR, MODIFIE, ...)
  valid_from            date NOT NULL,
  valid_to              date,                    -- NULL = pas de fin connue
  valid_period          daterange GENERATED ALWAYS AS (
                          CASE
                            WHEN valid_to IS NULL THEN daterange(valid_from, NULL, '[)')
                            WHEN valid_to > valid_from THEN daterange(valid_from, valid_to, '[)')
                            ELSE 'empty'::daterange
                          END) STORED,
  raw_valid_from        text NOT NULL,           -- valeur brute de la source
  raw_valid_to          text,                    -- valeur brute (ex. '2999-01-01')
  section_path          text[] NOT NULL DEFAULT '{}',
  text_content          text NOT NULL,
  text_sha256           char(64) NOT NULL,
  nota                  text,
  source_path           text NOT NULL,
  source_file_sha256    char(64) NOT NULL,
  ingestion_run_id      uuid NOT NULL REFERENCES ingestion_run(id),
  sys_from              timestamptz NOT NULL DEFAULT clock_timestamp(),
  sys_to                timestamptz,             -- NULL = connaissance actuelle
  superseded_by         uuid REFERENCES provision_version(id) DEFERRABLE INITIALLY DEFERRED,
  withdrawn_from_source boolean NOT NULL DEFAULT false,
  tsv                   tsvector GENERATED ALWAYS AS (to_tsvector('avx_fr'::regconfig, text_content)) STORED,
  embedding             vector,                  -- dimension fixée par l'ADR du modèle d'embeddings
  CHECK (sys_to IS NULL OR sys_to >= sys_from)
);

CREATE UNIQUE INDEX provision_version_current_uq
  ON provision_version (official_id) WHERE sys_to IS NULL;
CREATE INDEX provision_version_provision_idx ON provision_version (provision_id);
CREATE INDEX provision_version_period_idx ON provision_version USING gist (valid_period);
CREATE INDEX provision_version_tsv_idx ON provision_version USING gin (tsv);

-- Versions déclarées par la source (bloc VERSIONS) : permet de détecter les
-- versions connues mais non encore ingérées (lacunes du corpus).
CREATE TABLE provision_version_declared (
  provision_id   uuid NOT NULL REFERENCES provision(id),
  official_id    text NOT NULL,
  source_status  text NOT NULL,
  raw_valid_from text NOT NULL,
  raw_valid_to   text,
  first_seen_run uuid NOT NULL REFERENCES ingestion_run(id),
  PRIMARY KEY (provision_id, official_id)
);

-- Références croisées (bloc LIENS de LEGI et équivalents).
CREATE TABLE legal_reference (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  from_version_id      uuid NOT NULL REFERENCES provision_version(id),
  link_type            text NOT NULL,            -- ex. CITATION, MODIFIE, CODIFICATION
  direction            text,                     -- 'source' | 'cible' (valeur brute)
  target_official_id   text,
  target_text_id       text,
  target_label         text NOT NULL,
  target_date          date,
  UNIQUE (from_version_id, link_type, direction, target_official_id, target_text_id, target_label)
);
CREATE INDEX legal_reference_target_idx ON legal_reference (target_official_id);

-- Retraits signalés par la source (liste de suppression) : jamais de DELETE.
CREATE TABLE source_withdrawal (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ingestion_run_id  uuid NOT NULL REFERENCES ingestion_run(id),
  official_id       text NOT NULL,
  raw_entry         text NOT NULL,
  matched           boolean NOT NULL,
  recorded_at       timestamptz NOT NULL DEFAULT now()
);

-- Décisions de justice (structure initiale ; connecteurs en phase C).
-- Conformément à l'art. L111-13 COJ, aucune donnée d'identité de magistrat ou
-- de membre du greffe n'est structurée ni exploitée à des fins de profilage.
CREATE TABLE court_decision (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id          uuid NOT NULL REFERENCES legal_source(id),
  official_id        text NOT NULL,
  ecli               text,
  jurisdiction       text NOT NULL,
  formation          text,
  decision_date      date NOT NULL,
  decision_number    text,
  solution           text,
  publication_level  text,
  text_pseudonymised text NOT NULL,
  text_sha256        char(64) NOT NULL,
  ingestion_run_id   uuid NOT NULL REFERENCES ingestion_run(id),
  sys_from           timestamptz NOT NULL DEFAULT clock_timestamp(),
  sys_to             timestamptz,
  tsv                tsvector GENERATED ALWAYS AS (to_tsvector('avx_fr'::regconfig, text_pseudonymised)) STORED
);
CREATE UNIQUE INDEX court_decision_current_uq ON court_decision (source_id, official_id) WHERE sys_to IS NULL;

CREATE TABLE case_law_relation (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  from_decision_id     uuid NOT NULL REFERENCES court_decision(id),
  relation_type        text NOT NULL,           -- ex. APPLIQUE, INTERPRETE, CASSE, RAPPROCHEMENT
  to_decision_id       uuid REFERENCES court_decision(id),
  to_provision_id      uuid REFERENCES provision(id),
  origin               text NOT NULL CHECK (origin IN ('SOURCE', 'EXTRACTION_AUTOMATIQUE', 'VALIDATION_HUMAINE')),
  CHECK (to_decision_id IS NOT NULL OR to_provision_id IS NOT NULL)
);

-- Garde-fou d'immuabilité : seules la fermeture de la période système et le
-- marquage de retrait sont autorisés ; les suppressions sont interdites.
CREATE FUNCTION avx_forbid_history_rewrite() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'suppression interdite sur % (historique immuable)', TG_TABLE_NAME;
  END IF;
  IF OLD.sys_to IS NOT NULL THEN
    RAISE EXCEPTION 'ligne historique close : modification interdite sur %', TG_TABLE_NAME;
  END IF;
  -- Les colonnes générées (tsv, valid_period) ne sont pas encore calculées
  -- dans NEW lors d'un trigger BEFORE : elles sont exclues de la comparaison.
  IF (to_jsonb(NEW) - ARRAY['sys_to', 'superseded_by', 'withdrawn_from_source', 'embedding', 'tsv', 'valid_period'])
     IS DISTINCT FROM (to_jsonb(OLD) - ARRAY['sys_to', 'superseded_by', 'withdrawn_from_source', 'embedding', 'tsv', 'valid_period']) THEN
    RAISE EXCEPTION 'modification du contenu interdite sur % : insérer une nouvelle version', TG_TABLE_NAME;
  END IF;
  RETURN NEW;
END
$$;

CREATE TRIGGER provision_version_immutable
  BEFORE UPDATE OR DELETE ON provision_version
  FOR EACH ROW EXECUTE FUNCTION avx_forbid_history_rewrite();

CREATE TRIGGER court_decision_immutable
  BEFORE UPDATE OR DELETE ON court_decision
  FOR EACH ROW EXECUTE FUNCTION avx_forbid_history_rewrite();
