# -*- coding: utf-8 -*-
"""
================================================================================
 NO LEIDOS Y ETIQUETAS DEL EQUIPO  --  la proyeccion y las rutas, sin base
================================================================================

    py -3.13 tests/test_no_leidos_y_etiquetas.py

Corre sin base y sin red: se sustituye la persistencia y la config, y se piden
las rutas con el cliente de prueba de Flask. Lo que se mide contra PostgreSQL
real (la cuenta, la marca, el chat, el aislamiento) esta en
tests/test_no_leidos_y_etiquetas_base.py.

POR QUE EXISTE  (11/11/2026)
----------------------------
Dos funciones nuevas de la Bandeja, como WhatsApp Business:

  NO LEIDOS  la fila de un chat dice cuantos mensajes del cliente nadie del
             equipo abrio. Lo que se protege aca: que la fila AGRUPADA sume los
             de todas sus abiertas (el cliente puede haber escrito en la que no
             es la urgente), y que la ruta de «no leida» no tome un "false" en
             texto por verdadero.

  ETIQUETAS  las que pone una persona al chat. Lo que se protege: que una
             clave fuera del catalogo de la empresa se rechace ENTERA antes de
             escribir (fail-closed), que una borrada del catalogo no se muestre
             ni en la cola ni en la conversacion, y que el autor salga del
             cuerpo que arma el proxy y no se pueda omitir.
================================================================================
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.canales import api                                      # noqa: E402
from nucleo.config import cargar_config                             # noqa: E402
from nucleo.config import editor                                    # noqa: E402
from nucleo.relevo import proyeccion                                # noqa: E402

fallos: list[str] = []


def comprobar(condicion: bool, que: str, detalle: str = "") -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}"
          + (f"\n          {detalle}" if detalle and not condicion else ""))
    if not condicion:
        fallos.append(que)


ahora = datetime.now(timezone.utc)
CID = "3f2b8c1e-5d7a-4e9b-8c2d-1a6f0e4b7c9d"
ANA = {"autor": "Ana Perez", "autor_usuario_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7"}

yamls = [p for p in sorted((RAIZ / "tenants").glob("*.config.yaml"))
         if not p.name.startswith("tenant.config.example")]
_doc = cargar_config(yamls[0]).model_dump(mode="json")
_doc.setdefault("conversaciones", {})["etiquetas_del_equipo"] = [
    {"clave": "vip", "nombre": "Cliente VIP", "color": "violeta"},
    {"clave": "moroso", "nombre": "Moroso", "color": "rojo"},
]
CFG = editor._validar("prueba", _doc)


def fila(id_, numero, *, estado="abierta", no_leidos=0, etiquetas=(), dias=1, **extra):
    return {"id": id_, "canal": "whatsapp", "usuario_externo": numero, "estado": estado,
            "control": "humano", "no_leidos": no_leidos, "etiquetas_del_equipo": list(etiquetas),
            "ultimo_mensaje_en": ahora - timedelta(days=dias), "canal_operativo": True, **extra}


print()
print("=" * 78)
print("  NO LEIDOS Y ETIQUETAS DEL EQUIPO")
print("=" * 78)

# ---------------------------------------------------------------------------
print("\n== A. la fila de un chat suma los no leidos de sus abiertas ==")
filas = [
    # Un chat: una cerrada (cuenta 0 desde la consulta), dos abiertas.
    fila("c1", "573001", estado="cerrada", no_leidos=0, dias=5),
    fila("c2", "573001", no_leidos=2, dias=3, escalada_a_humano=True, banda=2),
    fila("c3", "573001", no_leidos=3, dias=1),
    # Otro chat, una sola.
    fila("d1", "573002", no_leidos=1),
    # Una cerrada que por error trajera no leidos: el chat no la suma.
    fila("e1", "573003", estado="cerrada", no_leidos=4),
    # Sin numero: no es un chat, queda suelta con lo suyo.
    fila("f1", "", no_leidos=7),
]
for f in filas:
    f.setdefault("banda", None)
nacimientos = {f["id"]: ahora - timedelta(days=i) for i, f in enumerate(reversed(filas))}
agrupadas = {f["id"]: f for f in proyeccion.agrupar_por_numero([dict(f) for f in filas], nacimientos)}
chat = next(f for f in agrupadas.values() if "c3" in f.get("ids", []))
comprobar(chat["no_leidos"] == 5,
          f"el chat de dos abiertas cuenta 2 + 3 = 5, no solo los de la urgente ({chat['no_leidos']})")
comprobar(next(f for f in agrupadas.values() if "d1" in f.get("ids", []))["no_leidos"] == 1,
          "un chat de una sola abierta cuenta lo suyo")
comprobar(next(f for f in agrupadas.values() if "e1" in f.get("ids", []))["no_leidos"] == 0,
          "las cerradas no suman, aunque la fila traiga algo")
comprobar(agrupadas["f1"]["no_leidos"] == 7, "una fila suelta (sin numero) conserva su cuenta")

filas_et = [fila("g1", "573004", estado="cerrada", etiquetas=["vip"], dias=4),
            fila("g2", "573004", etiquetas=["vip"], dias=1)]
for f in filas_et:
    f["banda"] = None
chat_g = proyeccion.agrupar_por_numero(filas_et, {"g1": ahora - timedelta(days=4),
                                                   "g2": ahora - timedelta(days=1)})[0]
comprobar(chat_g["etiquetas_del_equipo"] == ["vip"], "las etiquetas del chat viajan en la fila agrupada")

# ---------------------------------------------------------------------------
print("\n== B. la cola: catalogo una vez, y una clave borrada no se muestra ==")
reales = (api._config_de, api.persistencia.ultima_actividad, api.persistencia.salud_canal_whatsapp,
          api.persistencia.creado_en_de, api.persistencia.marcar_leida,
          api.persistencia.guardar_etiquetas_de_chat, api.persistencia.mensajes_de,
          api.persistencia.reincidencia_de, editor.guardar_etiquetas_del_equipo, api._TOKEN_SERVICIO)
llamadas: dict[str, list] = {"leida": [], "etiquetas": []}
api._TOKEN_SERVICIO = None
api._config_de = lambda tenant: CFG
cola = [fila("h1", "573005", etiquetas=["vip", "borrada_hace_rato", "moroso"]),
        fila("h2", "573006", estado="cerrada", etiquetas=["borrada_hace_rato"])]
api.persistencia.ultima_actividad = lambda tenant, canal=None, cerradas_dias=None: [dict(f) for f in cola]
api.persistencia.salud_canal_whatsapp = lambda tenant: None
api.persistencia.creado_en_de = lambda tenant, ids: {i: ahora for i in ids}
try:
    with api.app.test_client() as http:
        r = http.get("/conversaciones?tenant=prueba&por_numero=1")
        cuerpo = r.get_json() or {}
        por_id = {f["id"]: f for f in cuerpo.get("conversaciones", [])}
        comprobar(r.status_code == 200, f"la cola responde ({r.status_code})")
        comprobar([e["clave"] for e in cuerpo.get("etiquetas_del_equipo", [])] == ["vip", "moroso"]
                  and cuerpo["etiquetas_del_equipo"][0] == {"clave": "vip", "nombre": "Cliente VIP",
                                                             "color": "violeta"},
                  "el catalogo viaja una vez, con nombre y color")
        comprobar(por_id.get("h1", {}).get("etiquetas_del_equipo") == ["vip", "moroso"],
                  "la clave que se borro del catalogo no viaja en la fila",
                  str(por_id.get("h1", {}).get("etiquetas_del_equipo")))
        comprobar(por_id.get("h2", {}).get("etiquetas_del_equipo") == [],
                  "una fila con solo claves borradas queda sin etiquetas")

        # Sin config, ninguna: una clave sin nombre ni color no se dibuja.
        def sin_config(tenant):
            raise RuntimeError("sin config")
        api._config_de = sin_config
        r = http.get("/conversaciones?tenant=prueba&por_numero=1")
        cuerpo = r.get_json() or {}
        comprobar(r.status_code == 200 and cuerpo.get("etiquetas_del_equipo") == []
                  and all(f.get("etiquetas_del_equipo") == [] for f in cuerpo.get("conversaciones", [])),
                  "sin config la cola sigue, sin catalogo y sin etiquetas en las filas")
        api._config_de = lambda tenant: CFG

        # -------------------------------------------------------------------
        print("\n== C. POST /conversaciones/<id>/leida ==")

        def marcar(tenant, cid, leida):
            llamadas["leida"].append((cid, leida))
            return respuesta_leida
        api.persistencia.marcar_leida = marcar
        respuesta_leida = {"aplicada": True, "leida": True, "conversaciones": [CID],
                           "leida_hasta": ahora}

        r = http.post(f"/conversaciones/{CID}/leida", json={"tenant": "prueba", "leida": "false"})
        comprobar(r.status_code == 400 and not llamadas["leida"],
                  "'leida' en texto se rechaza: \"false\" es verdadero en Python y marcaria leida")
        r = http.post(f"/conversaciones/{CID}/leida", json={"leida": True})
        comprobar(r.status_code == 400 and not llamadas["leida"], "sin tenant: 400")
        r = http.post("/conversaciones/no-es-un-id/leida", json={"tenant": "prueba", "leida": True})
        comprobar(r.status_code == 404 and not llamadas["leida"], "un id que no es uuid es 404, no 500")

        r = http.post(f"/conversaciones/{CID}/leida", json={"tenant": "prueba", "leida": True})
        comprobar(r.status_code == 200 and llamadas["leida"] == [(CID, True)]
                  and (r.get_json() or {}).get("leida") is True,
                  "leida: true llega a la persistencia tal cual")

        respuesta_leida = {"aplicada": True, "leida": False, "conversaciones": [CID], "leida_hasta": ahora}
        r = http.post(f"/conversaciones/{CID}/leida", json={"tenant": "prueba", "leida": False})
        comprobar(r.status_code == 200 and llamadas["leida"][-1] == (CID, False),
                  "leida: false llega como False, no como True")

        respuesta_leida = {"aplicada": False, "leida": False, "motivo": "sin_mensajes_del_cliente"}
        r = http.post(f"/conversaciones/{CID}/leida", json={"tenant": "prueba", "leida": False})
        comprobar(r.status_code == 409 and (r.get_json() or {}).get("codigo") == "sin_mensajes_del_cliente",
                  "«no leida» sin mensajes del cliente es 409 con su codigo, no un 200 que no hizo nada")

        respuesta_leida = None
        r = http.post(f"/conversaciones/{CID}/leida", json={"tenant": "prueba", "leida": True})
        comprobar(r.status_code == 404, "una conversacion que no existe (o de otra empresa) es 404")

        # -------------------------------------------------------------------
        print("\n== D. PUT /conversaciones/<id>/etiquetas ==")
        guardado = {"r": ["vip"]}

        def guardar(tenant, cid, claves, autor_id, autor):
            llamadas["etiquetas"].append((cid, list(claves), autor_id, autor))
            if isinstance(guardado["r"], Exception):
                raise guardado["r"]
            return guardado["r"]
        api.persistencia.guardar_etiquetas_de_chat = guardar

        r = http.put(f"/conversaciones/{CID}/etiquetas",
                     json={"tenant": "prueba", "etiquetas": ["vip", "inventada"], **ANA})
        comprobar(r.status_code == 400 and (r.get_json() or {}).get("codigo") == "etiqueta_desconocida"
                  and not llamadas["etiquetas"],
                  "una clave fuera del catalogo rechaza el pedido ENTERO, sin escribir nada")
        r = http.put(f"/conversaciones/{CID}/etiquetas", json={"tenant": "prueba", "etiquetas": ["vip"]})
        comprobar(r.status_code == 400 and not llamadas["etiquetas"],
                  "sin autor no se guarda: 'cambiada_por' no puede quedar vacio")
        r = http.put(f"/conversaciones/{CID}/etiquetas",
                     json={"tenant": "prueba", "etiquetas": "vip", **ANA})
        comprobar(r.status_code == 400 and not llamadas["etiquetas"], "'etiquetas' que no es lista: 400")

        guardado["r"] = ["vip", "moroso"]
        r = http.put(f"/conversaciones/{CID}/etiquetas",
                     json={"tenant": "prueba", "etiquetas": ["moroso", "vip", "moroso", " vip "], **ANA})
        ultima = llamadas["etiquetas"][-1] if llamadas["etiquetas"] else None
        comprobar(r.status_code == 200 and ultima == (CID, ["vip", "moroso"], ANA["autor_usuario_id"], ANA["autor"]),
                  "se guardan sin repetidas, en el orden del catalogo, con el autor del cuerpo",
                  str(ultima))
        comprobar((r.get_json() or {}).get("etiquetas") == ["vip", "moroso"], "y devuelve lo guardado")

        r = http.put(f"/conversaciones/{CID}/etiquetas", json={"tenant": "prueba", "etiquetas": [], **ANA})
        comprobar(r.status_code == 200 and llamadas["etiquetas"][-1][1] == [],
                  "una lista vacia saca todas (se guarda vacia, no se ignora)")

        guardado["r"] = api.persistencia.SinChat("sin numero")
        r = http.put(f"/conversaciones/{CID}/etiquetas", json={"tenant": "prueba", "etiquetas": ["vip"], **ANA})
        comprobar(r.status_code == 409 and (r.get_json() or {}).get("codigo") == "sin_chat",
                  "una conversacion sin numero no es un chat: 409")

        n_antes = len(llamadas["etiquetas"])
        api._config_de = sin_config
        r = http.put(f"/conversaciones/{CID}/etiquetas", json={"tenant": "prueba", "etiquetas": ["vip"], **ANA})
        comprobar(r.status_code == 503 and len(llamadas["etiquetas"]) == n_antes,
                  "sin catalogo no se puede validar: no se escribe a ciegas")
        api._config_de = lambda tenant: CFG

        # -------------------------------------------------------------------
        print("\n== E. la conversacion tampoco muestra una etiqueta borrada ==")
        api.persistencia.mensajes_de = lambda tenant, cid: {
            "conversacion": {"id": cid, "canal": "whatsapp", "usuario_externo": "573005",
                             "estado": "abierta", "control": "humano",
                             "etiquetas_del_equipo": ["borrada_hace_rato", "moroso"]},
            "mensajes": []}
        api.persistencia.reincidencia_de = lambda tenant, cid, dias: None
        r = http.get(f"/conversaciones/{CID}/mensajes?tenant=prueba")
        comprobar(r.status_code == 200
                  and (r.get_json() or {}).get("conversacion", {}).get("etiquetas_del_equipo") == ["moroso"],
                  "el encabezado trae solo las que siguen en el catalogo",
                  str((r.get_json() or {}).get("conversacion", {}).get("etiquetas_del_equipo")))

        # -------------------------------------------------------------------
        print("\n== F. el catalogo se edita por /configuracion/bandeja/etiquetas ==")
        recibido = {}

        def guardar_catalogo(tenant, etiquetas):
            recibido["etiquetas"] = etiquetas
            return CFG
        editor.guardar_etiquetas_del_equipo = guardar_catalogo
        r = http.put("/configuracion/bandeja/etiquetas",
                     json={"tenant": "prueba", "etiquetas": [{"nombre": "Nueva", "color": "verde"}]})
        cuerpo = r.get_json() or {}
        comprobar(r.status_code == 200 and recibido.get("etiquetas") == [{"nombre": "Nueva", "color": "verde"}],
                  "la lista llega al editor tal cual")
        comprobar([e["clave"] for e in cuerpo.get("etiquetas_del_equipo", [])] == ["vip", "moroso"]
                  and "violeta" in cuerpo.get("colores_de_etiqueta", []),
                  "y vuelve el catalogo con la paleta, como los rotulos")

        def rechaza(tenant, etiquetas):
            raise editor.ErrorEdicion("'#ff00aa' no es uno de los colores de etiqueta")
        editor.guardar_etiquetas_del_equipo = rechaza
        r = http.put("/configuracion/bandeja/etiquetas",
                     json={"tenant": "prueba", "etiquetas": [{"nombre": "X", "color": "#ff00aa"}]})
        comprobar(r.status_code == 400 and "colores" in (r.get_json() or {}).get("error", ""),
                  "el rechazo del editor sale como 400 con su motivo")
        r = http.get("/configuracion/bandeja/rotulos?tenant=prueba")
        comprobar([e["clave"] for e in (r.get_json() or {}).get("etiquetas_del_equipo", [])] == ["vip", "moroso"],
                  "la lectura de la pantalla de ajustes trae el catalogo")
finally:
    (api._config_de, api.persistencia.ultima_actividad, api.persistencia.salud_canal_whatsapp,
     api.persistencia.creado_en_de, api.persistencia.marcar_leida,
     api.persistencia.guardar_etiquetas_de_chat, api.persistencia.mensajes_de,
     api.persistencia.reincidencia_de, editor.guardar_etiquetas_del_equipo, api._TOKEN_SERVICIO) = reales

print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es) no pasaron:")
    for f in fallos:
        print(f"   - {f}")
    raise SystemExit(1)
print("[OK] Los no leidos suman por chat y las etiquetas fuera del catalogo no se guardan ni se muestran.")
