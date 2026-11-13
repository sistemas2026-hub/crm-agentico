# -*- coding: utf-8 -*-
"""
================================================================================
 UN AGENTE EN DETALLE  --  13/11/2026
================================================================================
    py -3.13 tests/test_agentes_detalle.py

Lo que la pagina de cada agente necesita del motor:

  1. El historial de un rol, version a version, dicho en palabras
     (nucleo/config/cambios_de_rol.py) -- logica pura.
  2. El editor: pausar, restaurar, y el nombre y resumen para personas.
  3. La ruta HTTP: /agentes manda lo nuevo -- en especial 'aprobacion_humana',
     el freno REAL, que la pantalla no recibia y por eso decia "pide
     confirmacion" de algo que nada frena --, y los endpoints nuevos.
  4. EL TURNO de un agente en pausa: no llama al modelo, avisa UNA vez y deja
     la conversacion marcada para una persona. Corre atender_turno() real con
     el mundo exterior sustituido (mismo arnes que tests/test_pausa_escalada.py).
================================================================================
"""
from __future__ import annotations

import copy
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.canales import api                                      # noqa: E402
from nucleo.config import cambios_de_rol, editor                    # noqa: E402
from nucleo.config import cargar_config                             # noqa: E402
from nucleo.config.schema import TenantConfig                       # noqa: E402
from nucleo.persistencia import agentes as datos_agentes            # noqa: E402

fallos: list[str] = []


def comprobar(condicion: bool, que: str) -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}")
    if not condicion:
        fallos.append(que)


YAML = RAIZ / "tenants" / "rapilink.config.yaml"
CONFIG = cargar_config(YAML)
DOC = yaml.safe_load(YAML.read_text(encoding="utf-8"))

# =============================================================================
print("\n== 1. el historial de un rol, en palabras ==")
base = {"descripcion": "hola\nmundo", "puede_consultar": ["a", "b"],
        "campos_permitidos": {"a": ["x"], "b": ["y"]}, "atiende": "saldo"}
comprobar(cambios_de_rol.describir(base, copy.deepcopy(base)) is None,
          "un rol igual no es un cambio")

nuevo = copy.deepcopy(base)
nuevo["puede_consultar"] = ["a", "c"]
nuevo["campos_permitidos"] = {"a": ["x", "z"], "c": ["w"]}
nuevo["descripcion"] = "hola\nmundo\ny algo mas"
nuevo["pausado"] = True
c = cambios_de_rol.describir(base, nuevo)
texto = " | ".join(c["resumen"])
comprobar("Se agregó la herramienta c." in c["resumen"], f"dice la herramienta agregada ({texto})")
comprobar("Se quitó la herramienta b." in c["resumen"], "dice la herramienta quitada")
comprobar(any(f.startswith("En a: ve 1 campo más") for f in c["resumen"]),
          "dice que ve un campo mas en una herramienta que sigue")
comprobar(not any(f.startswith("En c:") or f.startswith("En b:") for f in c["resumen"]),
          "no repite los campos de una herramienta que entro o salio")
comprobar("Se pausó." in c["resumen"], "la pausa se dice en palabras")
comprobar(c["diff_instrucciones"] and "+y algo mas" in c["diff_instrucciones"],
          "el cambio de instrucciones trae su diff")

comprobar(cambios_de_rol.describir(None, base)["tipo"] == "creado", "de nada a algo: creado")
comprobar(cambios_de_rol.describir(base, None)["tipo"] == "borrado", "de algo a nada: borrado")

t = lambda d: datetime(2026, 11, d, tzinfo=timezone.utc)                         # noqa: E731
versiones = [{"version": 5, "creado_en": t(5), "rol": nuevo},
             {"version": 4, "creado_en": t(4), "rol": base},
             {"version": 3, "creado_en": t(3), "rol": base},
             {"version": 2, "creado_en": t(2), "rol": None}]
h = cambios_de_rol.historial(versiones)
comprobar([x["version"] for x in h] == [5, 3],
          f"solo las versiones en que ESTE rol cambio (dio {[x['version'] for x in h]})")
comprobar(h[1]["tipo"] == "creado" and h[1]["restaurable"] is True,
          "la version que lo creo es restaurable")
comprobar(cambios_de_rol.historial(versiones[:1]) == [],
          "la version mas vieja no se compara con nada: no se inventa 'se creo'")

# =============================================================================
print("\n== 2. el editor: pausar, restaurar, nombre y resumen ==")
doc = copy.deepcopy(DOC)
editor._mutar_pausa(doc, "soporte", True)
comprobar(doc["roles"]["soporte"].get("pausado") is True, "pausar pone la marca")
TenantConfig.model_validate(doc)
comprobar(True, "la config pausada sigue siendo valida")
editor._mutar_pausa(doc, "soporte", False)
comprobar("pausado" not in doc["roles"]["soporte"],
          "reanudar QUITA la clave: queda igual a un agente que nunca se pauso")
try:
    editor._mutar_pausa(doc, "no_existe", True)
    comprobar(False, "pausar un agente que no existe se rechaza")
except editor.ErrorEdicion:
    comprobar(True, "pausar un agente que no existe se rechaza")

doc = copy.deepcopy(DOC)
viejo = copy.deepcopy(doc["roles"]["soporte"])
viejo["descripcion"] = "version vieja"
editor._mutar_pausa(doc, "soporte", True)
editor._mutar_restaurar(doc, "soporte", viejo)
comprobar(doc["roles"]["soporte"]["descripcion"] == "version vieja", "restaurar trae el rol de esa version")
comprobar(doc["roles"]["soporte"].get("pausado") is True,
          "restaurar NO reanuda: la pausa es una decision aparte")
try:
    editor._mutar_restaurar(doc, "no_existe", viejo)
    comprobar(False, "restaurar no recrea un agente borrado")
except editor.ErrorEdicion:
    comprobar(True, "restaurar no recrea un agente borrado")

doc = copy.deepcopy(DOC)
editor._aplicar_extras(doc, "soporte", {"nombre_visible": "  Soporte   (equipo) ",
                                        "resumen": "Atiende\nal equipo"})
comprobar(doc["roles"]["soporte"]["nombre_visible"] == "Soporte (equipo)",
          "el nombre visible se guarda con los espacios normalizados")
comprobar(doc["roles"]["soporte"]["resumen"] == "Atiende al equipo", "el resumen va en una linea")
editor._aplicar_extras(doc, "soporte", {"atiende": "x"})
comprobar(doc["roles"]["soporte"]["nombre_visible"] == "Soporte (equipo)",
          "un formulario que no manda el nombre no lo borra")
TenantConfig.model_validate(doc)
comprobar(True, "la config con nombre y resumen sigue siendo valida")

# =============================================================================
print("\n== 3. la ruta HTTP ==")
api._config_de = lambda tenant: CONFIG
api._TOKEN_SERVICIO = None
api.olvidar_config = lambda tenant: None
http = api.app.test_client()

r = http.get("/agentes?tenant=rapilink").get_json()
soporte = next(a for a in r["agentes"] if a["nombre"] == "soporte")
for clave in ("nombre_visible", "resumen", "pausado"):
    comprobar(clave in soporte, f"/agentes manda '{clave}'")
escrituras = [x for x in soporte["herramientas"] if x["solo_lectura"] is False]
comprobar(escrituras and all("aprobacion_humana" in x and "irreversible" in x and "critica" in x
                             for x in escrituras),
          "cada herramienta manda aprobacion_humana, irreversible y critica")
reales = {x.name if hasattr(x, "name") else x.nombre: x for x in CONFIG.herramientas}
comprobar(all(x["aprobacion_humana"] == reales[x["nombre"]].aprobacion_humana for x in escrituras),
          "aprobacion_humana es la de la config, no otra cosa")

llamadas = []
editor_pausar = editor.pausar_rol
editor.pausar_rol = lambda tenant, nombre, pausado: (llamadas.append((nombre, pausado)), CONFIG)[1]
r = http.put("/agentes/soporte/pausa", json={"tenant": "rapilink", "pausado": True})
comprobar(r.status_code == 200 and llamadas == [("soporte", True)], "PUT pausa llega al editor")
r = http.put("/agentes/soporte/pausa", json={"tenant": "rapilink", "pausado": "si"})
comprobar(r.status_code == 400, "una pausa que no es true/false se rechaza")
editor.pausar_rol = editor_pausar

orig_versiones = datos_agentes.versiones_del_rol
datos_agentes.versiones_del_rol = lambda tenant, rol, limite=200: versiones
r = http.get("/agentes/soporte/historial?tenant=rapilink").get_json()
comprobar([c["version"] for c in r["cambios"]] == [5, 3], "el historial llega por HTTP")
comprobar(r["cambios"][0]["actual"] is True and r["cambios"][1]["actual"] is False,
          "la mas nueva se marca como la actual")
datos_agentes.versiones_del_rol = orig_versiones

orig_rol_en, orig_restaurar = datos_agentes.rol_en_version, editor.restaurar_rol
datos_agentes.rol_en_version = lambda tenant, rol, version: None
r = http.post("/agentes/soporte/restaurar", json={"tenant": "rapilink", "version": 2})
comprobar(r.status_code == 404, "restaurar una version en que el agente no existia: 404")
r = http.post("/agentes/soporte/restaurar", json={"tenant": "rapilink", "version": "2"})
comprobar(r.status_code == 400, "una version que no es numero se rechaza")
restaurados = []
datos_agentes.rol_en_version = lambda tenant, rol, version: {"descripcion": "x"}
editor.restaurar_rol = lambda tenant, nombre, anterior: (restaurados.append(anterior), CONFIG)[1]
r = http.post("/agentes/soporte/restaurar", json={"tenant": "rapilink", "version": 4})
comprobar(r.status_code == 200 and restaurados == [{"descripcion": "x"}],
          "restaurar pasa el rol de esa version al editor")
datos_agentes.rol_en_version, editor.restaurar_rol = orig_rol_en, orig_restaurar

orig_desempeno = datos_agentes.desempeno
datos_agentes.desempeno = lambda tenant, dias: {"dias": dias, "agentes": {
    "soporte": {"conversaciones": 10, "escaladas": 2, "por_motivo": {"x": 2},
                "herramientas": {"consultar_cliente": {"usos": 3, "fallos": 0}},
                "resueltas_sin_persona": 8, "tasa_sin_persona": 0.8}}}
r = http.get("/reportes/agentes?tenant=rapilink&dias=30").get_json()
sop = r["agentes"]["soporte"]
comprobar("consultar_cliente" not in sop["sin_uso"] and len(sop["sin_uso"]) > 0,
          "sin_uso: las que TIENE y no uso, sin la que si uso")
comprobar("cliente_final" not in r["agentes"],
          "un agente sin conversaciones no aparece: no se afirma 'sin uso' sin datos")
datos_agentes.desempeno = orig_desempeno

comprobar(datos_agentes.ultimos_digitos("whatsapp:+57 300 123 4821") == "•••• 4821",
          "la bitacora muestra solo los ultimos cuatro digitos")
comprobar(datos_agentes.ultimos_digitos(None) == "—", "sin contacto, un guion")

# =============================================================================
print("\n== 4. el turno de un agente en pausa ==")


def turno(config, mensaje="no tengo internet"):
    """atender_turno() real con la base, el modelo y el evaluador sustituidos."""
    p, esc, mot = api.persistencia, api.escalamiento, api.motor
    anotado = {"modelo": False, "guardados": [], "estado_escalada": []}

    def _responder(*a, **k):
        anotado["modelo"] = True
        return ("respuesta del bot", [], [])

    postizos = {
        p: {"estado_de_conversacion_abierta": lambda *a, **k: None,
            "control_de_conversacion_abierta": lambda *a, **k: None,
            "atendida_por_humano": lambda *a, **k: False,
            "registrar_mensaje": lambda t_, c_, i_, r_, rol_, txt_, *a, **k:
                (anotado["guardados"].append((rol_, txt_)), ("conv-1", "msg-1"))[1],
            "registrar_estado_escalada": lambda *a, **k: anotado["estado_escalada"].append((a, k)),
            "conversacion_vencida": lambda *a, **k: False,
            "identificar_cliente": lambda *a, **k: None,
            "resumen_anterior": lambda *a, **k: None,
            "historial_para_el_modelo": lambda *a, **k: [],
            "registrar_turno": lambda *a, **k: None,
            "actualizar_contenido_mensaje": lambda *a, **k: None,
            "caso_de_conversacion": lambda *a, **k: None,
            "ticket_operativo_de": lambda *a, **k: None,
            "cerrar_conversacion": lambda *a, **k: None,
            "guardar_resumen": lambda *a, **k: None,
            "marcar_caso": lambda *a, **k: None,
            "completar_medicion": lambda *a, **k: None,
            "guardar_estado_routing": lambda *a, **k: None,
            "registrar_marca_tv_desconocida": lambda *a, **k: None},
        esc: {"evaluar": lambda *a, **k: {}},
        mot: {"responder": _responder},
        api: {"_resolver_verificacion_pendiente": lambda *a, **k: None,
              "_hay_verificacion_pendiente": lambda *a, **k: False},
        api.consumo: {"estado_del_gasto": lambda *a, **k:
                      {"accion": "seguir", "gastado": 0, "tope": 0, "porcentaje": 0.0}},
    }
    orig = {(m, n): getattr(m, n) for m, d in postizos.items() for n in d if hasattr(m, n)}
    for m, d in postizos.items():
        for n, f in d.items():
            if hasattr(m, n):
                setattr(m, n, f)
    try:
        r = api.atender_turno(config, "rapilink", "cliente_final", "573000004821", mensaje, "api")
    finally:
        for (m, n), f in orig.items():
            setattr(m, n, f)
    return r, anotado


doc = copy.deepcopy(DOC)
doc["roles"]["cliente_final"]["pausado"] = True
PAUSADA = TenantConfig.model_validate(doc)

api._sesiones.clear()
r, a = turno(PAUSADA)
comprobar(not a["modelo"], "un agente en pausa NO llama al modelo")
comprobar(r.get("pausada") is True and "persona del equipo" in (r.get("respuesta") or ""),
          f"le dice al cliente que lo atiende una persona (dio {r.get('respuesta')!r})")
comprobar(any(rol_ == "assistant" for rol_, _ in a["guardados"]), "el aviso queda guardado")
comprobar(a["estado_escalada"] and a["estado_escalada"][0][1].get("necesita_atencion") is True,
          "la conversacion queda marcada para una persona")
comprobar("agente en pausa" in str(a["estado_escalada"][0][0]),
          "y el detalle dice por que: agente en pausa")

r2, a2 = turno(PAUSADA, "hola?? sigue sin servicio")
comprobar(not a2["modelo"], "el segundo turno tampoco llama al modelo")
comprobar(r2.get("respuesta") == "" and r2.get("pausada") is True,
          "el aviso NO se repite: el segundo turno queda en silencio")
comprobar(not any(rol_ == "assistant" for rol_, _ in a2["guardados"]),
          "y no se guarda un segundo aviso")
comprobar(a2["estado_escalada"], "pero la conversacion sigue marcada para una persona")

api._sesiones.clear()
r3, a3 = turno(CONFIG)
comprobar(a3["modelo"], "sin pausa, el mismo turno SI llama al modelo (la prueba ve la diferencia)")

print()
if fallos:
    print(f"FALLARON {len(fallos)}:")
    for f in fallos:
        print("  -", f)
    sys.exit(1)
print("todo en verde")
