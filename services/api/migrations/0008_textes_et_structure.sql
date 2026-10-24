-- 0008 — Versions de textes et structure (plan) des textes LEGI.
--
-- Mêmes principes que provision_version (0001, 0007) : insertion seule,
-- période juridique distincte du temps d'acquisition, provenance complète,
-- dates non fixées jamais converties en dates réelles.
--
--  * document_version         : fichier texte/version (une version LEGITEXT
--                               d'un texte identifié par son cid) ;
--  * structure_node_version   : racine du plan d'une version de texte
--                               (texte/struct) ou section (section_ta), telle
--                               que livrée ;
--  * structure_entry          : entrées ordonnées d'un nœud (sous-section,
--                               article, version du texte) avec leur période
--                               et leur état. Une section ne porte pas de dates
--                               propres : elles figurent sur l'entrée qui la
--                               rattache à son parent.

CREATE FUNCTION avx_period(p_from date, p_to date) RETURNS daterange
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT CASE
    WHEN p_from IS NULL THEN 'empty'::daterange
    WHEN p_to IS NULL THEN daterange(p_from, NULL, '[)')
    WHEN p_to > p_from THEN daterange(p_from, p_to, '[)')
    ELSE 'empty'::daterange
  END
$$;

CREATE TABLE document_version (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id           uuid NOT NULL REFERENCES legal_document(id),
  official_id           text NOT NULL,           -- LEGITEXT… (version)
  nature                text NOT NULL,
  title                 text NOT NULL,           -- TITRE
  title_full            text,                    -- TITREFULL
  source_status         text NOT NULL,
  valid_from            date,
  valid_to              date,
  end_undetermined      boolean NOT NULL DEFAULT false,
  valid_period          daterange GENERATED ALWAYS AS (avx_period(valid_from, valid_to)) STORED,
  raw_valid_from        text NOT NULL,
  raw_valid_to          text,
  number                text,
  nor                   text,
  publication_date      date,
  raw_publication_date  text,
  signature_date        date,                    -- DATE_TEXTE
  raw_signature_date    text,
  last_modified         date,                    -- DERNIERE_MODIFICATION
  upcoming_versions     text[] NOT NULL DEFAULT '{}',  -- VERSIONS_A_VENIR (brut)
  publication_origin    text,
  authority             text,
  ministry              text,
  visas                 text,
  signatories           text,
  preparatory_work      text,
  nota                  text,
  abrogation            text,
  rectification         text,
  source_path           text NOT NULL,
  source_file_sha256    char(64) NOT NULL,
  ingestion_run_id      uuid NOT NULL REFERENCES ingestion_run(id),
  sys_from              timestamptz NOT NULL DEFAULT clock_timestamp(),
  sys_to                timestamptz,
  superseded_by         uuid REFERENCES document_version(id) DEFERRABLE INITIALLY DEFERRED,
  withdrawn_from_source boolean NOT NULL DEFAULT false,
  CHECK (sys_to IS NULL OR sys_to >= sys_from),
  CHECK (NOT (end_undetermined AND valid_to IS NOT NULL))
);
CREATE UNIQUE INDEX document_version_current_uq ON document_version (official_id) WHERE sys_to IS NULL;
CREATE INDEX document_version_document_idx ON document_version (document_id);

CREATE TABLE document_reference (
  from_document_version_id uuid NOT NULL REFERENCES document_version(id),
  link_type                text NOT NULL,
  direction                text,
  target_official_id       text,
  target_text_id           text,
  target_label             text NOT NULL,
  target_date              date,
  UNIQUE (from_document_version_id, link_type, direction, target_official_id, target_text_id, target_label)
);
CREATE INDEX document_reference_target_idx ON document_reference (target_official_id);

CREATE TABLE structure_node_version (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kind                  text NOT NULL CHECK (kind IN ('TEXTE', 'SECTION')),
  official_id           text NOT NULL,           -- LEGITEXT… (racine) ou LEGISCTA…
  document_id           uuid NOT NULL REFERENCES legal_document(id),
  title                 text,                    -- TITRE_TA (sections)
  commentary            text,                    -- COMMENTAIRE
  context               jsonb NOT NULL DEFAULT '[]'::jsonb,  -- sections parentes et leurs intitulés datés (brut)
  source_path           text NOT NULL,
  source_file_sha256    char(64) NOT NULL,
  ingestion_run_id      uuid NOT NULL REFERENCES ingestion_run(id),
  sys_from              timestamptz NOT NULL DEFAULT clock_timestamp(),
  sys_to                timestamptz,
  superseded_by         uuid REFERENCES structure_node_version(id) DEFERRABLE INITIALLY DEFERRED,
  withdrawn_from_source boolean NOT NULL DEFAULT false,
  CHECK (sys_to IS NULL OR sys_to >= sys_from)
);
CREATE UNIQUE INDEX structure_node_current_uq ON structure_node_version (kind, official_id) WHERE sys_to IS NULL;
CREATE INDEX structure_node_document_idx ON structure_node_version (document_id) WHERE sys_to IS NULL;

CREATE TABLE structure_entry (
  node_version_id     uuid NOT NULL REFERENCES structure_node_version(id),
  position            integer NOT NULL,
  entry_kind          text NOT NULL CHECK (entry_kind IN ('SECTION', 'ARTICLE', 'VERSION_TEXTE')),
  target_official_id  text NOT NULL,
  target_cid          text,
  number              text,
  label               text,
  level               integer,
  source_status       text NOT NULL,           -- etat brut ('' observé pour la version JORF d'origine)
  valid_from          date,
  valid_to            date,
  end_undetermined    boolean NOT NULL DEFAULT false,
  valid_period        daterange GENERATED ALWAYS AS (avx_period(valid_from, valid_to)) STORED,
  raw_valid_from      text NOT NULL,
  raw_valid_to        text,
  origin              text,
  PRIMARY KEY (node_version_id, position),
  CHECK (NOT (end_undetermined AND valid_to IS NOT NULL))
);
CREATE INDEX structure_entry_target_idx ON structure_entry (target_official_id);

CREATE TRIGGER document_version_immutable
  BEFORE UPDATE OR DELETE ON document_version
  FOR EACH ROW EXECUTE FUNCTION avx_forbid_history_rewrite();

CREATE TRIGGER structure_node_version_immutable
  BEFORE UPDATE OR DELETE ON structure_node_version
  FOR EACH ROW EXECUTE FUNCTION avx_forbid_history_rewrite();

-- Les entrées et références appartiennent à une version immuable : jamais modifiées.
CREATE FUNCTION avx_forbid_any_change() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'modification interdite sur % (insertion seule)', TG_TABLE_NAME;
END
$$;
CREATE TRIGGER structure_entry_insert_only
  BEFORE UPDATE OR DELETE ON structure_entry
  FOR EACH ROW EXECUTE FUNCTION avx_forbid_any_change();
CREATE TRIGGER document_reference_insert_only
  BEFORE UPDATE OR DELETE ON document_reference
  FOR EACH ROW EXECUTE FUNCTION avx_forbid_any_change();

-- Suivi et reprise des ingestions (ING-02).
ALTER TABLE ingestion_run ADD COLUMN files_committed bigint NOT NULL DEFAULT 0;
ALTER TABLE ingestion_run ADD COLUMN last_committed_path text;
ALTER TABLE ingestion_run ADD COLUMN resume_count integer NOT NULL DEFAULT 0;

GRANT SELECT ON document_version, document_reference, structure_node_version, structure_entry TO avx_app;
