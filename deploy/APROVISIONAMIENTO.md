# Aprovisionamiento del servidor (Ubuntu 24.04)

Pasos para preparar un servidor nuevo, una sola vez. Los comandos se ejecutan como
un usuario con `sudo`. Reemplaza `noticias.ejemplo.com` por tu dominio.

## 1. Paquetes del sistema

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git curl python3.12 python3.12-venv nginx redis-server \
    certbot postgresql-client
```

`postgresql-client` aporta `psql`, que se usa para ejecutar `scripts/roles.sql`.

## 2. Firewall

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
```

La API (puerto 8000) y Redis (6379) escuchan solo en localhost, así que no se abren.

## 3. Redis (solo localhost)

En `/etc/redis/redis.conf`, comprueba o ajusta estas líneas:

```
bind 127.0.0.1 -::1
protected-mode yes
supervised systemd
maxmemory 256mb
maxmemory-policy allkeys-lru
```

Todas las claves del servicio tienen TTL, así que si se llena la memoria se pueden
descartar sin problema.

```bash
sudo systemctl enable --now redis-server
sudo systemctl restart redis-server
redis-cli ping                 # PONG
ss -ltnp | grep 6379           # solo 127.0.0.1 y [::1]
```

## 4. Usuario del servicio y código

El servicio corre con un usuario de sistema, sin shell y sin privilegios. El código
pertenece a root, así que ese usuario no puede modificarlo.

```bash
sudo useradd --system --no-create-home --home-dir /nonexistent \
    --shell /usr/sbin/nologin news-service

sudo git clone https://github.com/TU_ORG/news-service.git /opt/news-service
cd /opt/news-service
sudo python3.12 -m venv .venv
sudo .venv/bin/pip install -r requirements.txt
```

Si el repositorio es privado, configura una *deploy key* de solo lectura para root.

## 5. Base de datos (DigitalOcean)

1. En el panel del clúster, en **Trusted sources**, agrega la IP del servidor.
2. Usa siempre la conexión **directa** (puerto 25060), no el *connection pool*.
3. Crea los roles con el usuario administrador (`doadmin`):

   ```bash
   psql "postgresql://doadmin@HOST:25060/BASE?sslmode=require" \
        -v ON_ERROR_STOP=1 -f scripts/roles.sql
   ```

   El script pide la contraseña de cada rol nuevo. Genera contraseñas largas, por
   ejemplo con `openssl rand -base64 32`.

## 6. Variables de entorno

```bash
sudo mkdir -p /etc/news-service
sudo cp .env.example /etc/news-service/api.env
sudo nano /etc/news-service/api.env      # DATABASE_URL con api_noticias, etc.
sudo chown root:news-service /etc/news-service/api.env
sudo chmod 0640 /etc/news-service/api.env
```

La URL del rol propietario va en un archivo aparte, que solo puede leer root. El
proceso de la API nunca la ve:

```bash
echo 'ADMIN_DATABASE_URL=postgresql+asyncpg://owner_noticias:CONTRASEÑA@HOST:25060/BASE' \
    | sudo tee /etc/news-service/admin.env >/dev/null
sudo chmod 0600 /etc/news-service/admin.env
```

`deploy.sh` carga ambos archivos con `source`. Si una contraseña tiene caracteres
especiales de shell (`$`, `` ` ``, espacios), escribe el valor entre comillas simples.

Para verificar el certificado de PostgreSQL, descarga el CA del clúster desde el
panel y configura `DATABASE_SSL=verify-full` y
`DATABASE_SSL_ROOT_CERT=/etc/news-service/ca-certificate.crt`.

## 7. Migraciones y permisos

```bash
cd /opt/news-service
sudo bash -c 'set -a; . /etc/news-service/api.env; . /etc/news-service/admin.env; set +a;
              .venv/bin/alembic upgrade head'

# Segunda pasada de roles.sql: otorga permisos sobre las tablas recién creadas.
psql "postgresql://doadmin@HOST:25060/BASE?sslmode=require" \
     -v ON_ERROR_STOP=1 -f scripts/roles.sql
```

## 8. systemd

```bash
sudo cp deploy/news-service.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now news-service
curl -s http://127.0.0.1:8000/ready     # {"estado":"ok",...}
journalctl -u news-service -f            # logs JSON
```

## 9. Nginx y certificado TLS (Certbot)

El certificado se emite primero con la configuración por defecto de Nginx, que sirve
`/var/www/html`. Después se instala el sitio con TLS.

```bash
sudo certbot certonly --webroot -w /var/www/html -d noticias.ejemplo.com \
    --email tu@correo.com --agree-tos --no-eff-email

# Archivos de opciones TLS que referencia nginx.conf (los crea el plugin de nginx).
sudo apt install -y python3-certbot-nginx
ls /etc/letsencrypt/options-ssl-nginx.conf /etc/letsencrypt/ssl-dhparams.pem \
  || sudo certbot install --nginx --cert-name noticias.ejemplo.com

sudo sed 's/noticias.ejemplo.com/TU_DOMINIO/g' deploy/nginx.conf \
    | sudo tee /etc/nginx/sites-available/news-service >/dev/null
sudo ln -sf /etc/nginx/sites-available/news-service /etc/nginx/sites-enabled/news-service
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

La renovación es automática (`certbot.timer`). Para que Nginx tome el certificado
renovado:

```bash
echo -e '#!/bin/sh\nsystemctl reload nginx' \
    | sudo tee /etc/letsencrypt/renewal-hooks/deploy/reload-nginx >/dev/null
sudo chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx
sudo certbot renew --dry-run
```

## 10. Primera API key

```bash
cd /opt/news-service
sudo bash -c 'set -a; . /etc/news-service/api.env; . /etc/news-service/admin.env; set +a;
              .venv/bin/python scripts/crear_api_key.py crear "web"'
```

A partir de aquí, cada despliegue es `sudo /opt/news-service/deploy/deploy.sh`.
