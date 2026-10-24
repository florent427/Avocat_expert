-- 0011 — Index des références croisées.
--
-- Mesure sur le stock LEGI puis 221 livraisons incrémentales : legal_reference
-- compte 23 millions de lignes (chaque nouvelle version d'un article reprend
-- son bloc LIENS) et l'index unique sur six colonnes texte, qui ne servait
-- qu'à dédoublonner les liens d'une même version, occupait 4,7 Go. Le
-- dédoublonnage est fait par le connecteur avant écriture ; un index simple
-- sur la version source suffit aux lectures.
DO $$
DECLARE c record;
BEGIN
  FOR c IN SELECT conrelid::regclass AS tbl, conname FROM pg_constraint
           WHERE contype = 'u' AND conrelid IN ('legal_reference'::regclass, 'document_reference'::regclass)
  LOOP
    EXECUTE format('ALTER TABLE %s DROP CONSTRAINT %I', c.tbl, c.conname);
  END LOOP;
END
$$;
CREATE INDEX legal_reference_from_idx ON legal_reference (from_version_id);
CREATE INDEX document_reference_from_idx ON document_reference (from_document_version_id);
