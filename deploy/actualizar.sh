#!/usr/bin/env bash
# Actualización rápida de hierro: código, dependencias, migraciones y reinicio.
#
#   sudo /opt/hierro/deploy/actualizar.sh
#
# Versión simple de deploy.sh. Al final reintenta /health hasta que responda ok.
set -euo pipefail

cd /opt/hierro

echo "==> Actualizando el código"
git pull --ff-only origin main

echo "==> Instalando dependencias"
.venv/bin/pip install --quiet -r requirements.txt
.venv/bin/python -m compileall -q app migrations

echo "==> Aplicando migraciones"
.venv/bin/alembic upgrade head

echo "==> Reiniciando el servicio"
systemctl restart hierro

echo "==> Comprobando /health"
INTENTOS=10
for i in $(seq 1 "$INTENTOS"); do
    if curl --silent --max-time 2 http://127.0.0.1:8053/health | grep -q '"estado":"ok"'; then
        echo "OK: el servicio responde"
        exit 0
    fi
    echo "Intento $i/$INTENTOS sin respuesta; reintentando en 2 s"
    sleep 2
done

echo "ERROR: /health no respondió ok tras $INTENTOS intentos" >&2
journalctl -u hierro -n 30 --no-pager
exit 1
