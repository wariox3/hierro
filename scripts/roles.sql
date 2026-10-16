-- Roles de base de datos del servicio de noticias.
--
-- Ejecutar con el usuario administrador del servicio administrado (doadmin en
-- DigitalOcean), conectado a la base del servicio y en conexión directa (no al pool):
--
--   psql "postgresql://doadmin@HOST:25060/BASE?sslmode=require" \
--        -v ON_ERROR_STOP=1 -f scripts/roles.sql
--
-- Pide por teclado la contraseña de cada rol que todavía no existe; también se
-- pueden pasar con -v owner_password=... -v api_password=... -v editor_password=...
--
-- Es idempotente. Ejecútalo:
--   1. antes de la primera migración (crea los roles y los permisos de esquema), y
--   2. después de cada migración que cree tablas (otorga permisos sobre ellas).
--
-- Roles:
--   owner_noticias   propietario de las tablas; ejecuta las migraciones de Alembic.
--   api_noticias     solo SELECT sobre todas las tablas; lo usa la API.
--   editor_noticias  SELECT, INSERT y UPDATE sobre noticia. Sin DELETE
--                    (se despublica con estado_inactivo) y sin acceso a api_key.

\set ON_ERROR_STOP on

-- 1. Crear los roles que falten --------------------------------------------------

SELECT NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'owner_noticias') AS crear_owner,
       NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'api_noticias') AS crear_api,
       NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'editor_noticias') AS crear_editor
\gset

\if :crear_owner
  \if :{?owner_password}
  \else
    \prompt 'Contraseña para owner_noticias: ' owner_password
  \endif
  SELECT format('CREATE ROLE owner_noticias LOGIN PASSWORD %L', :'owner_password') \gexec
\endif

\if :crear_api
  \if :{?api_password}
  \else
    \prompt 'Contraseña para api_noticias: ' api_password
  \endif
  SELECT format('CREATE ROLE api_noticias LOGIN PASSWORD %L', :'api_password') \gexec
\endif

\if :crear_editor
  \if :{?editor_password}
  \else
    \prompt 'Contraseña para editor_noticias: ' editor_password
  \endif
  SELECT format('CREATE ROLE editor_noticias LOGIN PASSWORD %L', :'editor_password') \gexec
\endif

ALTER ROLE owner_noticias NOSUPERUSER NOCREATEDB NOCREATEROLE;
ALTER ROLE api_noticias NOSUPERUSER NOCREATEDB NOCREATEROLE;
ALTER ROLE editor_noticias NOSUPERUSER NOCREATEDB NOCREATEROLE;

-- Defensa en profundidad: la API nunca escribe.
ALTER ROLE api_noticias SET default_transaction_read_only = on;
ALTER ROLE api_noticias SET statement_timeout = '5s';
ALTER ROLE editor_noticias SET statement_timeout = '30s';

-- El administrador necesita poder actuar como owner_noticias para otorgar
-- permisos sobre sus tablas (en un servicio administrado no es superusuario).
GRANT owner_noticias TO CURRENT_USER;

-- 2. Base y esquema ----------------------------------------------------------------

SELECT format('GRANT CONNECT ON DATABASE %I TO owner_noticias, api_noticias, editor_noticias',
              current_database()) \gexec

GRANT USAGE, CREATE ON SCHEMA public TO owner_noticias;
GRANT USAGE ON SCHEMA public TO api_noticias, editor_noticias;

-- 3. Tablas (como owner_noticias, su propietario) ----------------------------------

SET ROLE owner_noticias;

-- Las tablas que creen migraciones futuras quedan legibles por la API.
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO api_noticias;

-- Si las migraciones ya se ejecutaron, se otorgan los permisos sobre las tablas existentes.
SELECT format('GRANT SELECT ON ALL TABLES IN SCHEMA public TO api_noticias') \gexec

SELECT format('GRANT SELECT, INSERT, UPDATE ON %I TO editor_noticias', 'noticia')
WHERE to_regclass('public.noticia') IS NOT NULL
\gexec

SELECT format('REVOKE ALL ON %I FROM editor_noticias', 'api_key')
WHERE to_regclass('public.api_key') IS NOT NULL
\gexec

RESET ROLE;
