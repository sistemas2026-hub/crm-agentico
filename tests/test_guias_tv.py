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

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

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


# =============================================================================
#  PASO 4 -- LA PANTALLA
# =============================================================================
#
# Se afirma sobre los ARCHIVOS porque no hay navegador en esta suite. Lo que
# se persigue no es como se ve: es que exista el camino completo, que la
# pantalla NO reimplemente las reglas, y que la asimetria de 'observaciones'
# siga en pie a los dos lados.

FRONT = RAIZ / "django-crm" / "frontend" / "src"


def texto(ruta) -> str:
    return ruta.read_text(encoding="utf-8") if ruta.exists() else ""


PUENTE = texto(FRONT / "lib" / "server" / "v2" / "guias-tv.js")
PAGINA = texto(FRONT / "routes" / "(app)" / "settings" / "guias-tv" / "+page.svelte")
SERVER = texto(FRONT / "routes" / "(app)" / "settings" / "guias-tv" / "+page.server.js")
INDICE = texto(FRONT / "routes" / "(app)" / "settings" / "+page.svelte")
HUB = texto(FRONT / "lib" / "server" / "v2" / "settings.js")


print("PASO4 12. el camino completo existe")
afirmar(bool(PUENTE) and bool(PAGINA) and bool(SERVER),
        "puente, pantalla y su modulo de servidor")
afirmar("/configuracion/guias-tv" in PUENTE,
        "el puente apunta al endpoint del motor")
afirmar("leerGuiasTV" in PUENTE and "guardarGuiasTV" in PUENTE,
        "con lectura y escritura")
afirmar("'/settings/guias-tv'" in INDICE,
        "y esta enlazada desde el indice -- una pantalla a la que nadie llega "
        "es una pantalla que no existe")


print("PASO4 13. la pantalla permite todo lo que hay que administrar")
for campo, que in (("g.marca", "marca"),
                   ("g.tipo_conexion", "tipo de conexion"),
                   ("g.instrucciones", "instrucciones"),
                   ("g.url_video", "URL del video"),
                   ("g.observaciones", "observaciones"),
                   ("g.activa", "activar/desactivar")):
    afirmar(f"bind:value={{{campo}}}" in PAGINA or f"bind:checked={{{campo}}}" in PAGINA,
            f"se puede editar la {que}")
afirmar("function agregar()" in PAGINA and "function quitar(" in PAGINA,
        "y crear y quitar guias")


print("PASO4 14. la pantalla NO reimplementa las reglas del schema")
# Reescribirlas en JavaScript daria dos lugares donde corregirlas y uno donde
# olvidarse -- y la copia del navegador se queda vieja sin que nada falle.
afirmar("problemas" not in PAGINA,
        "no hay un validador propio en la pantalla")
afirmar("instrucciones.trim()" not in PAGINA,
        "no reimplementa 'activa exige instrucciones'")
# La afirmacion que de verdad dice "no valida": el boton de guardar no se
# bloquea por un juicio propio de la pantalla. Contar cuantas veces aparece
# 'tdt' no lo decia -- fallaba con cuatro apariciones que eran dos de
# presentacion y dos de prevencion, ninguna una validacion.
afirmar("disabled={guardando}" in PAGINA,
        "el boton de guardar solo se bloquea mientras guarda, nunca porque la "
        "pantalla haya decidido que algo es invalido")
# Volver inalcanzable el error NO es duplicar una validacion: es no ofrecerlo.
afirmar("disabled={!data.can_edit || g.tipo_conexion === 'tdt'}" in PAGINA,
        "con TDT el campo de marca se deshabilita")
afirmar("guias[i].marca = ''" in PAGINA,
        "y se limpia, para que no falle por algo que ya no se ve en pantalla")
afirmar("err?.message" in SERVER,
        "el motivo del motor se muestra TAL CUAL: sus mensajes explican por "
        "que la regla existe, y resumirlos deja a quien edita sin saberlo")


print("PASO4 15. las dos de respaldo quedan identificadas")
afirmar("Guía general" in PAGINA and "Guía de TDT" in PAGINA,
        "la general y la de TDT se muestran aparte y con nombre propio")
afirmar("falta={!general}" in PAGINA and "falta={!tdt}" in PAGINA,
        "y se marcan cuando faltan -- sin la general, una marca sin guia "
        "propia deja al agente sin nada que entregar")
afirmar("tieneGeneral" in HUB and "tieneTdt" in HUB,
        "el indice de configuracion tambien avisa si falta alguna")


print("PASO4 16. la asimetria de 'observaciones', a los dos lados")
API = texto(RAIZ / "nucleo" / "canales" / "api.py")
admin = API[API.index('@app.get("/configuracion/guias-tv")'):][:1400]
afirmar("model_dump" in admin,
        "el endpoint de administracion serializa la guia entera, "
        "'observaciones' incluidas -- quien edita tiene que leerlas")
afirmar("observaciones" in PAGINA,
        "y la pantalla las muestra")
afirmar("observaciones" not in resolver(
            _Config([GuiaTV(marca="Samsung", instrucciones="x",
                            observaciones="nota interna")]),
            tipo_conexion="directo", marca="Samsung"),
        "y la resolucion que consume el agente sigue SIN entregarlas")


# =============================================================================
#  PASO 5 -- MARCAS DESCONOCIDAS
# =============================================================================
#
# Que una marca no tenga guia propia NO es un problema: la general resuelve la
# mayoria y el agente sigue atendiendo. Lo que si es un problema es que nadie
# se entere -- sin anotarla, cada cliente con esa marca recibe la general una
# y otra vez y la guia especifica no se escribe nunca.

from nucleo.seguridad.verificacion import Sesion                     # noqa: E402


def sesion_nueva():
    return Sesion(identificador_canal="573000000000")


print("PASO5 17. la marca sin guia queda anotada, tal cual la escribio")
ses = sesion_nueva()
r = motor._ejecutar_consulta_guia_tv(
    COMPLETO, {"tipo_conexion": "directo", "marca": "  Kalley  "}, ses)
afirmar(r.get("tipo_guia") == "general", "usa la general")
afirmar(ses.marcas_tv_sin_guia == ["Kalley"],
        "queda anotada EXACTAMENTE como la escribio el cliente -- quien cree "
        "la guia necesita ver como la nombra la gente, no como deberia "
        "llamarse")

# UN TIPEO NO ES UNA MARCA NUEVA, y esto casi se cuela como prueba.
#
# La primera version usaba 'Sansung' de ejemplo y fallo: el resolutor lo
# encuentra por parecido y entrega la guia de Samsung, que es la conducta que
# se decidio en el paso 2. Anotarlo como marca desconocida habria llenado la
# cola de trabajo de erratas -- y alguien habria terminado creando una guia
# 'Sansung' identica a la de Samsung.
ses = sesion_nueva()
r = motor._ejecutar_consulta_guia_tv(
    COMPLETO, {"tipo_conexion": "directo", "marca": "Sansung"}, ses)
afirmar(r.get("tipo_guia") == "especifica",
        "'Sansung' resuelve a la guia de Samsung por parecido")
afirmar(ses.marcas_tv_sin_guia == [],
        "y NO se anota como marca desconocida: es una errata, no un televisor "
        "que la empresa no conozca")


print("PASO5 18. no se anota lo que no corresponde")
ses = sesion_nueva()
motor._ejecutar_consulta_guia_tv(
    COMPLETO, {"tipo_conexion": "directo", "marca": "Samsung"}, ses)
afirmar(ses.marcas_tv_sin_guia == [],
        "una marca CON guia propia no se anota")

ses = sesion_nueva()
motor._ejecutar_consulta_guia_tv(COMPLETO, {"tipo_conexion": "tdt", "marca": "Kalley"}, ses)
afirmar(ses.marcas_tv_sin_guia == [],
        "con TDT tampoco: ahi la marca no interviene en la guia")

ses = sesion_nueva()
motor._ejecutar_consulta_guia_tv(COMPLETO, {"tipo_conexion": "directo"}, ses)
afirmar(ses.marcas_tv_sin_guia == [],
        "y sin marca no hay nada que anotar")

ses = sesion_nueva()
motor._ejecutar_consulta_guia_tv(
    _Config([SAMSUNG]), {"tipo_conexion": "directo", "marca": "Kalley"}, ses)
afirmar(ses.marcas_tv_sin_guia == [],
        "sin guia general tampoco se anota: no se llego a usar ninguna")


print("PASO5 19. no se repite dentro de la misma conversacion")
# El agente puede volver a preguntar, o reintentarse la sintonizacion. Sin
# esto, una sola conversacion llena la cola de trabajo con la misma marca.
ses = sesion_nueva()
for _ in range(4):
    motor._ejecutar_consulta_guia_tv(
        COMPLETO, {"tipo_conexion": "directo", "marca": "Kalley"}, ses)
afirmar(ses.marcas_tv_sin_guia == ["Kalley"],
        "cuatro consultas de la misma marca dejan UNA anotacion")
motor._ejecutar_consulta_guia_tv(
    COMPLETO, {"tipo_conexion": "directo", "marca": "Hyundai"}, ses)
afirmar(ses.marcas_tv_sin_guia == ["Kalley", "Hyundai"],
        "pero dos marcas distintas se anotan las dos")


print("PASO5 20. la marca desconocida NO escala por si sola")
# Es la regla que separa "falta un dato" de "no puedo atender". Sin ella, cada
# televisor de marca nueva terminaria en un humano.
ses = sesion_nueva()
r = motor._ejecutar_consulta_guia_tv(
    COMPLETO, {"tipo_conexion": "directo", "marca": "Kalley"}, ses)
afirmar(r.get("guia_encontrada") is True,
        "la resolucion sigue devolviendo una guia servible")
afirmar(r.get("instrucciones") == GENERAL["instrucciones"],
        "con el texto de la general")
afirmar("escala" not in (r.get("instruccion_interna") or "").lower(),
        "y su instruccion NO le dice al agente que escale")


print("PASO5 21. la migracion y la escritura")
MIG = next(RAIZ.joinpath("supabase").glob("*marcas_tv_desconocidas.sql"), None)
sql = MIG.read_text(encoding="utf-8") if MIG else ""
afirmar(bool(sql), "existe la migracion")
afirmar("enable row level security" in sql and "force row level security" in sql,
        "con RLS activado y forzado")
afirmar("asistente.org_actual()" in sql and "tenant_aislado" in sql,
        "y la misma politica de aislamiento por tenant que el resto")
for col, que in (("marca ", "la marca original"),
                 ("marca_normalizada", "la normalizada, APARTE"),
                 ("conversation_id", "de que conversacion salio"),
                 ("estado", "pendiente/atendida"),
                 ("creado_en", "la fecha")):
    afirmar(col in sql, f"guarda {que}")
afirmar("'pendiente', 'atendida'" in sql.replace('"', "'"),
        "y el estado esta acotado a esos dos valores")
afirmar("create unique index" in sql and "marca_normalizada, conversation_id" in sql,
        "una fila por marca y conversacion, no una por mencion")

FUENTE_DB = texto(RAIZ / "nucleo" / "persistencia" / "db.py")
afirmar("def registrar_marca_tv_desconocida" in FUENTE_DB,
        "existe la funcion que escribe")
afirmar("veces = asistente.marcas_tv_desconocidas.veces + 1" in FUENTE_DB,
        "y una mencion repetida SUBE el contador en vez de fallar -- es lo que "
        "permite priorizar cual guia escribir primero")
FUENTE_API = texto(RAIZ / "nucleo" / "canales" / "api.py")
afirmar("registrar_marca_tv_desconocida" in FUENTE_API,
        "y se llama despues de que exista conversation_id, no antes")


# =============================================================================
#  PASO 7 -- LA FICHA DEL ESCALAMIENTO
# =============================================================================
#
# La arma el CODIGO con lo que ya se resolvio. Marca, conexion y guia
# entregada se decidieron cuando se resolvio la guia; volver a pedirselos al
# modelo en prosa lo invita a recordarlos mal, y quien lee el ticket no tiene
# forma de saber cual de las dos versiones es cierta.

from nucleo.seguimiento import escalamiento                          # noqa: E402


def con_guia(**kw):
    """Una sesion con una guia ya resuelta."""
    ses = sesion_nueva()
    motor._ejecutar_consulta_guia_tv(COMPLETO, kw, ses)
    return ses


print("PASO7 22. lo que el codigo sabe con certeza")
ses = con_guia(tipo_conexion="directo", marca="Samsung")
f = escalamiento.ficha_tv(ses)
afirmar("coaxial entra directo" in f, "dice como esta conectado")
afirmar("Samsung" in f, "la marca del televisor")
afirmar("la de su marca" in f, "y que guia se le entrego")
afirmar("Se le mando el video" in f,
        "y si llevaba video -- la guia de Samsung tiene url cargada")
afirmar("NO aparecieron los canales" in f,
        "y que la siguio sin resultado: por eso escalo, y decirlo evita que "
        "el humano se la vuelva a mandar creyendo que no se probo")


print("PASO7 23. con TDT la marca no se lista")
# Ahi la marca no interviene en la guia. Mostrarla sugeriria que influyo.
ses = con_guia(tipo_conexion="tdt", marca="Kalley")
f = escalamiento.ficha_tv(ses)
afirmar("TDT" in f and "HDMI" in f, "dice que va por TDT y como llega al TV")
afirmar("Kalley" not in f, "y NO lista la marca")


print("PASO7 24. la marca sin guia propia se dice, y como es")
ses = con_guia(tipo_conexion="directo", marca="Kalley")
f = escalamiento.ficha_tv(ses)
afirmar("Kalley" in f, "la marca igual aparece")
afirmar("no tiene guia propia" in f,
        "y se aclara que se uso la general, que es lo que explica por que "
        "puede no haber funcionado")


print("PASO7 25. las tres que solo estan en la conversacion")
# No las puede saber ningun sistema: llegan del modelo en campos con nombre y
# el TEXTO lo escribe el codigo.
ses = con_guia(tipo_conexion="directo", marca="Samsung")
f = escalamiento.ficha_tv(ses, {"tv_cantidad_televisores": 3,
                                "tv_tiene_splitter": True,
                                "tv_cableado_del_cliente": True})
afirmar("Televisores conectados: 3" in f, "cuantos televisores")
afirmar("splitter" in f.lower(), "si hay splitter")
afirmar("lo modifico el cliente" in f, "y si el cableado lo toco el cliente")

# El maximo recomendado es 5. Pasarse degrada la señal en todos, y quien va a
# la casa tiene que saberlo antes de buscar la falla en otro lado.
f6 = escalamiento.ficha_tv(ses, {"tv_cantidad_televisores": 6})
afirmar("maximo recomendado de 5" in f6, "con 6 se avisa que pasa el maximo")
f5 = escalamiento.ficha_tv(ses, {"tv_cantidad_televisores": 5})
afirmar("maximo recomendado" not in f5, "con 5 no, porque 5 esta permitido")

# Un 'false' no se lista: "no tiene splitter" ocupa lugar y no es un hallazgo.
f0 = escalamiento.ficha_tv(ses, {"tv_tiene_splitter": False,
                                 "tv_cableado_del_cliente": False})
afirmar("splitter" not in f0.lower() and "cableado" not in f0.lower(),
        "lo que el cliente descarto no se lista")


print("PASO7 26. la evidencia se cuenta, no se interpreta")
# Esta etapa NO activa vision del modelo: solo dice que hay fotos para ir a
# buscarlas a la conversacion, donde ya se guardaban desde antes.
f = escalamiento.ficha_tv(con_guia(tipo_conexion="directo", marca="Samsung"),
                          None, evidencias=2)
afirmar("2 imagen(es)" in f, "dice cuantas imagenes mando el cliente")
afirmar("guardadas en la conversacion" in f, "y donde estan")
FUENTE_ESC = texto(RAIZ / "nucleo" / "seguimiento" / "escalamiento.py")
afirmar("image_url" not in FUENTE_ESC and "base64" not in FUENTE_ESC,
        "y NO se manda ninguna imagen al modelo: la vision es otra fase")


print("PASO7 27. sin television no hay ficha")
# Un bloque que dice "marca: --, conexion: --" ocupa lugar y no informa nada.
afirmar(escalamiento.ficha_tv(sesion_nueva()) == "",
        "una conversacion que nunca hablo de TV no genera ficha")
afirmar(escalamiento.ficha_tv(None) == "",
        "ni una sin sesion")
afirmar(escalamiento.ficha_tv(sesion_nueva(), {"resumen": "x"}) == "",
        "ni una evaluacion de otro tema")


print("PASO7 28. no se toco la logica de escalamiento")
# Los tres campos nuevos son OPCIONALES: no cambian cuando escala ni cuando
# no. Si fueran requeridos, una conversacion de facturacion sin televisor
# quedaria sin poder responder el esquema.
afirmar('"tv_cantidad_televisores"' in FUENTE_ESC,
        "los campos existen en el esquema")
i = FUENTE_ESC.index("requeridos = [")
for campo in ("tv_cantidad_televisores", "tv_tiene_splitter",
              "tv_cableado_del_cliente"):
    afirmar(campo not in FUENTE_ESC[i:i + 400],
            f"'{campo}' NO es requerido")
FUENTE_API2 = texto(RAIZ / "nucleo" / "canales" / "api.py")
afirmar("descripcion_ticket.strip() + chr(10) * 2 + ficha" in FUENTE_API2,
        "la ficha se SUMA al resumen, no lo reemplaza -- el relato y los "
        "datos duros cumplen funciones distintas")


print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es):")
    for f in fallos:
        print(f"  - {f}")
    raise SystemExit(1)
print("[OK] El modelo del catalogo impide las guias que no pueden existir.")
