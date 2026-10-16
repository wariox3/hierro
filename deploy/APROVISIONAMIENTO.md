# Aprovisionamiento del servidor (Ubuntu 24.04)

Pasos para preparar un servidor nuevo, una sola vez. Los comandos se ejecutan como
un usuario con `sudo`. El dominio es `servicio.semanticaapi.com.co` y pasa por el proxy
de Cloudflare.

## 1. Paquetes del sistema

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git curl python3.12 python3.12-venv nginx redis-tools \
    postgresql-client
```

`postgresql-client` aporta `psql`, que se usa para ejecutar `scripts/roles.sql`.
`redis-tools` aporta `redis-cli`, para comprobar la conexión con Redis.

## 2. Firewall

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
```

La API (puerto 8053) escucha solo en localhost, así que no se abre. PostgreSQL y Redis
son servicios administrados: el servidor solo abre conexiones salientes hacia ellos.

## 3. Redis administrado

Crea el Redis administrado en la misma región y VPC que el servidor y que PostgreSQL. En
el panel del servicio:

- **Orígenes de confianza:** solo este servidor.
- **Política de expulsión:** `allkeys-lru`. Todas las claves del servicio tienen TTL, así
  que si se llena la memoria se pueden descartar sin problema.

Toda la conexión va en `REDIS_URL`, en `/opt/hierro/.env` (paso 6). El servicio exige TLS, así
que la URL empieza por `rediss://`. Descarga el certificado CA del panel a
`/opt/hierro/certs/redis-ca.crt` (la carpeta se crea en el paso 4) e indícalo en la propia
URL para verificar el servidor:

```bash
REDIS_URL='rediss://default:CONTRASEÑA@HOST:25061/0?ssl_ca_certs=/opt/hierro/certs/redis-ca.crt'
REDIS_KEY_PREFIX=hierro:produccion
```

El Redis es compartido con otros servicios: `REDIS_KEY_PREFIX` es obligatoria y todas
las claves del servicio empiezan por ella. Usa un prefijo distinto en cada entorno y no
ejecutes nunca `FLUSHDB` ni `FLUSHALL` en el Redis compartido; para limpiar solo las de
este entorno:

```bash
redis-cli -u "$REDIS_URL" --tls --cacert /opt/hierro/certs/redis-ca.crt \
    --scan --pattern 'hierro:produccion:*' | xargs -r redis-cli -u "$REDIS_URL" --tls \
    --cacert /opt/hierro/certs/redis-ca.crt del
```

Sin el CA, la verificación del certificado falla y la API funciona sin caché ni límite
de solicitudes (queda en el log como `redis_no_disponible`). Para cifrar sin verificar,
cambia el parámetro por `?ssl_cert_reqs=none&ssl_check_hostname=false`.

Comprueba la conexión desde el servidor:

```bash
redis-cli -u 'rediss://default:CONTRASEÑA@HOST:25061/0' --tls --cacert /opt/hierro/certs/redis-ca.crt ping   # PONG
```

## 4. Usuario del servicio y código

El servicio corre con un usuario de sistema, sin shell y sin privilegios. El código
pertenece a root, así que ese usuario no puede modificarlo.

```bash
sudo useradd --system --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin hierro

sudo git clone https://github.com/wariox3/hierro.git /opt/hierro
cd /opt/hierro
sudo python3.12 -m venv .venv
sudo .venv/bin/pip install -r requirements.txt
sudo mkdir -p certs                 # certificados CA de PostgreSQL y Redis (paso 3 y 6)
```

Si el repositorio es privado, configura una *deploy key* de solo lectura para root.

## 5. Base de datos (DigitalOcean)

1. En el panel del clúster, en **Trusted sources**, agrega la IP del servidor.
2. Usa siempre la conexión **directa** (puerto 25060), no el *connection pool*.
3. Crea los roles con el usuario administrador (`doadmin`):

   ```bash
   psql "postgresql://doadmin@HOST:25060/BASE?sslmode=require" -v ON_ERROR_STOP=1 -f scripts/roles.sql
   ```

   El script pide la contraseña de cada rol nuevo. Genera contraseñas largas, por
   ejemplo con `openssl rand -base64 32`.

## 6. Variables de entorno

Las variables van en `/opt/hierro/.env`, junto al código. Git lo ignora, así que
`git pull` no lo toca; no ejecutes nunca `git clean -x` en `/opt/hierro`, porque lo borraría.

```bash
cd /opt/hierro
sudo cp .env.example .env
sudo nano .env                      # DATABASE_URL con api_noticias, etc.
sudo chown root:hierro .env
sudo chmod 0640 .env                # la API lo lee, pero no puede modificarlo
```

La URL del rol propietario va en un archivo aparte, `/opt/hierro/.env.admin`, que solo
puede leer root. El proceso de la API nunca la ve:

```bash
echo 'ADMIN_DATABASE_URL=postgresql+asyncpg://owner_noticias:CONTRASEÑA@HOST:25060/BASE' | sudo tee /opt/hierro/.env.admin >/dev/null
sudo chmod 0600 /opt/hierro/.env.admin
```

`deploy.sh` carga ambos archivos con `source`. Si una contraseña tiene caracteres
especiales de shell (`$`, `` ` ``, espacios), escribe el valor entre comillas simples.

Para verificar el certificado de PostgreSQL, descarga el CA del clúster desde el
panel y configura `DATABASE_SSL=verify-full` y
`DATABASE_SSL_ROOT_CERT=/opt/hierro/certs/ca-certificate.crt`.

## 7. Migraciones y permisos

```bash
cd /opt/hierro
sudo bash -c 'set -a; . ./.env; . ./.env.admin; set +a;
              .venv/bin/alembic upgrade head'

# Segunda pasada de roles.sql: otorga permisos sobre las tablas recién creadas.
psql "postgresql://doadmin@HOST:25060/BASE?sslmode=require" \
     -v ON_ERROR_STOP=1 -f scripts/roles.sql
```

## 8. systemd

```bash
sudo cp deploy/hierro.service /etc/systemd/system/ -- ESTE REVISO EL DE JARDIN
sudo systemctl daemon-reload
sudo systemctl enable --now hierro
curl -s http://127.0.0.1:8053/health    # {"estado":"ok"}
journalctl -u hierro -f            # logs JSON
```

## 9. Nginx y certificado de origen de Cloudflare

El dominio pasa por el proxy de Cloudflare (nube naranja), así que el TLS se hace en dos
tramos: del cliente a Cloudflare con el certificado de Cloudflare, y de Cloudflare al
servidor con un **certificado de origen** que emite Cloudflare. No se usa Let's Encrypt:
su validación llega a Cloudflare, no al servidor, y falla con el error 520.

**En Cloudflare:**

1. *SSL/TLS → Origin Server → Create Certificate*: clave RSA, host
   `servicio.semanticaapi.com.co` y validez de 15 años.
2. Copia el certificado y la clave privada. La clave solo se muestra en ese momento.
3. *SSL/TLS → Overview*: modo **Full (strict)**.
4. *DNS*: el registro de `servicio.semanticaapi.com.co` apunta a la IP del servidor, con
   el proxy activado.

**En el servidor**, guarda el certificado y la clave:

```bash
sudo mkdir -p /etc/ssl/cloudflare
sudo nano /etc/ssl/cloudflare/hierro.pem    # pega el certificado de origen
sudo nano /etc/ssl/cloudflare/hierro.key    # pega la clave privada
sudo chmod 0644 /etc/ssl/cloudflare/hierro.pem
sudo chmod 0600 /etc/ssl/cloudflare/hierro.key
```

Nginx toma la IP real del cliente del header `CF-Connecting-IP`, pero solo si la
petición viene de Cloudflare. La lista de sus rangos se genera así:

```bash
{ curl -fsS https://www.cloudflare.com/ips-v4; echo; curl -fsS https://www.cloudflare.com/ips-v6; } \
    | awk 'NF { print "set_real_ip_from " $1 ";" }' \
    | sudo tee /etc/nginx/cloudflare-real-ip.conf >/dev/null
```

Cloudflare cambia esos rangos muy pocas veces. Repite el comando si publica nuevos.

Instala el sitio:
```bash
cd /opt/hierro
sudo cp deploy/nginx.conf /etc/nginx/sites-available/hierro
sudo ln -sf /etc/nginx/sites-available/hierro /etc/nginx/sites-enabled/hierro
sudo nginx -t && sudo systemctl reload nginx
curl -s https://servicio.semanticaapi.com.co/health    # {"estado":"ok"}
```

Si el servidor aloja otros sitios, deja su configuración como está. Solo borra
`/etc/nginx/sites-enabled/default` si nadie más lo usa.

El certificado de origen dura 15 años y no se renueva. Apunta en el calendario la fecha
en que vence.

## 10. Primera API key

```bash
cd /opt/hierro
sudo bash -c 'set -a; . ./.env; . ./.env.admin; set +a;
              .venv/bin/python scripts/crear_api_key.py crear "web"'
```

A partir de aquí, cada despliegue es `sudo /opt/hierro/deploy/deploy.sh`.
