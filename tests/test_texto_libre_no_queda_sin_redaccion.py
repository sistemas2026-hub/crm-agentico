# -*- coding: utf-8 -*-
"""
================================================================================
 UN CAMPO DE TEXTO LIBRE NO PASA SIN REDACCION
================================================================================

Por que existe
--------------
CLAUDE.md §5 lo pide en una frase: «al agregar un campo a una lista blanca,
preguntarse si es texto libre; si lo es, va tambien a `campos_texto_libre`».
Esa pregunta la tiene que hacer una persona, y el 08/10/2026 se comprobo que
hacia rato que nadie la hacia.

`asunto` estaba en la lista blanca de `soporte`, `administracion` y
`supervisor_noc`, y en NINGUNA de las cinco herramientas estaba declarado como
texto libre. Parecia un enum --el catalogo
`/api/tickets/asuntos-tickets/` declara 142 asuntos-- y no lo es: sobre 3.418
tickets reales hay **356 distintos**, 277 fuera del catalogo, y **126 traen el
NOMBRE y el BARRIO del prospecto** porque los tickets de instalacion usan ese
campo como rotulo.

Nadie lo vio porque la lista blanca hacia su trabajo: el campo estaba
autorizado. Lo que faltaba era la capa 2, y su ausencia no da error.

Que se verifica
---------------
Para cada herramienta, que todo campo de la LISTA NEGRA de nombres --los que
en esta API son texto escrito por una persona-- que algun rol deja pasar, este
tambien en `campos_texto_libre`.

Es una guarda de forma, no de contenido: no puede saber si un campo nuevo
traera PII. Lo que si puede es que los que YA se sabe que son texto libre no se
agreguen a una lista blanca sin su redaccion -- que es exactamente como paso
esta vez.

    py -3.13 tests/test_texto_libre_no_queda_sin_redaccion.py
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo.config import cargar_config                          # noqa: E402

#: Campos que en estas APIs los escribe una persona, no un sistema.
#:
#: Cada uno con el motivo por el que esta, porque una lista sin motivos se
#: vuelve intocable: nadie sabe si puede sacar uno.
TEXTO_LIBRE_CONOCIDO = {
    "descripcion": (
        "texto libre de un operador. PRD 7.4: un caso real traia nombre, "
        "telefono, email, direccion, GPS, cedula y un enlace en un solo campo. "
        "Y 136 de 300 tickets traian un documento embebido."
    ),
    "asunto": (
        "parece un enum y no lo es: 356 valores distintos sobre 3.418 tickets "
        "(08/10/2026), 277 fuera del catalogo del proveedor, y 126 con el "
        "nombre y el barrio del prospecto."
    ),
    "respuesta": "lo que un operador le contesta al cliente.",
    "comentarios": "texto libre del operador en la ficha del cliente.",
    "observaciones": "idem.",
    "motivo": "texto libre al abrir o cerrar algo.",
}

#: Donde ese NOMBRE de campo no significa texto escrito por una persona.
#:
#: Sin esto la guarda grita por cinco casos correctos, y una guarda que grita
#: por lo que esta bien se termina apagando -- que es peor que no tenerla.
#: Cada excepcion lleva su motivo VERIFICADO, para que quien la lea pueda
#: discutirla en vez de confiar.
EXCEPCIONES = {
    ("consultar_plan_detalle", "descripcion"):
        "es la descripcion del PLAN COMERCIAL ('PLAN ELITE 700MB + TV + "
        "DISNEY+'), no texto de una persona sobre un cliente. Sale del "
        "catalogo del proveedor.",
    ("consultar_plan_tv", "descripcion"):
        "idem: la descripcion del plan, que es justo lo que esta herramienta "
        "lee para saber si incluye TV.",
    ("diagnosticar_servicio", "motivo"):
        "lo genera el codigo del diagnostico ('sin_energia', 'fibra'), no una "
        "persona. Herramienta interna.",
    ("consultar_incidente_red", "motivo"):
        "idem: el veredicto de la correlacion contra los incidentes de la OLT.",
    ("consultar_estabilidad_enlace", "motivo"):
        "idem: por que se cayo el enlace, derivado de las lecturas de SmartOLT.",
}

fallos: list[str] = []


def check(condicion: bool, que: str) -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}")
    if not condicion:
        fallos.append(que)


def _hoja(campo: str) -> str:
    """El ultimo tramo de un campo con punto: 'servicio.asunto' -> 'asunto'."""
    return str(campo).split(".")[-1]


def revisar(ruta: Path) -> None:
    config = cargar_config(ruta)
    por_nombre = {h.nombre: h for h in config.herramientas}

    # Que campo de texto libre deja pasar cada herramienta, y por que rol.
    expuestos: dict[str, dict[str, set]] = {}
    for nombre_rol, rol in config.roles.items():
        for herramienta, campos in rol.campos_permitidos.items():
            for campo in campos:
                hoja = _hoja(campo)
                if hoja in TEXTO_LIBRE_CONOCIDO:
                    expuestos.setdefault(herramienta, {}).setdefault(
                        hoja, set()).add(nombre_rol)

    print(f"\n{ruta.name}")
    if not expuestos:
        check(True, "ninguna lista blanca deja pasar un campo de texto libre")
        return

    for herramienta in sorted(expuestos):
        h = por_nombre.get(herramienta)
        if h is None:
            # Una lista blanca que nombra una herramienta inexistente es otro
            # problema, y lo caza el propio validador del esquema.
            continue
        declarados = set(h.campos_texto_libre or [])
        for campo, roles in sorted(expuestos[herramienta].items()):
            motivo = EXCEPCIONES.get((herramienta, campo))
            if motivo and campo not in declarados:
                #  Declarada: se informa para que se vea, pero no falla. Si
                #  alguien la quiere revisar, el motivo esta escrito al lado.
                print(f"  [exc]  {herramienta}: '{campo}' -- {motivo}")
                continue
            quienes = ", ".join(sorted(roles))
            check(
                campo in declarados,
                f"{herramienta}: '{campo}' lo ven [{quienes}] y esta en "
                f"campos_texto_libre",
            )


if __name__ == "__main__":
    print("=" * 70)
    print(" TEXTO LIBRE SIN REDACCION  --  la capa 2 de CLAUDE.md §5")
    print("=" * 70)

    yamls = [p for p in sorted((RAIZ / "tenants").glob("*.config.yaml"))
             if not p.name.startswith("tenant.config.example")]
    if not yamls:
        raise SystemExit("No hay ningun tenants/*.config.yaml que revisar.")
    for ruta in yamls:
        revisar(ruta)

    print("\n" + "=" * 70)
    if fallos:
        print(f" {len(fallos)} campo(s) de texto libre SIN redaccion:")
        for f in fallos:
            print(f"   - {f}")
        print("\n Cada uno llega al modelo tal cual lo escribio una persona.")
        print(" Agregalo a 'campos_texto_libre' de esa herramienta.")
        sys.exit(1)
    print(" Todo campo de texto libre que alguna lista blanca deja pasar")
    print(" tiene su redaccion declarada.")
