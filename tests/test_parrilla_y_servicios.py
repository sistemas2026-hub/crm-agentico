# -*- coding: utf-8 -*-
"""
================================================================================
 SERVICIOS OFRECIDOS Y PARRILLA DE CANALES
================================================================================

Por que existe
--------------
Nace de una falla MEDIDA, no imaginada. El 08/09/2026, tres corridas seguidas
del simulador de WhatsApp: un prospecto pidio telefonia fija y el rol de
entrada contesto "solo tenemos planes de internet residencial y combos de
internet con television".

La respuesta era correcta. El problema es que el agente NO TENIA de donde
sacarla -- ni herramienta ni dato en su prompt-- asi que la improviso, y
acerto porque un ISP obviamente vende internet. El mismo prompt, en un tenant
que si venda VoIP, habria negado un servicio real con el mismo tono seguro.
Cero llamadas a herramientas en las tres corridas, confirmado en la traza.

Lo que se fija
--------------
1. LOS SERVICIOS SALEN DE LA CONFIG, y solo los activos. Apagar uno no es lo
   mismo que borrarlo: vuelve, y borrarlo pierde su descripcion.

2. SIN DATO CARGADO NO SE DEDUCE. Lista vacia devuelve una instruccion de
   escalar, nunca "no vendemos nada". Es la unica forma de que el proximo
   tenant no herede la adivinanza de este.

3. EL CODIGO RECONOCE EL CANAL, NO EL MODELO (PRD 12.5). El cliente escribe
   'discovery' y la parrilla dice 'DISCOVERY H&H'. Con comparacion exacta eso
   da "no lo tenemos" -- un NO falso sobre un canal que si esta, dicho con
   total seguridad. Mayusculas, tildes, espacios y nombre parcial tienen que
   resolver igual.

4. VARIAS COINCIDENCIAS NO SE RESUELVEN SOLAS. 'discovery' puede ser tres
   canales; se devuelven los tres y elige el cliente. Elegir por el es
   adivinar cual quiso.

5. CANAL AUSENTE NO OFRECE OTRO PLAN. La parrilla es UNA SOLA para todos los
   planes con TV (decision de negocio, 08/09/2026), asi que no existe un plan
   que si lo traiga. Ofrecerlo seria mentir.

6. LA PARRILLA VACIA TAMBIEN FALLA CERRADO, y es el caso mas peligroso de los
   dos: inventar un nombre de canal es mucho mas creible que inventar un
   servicio entero.

7. EL TENANT REAL LAS DECLARA BIEN -- que las herramientas existan, sean
   'interno', y el argumento 'canal' llegue por 'filtros_verificados'.

Corre SIN BASE DE DATOS y sin red: los ejecutores solo leen config que ya
esta en memoria del turno.

Uso
---
    py -3.13 tests/test_parrilla_y_servicios.py
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nucleo.config.schema import Canal, ServicioOfrecido                # noqa: E402
from nucleo.modelo import motor                                         # noqa: E402

fallos: list[str] = []


def afirmar(condicion: bool, que: str) -> None:
    print(f"  {'OK  ' if condicion else 'FALLA'}  {que}")
    if not condicion:
        fallos.append(que)


def _config(servicios=(), canales=()):
    """Los ejecutores solo tocan estos dos atributos -- no hace falta una
    TenantConfig entera, que exige medio archivo de campos sin relacion."""
    return SimpleNamespace(
        servicios_ofrecidos=[s if isinstance(s, ServicioOfrecido)
                             else ServicioOfrecido(**s) for s in servicios],
        parrilla_canales=[Canal(nombre=c) for c in canales],
    )


PARRILLA = ["DISCOVERY CHANNEL", "DISCOVERY H&H", "DISCOVERY TURBO",
            "ESPN", "ESPN 2", "CANAL CARACOL", "RCN", "NATIONAL GEOGRAPHIC"]


print("== 1-2. los servicios salen de la config, y sin config no se deducen ==")

c = _config(servicios=[{"nombre": "Internet residencial"},
                       {"nombre": "Television"},
                       {"nombre": "Telefonia fija", "activo": False}])
r = motor._ejecutar_consulta_servicios_ofrecidos(c)
nombres = [s["nombre"] for s in r["servicios"]]
afirmar(nombres == ["Internet residencial", "Television"],
        "devuelve solo los servicios activos, en orden")
afirmar("Telefonia fija" not in nombres,
        "un servicio apagado no se ofrece -- pero sigue en la config, no se borro")

vacio = motor._ejecutar_consulta_servicios_ofrecidos(_config())
afirmar(vacio["servicios"] == [],
        "sin servicios cargados no inventa ninguno")
afirmar("instruccion_interna" in vacio,
        "y NO se queda callado: manda una instruccion de que hacer")
afirmar("escala" in vacio["instruccion_interna"].lower(),
        "esa instruccion es escalar, no deducir -- es el bug del 08/09 cerrado")

# El caso que de verdad importa para multi-tenant: 'todos apagados' tiene que
# comportarse igual que 'lista vacia'. Si no, una empresa que apaga todo
# mientras revisa su catalogo recibiria "no vendemos nada" como respuesta.
todos_off = motor._ejecutar_consulta_servicios_ofrecidos(
    _config(servicios=[{"nombre": "Internet", "activo": False}]))
afirmar("instruccion_interna" in todos_off,
        "con TODOS los servicios apagados falla cerrado igual que con la lista vacia")


print("\n== 2b. el 'no' se responde, no se deduce de una lista ==")
# Medido el 08/09/2026: alguien pidio telefonia fija y recibio "por aca
# manejamos internet residencial y combos que incluyen television. ¿En que
# barrio estas?". Todo cierto, y sin decir NUNCA que lo que pidio no existe --
# el cliente tenia que deducir el "no" de una lista donde su servicio no
# aparecia. En otra corrida el mismo modelo si lo decia: dependia de que se
# acordara de mirar.
#
# Misma solucion que ya tenia la parrilla: el codigo compara y responde la
# pregunta; el modelo redacta (PRD 12.5).
c = _config(servicios=[{"nombre": "Internet residencial"},
                       {"nombre": "Television"}])

r = motor._ejecutar_consulta_servicios_ofrecidos(c, {"servicio": "telefonia fija"})
afirmar(r["se_ofrece"] is False,
        "un servicio que no esta se responde que NO esta, explicito")
afirmar("NO esta entre los servicios" in r["instruccion_interna"],
        "y la instruccion manda decirlo primero, antes de listar lo que si hay")
afirmar(len(r["servicios"]) == 2,
        "pero el catalogo viaja igual: el 'no' se acompaña con lo que si "
        "existe, no se deja al cliente sin nada")

afirmar(motor._ejecutar_consulta_servicios_ofrecidos(
            c, {"servicio": "internet"})["se_ofrece"] is True,
        "'internet' contenido en 'Internet residencial' cuenta como que si "
        "se ofrece -- es el mismo servicio dicho corto")
afirmar("se_ofrece" not in motor._ejecutar_consulta_servicios_ofrecidos(c, {}),
        "sin preguntar por uno concreto devuelve la lista y nada mas: no "
        "inventa un veredicto sobre algo que nadie pregunto")


print("\n== 3. el codigo reconoce el canal, no el modelo ==")

c = _config(canales=PARRILLA)
afirmar(motor._ejecutar_consulta_parrilla(c, {"canal": "ESPN"})["en_parrilla"],
        "nombre exacto encuentra")
afirmar(motor._ejecutar_consulta_parrilla(c, {"canal": "espn"})["en_parrilla"],
        "en minusculas tambien -- el cliente no escribe en mayusculas")
afirmar(motor._ejecutar_consulta_parrilla(c, {"canal": "  espn  "})["en_parrilla"],
        "con espacios de sobra tambien: _sin_tildes no recorta bordes, hay que hacerlo")
afirmar(motor._ejecutar_consulta_parrilla(
            c, {"canal": "national geographic"})["en_parrilla"],
        "sin importar mayusculas en un nombre largo")

r = motor._ejecutar_consulta_parrilla(c, {"canal": "discovery"})
afirmar(r["en_parrilla"],
        "'discovery' encuentra 'DISCOVERY H&H' -- el NO falso que este test viene a evitar")


print("\n== 4. varias coincidencias las resuelve el cliente, no el sistema ==")

afirmar(len(r["coincidencias"]) == 3,
        f"'discovery' devuelve los 3 canales que lo contienen, no uno solo "
        f"(devolvio {len(r['coincidencias'])})")
afirmar(all(x in r["coincidencias"] for x in
            ("DISCOVERY CHANNEL", "DISCOVERY H&H", "DISCOVERY TURBO")),
        "y son los tres correctos")
afirmar("elijas vos" in r["instruccion_interna"],
        "la instruccion prohibe elegir por el cliente")
afirmar("EXACTO" in r["instruccion_interna"],
        "y exige responder con el nombre tal cual figura en la parrilla, "
        "para que el cliente vea lo que de verdad hay")


print("\n== 4b. un PARECIDO no es una confirmacion ==")
# Medido el 08/09/2026 en el simulador: alguien pregunto por "wins sport +" y
# la parrilla solo trae "Win Sports". Son productos distintos -- el '+' es la
# senal premium-- y el asistente contesto "si, tenemos Win Sports". Ese cliente
# iba a contratar esperando algo que no esta incluido.
#
# La causa era que el codigo mezclaba dos tipos de coincidencia en una sola
# lista y devolvia en_parrilla=True para las dos.
c2 = _config(canales=PARRILLA + ["WIN SPORTS"])

r = motor._ejecutar_consulta_parrilla(c2, {"canal": "wins sport +"})
afirmar(r["en_parrilla"] is False,
        "'wins sport +' contra una parrilla que solo trae 'WIN SPORTS' NO se "
        "confirma: es otro producto, y decir que si lo manda a buscar algo "
        "que no va a encontrar")
afirmar(r.get("parecidos") == ["WIN SPORTS"],
        "pero el parecido se devuelve igual -- perderlo seria empujar al "
        "modelo a decir 'no tenemos nada' cuando hay algo cerca")
afirmar("NO le digas que si" in r["instruccion_interna"],
        "y la instruccion se lo prohibe con todas las letras")
afirmar("preguntale" in r["instruccion_interna"],
        "lo que corresponde es preguntar, no elegir por el cliente")

exacto = motor._ejecutar_consulta_parrilla(c2, {"canal": "win sports"})
afirmar(exacto["en_parrilla"] is True,
        "el nombre real, aunque venga en minusculas, SI se confirma -- la "
        "distincion es parecido/contenido, no exacto/inexacto")

contenido = motor._ejecutar_consulta_parrilla(c2, {"canal": "discovery"})
afirmar(contenido["en_parrilla"] is True,
        "y un nombre CONTENIDO en el real ('discovery' dentro de 'DISCOVERY "
        "H&H') tambien: ahi es el mismo canal escrito corto, no otro producto")


print("\n== 5. canal ausente no ofrece otro plan ==")

r = motor._ejecutar_consulta_parrilla(c, {"canal": "HBO"})
afirmar(r["en_parrilla"] is False,
        "un canal que no esta se responde que no esta")
afirmar(r["consultado"] == "HBO",
        "y queda registrado que fue lo que se consulto")
afirmar("no ofrecer" in r["instruccion_interna"] or
        "sin ofrecer otro plan" in r["instruccion_interna"],
        "la instruccion prohibe ofrecer otro plan: todos traen la misma parrilla")


print("\n== 6. la parrilla vacia falla cerrado ==")

v = motor._ejecutar_consulta_parrilla(_config(), {"canal": "ESPN"})
afirmar(v["parrilla_cargada"] is False,
        "sin parrilla cargada lo dice explicito")
afirmar("en_parrilla" not in v,
        "y NO responde que el canal no esta -- no tiene con que saberlo. "
        "Este es el punto entero: un 'no' sin datos es una mentira")
afirmar("inventes" in v["instruccion_interna"],
        "la instruccion se lo prohibe con todas las letras")

entera = motor._ejecutar_consulta_parrilla(c, {})
afirmar(entera["total"] == len(PARRILLA) and entera["canales"] == PARRILLA,
        "sin argumento devuelve la parrilla entera -- para 'que canales tienen'")


print("\n== 7. el tenant real declara las dos herramientas ==")

import yaml, io                                                          # noqa: E402
from nucleo.config.schema import TenantConfig                            # noqa: E402

real = TenantConfig(**yaml.safe_load(
    io.open("tenants/rapilink.config.yaml", encoding="utf-8")))
hs = {h.nombre: h for h in real.herramientas}

afirmar("consultar_servicios_ofrecidos" in hs and "consultar_parrilla_canales" in hs,
        "las dos herramientas existen en el catalogo del tenant")
afirmar(hs["consultar_servicios_ofrecidos"].consulta_servicios_ofrecidos is True
        and hs["consultar_parrilla_canales"].consulta_parrilla is True,
        "cada una lleva su marcador, que es lo que el motor despacha")
afirmar(all(hs[n].tipo == "interno" for n in
            ("consultar_servicios_ofrecidos", "consultar_parrilla_canales")),
        "las dos son 'interno': leen config, no salen a la red")
afirmar(all(hs[n].solo_lectura for n in
            ("consultar_servicios_ofrecidos", "consultar_parrilla_canales")),
        "y solo de lectura -- ninguna escribe nada")
afirmar("canal" in hs["consultar_parrilla_canales"].filtros_verificados,
        "el argumento 'canal' viaja por filtros_verificados, el mismo camino "
        "que 'localidad' en consultar_planes_venta")
afirmar("ventas" in real.roles and
        "consultar_parrilla_canales" in real.roles["ventas"].puede_consultar,
        "ventas las tiene en su catalogo -- es quien atiende el pedido de un "
        "servicio, sea prospecto o cliente actual (decision de negocio 08/09/2026)")
afirmar(real.parrilla_canales == [],
        "la parrilla se siembra VACIA: se carga por Excel, no a mano en el YAML")
afirmar([s.nombre for s in real.servicios_ofrecidos if s.activo] != [],
        "los servicios si vienen sembrados, con lo que la config ya daba por cierto")


print("\n== 8. la carga por Excel ==")
# 'canales_desde_excel' es pura -- recibe bytes-- asi que se prueba con un
# .xlsx armado aca mismo, sin subir nada ni tocar la base.
from openpyxl import Workbook                                            # noqa: E402
from nucleo.config import editor                                         # noqa: E402


def _xlsx(filas):
    libro = Workbook()
    hoja = libro.active
    for f in filas:
        hoja.append([f])
    buf = io.BytesIO()
    libro.save(buf)
    return buf.getvalue()


canales, descartados = editor.canales_desde_excel(_xlsx(
    ["DISCOVERY CHANNEL", "ESPN", "  ESPN  ", "espn", "RCN",
     None, "", "Canal Caracol", "CANAL CARACOL"]))

afirmar(canales == ["DISCOVERY CHANNEL", "ESPN", "RCN", "Canal Caracol"],
        "lee la primera columna y respeta el orden del archivo -- ese orden es "
        "el criterio de la empresa, alfabetizarlo se lo esconde")
afirmar(descartados == ["ESPN", "espn", "CANAL CARACOL"],
        "los duplicados se descartan comparando SIN mayusculas ni tildes: es "
        "como los compara el buscador, y deducirlo distinto aca dejaria "
        "entrar dos filas que el buscador considera el mismo canal")
afirmar(descartados != [],
        "y se devuelven, no se descartan en silencio -- quien sube el archivo "
        "tiene que ver que falto, o cree que cargo mas de lo que cargo")
afirmar(None not in canales and "" not in canales,
        "las filas vacias del medio no rompen ni entran como canal")

for entrada, que in ((_xlsx([None, ""]), "un archivo sin ningun canal"),
                     (b"no soy un excel", "un archivo que no es Excel")):
    try:
        editor.canales_desde_excel(entrada)
        afirmar(False, f"{que} tiene que ser rechazado")
    except editor.ErrorEdicion:
        afirmar(True, f"{que} se rechaza con un mensaje explicable, no una traza")
    except Exception as e:
        afirmar(False, f"{que} revento con {type(e).__name__} en vez de ErrorEdicion")

# La mutacion REEMPLAZA: no existe "agregar un canal suelto". Mezclar con lo
# anterior deja canales de una version vieja que nadie recuerda haber subido.
doc = {"parrilla_canales": [{"nombre": "CANAL VIEJO"}]}
editor._mutar_parrilla_canales(doc, ["ESPN", "RCN"])
afirmar([c["nombre"] for c in doc["parrilla_canales"]] == ["ESPN", "RCN"],
        "subir un Excel reemplaza la parrilla entera, no la mezcla con la anterior")

doc = {}
editor._mutar_servicios_ofrecidos(doc, [
    {"nombre": " Internet ", "activo": True, "descripcion": " fibra "},
    {"nombre": "", "activo": True},
    {"nombre": "Telefonia", "activo": False}])
afirmar([s["nombre"] for s in doc["servicios_ofrecidos"]] == ["Internet", "Telefonia"],
        "los servicios se limpian de espacios y se ignora una fila sin nombre")
afirmar(doc["servicios_ofrecidos"][1]["activo"] is False,
        "un servicio apagado se CONSERVA apagado, no se borra: vuelve, y "
        "borrarlo pierde la descripcion que alguien redacto")


print("\n== 9. el cliente sin TV: que 'ventas' pueda mirarlo, y solo eso ==")
# La parrilla es unica, pero un cliente cuyo plan NO incluye television no ve
# el canal aunque este cargado. Decirle "si, lo tenemos" y que despues no lo
# encuentre es peor que no responder, asi que 'ventas' necesita poder mirar SU
# plan. Eso es acceso nuevo a datos de cliente y por eso se fija aca.
v = real.roles["ventas"]
afirmar("consultar_mi_servicio" in v.puede_consultar
        and "consultar_plan_tv" in v.puede_consultar,
        "ventas puede mirar el plan del cliente y si ese plan incluye TV")
afirmar(v.campos_permitidos.get("consultar_mi_servicio") == ["plan_internet"],
        "y de su ficha ve UN SOLO campo: el plan. Nada mas de esa ficha le "
        "hace falta, y la lista blanca es lo unico que lo impide")

# EL PUNTO DE ESTA SECCION.
#
# El gate de identidad del ROL no protege esto: 'ventas' declara
# exige_verificacion=false -- un prospecto no puede verificarse, y forzarlo
# rompio el rol una vez (19/08/2026)-- asi que su nivel exigido es 0 y el gate
# nunca frena nada.
#
# Lo que protege es la HERRAMIENTA: consultar_mi_servicio exige que
# 'id_servicio' llegue inyectado desde la sesion, y sin verificar no hay
# id_cliente que inyectar, asi que el motor corta con FaltaIdentidadEnSesion.
# Si alguien saca esa linea, 'ventas' pasa a leer la ficha de cualquiera sin
# pedir nada -- y el gate del rol no lo va a detener.
h = {x.nombre: x for x in real.herramientas}
afirmar(h["consultar_mi_servicio"].inyectados_obligatorios == ["id_servicio"],
        "consultar_mi_servicio EXIGE id_servicio inyectado -- es la unica "
        "barrera real: el gate del rol vale 0 para ventas (exige_verificacion "
        "false) y no frena nada")
afirmar(v.exige_verificacion is False,
        "y se deja escrito que ventas NO exige verificacion a nivel rol, para "
        "que nadie 'arregle' la barrera en el lugar equivocado")
afirmar("id_servicio" in h["consultar_mi_servicio"].inyectar_sesion,
        "el id sale de la SESION, nunca de lo que el modelo proponga")

afirmar("ventas" in h["consultar_plan_tv"].roles_permitidos,
        "consultar_plan_tv admite a ventas")
afirmar(h["consultar_plan_tv"].endpoint == h["consultar_plan_detalle"].endpoint,
        "y no amplia a que datos llega: es el MISMO endpoint que "
        "consultar_plan_detalle, que ventas ya podia llamar")


print("\n== 10. una recarga del YAML no puede borrar lo que se subio ==")
# El YAML trae 'parrilla_canales: []' a proposito -- los canales se cargan
# desde la pantalla, no a mano. Si estas secciones no estan declaradas como
# EDITABLES POR LA INTERFAZ, la primera recarga del archivo las pisa con la
# lista vacia y se pierden cientos de canales sin que nadie se entere.
#
# No es hipotetico y por eso esta seccion existe: paso el 23/08/2026 (6 planes
# curados y 128 localidades) y otra vez el 05/09/2026 (la tarifa de DeepSeek y
# el endpoint de saldo). Las dos veces por el mismo motivo -- alguien agrego un
# mutador y no agrego la seccion a esta lista.
for seccion in ("servicios_ofrecidos", "parrilla_canales"):
    afirmar(seccion in editor.SECCIONES_EDITABLES,
            f"'{seccion}' esta en SECCIONES_EDITABLES -- sin eso, cargar el "
            f"YAML encima de la base la borra en silencio")

afirmar("parrilla_canales" in editor.SECCIONES_EDITABLES
        and real.parrilla_canales == [],
        "y el caso es justamente ese: el YAML la trae vacia, asi que una "
        "recarga desprotegida no dejaria rastro de lo que se perdio")


print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es):")
    for f in fallos:
        print(f"  - {f}")
    raise SystemExit(1)
print("[OK] Los servicios y la parrilla salen de la config, y sin datos no se inventan.")
