-- 0005 — Le rôle applicatif lit la provenance des versions citées.
-- Chaque référence de source expose la version du connecteur et l'archive
-- d'origine (ingestion_run) : sans ce droit, toute réponse échoue sous le rôle
-- à moindre privilège (constaté par le test de fumée de la pile locale).
GRANT SELECT ON ingestion_run TO avx_app;
