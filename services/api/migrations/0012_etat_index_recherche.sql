-- 0012 — Suivi de l'index de recherche (OpenSearch).
--
-- L'index est une projection du corpus courant, reconstructible à tout moment
-- depuis PostgreSQL. Le point de contrôle permet une mise à jour incrémentale :
-- versions créées ou closes, et retraits enregistrés, depuis la dernière
-- synchronisation.
CREATE TABLE search_index_state (
  alias            text PRIMARY KEY,
  physical_index   text NOT NULL,
  checkpoint       timestamptz NOT NULL,
  documents        bigint NOT NULL,
  updated_at       timestamptz NOT NULL DEFAULT now()
);
