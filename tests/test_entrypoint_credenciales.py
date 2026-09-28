# -*- coding: utf-8 -*-
"""
================================================================================
 GUARDA  --  el entrypoint migra con la credencial de migraciones, no con la
             de trafico                                          (Etapa B.4)
================================================================================

    py -3.13 tests/test_entrypoint_credenciales.py

Que prueba
----------
'django-crm/docker/backend/entrypoint.sh' decide, en tiempo de arranque, con
que credencial corre 'migrate'. Esa decision es codigo de shell, y el codigo de
shell no lo cubre pytest ni el corredor de Django: se probaria solo desplegando.

Aqui se prueba de verdad, sin base de datos y sin red: se sustituye 'manage.py'
por uno de mentira que anota con que DBUSER lo llamaron y con que argumentos, y
se corre el entrypoint con distintas configuraciones. Lo que se afirma es el
EFECTO -- que 'migrate' vio la credencial correcta y que gunicorn/runserver vio
la otra--, no que exista una linea en el archivo.

Por que importa que sean dos credenciales distintas
---------------------------------------------------
Si 'migrate' corre con la credencial de trafico y esa credencial no es duena de
las tablas, la primera migracion que active RLS falla con 'must be owner of
table' -- a mitad de camino, con parte de la migracion aplicada. Medido contra
PostgreSQL 17 en la Etapa B.3.

Y si el override se hiciera exportando la variable en vez de por proceso,
gunicorn levantaria con la credencial de MIGRACIONES: serviria peticiones como
dueno de las tablas, que se saltea su propia politica de RLS salvo que este
FORCE. Esa es la razon de la ultima prueba de este archivo.
================================================================================
"""

import os
import shutil
import socket
import subprocess
import tempfile
import threading
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ENTRYPOINT = RAIZ / "django-crm" / "docker" / "backend" / "entrypoint.sh"

fallos: list[str] = []


def _socket_de_mentira():
    """
    Un puerto que acepta conexiones y no dice nada.

    El entrypoint solo comprueba que el puerto ACEPTE (abre un socket y lo
    cierra), no habla el protocolo de Postgres. Con esto la prueba no depende
    de ningun contenedor: se ejecuta sola, que es lo que hace que alguien la
    corra.
    """
    servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    servidor.bind(("127.0.0.1", 0))
    servidor.listen(16)

    def atender():
        while True:
            try:
                cliente, _ = servidor.accept()
                cliente.close()
            except OSError:
                return

    threading.Thread(target=atender, daemon=True).start()
    return servidor, servidor.getsockname()[1]


SERVIDOR_FALSO, PUERTO_FALSO = _socket_de_mentira()


def afirmar(condicion, que, detalle=""):
    print(("  [ok]    " if condicion else "  [FALLA] ") + que
          + ("\n           -> " + detalle if detalle else ""))
    if not condicion:
        fallos.append(que)


MANAGE_FALSO = r'''#!/usr/bin/env python3
"""
manage.py de mentira: anota como lo llamaron y sale.

'verificar_credenciales' devuelve 0 salvo que le pidan fallar (FINGIR_FALLO),
porque lo que se prueba aqui es el flujo del shell, no la guarda -- esa tiene
sus propias pruebas en django-crm/backend/common/tests/test_credenciales.py.
"""
import os, sys
registro = os.environ["REGISTRO"]
with open(registro, "a", encoding="utf-8") as f:
    f.write("%s\t%s\n" % (" ".join(sys.argv[1:]), os.environ.get("DBUSER", "")))
if sys.argv[1:2] == ["verificar_credenciales"] and os.environ.get("FINGIR_FALLO"):
    sys.exit(1)
sys.exit(0)
'''

# 'runserver'/'gunicorn' son el ultimo paso del entrypoint y bloquean para
# siempre. Se sustituyen por algo que anote y termine.
GUNICORN_FALSO = r'''#!/bin/sh
echo "gunicorn: $DBUSER" >> "$REGISTRO_ARRANQUE"
exit 0
'''


def correr(entorno_extra, fingir_fallo=False):
    """
    Corre el entrypoint en un directorio de trabajo desechable.

    Devuelve (codigo_de_salida, lineas_del_registro, arranque).
    """
    tmp = Path(tempfile.mkdtemp(prefix="b4_"))
    try:
        registro = tmp / "llamadas.tsv"
        arranque = tmp / "arranque.txt"

        (tmp / "manage.py").write_text(MANAGE_FALSO, encoding="utf-8")
        os.chmod(tmp / "manage.py", 0o755)
        # El entrypoint invoca 'python manage.py ...' y, al final, 'gunicorn'.
        binario = tmp / "bin"
        binario.mkdir()
        (binario / "gunicorn").write_text(GUNICORN_FALSO, encoding="utf-8")
        os.chmod(binario / "gunicorn", 0o755)

        entorno = {
            **os.environ,
            "PATH": str(binario) + os.pathsep + os.environ["PATH"],
            "REGISTRO": str(registro),
            "REGISTRO_ARRANQUE": str(arranque),
            # El entrypoint espera a que el puerto de Postgres acepte
            # conexiones antes de seguir. Se le apunta al socket de mentira
            # que levanta esta misma prueba: con un puerto muerto el bucle
            # reintenta 30 veces, tarda medio minuto por corrida y termina
            # fallando por un motivo que no tiene nada que ver con lo que se
            # esta midiendo. La primera version dependia de un contenedor
            # externo y por eso era fragil.
            "DBHOST": "127.0.0.1",
            "DBPORT": str(PUERTO_FALSO),
            "DBNAME": "crm_db",
            "ENV_TYPE": "prod",
            **entorno_extra,
        }
        if fingir_fallo:
            entorno["FINGIR_FALLO"] = "1"
        entorno.pop("MIGRATOR_DBUSER", None) if "MIGRATOR_DBUSER" not in entorno_extra else None

        proceso = subprocess.run(
            ["bash", str(ENTRYPOINT)], cwd=tmp, env=entorno,
            capture_output=True, text=True, timeout=120)

        lineas = []
        if registro.exists():
            for linea in registro.read_text(encoding="utf-8").splitlines():
                if "\t" in linea:
                    args, dbuser = linea.split("\t", 1)
                    lineas.append((args, dbuser))
        texto_arranque = arranque.read_text(encoding="utf-8") if arranque.exists() else ""
        return proceso.returncode, lineas, texto_arranque
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def dbuser_de(lineas, subcomando):
    """Con que DBUSER se llamo a un subcomando concreto."""
    for args, dbuser in lineas:
        if args.split()[0:1] == [subcomando]:
            return dbuser
    return None


def todas_las_llamadas(lineas, subcomando):
    return [(a, u) for a, u in lineas if a.split()[0:1] == [subcomando]]


print("=" * 78)
print("  GUARDA  --  entrypoint.sh y la credencial de migraciones")
print("=" * 78)

# El bucle de espera del entrypoint llama a python con un socket contra DBHOST.
# Con DBHOST=db y sin ese servicio, fallaria 30 veces y tardaria 30 segundos.
# Se comprueba primero que el archivo exista, para no confundir un error de
# ruta con un fallo de conducta.
if not ENTRYPOINT.exists():
    print(f"  no se encontro {ENTRYPOINT}")
    raise SystemExit(1)

# ---------------------------------------------------------------------------
print("\n--- 1. la configuracion de HOY: sin credencial de migraciones ---")
print("    (DBUSER=postgres, MIGRATOR_* sin definir -- lo desplegado al 16/09)")
codigo, llamadas, arranque = correr({"DBUSER": "postgres.05b5a4b4", "DBPASSWORD": "x"})

afirmar(codigo == 0, "el entrypoint termina bien", f"codigo={codigo}")
afirmar(dbuser_de(llamadas, "migrate") == "postgres.05b5a4b4",
        "'migrate' corre con DBUSER, como siempre",
        str(dbuser_de(llamadas, "migrate")))
afirmar(any("--proposito trafico" in a for a, _ in llamadas),
        "se comprueba la credencial de trafico antes de nada")
afirmar(any("--proposito migraciones" in a for a, _ in llamadas),
        "y tambien la de migraciones")

# ---------------------------------------------------------------------------
print("\n--- 2. la configuracion OBJETIVO: credencial de migraciones aparte ---")
codigo, llamadas, arranque = correr({
    "DBUSER": "crm_user.05b5a4b4", "DBPASSWORD": "x",
    "MIGRATOR_DBUSER": "crm_migrator.05b5a4b4", "MIGRATOR_DBPASSWORD": "y"})

afirmar(codigo == 0, "el entrypoint termina bien", f"codigo={codigo}")
afirmar(dbuser_de(llamadas, "migrate") == "crm_migrator.05b5a4b4",
        "'migrate' corre con la credencial de MIGRACIONES",
        str(dbuser_de(llamadas, "migrate")))

# La afirmacion que de verdad importa: el override es POR PROCESO.
afirmar("crm_user" in arranque,
        "gunicorn arranca con la credencial de TRAFICO, no con la de migraciones",
        f"arranque={arranque.strip()!r}")
afirmar("crm_migrator" not in arranque,
        "y en particular NO arranca como crm_migrator",
        "servir peticiones como crm_migrator seria servirlas como DUENO de las "
        "tablas, que se saltea su propia politica RLS salvo que este FORCE")

# 'create_default_admin' escribe filas: va con la credencial de trafico.
afirmar(dbuser_de(llamadas, "create_default_admin") == "crm_user.05b5a4b4",
        "'create_default_admin' usa la credencial de trafico: inserta filas, no DDL",
        str(dbuser_de(llamadas, "create_default_admin")))

# ---------------------------------------------------------------------------
print("\n--- 3. la guarda corta el arranque, no lo deja seguir ---")
codigo, llamadas, arranque = correr(
    {"DBUSER": "crm_migrator.05b5a4b4", "DBPASSWORD": "x"}, fingir_fallo=True)

afirmar(codigo != 0,
        "si 'verificar_credenciales' falla, el entrypoint NO continua",
        f"codigo={codigo}")
afirmar(not todas_las_llamadas(llamadas, "migrate"),
        "y no llega a ejecutar 'migrate'",
        str(todas_las_llamadas(llamadas, "migrate")))
afirmar(arranque == "",
        "ni levanta el servidor")

# ---------------------------------------------------------------------------
print("\n--- 4. la comprobacion de migraciones va CONTRA LA BASE ---")
print("    (decidir por el nombre del rol rompia el compose de desarrollo,")
print("     donde crm_user SI es dueno de todo el esquema)")
codigo, llamadas, arranque = correr({"DBUSER": "postgres", "DBPASSWORD": "x"})
migraciones = [a for a, _ in llamadas if "--proposito migraciones" in a]
afirmar(migraciones and all("--con-base" in a for a in migraciones),
        "la comprobacion de migraciones siempre pide --con-base",
        str(migraciones))

# ---------------------------------------------------------------------------
print("\n--- 5. el override alcanza a 'migrate' y a NADA mas ---")
# La primera version de esta prueba escaneaba el texto del script buscando
# asignaciones a DBUSER, y marcaba como peligrosa justo la forma correcta:
# 'DBUSER=... comando' es un override POR PROCESO, que es exactamente lo que
# hace falta. Un escaneo de texto no distingue eso de 'export DBUSER=...'.
#
# Se afirma sobre el efecto: de todas las llamadas del arranque, la credencial
# de migraciones tiene que aparecer en 'migrate' (y en su comprobacion) y en
# ninguna otra.
codigo, llamadas, arranque = correr({
    "DBUSER": "crm_user.05b5a4b4", "DBPASSWORD": "x",
    "MIGRATOR_DBUSER": "crm_migrator.05b5a4b4", "MIGRATOR_DBPASSWORD": "y"})

con_migrador = [a for a, u in llamadas if u == "crm_migrator.05b5a4b4"]
con_trafico = [a for a, u in llamadas if u == "crm_user.05b5a4b4"]

print(f"    llamadas con la credencial de migraciones: {con_migrador}")
print(f"    llamadas con la credencial de trafico:     {con_trafico}")

afirmar(all(a.startswith("migrate") or "--proposito migraciones" in a
            for a in con_migrador),
        "la credencial de migraciones SOLO aparece en migrate y su comprobacion",
        str(con_migrador))
afirmar(con_trafico and not any("migrate" == a.split()[0] for a in con_trafico),
        "la credencial de trafico NUNCA aparece en un 'migrate'",
        str(con_trafico))
afirmar("crm_user" in arranque and "crm_migrator" not in arranque,
        "y el proceso que queda sirviendo es el de trafico",
        f"arranque={arranque.strip()!r}")

print("\n" + "=" * 78)
print(f"  {len(fallos)} falla(s)")
for f in fallos:
    print("    - " + f)
print("=" * 78)
if fallos:
    raise SystemExit(1)
