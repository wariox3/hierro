-- Datos de ejemplo para desarrollo local. NO ejecutar en producción.
--
--   psql "postgresql://USUARIO@localhost:5432/bdhierro" -v ON_ERROR_STOP=1 -f scripts/seed.sql
--
-- Es idempotente: se puede ejecutar varias veces sin duplicar datos.
--
-- Crea dos API keys conocidas, SOLO para desarrollo:
--   web-desarrollo    nk_desarrollo_web_0000000000000000000000000000
--   movil-desarrollo  nk_desarrollo_movil_00000000000000000000000000

BEGIN;

INSERT INTO api_key (nombre, hash, prefijo) VALUES
    ('web-desarrollo',
     encode(sha256('nk_desarrollo_web_0000000000000000000000000000'::bytea), 'hex'),
     'nk_desarrollo'),
    ('movil-desarrollo',
     encode(sha256('nk_desarrollo_movil_00000000000000000000000000'::bytea), 'hex'),
     'nk_desarrollo')
ON CONFLICT (nombre) DO NOTHING;

-- Noticias. Se identifican por título para no duplicarlas.
INSERT INTO noticia (titulo, contenido, url_imagen, fecha_publicacion, estado_inactivo)
SELECT v.titulo, v.contenido, v.url_imagen, v.fecha_publicacion, v.estado_inactivo
FROM (VALUES
    ('El equipo local gana el campeonato',
     '<p>El equipo local <strong>ganó</strong> la final.</p><p><a href="https://ejemplo.com">Ver más</a></p>',
     'https://picsum.photos/seed/deportes/800/450',
     now() - interval '2 hours', false),
    ('Nueva versión del sistema operativo',
     '<h2>Novedades</h2><ul><li>Más rápido</li><li>Más seguro</li></ul><script>alert(1)</script>',
     'https://picsum.photos/seed/tecnologia/800/450',
     now() - interval '1 day', false),
    ('El dólar cierra estable',
     '<p onclick="robar()">Jornada tranquila en los mercados.</p>',
     NULL,
     now() - interval '3 days', false),
    ('Noticia programada para mañana',
     '<p>Todavía no se ve.</p>',
     NULL,
     now() + interval '1 day', false),
    ('Noticia despublicada',
     '<p>Tiene estado_inactivo = true, así que no se ve.</p>',
     NULL,
     now() - interval '5 days', true)
) AS v(titulo, contenido, url_imagen, fecha_publicacion, estado_inactivo)
WHERE NOT EXISTS (SELECT FROM noticia n WHERE n.titulo = v.titulo);

COMMIT;
