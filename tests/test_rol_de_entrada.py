# -*- coding: utf-8 -*-
"""
Quien atiende un canal publico se DECIDE, no se hereda del orden de un dict.

    py -3.13 tests/test_rol_de_entrada.py

Corre SIN RED y SIN BASE.

QUE PASO
--------
Todo mensaje que entra por WhatsApp se atiende con el rol que devuelve
nucleo/canales/api.py::_rol_de_cliente(). Devolvia el PRIMER rol con
orientado_a='cliente_final'.

Buscar por 'orientado_a' y no por nombre es correcto -- el nucleo no puede
saber como llamo cada empresa a su rol de autoservicio (PRD 3). Pero eso
resuelve QUE roles son candidatos, no CUAL atiende. Rapilink tiene cuatro:

    ventas · cliente_final · facturacion_cliente · soporte_tecnico_cliente

El 07/09/2026 el primero era 'ventas', que existe para PROSPECTOS ("todavia
no es cliente de Rapilink", dice su propia descripcion) y que NO tiene
'derivar_a_area'. Un suscriptor sin internet escribia "Hola" y le contestaba
el agente comercial, sin ninguna forma de pasarlo a soporte.

Y no fue una eleccion que alguien hizo mal: el orden de las claves cambia
solo, porque editar la configuracion desde la interfaz reserializa el JSON
entero. Nadie decidio que fuera 'ventas', y nadie iba a enterarse.

QUE FIJA ESTE TEST
------------------
Que exista la configuracion explicita, que valga mas que el orden, que un
valor mal escrito se rechace en vez de caer en silencio al comportamiento
viejo, y que ese comportamiento viejo AVISE cuando hay mas de un candidato.
"""

from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

fallos: list[str] = []


def revisar(ok: bool, que: str, detalle: str = "") -> None:
    if ok:
        print(f"  ok     {que}")
    else:
        fallos.append(que)
        print(f"  FALLA  {que}" + (f"\n         {detalle}" if detalle else ""))


class _Rol:
    def __init__(self, orientado_a):
        self.orientado_a = orientado_a


class _Config:
    """Lo minimo que mira _rol_de_cliente. Sin base y sin red."""
    def __init__(self, roles, entrada=None):
        self.roles = roles
        self.rol_de_entrada = entrada


# El orden es el del caso real: 'ventas' primero.
CUATRO = {
    "ventas": _Rol("cliente_final"),
    "soporte": _Rol("colaborador"),
    "cliente_final": _Rol("cliente_final"),
    "facturacion_cliente": _Rol("cliente_final"),
}

from nucleo.canales.api import _rol_de_cliente  # noqa: E402


# --- 1. la configuracion manda sobre el orden --------------------------------
elegido = _rol_de_cliente(_Config(CUATRO, entrada="cliente_final"))
revisar(elegido == "cliente_final",
        "con 'rol_de_entrada' definido, atiende ese y no el primero",
        f"atendio '{elegido}' teniendo 'cliente_final' configurado")


# --- 2. sin configurar, el viejo comportamiento AVISA -------------------------
# No se hace obligatorio para no dejar mudo a un tenant ya cargado. Pero
# elegir por un orden que nadie decidio es justo lo que hay que poder ver.
salida = io.StringIO()
with redirect_stdout(salida):
    sin_config = _rol_de_cliente(_Config(CUATRO))
aviso = salida.getvalue()
revisar(sin_config == "ventas" and "rol_de_entrada" in aviso,
        "sin configurar sigue tomando el primero, PERO avisa",
        f"eligio {sin_config!r}; aviso={aviso.strip()[:90]!r}")


# --- 3. un solo candidato no molesta -----------------------------------------
# Un tenant con un unico rol de cliente no tiene ninguna ambiguedad que
# resolver: avisarle seria ruido en cada arranque.
salida = io.StringIO()
with redirect_stdout(salida):
    uno = _rol_de_cliente(_Config({"cf": _Rol("cliente_final"),
                                   "int": _Rol("colaborador")}))
revisar(uno == "cf" and not salida.getvalue().strip(),
        "con un solo rol de cliente no avisa nada")


# --- 4. sin ningun candidato, None (el llamador ya lo contempla) --------------
revisar(_rol_de_cliente(_Config({"int": _Rol("colaborador")})) is None,
        "sin ningun rol de cliente devuelve None")


# --- 5. un valor mal escrito se RECHAZA --------------------------------------
# Esto es lo que evita que el arreglo se deshaga en silencio: un typo que
# cayera al comportamiento viejo se veria exactamente igual que si funcionara.
import yaml  # noqa: E402
from nucleo.config.schema import TenantConfig, cargar_config  # noqa: E402

ruta = RAIZ / "tenants" / "rapilink.config.yaml"
base = cargar_config(ruta).model_dump()

for etiqueta, valor, esperado in [
    ("un rol inexistente", "no_existe", "no existe"),
    ("un rol interno", "soporte", "colaborador"),
]:
    try:
        TenantConfig(**{**base, "rol_de_entrada": valor})
        revisar(False, f"se rechaza {etiqueta} como rol_de_entrada",
                "fue aceptado")
    except Exception as e:
        revisar(esperado in str(e),
                f"se rechaza {etiqueta} como rol_de_entrada",
                f"se rechazo, pero el motivo no menciona {esperado!r}: "
                f"{str(e)[:120]}")


# --- 6. el YAML semilla lo trae ----------------------------------------------
# El YAML es la semilla de un tenant nuevo. Si no lo trae, la proxima empresa
# que se conecte arranca con el mismo problema.
crudo = yaml.safe_load(ruta.read_text(encoding="utf-8"))
revisar(bool(crudo.get("rol_de_entrada")),
        "el YAML semilla define rol_de_entrada",
        "Sin esto, el proximo ISP que se conecte elige por orden de "
        "diccionario, igual que antes.")


print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    raise SystemExit(1)
print("[OK] Quien atiende un canal publico se decide, no se hereda.")
