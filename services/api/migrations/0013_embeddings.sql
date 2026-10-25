-- 0013 — Embeddings du corpus (SRCH-02, ADR 0017).
--
-- Vecteurs adressés par leur contenu : l'empreinte porte sur le texte exact
-- soumis au modèle (préfixe, contexte, texte de l'article). Une nouvelle
-- version d'article de même texte et de même contexte réutilise le vecteur
-- déjà calculé. Chaque version indique quel texte a été vectorisé, par quel
-- modèle (dépôt et révision épinglés) : la recherche sémantique est
-- reproductible et auditable.
--
-- La recherche des plus proches voisins est faite par OpenSearch (filtrage
-- par date et par texte pendant le parcours du graphe) ; PostgreSQL conserve
-- les vecteurs, ce qui permet de reconstruire l'index sans recalcul.
CREATE TABLE embedding_model (
  key          text PRIMARY KEY,
  repository   text NOT NULL,
  revision     text NOT NULL,
  dimension    integer NOT NULL CHECK (dimension > 0),
  recorded_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE embedding_vector (
  model_key     text NOT NULL REFERENCES embedding_model(key),
  input_sha256  char(64) NOT NULL,
  embedding     vector NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (model_key, input_sha256)
);

CREATE TABLE provision_embedding (
  model_key     text NOT NULL,
  version_id    uuid NOT NULL REFERENCES provision_version(id),
  input_sha256  char(64) NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (model_key, version_id),
  FOREIGN KEY (model_key, input_sha256) REFERENCES embedding_vector (model_key, input_sha256)
);
CREATE INDEX provision_embedding_created_idx ON provision_embedding (model_key, created_at);

CREATE TRIGGER embedding_vector_insert_only
  BEFORE UPDATE OR DELETE ON embedding_vector
  FOR EACH ROW EXECUTE FUNCTION avx_forbid_any_change();
CREATE TRIGGER provision_embedding_insert_only
  BEFORE UPDATE OR DELETE ON provision_embedding
  FOR EACH ROW EXECUTE FUNCTION avx_forbid_any_change();

-- Colonne réservée en 0001, jamais alimentée : une mise à jour de
-- provision_version par vecteur réécrirait chaque ligne (7,8 Go sur le corpus
-- complet) et lierait le corpus à un modèle unique.
ALTER TABLE provision_version DROP COLUMN embedding;

GRANT SELECT ON embedding_model, embedding_vector, provision_embedding TO avx_app;
