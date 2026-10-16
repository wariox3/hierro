# news-service

Servicio REST de **solo lectura** que provee noticias a las aplicaciones del ecosistema.
Las noticias se cargan **manualmente por SQL**. La API no tiene endpoints de escritura.

## Arquitectura

```
Apps cliente ──HTTPS──▶ Nginx (TLS, gzip, límite por IP)
                          │ 127.0.0.1:8000
                          ▼
                 Uvicorn (4 workers, systemd) ── FastAPI
                          │                 │
           SQLAlchemy async + asyncpg    redis.asyncio
                          │                 │
       PostgreSQL administrado (DO)    Redis local
       conexión directa, TLS           caché, auth y rate limit
```

- **Autenticación:** cada cliente usa una API key (tabla `api_key`), que se envía en el
  header `X-API-Key`. En la base solo se guardan su SHA-256 y un prefijo para identificarla. El
  resultado de la validación se cachea en Redis.
- **Visibilidad:** una noticia es visible si `estado_inactivo = false`. Es igual para
  todas las API keys. Las noticias con `fecha_publicacion` futura también se muestran.
- **Caché:** los listados se guardan en Redis (TTL de 120 s por defecto),
  con claves que incluyen el recurso y los parámetros, si los hay; todas las keys comparten la caché. Las respuestas llevan `ETag`
  y `Cache-Control`, y un `If-None-Match` que coincide recibe `304`.
- **Degradación:** si Redis cae, la API sigue funcionando contra PostgreSQL, sin caché
  ni rate limit, y deja el error en el log.
- **Contenido:** el HTML de `contenido` se sanitiza al servirlo con `nh3`, que aplica una
  lista blanca de etiquetas y elimina `<script>`, `on*`, `style` y `javascript:`.
- **Operación:** los logs salen en JSON a stdout (journald) e incluyen el request ID, que
  se recibe en `X-Request-ID` o se genera. Todos los errores comparten el formato
  `{"error": {"codigo", "mensaje", "request_id"}}`.

### Estructura

```
app/                  código de la API
  main.py             create_app(): lifespan, middlewares, routers
  core/               núcleo transversal, sin lógica de noticias
    config.py         variables de entorno (pydantic-settings)
    db.py             engine de PostgreSQL (asyncpg, TLS, pool)
    redis_client.py   cliente Redis tolerante a fallos
    recursos.py       recursos compartidos y dependencias (sesión, Redis)
    logging_config.py logs JSON y request ID
    middleware.py     request ID, log de acceso y errores no controlados
    errors.py         ErrorAPI y formato uniforme de errores
    cache.py          caché Redis + ETag/304
    auth.py           API key y rate limit
    api_keys.py       generación y hash de API keys
  models/             modelos SQLAlchemy 2.x, uno por tabla (la Base está en core/db.py)
  schemas/            esquemas Pydantic de las respuestas, por dominio (noticia, errores, salud)
  routers/            health, noticias
  utilidades/         utilidades específicas: gestión de API keys, paginación y sanitización
    gestion_api_keys.py alta, rotación y listado de API keys (usa scripts/crear_api_key.py)
    paginacion.py     paginación por cursor común a todos los listados
    sanitizacion.py   limpieza del HTML de contenido (nh3)
migrations/           Alembic (esquema, índices y trigger)
scripts/              roles.sql, seed.sql, crear_api_key.py
deploy/               systemd, Nginx, deploy.sh, aprovisionamiento
tests/                tests de integración (PostgreSQL y Redis locales)
```

## Endpoints

Todos van bajo `/v1` y requieren `X-API-Key`, salvo los de salud. La documentación
OpenAPI está en `/docs`.

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/v1/lista` | Las últimas 10 noticias activas, con `contenido` HTML sanitizado. Sin parámetros |
| GET | `/health` | Liveness, sin dependencias |
| GET | `/ready` | Verifica PostgreSQL y Redis; responde 503 si alguno falla |

Códigos de error: `401` sin key o con key inválida, `403` API key inactiva y `429`
límite excedido (incluye `Retry-After`).

**Paginación.** El estándar para los listados es la paginación por cursor de
`app/utilidades/paginacion.py` (`limit`, `cursor` y `siguiente_cursor`). `/v1/lista` es
la excepción: siempre devuelve las 10 noticias más recientes, ordenadas por
`fecha_publicacion` descendente, sin paginación ni filtros.

```bash
curl -H "X-API-Key: $KEY" "https://noticias.ejemplo.com/v1/lista"
```

## Desarrollo local

Requisitos: Python 3.12, PostgreSQL 16 y Redis, todos locales (sin Docker).

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt

cp .env.example .env        # completa DATABASE_URL y pon DATABASE_SSL=disable

.venv/bin/alembic upgrade head                                     # crea el esquema
psql "postgresql://USUARIO@localhost/bdhierro" -f scripts/seed.sql   # datos de ejemplo

.venv/bin/uvicorn app.main:app --reload
```

`seed.sql` crea dos API keys fijas, **solo para desarrollo**:

```bash
curl -H "X-API-Key: nk_desarrollo_web_0000000000000000000000000000" localhost:8000/v1/lista
curl -H "X-API-Key: nk_desarrollo_movil_00000000000000000000000000" localhost:8000/v1/lista
```

### Verificación

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy
.venv/bin/pytest
```

Los tests usan las credenciales de `DATABASE_URL` sobre una base aparte, con el mismo
nombre más el sufijo `_test` (por ejemplo `bdhierro_test`). Si no existe, la crean, así
que el usuario necesita permiso `CREATEDB`. Al empezar cada corrida **borran su esquema**
y ejecutan `alembic upgrade head`, con lo que también comprueban que la migración funciona
sobre una base vacía. La base de `DATABASE_URL` no se toca. Redis usa `TEST_REDIS_URL`
(por defecto la base 15), que se vacía en cada test.

### Dependencias

Las versiones exactas están en `requirements.txt` (producción) y `requirements-dev.txt`
(agrega lint, tipos y tests). Para agregar una dependencia:

```bash
.venv/bin/pip install paquete
.venv/bin/pip freeze   # copia la línea nueva, y sus dependencias, al requirements que corresponda
```

## Variables de entorno

Están documentadas en [`.env.example`](.env.example). Las principales:

| Variable | Por defecto | Uso |
|---|---|---|
| `DATABASE_URL` | — | Conexión de la API (rol `api_noticias`), `postgresql+asyncpg://…` |
| `ADMIN_DATABASE_URL` | `DATABASE_URL` | Rol propietario: migraciones y `crear_api_key.py` |
| `DATABASE_SSL` | `require` | `disable`, `require` o `verify-full` (con `DATABASE_SSL_ROOT_CERT`) |
| `REDIS_URL` | `redis://localhost:6379/0` | Caché, autenticación y rate limit |
| `CACHE_TTL` | `120` | Segundos en caché de los listados |
| `HTTP_CACHE_MAX_AGE` | `60` | `max-age` de `Cache-Control` |
| `AUTH_CACHE_TTL` | `300` | Segundos en caché de la validación de una key |
| `RATE_LIMIT_REQUESTS` / `RATE_LIMIT_WINDOW` | `120` / `60` | Solicitudes por ventana (s) y por API key |
| `CORS_ORIGINS` | vacío (cerrado) | Orígenes permitidos, separados por comas |
| `DOCS_ENABLED` | `true` | Publica `/docs` y `/openapi.json` |
| `LOG_LEVEL` | `INFO` | Nivel de log |

## Base de datos

### Roles

`scripts/roles.sql` se ejecuta con el usuario administrador (`doadmin`) y crea tres roles:

- `owner_noticias`: propietario de las tablas; ejecuta las migraciones.
- `api_noticias`: solo `SELECT` y sesiones de solo lectura. Es el rol de la API.
- `editor_noticias`: `SELECT`, `INSERT` y `UPDATE` sobre `noticia`. No
  tiene `DELETE` ni acceso a `api_key`.

Es idempotente. Ejecútalo antes de la primera migración y otra vez después de cada
migración que cree tablas nuevas (ver `deploy/APROVISIONAMIENTO.md`).

### API keys

```bash
# Con ADMIN_DATABASE_URL en el entorno (rol propietario):
.venv/bin/python scripts/crear_api_key.py crear "web"     # muestra la key UNA vez
.venv/bin/python scripts/crear_api_key.py rotar "web"     # la anterior deja de valer
.venv/bin/python scripts/crear_api_key.py listar          # ids, prefijos y estado
```

En producción, carga antes las variables:
`sudo bash -c 'set -a; . /etc/news-service/api.env; . /etc/news-service/admin.env; set +a; .venv/bin/python scripts/crear_api_key.py listar'`.

Para desactivar una key por SQL: `UPDATE api_key SET estado_inactivo = true
WHERE nombre = 'web';`. El cambio rige como máximo en `AUTH_CACHE_TTL` segundos. Para
cortarle el acceso al instante, rota su key.

### Insertar noticias por SQL

Conéctate con el rol `editor_noticias`. `fecha_actualizacion` la mantiene un trigger,
así que no hace falta tocarla. Las fechas son `timestamptz`: indica siempre la zona horaria.

```sql
-- Noticia publicada ahora.
INSERT INTO noticia (titulo, contenido, url_imagen, fecha_publicacion)
VALUES (
    'Abre el nuevo museo',
    '<p>El museo abre sus puertas este sábado.</p>',
    'https://cdn.ejemplo.com/noticias/museo.jpg',          -- debe empezar por https://
    now()
)
RETURNING id;

-- Noticia programada: aparece sola cuando llega su fecha.
INSERT INTO noticia (titulo, contenido, fecha_publicacion)
VALUES ('Resultados del sorteo', '<p>Se publican el lunes.</p>', '2026-10-20 09:00:00-05');

-- Editar (el trigger actualiza fecha_actualizacion).
UPDATE noticia SET titulo = 'Abre el nuevo museo de arte' WHERE id = 41;

-- Despublicar (no hay DELETE) y volver a publicar.
UPDATE noticia SET estado_inactivo = true  WHERE id = 41;
UPDATE noticia SET estado_inactivo = false WHERE id = 41;
```

Los cambios se ven en la API en un máximo de `CACHE_TTL` segundos, que es lo que dura la
caché.

## Despliegue

El servidor se prepara una sola vez siguiendo
[`deploy/APROVISIONAMIENTO.md`](deploy/APROVISIONAMIENTO.md) (Ubuntu 24.04: usuario del
servicio, Redis, Nginx, Certbot y systemd).

Cada despliegue es manual:

```bash
ssh servidor
sudo /opt/news-service/deploy/deploy.sh
```

El script hace `git pull`, instala `requirements.txt`, ejecuta `alembic upgrade head`,
reinicia el servicio y espera a que `/ready` responda. Ante el primer error se detiene
y muestra los últimos logs. Es idempotente: ejecutarlo dos veces seguidas no cambia nada.

Si la migración crea tablas nuevas, ejecuta después `scripts/roles.sql` para otorgar
los permisos.

```bash
journalctl -u news-service -f              # logs JSON
journalctl -u news-service -o cat | jq .   # legibles
systemctl status news-service
```
