#!/usr/bin/env bash
# Despliegue manual e idempotente del servicio de noticias.
#
#   sudo /opt/news-service/deploy/deploy.sh
#
# Pasos: git pull, dependencias, migraciones, reinicio y verificación de /ready.
# Se detiene ante el primer error.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/news-service}"
SERVICIO="${SERVICIO:-news-service}"
RAMA="${RAMA:-main}"
ENV_API="${ENV_API:-/etc/news-service/api.env}"
ENV_ADMIN="${ENV_ADMIN:-/etc/news-service/admin.env}"
READY_URL="${READY_URL:-http://127.0.0.1:8000/ready}"
ESPERA_READY="${ESPERA_READY:-30}"

log() { printf '[deploy %(%H:%M:%S)T] %s\n' -1 "$*"; }

if [[ $EUID -ne 0 ]]; then
    echo "Ejecuta este script con sudo." >&2
    exit 1
fi
for archivo in "$ENV_API" "$ENV_ADMIN"; do
    [[ -r "$archivo" ]] || { echo "No se puede leer $archivo" >&2; exit 1; }
done

cd "$APP_DIR"

log "Actualizando el código (rama $RAMA)"
git fetch --prune origin
git checkout --quiet "$RAMA"
git pull --ff-only origin "$RAMA"
log "Versión: $(git rev-parse --short HEAD)"

log "Instalando dependencias"
[[ -x .venv/bin/python ]] || python3.12 -m venv .venv
.venv/bin/pip install --quiet --disable-pip-version-check --require-virtualenv \
    -r requirements.txt
# El servicio corre con ProtectSystem=strict y no puede escribir los .pyc.
.venv/bin/python -m compileall -q app migrations

log "Aplicando migraciones"
(
    set -a
    # shellcheck source=/dev/null
    . "$ENV_API"
    # shellcheck source=/dev/null
    . "$ENV_ADMIN"
    set +a
    .venv/bin/alembic upgrade head
)

log "Reiniciando $SERVICIO"
systemctl restart "$SERVICIO"

log "Esperando $READY_URL (hasta ${ESPERA_READY}s)"
for _ in $(seq 1 "$ESPERA_READY"); do
    if curl --fail --silent --show-error --max-time 2 "$READY_URL" >/dev/null 2>&1; then
        log "Despliegue completado"
        exit 0
    fi
    sleep 1
done

log "ERROR: el servicio no quedó listo"
curl --silent --max-time 2 "$READY_URL" || true
echo
journalctl -u "$SERVICIO" -n 50 --no-pager || true
exit 1
