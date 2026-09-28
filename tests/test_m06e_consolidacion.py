# -*- coding: utf-8 -*-
"""
================================================================================
 M06-E  --  consolidacion M04-M06: excepciones conservadoras y rutas
================================================================================

Fija las reglas de la seccion 3 del bloque y los invariantes de la auditoria de
rutas, sobre el codigo real (frontera, ejecutor HTTP, motor) con red y base
sustituidas por el entorno de tests/test_m06a_gate_critico.py.

  3.A  lecturas sin efecto autonomo
  3.B  las 3 escrituras INDETERMINADAS no salen por la puerta autonoma
       (la humana -- una persona desde la pantalla -- sigue igual);
       sondear_api no es alcanzable por ninguna ruta sin persona
  3.C  cancelar_solicitud_servicio: aprobacion humana atada (puerta critica)
  3.D  ping_cliente: efecto externo; ninguna ruta sin persona lo usa
  3.E  las R1 NO bajan de nivel: nada declara nivel_autonomia

  Rutas: el nucleo no escribe afuera sin el ejecutor; Django no llama directo a
  WispHub/SmartOLT y solo pide al motor herramientas de servicio o lecturas; el
  script manual de reinicio ya no corre sin confirmacion.

Datos inventados. Ninguna llamada real.
================================================================================
"""

from __future__ import annotations

import ast
import pathlib
import re
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from tests import test_m06a_gate_critico as g                      # noqa: E402
from nucleo.herramientas import http as ejecutor_http             # noqa: E402
from nucleo.modelo import motor                                    # noqa: E402
from nucleo.seguridad import frontera                              # noqa: E402
from nucleo.seguridad import techo as techos                       # noqa: E402
from tests.test_m10a_gobierno_frontera import R1_INTERNO, R2_REGISTRO_EXTERNO  # noqa: E402

FALLOS: list[str] = []
CONFIG, H, TENANT, SESION = g.CONFIG, g.H, g.TENANT, g.SESION
INDETERMINADAS_ESCRITURA = ("responder_ticket_operativo", "cerrar_ticket_operativo",
                            "completar_ticket_instalacion")
#  Rutas SIN persona detras: el scheduler, el importador, el agendamiento
#  automatico, las acciones operativas por vencimiento, la ruta de servicio.
MODULOS_SIN_PERSONA = ("nucleo/reloj.py", "nucleo/programador",
                       "nucleo/seguimiento/importacion_io.py",
                       "nucleo/seguimiento/agendamiento.py",
                       "nucleo/seguimiento/operativo.py")


def afirmar(c: bool, que: str, detalle: str = "") -> None:
    print(("  [ok]    " if c else "  [FALLA] ") + que)
    if not c:
        FALLOS.append(que)
        if detalle:
            print(f"          {detalle}")


def seccion(t: str) -> None:
    print(f"\n--- {t} ---")


def fuentes(*rutas) -> str:
    texto = []
    for r in rutas:
        p = RAIZ / r
        for f in ([p] if p.is_file() else p.rglob("*.py")):
            texto.append(f.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(texto)


def main() -> int:
    print("=" * 78)
    print("  M06-E  --  excepciones conservadoras e invariantes de rutas")
    print("=" * 78)

    seccion("3.E  Ningun nivel se relajo: el runtime sigue como antes")
    declarados = [h.nombre for h in CONFIG.herramientas if h.nivel_autonomia is not None]
    afirmar(not declarados, f"ninguna herramienta declara nivel_autonomia {declarados}")
    afirmar(all(techos.nivel_requerido_de(H[n]) == 2 for n in R1_INTERNO),
            "las R1 siguen exigiendo 2 (M06-D proponia 1: NO se aplico)")

    seccion("3.C  cancelar_solicitud_servicio: aprobacion atada, puerta critica")
    h = H["cancelar_solicitud_servicio"]
    afirmar(h.irreversible and h.aprobacion_humana and not h.invocable_por_servicio,
            "irreversible + aprobacion humana, no invocable por servicio")
    afirmar("cancelar_solicitud_servicio" in R2_REGISTRO_EXTERNO,
            "su clase historica (R2 en M10-A) NO se cambio")
    afirmar("cancelar_solicitud_servicio" in g.IRREVERSIBLES,
            "y la bateria de M06-A (sin/con aprobacion, sello, kill switch, bypass) la cubre")
    with g.Entorno() as e:
        cod = g.intento_directo(lambda: motor._ejecutar_tool(
            h, SESION, dict(g.MODELO["cancelar_solicitud_servicio"]), TENANT,
            CONFIG.variables_tenant, origen="evento:m06e"))
    afirmar(cod == frontera.IRREVERSIBLE_SIN_APROBACION and e.red.llamadas == [],
            f"por la conversacion/agente no sale -> {cod}, {len(e.red.llamadas)} llamadas")

    seccion("3.B  Las 3 escrituras INDETERMINADAS: fuera de la puerta autonoma")
    for n in INDETERMINADAS_ESCRITURA:
        hn = H[n]
        afirmar(hn.aprobacion_humana and not hn.irreversible,
                f"{n}: aprobacion_humana (bloqueo autonomo) sin cambiar su clase")
        args = {"id_ticket": 999001, "respuesta": "prueba"}
        with g.Entorno(autorizadas=g.IRREVERSIBLES + INDETERMINADAS_ESCRITURA) as e:
            with frontera.autonoma(TENANT, n, origen="evento:m06e"):
                cod = g.intento_directo(lambda: ejecutor_http.ejecutar(
                    hn, args, TENANT, CONFIG.variables_tenant))
        afirmar(cod == frontera.APROBACION_REQUERIDA and e.red.llamadas == [],
                f"{n}: puerta autonoma con techo, etapa y autorizacion en regla -> {cod}, "
                f"{len(e.red.llamadas)} llamadas")
        if hn.invocable_por_servicio:
            with g.Entorno(autorizadas=g.IRREVERSIBLES + INDETERMINADAS_ESCRITURA) as e:
                #  El codigo EXACTO, no "cualquier excepcion": una firma mal
                #  llamada tambien levanta, y eso no probaria el bloqueo.
                cod = g.intento_directo(lambda: motor.ejecutar_para_servicio(
                    CONFIG, hn, dict(args), origen="servicio:m06e"))
            afirmar(cod == frontera.APROBACION_REQUERIDA and e.red.llamadas == [],
                    f"{n}: por la ruta de servicio (sin persona) -> {cod}, "
                    f"{len(e.red.llamadas)} llamadas")
        with g.Entorno() as e:
            with frontera.humana(TENANT, n, actor="colaborador.prueba",
                                 evidencia="mensaje-desde-la-pantalla"):
                ejecutor_http.ejecutar(hn, args, TENANT, CONFIG.variables_tenant)
        afirmar(len(e.red.escrituras) == 1,
                f"{n}: por la puerta HUMANA (una persona desde la pantalla) sigue saliendo")

    seccion("3.B  sondear_api y 3.D ping_cliente: ninguna ruta sin persona")
    sin_persona = fuentes(*MODULOS_SIN_PERSONA)
    for n in ("sondear_api", "ping_cliente"):
        afirmar(not H[n].invocable_por_servicio, f"{n}: no invocable por servicio")
        afirmar(n not in sin_persona,
                f"{n}: ningun modulo sin persona (scheduler, importador, agendamiento, "
                f"operativo) lo nombra")
        with g.Entorno() as e:
            try:
                motor.ejecutar_para_servicio(CONFIG, H[n], {})
                motivo = ""
            except ValueError as ex:
                motivo = str(ex)
        afirmar("invocable_por_servicio" in motivo and e.red.llamadas == [],
                f"{n}: la ruta de servicio lo rechaza por no ser invocable "
                f"({motivo[:60]}...)")
    afirmar(H["sondear_api"].roles_permitidos == ["configuracion_guiada"],
            "sondear_api: solo en la configuracion guiada (un ADMIN en la pantalla)")
    afirmar(H["ping_cliente"].metodo == "POST",
            "ping_cliente: documentado como efecto externo (POST), aunque figure como lectura")

    seccion("3.A  Las lecturas no pasan por la frontera ni producen efecto")
    lecturas = [x for x in CONFIG.herramientas if x.solo_lectura]
    lecturas_post = sorted(x.nombre for x in lecturas if x.metodo == "POST")
    afirmar(set(lecturas_post) <= {"ping_cliente", "consultar_solicitud_por_cedula"},
            f"las unicas lecturas por POST son las ya identificadas {lecturas_post}")

    seccion("Rutas: nada escribe afuera sin el ejecutor y la frontera")
    directos = []
    for ruta in (RAIZ / "nucleo").rglob("*.py"):
        rel = ruta.relative_to(RAIZ).as_posix()
        if rel in ("nucleo/herramientas/http.py", "nucleo/canales/whatsapp.py"):
            continue
        for n in ast.walk(ast.parse(ruta.read_text(encoding="utf-8"))):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr in ("post", "put", "patch", "delete", "request")
                    and ast.unparse(n.func.value) in ("requests", "httpx")):
                directos.append(f"{rel}:{n.lineno}")
    afirmar(not directos, f"ningun modulo del nucleo escribe HTTP directo {directos}")
    r = subprocess.run([sys.executable, str(RAIZ / "tests" / "test_frontera_externa.py")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    afirmar(r.returncode == 0, "test_frontera_externa (llamadores permitidos del ejecutor) en verde")

    django = RAIZ / "django-crm" / "backend"
    llamadas_directas = []
    for ruta in django.rglob("*.py"):
        if "tests" in ruta.parts or "migrations" in ruta.parts:
            continue
        texto = ruta.read_text(encoding="utf-8", errors="replace")
        if re.search(r"api\.wisphub\.io|/api/onu/|smartolt\.com", texto):
            llamadas_directas.append(ruta.relative_to(RAIZ).as_posix())
    afirmar(not llamadas_directas,
            f"Django no llama directo a la API de WispHub ni a SmartOLT {llamadas_directas}")
    pedidas = set()
    for ruta in django.rglob("*.py"):
        if "tests" in ruta.parts:
            continue
        texto = ruta.read_text(encoding="utf-8", errors="replace")
        pedidas |= set(re.findall(r"/interno/herramienta/([a-z_]+)", texto))
        pedidas |= set(re.findall(r"HERRAMIENTA_[A-Z_]+\", \"\"\)\s*\n?\s*or \"([a-z_]+)\"", texto))
        pedidas |= set(re.findall(r'or "([a-z_]+_(?:operativo|instalacion))"', texto))
    no_servicio = sorted(n for n in pedidas if n in H and not H[n].solo_lectura
                         and not H[n].invocable_por_servicio)
    afirmar(pedidas and not no_servicio,
            f"Django solo pide al motor lecturas o herramientas de servicio "
            f"({sorted(pedidas)}); ninguna escritura fuera de esa lista {no_servicio}")

    r = subprocess.run([sys.executable, str(RAIZ / "cli" / "prueba_reinicio_con_ping.py")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env={"SMARTOLT_BASE_URL": "https://x.invalid", "SMARTOLT_API_KEY": "x",
                            "WISPHUB_API_KEY": "x", "SYSTEMROOT": "C:\\Windows", "PATH": ""})
    afirmar(r.returncode == 2 and "NO se reinicia nada" in r.stdout,
            f"el script manual de reinicio (R3 directo) ya no corre sin confirmacion "
            f"(exit {r.returncode})")

    print()
    if FALLOS:
        print(f"  {len(FALLOS)} falla(s):")
        for x in FALLOS:
            print(f"    - {x}")
        return 1
    print("  [OK] Excepciones conservadoras aplicadas; ninguna ruta sin persona las alcanza.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
