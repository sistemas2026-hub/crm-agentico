"""
================================================================================
 OVERRIDES DE PRODUCCION  --  para ESTE despliegue, auto-hospedado
================================================================================

crm/settings.py hace 'from .server_settings import *' cuando ENV_TYPE == "prod",
y su comentario lo describe como un archivo que provee el operador. El que traia
el proyecto original describia el despliegue SaaS de bottlecrm.io y no servia
aca:

  - Exigia AWS_BUCKET_NAME, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY,
    AWS_SES_REGION_NAME, AWS_SES_REGION_ENDPOINT y SENTRY_DSN con
    os.environ[...] -- sin valor por defecto, asi que el contenedor moria con
    KeyError antes de levantar.
  - Fijaba SESSION_COOKIE_DOMAIN = ".bottlecrm.io". Eso es peor que el
    KeyError, porque no rompe el arranque: rompe el LOGIN. El navegador no
    manda a agent.rapilinksas.co una cookie acotada a otro dominio, y el
    sintoma seria "inicio sesion y me devuelve al login", sin ningun error.

Aqui no hay S3 ni SES: los archivos van al disco del contenedor y el correo se
configura por SMTP con variables de entorno. Sentry solo se activa si le pasan
un DSN.
================================================================================
"""

import os

DEBUG = False

# --- Archivos subidos ---------------------------------------------------------
# Al disco, no a S3. Necesita volumen en el compose: sin el, cada redespliegue
# se lleva los adjuntos que hayan subido los usuarios.
MEDIA_ROOT = os.environ.get("MEDIA_ROOT", "/app/media")
MEDIA_URL = "/media/"

# --- Cookies ------------------------------------------------------------------
# Sin dominio fijo: la cookie queda acotada al host que la emite, que es lo
# correcto cuando el dominio lo elige quien despliega. Se puede fijar por
# entorno si algun dia hace falta compartirla entre subdominios.
_dominio_cookie = os.environ.get("SESSION_COOKIE_DOMAIN", "").strip()
if _dominio_cookie:
    SESSION_COOKIE_DOMAIN = _dominio_cookie

# Traefik termina TLS delante, asi que todo viaja por HTTPS.
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# --- Sentry -------------------------------------------------------------------
# Opcional. El archivo original lo exigia siempre; aca solo se inicia si hay DSN,
# para que no reporte a un proyecto ajeno ni impida arrancar sin cuenta.
_sentry_dsn = os.environ.get("SENTRY_DSN", "").strip()
if _sentry_dsn:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=_sentry_dsn,
        integrations=[DjangoIntegration()],
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        # send_default_pii queda en False a proposito: este CRM guarda datos de
        # clientes de un ISP -cedula, direccion, telefono- y mandarlos a un
        # tercero con cada traza no lo cubre ninguna autorizacion.
        send_default_pii=False,
    )
