-- Création du rôle de connexion de l'API, membre du rôle applicatif avx_app
-- (aucun privilège propre : il hérite uniquement de ceux d'avx_app).
-- À exécuter après `avx migrate`, par un administrateur, avec psql :
--   psql -v api_role=avx_api -v api_password="$MOT_DE_PASSE" -f create_login_role.sql
-- Le mot de passe provient du gestionnaire de secrets ; il n'est jamais versionné.
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L IN ROLE avx_app', :'api_role', :'api_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'api_role') \gexec
SELECT format('ALTER ROLE %I PASSWORD %L', :'api_role', :'api_password') \gexec
