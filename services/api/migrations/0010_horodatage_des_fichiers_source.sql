-- 0010 — Horodatage des fichiers source.
--
-- Le stock LEGI du 2025-07-13 contient 12 143 articles et 1 945 sections
-- présents dans deux branches (« vigueur » et « non vigueur ») ; 5 546 copies
-- diffèrent (ex. ABROGE_DIFF dans la branche vigueur, ABROGE dans la branche
-- non vigueur, même fin de période). La documentation DILA décrit ce
-- mouvement (suppression dans une branche, recréation dans l'autre). Sur un
-- échantillon de 481 paires, l'horodatage des fichiers dans l'archive diffère
-- toujours : au sein d'une même livraison, la copie la plus récente fait foi,
-- au lieu de la dernière lue.
ALTER TABLE provision_version ADD COLUMN source_mtime timestamptz;
ALTER TABLE document_version ADD COLUMN source_mtime timestamptz;
ALTER TABLE structure_node_version ADD COLUMN source_mtime timestamptz;
