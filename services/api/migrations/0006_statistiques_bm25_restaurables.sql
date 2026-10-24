-- 0006 — Vue de statistiques BM25 restaurable.
--
-- pg_restore exécute les rafraîchissements avec un search_path vide ; la
-- requête textuelle passée à ts_stat() n'est pas réécrite par pg_dump, et
-- « provision_version » non qualifié rendait toute restauration impossible
-- (constaté par l'exercice de sauvegarde/restauration). Le nom est désormais
-- qualifié par son schéma.
DROP MATERIALIZED VIEW corpus_lexeme_stats;
CREATE MATERIALIZED VIEW corpus_lexeme_stats AS
  SELECT word AS lexeme, ndoc AS document_frequency
  FROM ts_stat($$SELECT tsv FROM public.provision_version WHERE sys_to IS NULL AND NOT withdrawn_from_source$$);
CREATE UNIQUE INDEX corpus_lexeme_stats_uq ON corpus_lexeme_stats (lexeme);
GRANT SELECT ON corpus_lexeme_stats TO avx_app;
