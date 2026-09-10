# -*- coding: utf-8 -*-
"""
================================================================================
 EL CATALOGO DE GUIAS DE SINTONIZACION  --  Paso 1: el modelo
================================================================================

Por que existe
--------------
Decision de negocio del 10/09/2026: las instrucciones de sintonizacion pasan a
ser un catalogo administrable desde la pantalla, y dejan de vivir en el prompt.

Hasta hoy el paso a paso estaba escrito en TRES lugares -- el prompt del rol,
la descripcion de 'activar_catv' en tenants/, y la misma descripcion copiada
en conectores/ -- para una instruccion que cambia por marca de televisor y que
nadie podia corregir sin un desarrollador.

LO QUE ESTE ARCHIVO FIJA, Y POR QUE EN EL MODELO Y NO EN LA PANTALLA
--------------------------------------------------------------------
Las tres reglas de abajo son de NEGOCIO, no de interfaz. Puestas en el
formulario web se cumplen mientras alguien use el formulario; puestas en el
schema se cumplen tambien cuando la config se carga desde el YAML, se importa
de otro tenant, o la escribe un script. Es la misma eleccion que ya hizo este
proyecto con 'filtros_verificados' y con 'argumentos_calculados'.

  1. Con TDT la marca va vacia. No es un dato incompleto: es IMPOSIBLE. Quien
     sintoniza es la cajita, no el televisor, asi que 'Samsung + TDT' y
     'LG + TDT' dirian exactamente lo mismo -- y el catalogo se multiplicaria
     por marca sin agregar una sola instruccion distinta.

  2. Una guia ACTIVA tiene que tener instrucciones. Vacia gana la resolucion
     por ser la mas especifica y deja al agente sin nada que entregar, justo
     donde antes habia un texto en el prompt.

  3. Una sola guia activa por (marca, conexion). La resolucion es de codigo y
     tiene que ser determinista: con dos, cual gana depende del orden en que
     quedaron guardadas.

Corre SIN BASE DE DATOS y sin red.

Uso
---
    py -3.13 tests/test_guias_tv.py
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nucleo.config import cargar_config                              # noqa: E402
from nucleo.config.schema import GuiaTV, Herramienta, TenantConfig    # noqa: E402
from nucleo.config import editor                                     # noqa: E402
from nucleo.modelo import motor                                      # noqa: E402

fallos: list[str] = []


def afirmar(condicion: bool, que: str) -> None:
    print(f"  {'OK  ' if condicion else 'FALLA'}  {que}")
    if not condicion:
        fallos.append(que)


def acepta(**kw) -> bool:
    try:
        GuiaTV(**kw)
        return True
    except Exception:
        return False


print("== 1. las dos conexiones reales de Rapilink ==")
afirmar(acepta(marca="Samsung", tipo_conexion="directo",
               instrucciones="Menu > Canales > Busqueda automatica > ANTENA"),
        "TV directo con marca y su paso a paso")
afirmar(acepta(marca="", tipo_conexion="directo",
               instrucciones="Busca sintonizacion automatica y elige ANTENA"),
        "la guia GENERAL de TV directo (marca vacia)")
afirmar(acepta(marca="", tipo_conexion="tdt",
               instrucciones="Enciende el TDT y pon el TV en HDMI"),
        "la unica guia de TDT")
afirmar(not acepta(marca="Samsung", tipo_conexion="satelital",
                   instrucciones="x"),
        "un tipo de conexion inventado se rechaza -- solo hay dos")


print("\n== 2. con TDT la marca va vacia ==")
# La regla que evita que el catalogo se multiplique. Con TDT quien sintoniza
# es la cajita: la marca del televisor no cambia el procedimiento.
for marca in ("Samsung", "LG", "Sony", "  Kalley  "):
    afirmar(not acepta(marca=marca, tipo_conexion="tdt", instrucciones="x"),
            f"se rechaza {marca.strip()!r} + TDT")
afirmar(acepta(marca="   ", tipo_conexion="tdt", instrucciones="x"),
        "y solo espacios cuenta como vacia -- no se rechaza por un descuido "
        "de tipeo")


print("\n== 3. una guia ACTIVA tiene que decir algo ==")
afirmar(not acepta(marca="Samsung", instrucciones="", activa=True),
        "activa y sin instrucciones se rechaza: ganaria la resolucion y "
        "dejaria al agente sin nada que entregar")
afirmar(not acepta(marca="Samsung", instrucciones="   ", activa=True),
        "y con solo espacios tampoco")
afirmar(acepta(marca="Samsung", instrucciones="", activa=False),
        "apagada SI puede estar vacia -- es un borrador mientras se redacta")


print("\n== 4. lo demas es opcional, y eso importa ==")
# El video se manda solo si esta cargado: el agente no puede inventar un
# enlace. Y las observaciones son internas -- la resolucion las deja fuera.
g = GuiaTV(marca="LG", instrucciones="paso a paso")
afirmar(g.url_video == "" and g.observaciones == "",
        "sin video ni observaciones es una guia valida")
afirmar(g.activa is True and g.tipo_conexion == "directo",
        "y por defecto es activa y de TV directo")


print("\n== 5. una sola guia activa por (marca, conexion) ==")


# Se parte de la config REAL del tenant y solo se cambian las guias. Armar
# una config minima a mano fallaba por campos sin relacion -- y entonces el
# ayudante no distinguia "rechazada por las guias" de "rechazada por el slug",
# que es como esta prueba paso en verde la primera vez sin probar nada.
_BASE = cargar_config(
    Path(__file__).resolve().parents[1] / "tenants" / "rapilink.config.yaml"
).model_dump(mode="json")


def config_con(guias: list[dict]) -> bool:
    """True si la config con esas guias se acepta."""
    datos = dict(_BASE)
    datos["guias_tv"] = guias
    try:
        TenantConfig(**datos)
        return True
    except Exception:
        return False


afirmar(not config_con([
            {"marca": "Samsung", "instrucciones": "a"},
            {"marca": "Samsung", "instrucciones": "b"}]),
        "dos activas para la misma marca se rechazan")
# Normalizado, porque la resolucion tambien las trata igual: si aca no
# colisionaran, al resolver 'samsung' habria dos candidatas.
afirmar(not config_con([
            {"marca": "Samsung", "instrucciones": "a"},
            {"marca": "SAMSUNG", "instrucciones": "b"}]),
        "y 'Samsung' contra 'SAMSUNG' tambien -- son la misma marca para "
        "quien pregunta")
afirmar(config_con([
            {"marca": "Samsung", "instrucciones": "a"},
            {"marca": "Samsung", "instrucciones": "b", "activa": False}]),
        "pero la vigente y su borrador apagado conviven: para eso esta "
        "'activa'")
afirmar(config_con([
            {"marca": "", "instrucciones": "general"},
            {"marca": "", "tipo_conexion": "tdt", "instrucciones": "tdt"}]),
        "la general y la de TDT no chocan entre si -- distinta conexion")


print("\n== 6. el marcador que la vuelve consultable ==")
# Mismo patron que 'consulta_parrilla' y 'consulta_servicios_ofrecidos': el
# motor despacha por el marcador, no por el nombre de la herramienta, para que
# otro tenant pueda llamarla distinto.
afirmar("consulta_guias_tv" in Herramienta.model_fields,
        "Herramienta declara 'consulta_guias_tv'")
h = Herramienta(nombre="consultar_guia_sintonizacion", tipo="interno",
                descripcion="x", roles_permitidos=["soporte"],
                consulta_guias_tv=True)
afirmar(h.consulta_guias_tv is True,
        "y una herramienta interna puede declararlo")
afirmar("guias_tv" in TenantConfig.model_fields,
        "TenantConfig tiene el catalogo")


# =============================================================================
#  PASO 2 -- LA RESOLUCION
# =============================================================================
#
# Cual guia corresponde lo decide el CODIGO, no el modelo (PRD 12.5). Son tres
# reglas encadenadas y equivocarse en cualquiera le entrega al cliente un
# procedimiento que no corresponde a su televisor.


class _Config:
    """Una config con solo lo que la resolucion mira."""
    def __init__(self, guias):
        self.guias_tv = [GuiaTV(**g) if isinstance(g, dict) else g for g in guias]


SAMSUNG = {"marca": "Samsung", "instrucciones": "Menu > Canales > ANTENA",
           "url_video": "https://v.example/samsung", "observaciones": "interno"}
GENERAL = {"marca": "", "instrucciones": "Busca sintonizacion automatica",
           "observaciones": "nota del administrador"}
TDT = {"marca": "", "tipo_conexion": "tdt",
       "instrucciones": "Enciende el TDT y pon el TV en HDMI",
       "url_video": "https://v.example/tdt", "observaciones": "solo modelos nuevos"}

COMPLETO = _Config([SAMSUNG, GENERAL, TDT])


def resolver(config, **kw):
    return motor._ejecutar_consulta_guia_tv(config, kw)


print("\n== 7. marca + directo -> la guia especifica ==")
r = resolver(COMPLETO, tipo_conexion="directo", marca="Samsung")
afirmar(r.get("tipo_guia") == "especifica", "elige la guia de la marca")
afirmar(r.get("instrucciones") == SAMSUNG["instrucciones"],
        "y entrega SUS instrucciones, no las generales")
afirmar(r.get("url_video") == SAMSUNG["url_video"], "con su video")

# Normalizado: una guia cargada no puede quedar invisible por una mayuscula
# o una tilde, ni por un tipeo del cliente.
for escrito in ("samsung", "SAMSUNG", "  Samsung  ", "Sansung"):
    afirmar(resolver(COMPLETO, tipo_conexion="directo",
                     marca=escrito).get("tipo_guia") == "especifica",
            f"la encuentra escribiendo {escrito!r}")


print("\n== 8. marca sin guia propia -> la general ==")
r = resolver(COMPLETO, tipo_conexion="directo", marca="Kalley")
afirmar(r.get("tipo_guia") == "general", "cae a la general")
afirmar(r.get("instrucciones") == GENERAL["instrucciones"],
        "con el texto de la general")
afirmar(r.get("marca_sin_guia_propia") == "Kalley",
        "y avisa que esa marca no tiene guia -- para registrarla, no para "
        "escalar")


print("\n== 9. tdt -> la unica de TDT, ignorando la marca ==")
# El coaxial ni llega al televisor: quien sintoniza es la cajita.
for marca in ("Samsung", "Kalley", "", "LG"):
    r = resolver(COMPLETO, tipo_conexion="tdt", marca=marca)
    afirmar(r.get("tipo_guia") == "tdt"
            and r.get("instrucciones") == TDT["instrucciones"],
            f"con marca={marca!r} entrega la de TDT")
afirmar("marca_sin_guia_propia" not in resolver(
            COMPLETO, tipo_conexion="tdt", marca="Kalley"),
        "y NO la registra como marca sin guia: en TDT la marca es irrelevante")


print("\n== 10. una guia inactiva no se usa ==")
apagada = _Config([{**SAMSUNG, "activa": False}, GENERAL])
r = resolver(apagada, tipo_conexion="directo", marca="Samsung")
afirmar(r.get("tipo_guia") == "general",
        "con la de Samsung apagada, cae a la general en vez de usarla")
afirmar(r.get("instrucciones") != SAMSUNG["instrucciones"],
        "y no entrega su texto")


print("\n== 11. sin guia: fail-closed, no se inventa nada ==")
# Antes del catalogo el paso a paso vivia en el prompt y el modelo siempre
# tenia algo que decir. Ahora la fuente es el catalogo: si esta vacio, la
# respuesta correcta es no saber.
for config, caso in ((_Config([]), "catalogo vacio"),
                     (_Config([TDT]), "solo hay de TDT y piden directo")):
    r = resolver(config, tipo_conexion="directo", marca="Samsung")
    afirmar(r.get("guia_encontrada") is False, f"{caso}: no hay guia")
    afirmar("instrucciones" not in r and "url_video" not in r,
            f"{caso}: no devuelve instrucciones inventadas")
    afirmar("NO inventes" in (r.get("instruccion_interna") or ""),
            f"{caso}: y se lo dice al modelo explicitamente")

r = resolver(_Config([SAMSUNG, GENERAL]), tipo_conexion="tdt")
afirmar(r.get("guia_encontrada") is False,
        "sin guia de TDT tampoco se cae a la general -- son procedimientos "
        "distintos, no uno el respaldo del otro")


print("\n== 12. sin saber la conexion, se pregunta ==")
# La de TDT y la de TV directo no se parecen en nada: suponer cual es le
# entrega al cliente el procedimiento del equipo que no tiene.
for kw in ({}, {"marca": "Samsung"}, {"tipo_conexion": "cable"}):
    r = resolver(COMPLETO, **kw)
    afirmar(r.get("guia_encontrada") is False and "instrucciones" not in r,
            f"con {kw or 'nada'} no entrega ninguna guia")
afirmar("cajita" in (resolver(COMPLETO).get("instruccion_interna") or ""),
        "y le dice al agente que pregunte por la cajita")


print("\n== 13. las observaciones NUNCA salen ==")
# Son notas para quien administra el catalogo ("confirmado con el tecnico"),
# no para el cliente ni para el modelo que redacta.
for kw in ({"tipo_conexion": "directo", "marca": "Samsung"},
           {"tipo_conexion": "directo", "marca": "Kalley"},
           {"tipo_conexion": "tdt"}):
    r = resolver(COMPLETO, **kw)
    afirmar("observaciones" not in r,
            f"no hay clave 'observaciones' resolviendo {kw}")
    afirmar(not any("interno" in str(v) or "administrador" in str(v)
                    or "modelos nuevos" in str(v) for v in r.values()),
            f"ni su texto se cuela por otra clave resolviendo {kw}")


print("\n== 14. una guia sin video no inventa la clave ==")
sin_video = _Config([{"marca": "LG", "instrucciones": "paso a paso"}, GENERAL])
r = resolver(sin_video, tipo_conexion="directo", marca="LG")
afirmar("url_video" not in r,
        "sin video cargado la clave NO viene -- una clave vacia invita al "
        "modelo a rellenarla")


# =============================================================================
#  PASO 3 -- LA ADMINISTRACION
# =============================================================================
#
# El mutador NO repite las reglas de negocio: las hace cumplir el schema
# cuando _editar() valida la config entera antes de guardar. Lo que se prueba
# aca es que normalice la FORMA y que la seccion este registrada -- si no lo
# esta, una carga del YAML borra el catalogo en silencio.


def mutado(guias):
    doc = {}
    editor._mutar_guias_tv(doc, guias)
    return doc["guias_tv"]


print("PASO3 7. el mutador normaliza lo que manda la pantalla")
r = mutado([{"marca": "  Samsung  ", "tipo_conexion": " DIRECTO ",
             "instrucciones": "  Menu > ANTENA  ", "url_video": " http://v  ",
             "observaciones": "  nota  "}])
afirmar(r[0]["marca"] == "Samsung", "recorta la marca")
afirmar(r[0]["tipo_conexion"] == "directo",
        "y el tipo llega en minusculas -- 'DIRECTO' desde un formulario no "
        "puede quedar fuera del enum por una mayuscula")
afirmar(r[0]["instrucciones"] == "Menu > ANTENA", "recorta las instrucciones")
afirmar(r[0]["url_video"] == "http://v", "y la URL")
afirmar(r[0]["activa"] is True, "activa por defecto")

# La fila vacia que deja un formulario cuando alguien agrega y no completa.
afirmar(mutado([{"marca": "", "instrucciones": "", "url_video": ""}]) == [],
        "una fila del todo vacia se descarta, no se guarda como guia rota")
afirmar(len(mutado([{"marca": "", "instrucciones": "la general"}])) == 1,
        "pero la GENERAL -- sin marca y con texto-- si se guarda")


print("PASO3 8. reemplaza el catalogo entero, apagadas incluidas")
r = mutado([{"marca": "Samsung", "instrucciones": "a"},
            {"marca": "LG", "instrucciones": "b", "activa": False}])
afirmar(len(r) == 2 and r[1]["activa"] is False,
        "la apagada se conserva: es un borrador o una version vieja que "
        "alguien quiere poder volver a encender")


print("PASO3 9. las reglas siguen siendo del schema, no del mutador")
# El mutador deja pasar lo que el schema rechaza. Es lo correcto: una sola
# fuente para cada regla. Lo que garantiza que no se guarde es _editar(),
# que valida la config entera y hace rollback.
crudo = mutado([{"marca": "Samsung", "tipo_conexion": "tdt",
                 "instrucciones": "x"}])
afirmar(crudo and crudo[0]["marca"] == "Samsung",
        "el mutador no juzga: normaliza y pasa")
afirmar(not config_con(crudo),
        "y el schema lo rechaza al validar -- Samsung + TDT no se guarda")
afirmar(not config_con(mutado([{"marca": "LG", "instrucciones": ""}])),
        "una activa sin instrucciones tampoco")
afirmar(not config_con(mutado([{"marca": "LG", "instrucciones": "a"},
                               {"marca": "lg", "instrucciones": "b"}])),
        "ni dos activas para la misma marca")


print("PASO3 10. la seccion esta registrada donde corresponde")
afirmar("guias_tv" in editor.SECCIONES_EDITABLES,
        "en SECCIONES_EDITABLES: sin esto, una carga del YAML borra el "
        "catalogo sin siquiera avisar")
# Y NO en SINCRONIZADOS, a proposito: el criterio de esa lista es "lo produjo
# un proceso y se reemplaza entero" (128 localidades, 100 canales de un
# Excel). Una guia la redacta una persona, se lee bien en un diff, y un tenant
# nuevo tiene que poder nacer con guias semilla desde el YAML.
afirmar("guias_tv" not in TenantConfig.SINCRONIZADOS,
        "y NO en SINCRONIZADOS: es una decision de una persona, como "
        "planes_venta, no la salida de un proceso")
afirmar(callable(getattr(editor, "guardar_guias_tv", None)),
        "existe guardar_guias_tv, que valida y guarda en una transaccion")


print("PASO3 11. la administracion SI ve las observaciones")
# Es la asimetria del diseño: quien edita el catalogo tiene que verlas; el
# modelo que redacta, no. Se comprueban las dos puntas contra el mismo dato.
guia = GuiaTV(marca="Samsung", instrucciones="x", observaciones="secreto interno")
afirmar("observaciones" in guia.model_dump(mode="json"),
        "el modelo serializado que devuelve el endpoint las incluye")
afirmar("observaciones" not in resolver(_Config([guia]),
                                        tipo_conexion="directo", marca="Samsung"),
        "y la resolucion que consume el agente NO")


print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es):")
    for f in fallos:
        print(f"  - {f}")
    raise SystemExit(1)
print("[OK] El modelo del catalogo impide las guias que no pueden existir.")
