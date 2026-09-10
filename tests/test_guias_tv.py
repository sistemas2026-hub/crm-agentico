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


print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es):")
    for f in fallos:
        print(f"  - {f}")
    raise SystemExit(1)
print("[OK] El modelo del catalogo impide las guias que no pueden existir.")
