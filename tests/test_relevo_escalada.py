# -*- coding: utf-8 -*-
"""
El relevo: que quien toma un caso escalado sepa que le falta hacer.

    py -3.13 tests/test_relevo_escalada.py

POR QUE EXISTE
--------------
Medido contra produccion el 08/09/2026: de 52 conversaciones escaladas, las
52 llegaron a la bandeja con 'escalada_siguiente_paso' vacio. No era que el
campo fuera nuevo -- ya habia escaladas decididas por el evaluador despues de
crearlo, y tambien salieron vacias. Era que estaba declarado OPCIONAL con una
redaccion cautelosa ("Solo si escalar=true..."), la misma forma que este
proyecto ya habia descubierto que el modelo saltea (ver el comentario de
'caso_manual' en nucleo/seguimiento/escalamiento.py).

LO QUE ESTE TEST NO PUEDE HACER, Y HAY QUE SABERLO
--------------------------------------------------
Corre SIN RED: no llama al modelo. Asi que puede fijar que el esquema EXIJA
los dos campos, pero no que el modelo los complete con algo util. Obligatorio
garantiza que la clave exista, no que traiga contenido: con escalar=true y el
campo en "" el esquema queda conforme y el hueco es el mismo.

Esa mitad se mide en produccion, no aca:

    py -3.13 cli/reporte_escalamiento.py --tenant rapilink --dias 7

que ahora imprime 'con proximo paso' / 'sin proximo paso'. La linea base
contra la que comparar es 0 de 52 (0%). Y cada vez que ocurre, el motor lo
deja anotado en el log ('[escalamiento] escala sin siguiente_paso...').
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from nucleo.config import cargar_config                    # noqa: E402
from nucleo.seguimiento import escalamiento                # noqa: E402

fallos: list[str] = []

RELEVO = ("no_se_pudo_comprobar", "siguiente_paso")


def revisar(condicion: bool, descripcion: str, detalle: str = "") -> None:
    if condicion:
        print(f"  ok     {descripcion}")
    else:
        fallos.append(descripcion)
        print(f"  FALLA  {descripcion}" + (f"\n         {detalle}" if detalle else ""))


yamls = [p for p in sorted((RAIZ / "tenants").glob("*.config.yaml"))
         if not p.name.startswith("tenant.config.example")]
if not yamls:
    raise SystemExit("No hay ningun tenants/*.config.yaml con que probar.")
cfg = cargar_config(yamls[0])
rol = next(r for r in cfg.roles.values() if r.orientado_a == "cliente_final")


# --- 1. el esquema los EXIGE, con y sin manual de casos ---------------------
# Los dos caminos existen (ver _esquema_evaluacion): un tenant sin casos de
# manual arma una lista de requeridos distinta, y el arreglo tiene que valer
# para los dos. Si alguien agrega un campo obligatorio nuevo y rearma la
# lista a mano, es facil que uno de los dos ramales se quede sin estos.
print("el esquema del evaluador exige los dos campos del relevo")
esquema = escalamiento._esquema_evaluacion(cfg, rol)
requeridos = esquema["function"]["parameters"]["required"]
for campo in RELEVO:
    revisar(campo in requeridos, f"'{campo}' es obligatorio",
            f"requeridos: {requeridos}")

sin_manual = cargar_config(yamls[0])
sin_manual.manual.casos = {}
req_sin = escalamiento._esquema_evaluacion(sin_manual, rol)["function"]["parameters"]["required"]
for campo in RELEVO:
    revisar(campo in req_sin,
            f"'{campo}' sigue siendo obligatorio en un tenant sin manual de casos",
            f"requeridos: {req_sin}")


# --- 2. la redaccion no vuelve a ser la que el modelo saltea ----------------
# No es estilo: es la causa medida. 'caso_manual' fallaba por lo mismo y se
# arreglo cambiando la redaccion cautelosa por una directiva. Si alguien
# reescribe estas descripciones y les vuelve a poner "solo si...", el campo
# se apaga en silencio -- pasa el esquema, pasa el test de arriba, y vuelve a
# salir vacio en produccion.
print("\nla descripcion es directiva, no cautelosa")
propiedades = esquema["function"]["parameters"]["properties"]
for campo in RELEVO:
    desc = propiedades[campo]["description"]
    revisar(not re.match(r"^\s*solo si\b", desc, re.I),
            f"'{campo}' no empieza con 'Solo si...'", desc[:70])
    revisar("escalar=false" in desc,
            f"'{campo}' dice que hacer cuando NO se escala",
            "sin esa salida el modelo tiene que inventar algo en cada turno")


# --- 3. una escalada FORZADA no inventa el relevo ---------------------------
# Cuando escala una herramienta y no el evaluador, no hay de donde sacar el
# proximo paso. Rellenarlo seria repetir el error que se acaba de sacar de
# 'resumen': un texto que ocupa el renglon mas leido sin decir nada. Se
# comprueba sobre el fuente porque esa rama vive dentro de atender_turno(),
# que no se puede llamar sin base ni modelo.
print("\nla escalada forzada no fabrica un proximo paso")
api = (RAIZ / "nucleo" / "canales" / "api.py").read_text(encoding="utf-8")
revisar('setdefault("siguiente_paso"' not in api
        and "setdefault('siguiente_paso'" not in api,
        "api.py no rellena 'siguiente_paso' por su cuenta")
revisar("El evaluador no dejo resumen" not in api,
        "el resumen de relleno con jerga interna ya no existe",
        "'El evaluador no dejo resumen...' le hablaba a quien programo esto, "
        "no a quien abre el caso")


# --- 4. vacio se guarda como NULL, no como cadena vacia ---------------------
# Es lo que hace que "obligatorio" no ensucie la base: con escalar=false el
# modelo manda "", y la columna tiene que quedar NULL para que la pantalla y
# la metrica lo cuenten como ausente y no como un valor.
print("\nun campo vacio no se guarda como valor")
db = (RAIZ / "nucleo" / "persistencia" / "db.py").read_text(encoding="utf-8")
for campo in ("escalada_siguiente_paso", "escalada_no_comprobado"):
    patron = re.compile(campo + r"\s*=\s*coalesce\(\s*nullif\(", re.S)
    revisar(bool(patron.search(db)), f"'{campo}' se escribe con nullif",
            "sin nullif, un \"\" quedaria guardado y contaria como relevo escrito")


# --- 5. la metrica que mide la otra mitad existe ----------------------------
# La parte que este test NO puede cubrir (que el contenido sea util) se mide
# en produccion. Si alguien saca estas claves, la unica forma de saber si el
# arreglo sirvio se pierde.
print("\nla mitad que no se puede probar sin red, se mide")
revisar("con_siguiente_paso" in db and "sin_siguiente_paso" in db,
        "tasa_escalamiento() cuenta cuantas escaladas traen el relevo")
reporte = (RAIZ / "cli" / "reporte_escalamiento.py").read_text(encoding="utf-8")
revisar("sin proximo paso" in reporte,
        "el reporte lo imprime, no solo lo calcula")
esc = (RAIZ / "nucleo" / "seguimiento" / "escalamiento.py").read_text(encoding="utf-8")
revisar("escala sin" in esc,
        "el motor deja constancia en el log cuando escala sin relevo")


# --- 6. la bandeja: la alarma se reserva para lo que de verdad alarma -------
# Sin caso en el CRM, un proximo paso vacio significa que nadie lo tiene: eso
# es un cliente esperando a nadie. CON caso abierto y responsable asignado no
# lo es, y el triangulo salia igual -- en el 100% de los casos, porque el
# campo estaba siempre vacio. Una alarma que suena siempre deja de serlo.
print("\nla bandeja no alarma cuando el caso esta en una cola")
pantalla = (RAIZ / "django-crm" / "frontend" / "src" / "routes" / "(app)"
            / "conversaciones" / "[id]" / "+page.svelte").read_text(encoding="utf-8")
revisar("alerta: !tieneCaso" in pantalla,
        "la alarma de 'Qué falta' depende de que NO haya caso en el CRM",
        "si vuelve a ser 'alerta: true' fijo, suena en todas otra vez")
revisar("no está en ninguna cola" in pantalla,
        "y el caso sin CRM dice explicitamente que nadie lo tiene")


print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    raise SystemExit(1)
print("[OK] El relevo se exige, no se inventa, y lo que falta se mide.")
