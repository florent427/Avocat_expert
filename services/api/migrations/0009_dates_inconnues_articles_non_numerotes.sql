-- 0009 — Cas réels du stock LEGI du 2025-07-13 (analyse des 2 276 109 fichiers).
--
--  * Dates d'application non renseignées (229 644 articles : ETAT vide,
--    DATE_DEBUT et DATE_FIN à 2999-01-01) : dates_unknown = true, valid_from
--    NULL ; applicabilité toujours indéterminée, jamais « en vigueur » ni
--    « non en vigueur ».
--  * Articles non numérotés (25 121, NUM vide) : la disposition logique est
--    identifiée par le plus petit identifiant de version connu de l'article
--    (bloc VERSIONS), au lieu du numéro.

ALTER TABLE provision_version ADD COLUMN dates_unknown boolean NOT NULL DEFAULT false;
ALTER TABLE provision_version ADD CONSTRAINT provision_version_unknown_coherent
  CHECK (NOT (dates_unknown AND valid_from IS NOT NULL));
ALTER TABLE document_version ADD COLUMN dates_unknown boolean NOT NULL DEFAULT false;
ALTER TABLE structure_entry ADD COLUMN dates_unknown boolean NOT NULL DEFAULT false;

ALTER TABLE provision ADD COLUMN unnumbered_key text;
ALTER TABLE provision ADD CONSTRAINT provision_unnumbered_coherent
  CHECK ((number = '') = (unnumbered_key IS NOT NULL));
ALTER TABLE provision DROP CONSTRAINT provision_document_id_kind_number_key;
CREATE UNIQUE INDEX provision_identity_uq ON provision (document_id, kind, number, (coalesce(unnumbered_key, '')));
