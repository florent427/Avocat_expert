-- 0007 — Dates non fixées par la source et date de connaissance du corpus.
--
-- LEGI publie 2222-02-22 pour une date d'entrée en vigueur ou d'abrogation
-- non encore fixée (voir connectors/legi/dates.py). Une telle valeur ne doit
-- jamais être exploitée comme une date réelle :
--  * début non fixé  -> valid_from NULL (période vide : jamais en vigueur à
--    une date connue) ;
--  * fin non fixée   -> valid_to NULL et end_undetermined = true : en vigueur
--    jusqu'à la date de connaissance, applicabilité indéterminée au-delà.
-- Les valeurs brutes restent dans raw_valid_from / raw_valid_to.
--
-- Les lignes déjà ingérées ne sont pas réécrites (historique immuable) : la
-- relivraison d'un fichier concerné produit une nouvelle version et clôt
-- l'ancienne.

ALTER TABLE provision_version ALTER COLUMN valid_from DROP NOT NULL;
ALTER TABLE provision_version ADD COLUMN end_undetermined boolean NOT NULL DEFAULT false;
ALTER TABLE provision_version ADD CONSTRAINT provision_version_end_coherent
  CHECK (NOT (end_undetermined AND valid_to IS NOT NULL));

ALTER TABLE provision_version DROP COLUMN valid_period;
ALTER TABLE provision_version ADD COLUMN valid_period daterange GENERATED ALWAYS AS (
  CASE
    WHEN valid_from IS NULL THEN 'empty'::daterange
    WHEN valid_to IS NULL THEN daterange(valid_from, NULL, '[)')
    WHEN valid_to > valid_from THEN daterange(valid_from, valid_to, '[)')
    ELSE 'empty'::daterange
  END) STORED;
CREATE INDEX provision_version_period_idx ON provision_version USING gist (valid_period);

-- Horodatage porté par le nom de l'archive DILA (AAAAMMJJ-HHMMSS). Le fuseau
-- n'est pas documenté par la DILA : valeur conservée sans fuseau.
ALTER TABLE ingestion_run ADD COLUMN archive_timestamp timestamp;
CREATE INDEX ingestion_run_order_idx ON ingestion_run (source_id, archive_timestamp) WHERE status = 'SUCCEEDED';

-- Date de connaissance : date de la livraison la plus récente intégrée avec succès.
CREATE FUNCTION avx_knowledge_date(p_source_code text) RETURNS date
LANGUAGE sql STABLE AS $$
  SELECT max(r.archive_timestamp)::date
  FROM public.ingestion_run r JOIN public.legal_source s ON s.id = r.source_id
  WHERE s.code = p_source_code AND r.status = 'SUCCEEDED'
$$;
