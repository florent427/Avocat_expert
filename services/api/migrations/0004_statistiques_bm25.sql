-- 0004 — Statistiques de corpus pour le classement BM25 du canal lexical.
--
-- Population : versions courantes (sys_to IS NULL), non retirées par la source,
-- toutes dates de validité confondues. Rafraîchies après chaque ingestion.

CREATE FUNCTION avx_tsv_length(v tsvector) RETURNS integer
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT coalesce(sum(coalesce(array_length(positions, 1), 1)), 0)::integer FROM unnest(v)
$$;

CREATE MATERIALIZED VIEW corpus_lexeme_stats AS
  SELECT word AS lexeme, ndoc AS document_frequency
  FROM ts_stat($$SELECT tsv FROM provision_version WHERE sys_to IS NULL AND NOT withdrawn_from_source$$);
CREATE UNIQUE INDEX corpus_lexeme_stats_uq ON corpus_lexeme_stats (lexeme);

CREATE MATERIALIZED VIEW corpus_stats AS
  SELECT count(*)::bigint AS document_count,
         coalesce(avg(avx_tsv_length(tsv)), 0)::double precision AS average_length
  FROM provision_version WHERE sys_to IS NULL AND NOT withdrawn_from_source;
CREATE UNIQUE INDEX corpus_stats_singleton ON corpus_stats ((true));

GRANT SELECT ON corpus_lexeme_stats, corpus_stats TO avx_app;
