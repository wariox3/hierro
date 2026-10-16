#!/usr/bin/env bash
# Despliegue manual e idempotente de hierro (servicios de Semántica Digital).
#
#   sudo /opt/hierro/deploy/deploy.sh
#
# Pasos: git pull, dependencias, migraciones, reinicio y verificación de /health.
# Se detiene ante el primer error.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/hierro}"
SERVICIO="${SERVICIO:-hierro}"
RAMA="${RAMA:-main}"
ENV_API="${ENV_API:-/opt/hierro/.env}"
ENV_ADMIN="${ENV_ADMIN:-/opt/hierro/.env.admin}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8053/health}"
ESPERA_HEALTH="${ESPERA_HEALTH:-30}"

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

log "Esperando $HEALTH_URL (hasta ${ESPERA_HEALTH}s)"
for _ in $(seq 1 "$ESPERA_HEALTH"); do
    if curl --fail --silent --show-error --max-time 2 "$HEALTH_URL" >/dev/null 2>&1; then
        log "Despliegue completado"
        exit 0
    fi
    sleep 1
done

log "ERROR: el servicio no respondió"
curl --silent --max-time 2 "$HEALTH_URL" || true
echo
journalctl -u "$SERVICIO" -n 50 --no-pager || true
exit 1
