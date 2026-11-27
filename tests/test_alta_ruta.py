# -*- coding: utf-8 -*-
"""La ruta por donde el backend pide crear un cliente es ANGOSTA.

LO QUE ESTE ARCHIVO DEFIENDE  --  25/11/2026 (auditoria de frontera: la ruta
no tenia ninguna prueba, y aceptar `origen` del cuerpo, soltar las listas
cerradas o dejar pasar un pedido sin actor no ponia nada en rojo).

* **El `origen` lo arma el motor** con el id del contrato de la URL y el
  numero de pedido. Del cuerpo no se acepta.
* **No hay «reintentar».** El campo se rechaza: lo que fallo no se reejecuta.
* **Listas cerradas.** Un campo de mas --una contrasena, un campo arbitrario
  del proveedor-- se rechaza con 400 y NO se llama a nada.
* **Sin actor no hay puerta humana.**
* **Los codigos dicen la verdad:** «nadie sabe todavia» es 202 y no 502.
* **El cuerpo que arma Django es el que esta ruta acepta.** El literal de
  abajo es el de `campo/services/alta_en_el_isp.py`; si cambia uno, cambia el
  otro.

No habla con ningun proveedor: `crear` y `comprobar` estan reemplazados.

    MOTOR_SERVICE_TOKEN= python tests/test_alta_ruta.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

#  Sin token de servicio: esta prueba mira la ruta, no la autenticacion.
os.environ["MOTOR_SERVICE_TOKEN"] = ""

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.canales import api                                     # noqa: E402
from nucleo.seguimiento import alta_de_cliente as alta             # noqa: E402

cliente = api.app.test_client()
CONTRATO = "11111111-2222-3333-4444-555555555555"
URL = f"/interno/contrato/{CONTRATO}/crear-cliente?tenant=tenant-de-prueba"
URL_COMPROBAR = f"/interno/contrato/{CONTRATO}/comprobar-cliente?tenant=tenant-de-prueba"

_fallos: list[str] = []


def afirmar(condicion: bool, que: str) -> None:
    print(("  OK   " if condicion else "  FALLA ") + que)
    if not condicion:
        _fallos.append(que)


def seccion(titulo: str) -> None:
    print("\n" + titulo)
    print("-" * len(titulo))


#  EL CUERPO TAL COMO LO ARMA DJANGO (`alta_en_el_isp.pedir`).
DATOS = {"zona": 20049, "ip": "172.16.9.37", "plan": "PLAN FAMILIA",
         "cliente": {"nombre": "LAURA", "apellido": "PINEDA", "documento": "1234500001",
                     "correo": "laura@example.com", "telefono": "3005550101",
                     "direccion": "CRA 3B # 54-20", "barrio": "VILLA DEL SOL"},
         "coordenadas": {"lat": "10.8982702", "lng": "-74.8017717"},
         "nota": "Contrato C-2026-000011 · OT-11"}
PEDIDO = {"actor": "Dilan Moreno", "datos": DATOS, "intento": 1}
#  Y EL DE VOLVER A MIRAR (`alta_en_el_isp.comprobar`): solo lo minimo.
PARA_RECONOCER = {"zona": 20049, "ip": "172.16.9.37", "plan": "PLAN FAMILIA",
                  "cliente": {"nombre": "LAURA", "apellido": "PINEDA",
                              "documento": "1234500001"}}

llamadas: list[dict] = []
_resultado = [alta.ResultadoAlta(alta.CREADO, id_cliente="9000")]

_viejos = (api._config_de, alta.crear, alta.comprobar)
api._config_de = lambda t: object()


def _crear(config, tenant, **kw):
    llamadas.append({"que": "crear", "tenant": tenant, **kw})
    return _resultado[0]


def _comprobar(config, tenant, **kw):
    llamadas.append({"que": "comprobar", "tenant": tenant, **kw})
    return _resultado[0]


alta.crear, alta.comprobar = _crear, _comprobar


def pedir(cuerpo, url=URL):
    llamadas.clear()
    r = cliente.post(url, json=cuerpo)
    return r.status_code, (r.get_json() or {})


try:
    # -----------------------------------------------------------------------
    seccion("1. el cuerpo que arma Django pasa, y el ORIGEN lo arma el motor")
    codigo, cuerpo = pedir(PEDIDO)
    afirmar(codigo == 200 and cuerpo.get("estado") == "creado", f"200 creado: {codigo} {cuerpo}")
    afirmar(len(llamadas) == 1, "se llamo a crear UNA vez")
    ll = llamadas[0] if llamadas else {}
    afirmar(ll.get("origen") == f"alta_de_contrato:{CONTRATO}:1",
            f"el origen sale del contrato de la URL y del numero de pedido: {ll.get('origen')!r}")
    afirmar(ll.get("actor") == "Dilan Moreno" and ll.get("tenant") == "tenant-de-prueba",
            "con quien lo pidio y para que empresa")
    afirmar(ll.get("datos") == DATOS, "y los datos llegan tal cual")
    afirmar("reintentar" not in ll, "a `crear` no se le pasa ningun «reintentar»")

    codigo, _ = pedir({**PEDIDO, "intento": 3})
    afirmar(codigo == 200 and llamadas[0]["origen"].endswith(":3"),
            "otro numero de pedido es otro origen")

    # -----------------------------------------------------------------------
    seccion("2. lo que la ruta NO acepta: 400 y no se llama a nada")
    for extra, que in (
            ({"origen": "alta_de_contrato:otro:9"}, "un `origen` propio"),
            ({"reintentar": True}, "«reintentar»"),
            ({"evidencia": "x"}, "una evidencia propia"),
            ({"clave": "x"}, "una clave idempotente propia")):
        codigo, cuerpo = pedir({**PEDIDO, **extra})
        afirmar(codigo == 400 and llamadas == [], f"{que}: {codigo}, {len(llamadas)} llamadas")

    for datos, que in (
            ({**DATOS, "password_servicio": "x"}, "una contrasena entre los datos"),
            ({**DATOS, "usuario_rb": "x"}, "un campo con el nombre del proveedor"),
            ({**DATOS, "cliente": {**DATOS["cliente"], "password_portal_cliente": "x"}},
             "una contrasena dentro del cliente"),
            ("no soy un objeto", "datos que no son un objeto"),
            (None, "sin datos")):
        codigo, cuerpo = pedir({**PEDIDO, "datos": datos})
        afirmar(codigo == 400 and llamadas == [], f"{que}: {codigo}, {len(llamadas)} llamadas")
        afirmar("x" != cuerpo.get("error") and "= x" not in str(cuerpo),
                "y el error nombra el campo, no repite su valor")

    for actor, que in (("", "sin actor"), ("   ", "un actor en blanco"), (None, "actor nulo")):
        codigo, _ = pedir({**PEDIDO, "actor": actor})
        afirmar(codigo == 400 and llamadas == [], f"{que}: {codigo}")

    for intento, que in ((0, "el pedido 0"), (-1, "un pedido negativo"), (21, "el pedido 21"),
                         (True, "un booleano"), ("1", "un texto"), (1.5, "un decimal")):
        codigo, _ = pedir({**PEDIDO, "intento": intento})
        afirmar(codigo == 400 and llamadas == [], f"{que}: {codigo}")
    codigo, _ = pedir({**PEDIDO, "intento": 20})
    afirmar(codigo == 200, f"EL CONTROL: el pedido 20 si pasa ({codigo})")

    r = cliente.post(f"/interno/contrato/{CONTRATO}/crear-cliente", json=PEDIDO)
    afirmar(r.status_code == 400, f"sin tenant: {r.status_code}")
    llamadas.clear()
    r = cliente.post(URL, json=["no", "soy", "un", "objeto"])
    afirmar(r.status_code == 400 and llamadas == [], f"un cuerpo que no es un objeto: {r.status_code}")

    # -----------------------------------------------------------------------
    seccion("3. los codigos dicen la verdad")
    for estado, esperado, que in (
            (alta.CREADO, 200, "creado"), (alta.YA_ESTABA, 200, "ya estaba"),
            (alta.EN_CURSO, 202, "en curso: nadie sabe todavia"),
            (alta.NO_RECONOCIDO, 202, "no reconocido: nadie sabe, y NO es un fallo"),
            (alta.FALLO, 502, "el proveedor dijo que no"),
            (alta.DATOS_INVALIDOS, 400, "datos invalidos"),
            (alta.IP_OCUPADA, 409, "ip ocupada: no se creo, la peticion estaba bien"),
            (alta.IP_FUERA_DEL_RANGO, 409, "ip fuera del rango"),
            (alta.PLAN_DESCONOCIDO, 409, "plan desconocido"),
            (alta.BLOQUEADO, 409, "bloqueado"),
            (alta.NO_SE_PUDO_COMPROBAR, 409, "no se pudo comprobar"),
            (alta.SIN_HERRAMIENTA, 409, "sin herramienta")):
        _resultado[0] = alta.ResultadoAlta(estado, "motivo fijo", emitido=True)
        codigo, cuerpo = pedir(PEDIDO)
        afirmar(codigo == esperado and cuerpo.get("estado") == estado,
                f"{que}: {codigo}")
    afirmar(set(cuerpo) == {"estado", "motivo", "referencia", "id_cliente", "tarea",
                            "avisos", "emitido"},
            f"la respuesta lleva solo el resultado, nada del cliente: {sorted(cuerpo)}")

    # -----------------------------------------------------------------------
    seccion("4. comprobar: solo lee, y acepta lo minimo que manda Django")
    _resultado[0] = alta.ResultadoAlta(alta.EN_CURSO, emitido=True)
    codigo, cuerpo = pedir({"datos": PARA_RECONOCER, "tarea": "tarea-1"}, URL_COMPROBAR)
    afirmar(codigo == 202 and [ll["que"] for ll in llamadas] == ["comprobar"],
            f"llama a comprobar y NO a crear: {codigo} {[ll['que'] for ll in llamadas]}")
    afirmar(llamadas[0]["datos"] == PARA_RECONOCER and llamadas[0]["tarea"] == "tarea-1",
            "con lo minimo para reconocer al cliente, y su tarea")
    for extra, que in (({"actor": "x"}, "un actor"), ({"intento": 2}, "un numero de pedido"),
                       ({"reintentar": True}, "«reintentar»")):
        codigo, _ = pedir({"datos": PARA_RECONOCER, **extra}, URL_COMPROBAR)
        afirmar(codigo == 400 and llamadas == [], f"comprobar no acepta {que}: {codigo}")
    codigo, _ = pedir({"datos": {**PARA_RECONOCER, "password_cpe": "x"}}, URL_COMPROBAR)
    afirmar(codigo == 400 and llamadas == [], f"ni una contrasena entre los datos: {codigo}")
    # -----------------------------------------------------------------------
    seccion("9. ACTIVAR la instalacion (26/11/2026): mismo contrato angosto y la misma puerta")
    URL_ACTIVAR = f"/interno/contrato/{CONTRATO}/activar-cliente?tenant=tenant-de-prueba"
    URL_COMP_ACT = f"/interno/contrato/{CONTRATO}/comprobar-activacion?tenant=tenant-de-prueba"
    _viejos_act = (alta.activar, alta.comprobar_activacion)

    def _activar(config, tenant, **kw):
        llamadas.append({"que": "activar", "tenant": tenant, **kw})
        return alta.ResultadoAlta(alta.ACTIVADO, id_cliente="7000")

    def _comprobar_act(config, tenant, **kw):
        llamadas.append({"que": "comprobar_activacion", "tenant": tenant, **kw})
        return alta.ResultadoAlta(alta.EN_CURSO, id_cliente="7000")

    alta.activar, alta.comprobar_activacion = _activar, _comprobar_act
    try:
        codigo, cuerpo = pedir({"actor": "Encargada Rosa", "datos": {**DATOS, "costo_instalacion": 80000,
                                "serial_onu": "FHTT12345678"}, "intento": 2, "id_servicio": "7000"},
                               URL_ACTIVAR)
        afirmar(codigo == 200 and cuerpo.get("estado") == "activado", f"200 activado: {codigo} {cuerpo}")
        afirmar(llamadas and llamadas[0].get("origen") == f"activacion_de_contrato:{CONTRATO}:2"
                and llamadas[0].get("actor") == "Encargada Rosa"
                and llamadas[0].get("id_servicio") == "7000",
                f"el ORIGEN lo arma el motor, y viajan quien valido y el numero: {llamadas[:1]}")
        codigo, _ = pedir({"datos": DATOS, "id_servicio": "7000"}, URL_ACTIVAR)
        afirmar(codigo == 400 and llamadas == [], f"sin quien valido no hay activacion: {codigo}")
        codigo, _ = pedir({"actor": "x", "datos": DATOS, "id_servicio": "7000", "origen": "otro"},
                          URL_ACTIVAR)
        afirmar(codigo == 400 and llamadas == [], f"el origen NO se acepta de afuera: {codigo}")
        codigo, _ = pedir({"actor": "x", "datos": {**DATOS, "password_cpe": "x"}, "id_servicio": "7000"},
                          URL_ACTIVAR)
        afirmar(codigo == 400 and llamadas == [], f"ni una contrasena entre los datos: {codigo}")
        codigo, cuerpo = pedir({"datos": PARA_RECONOCER, "id_servicio": "7000"}, URL_COMP_ACT)
        afirmar(codigo == 202 and llamadas and llamadas[0]["que"] == "comprobar_activacion",
                f"comprobar solo lee y dice como va: {codigo} {cuerpo}")
        codigo, _ = pedir({"datos": PARA_RECONOCER, "id_servicio": "7000", "actor": "x"}, URL_COMP_ACT)
        afirmar(codigo == 400, f"comprobar no acepta un actor: no escribe nada: {codigo}")
    finally:
        alta.activar, alta.comprobar_activacion = _viejos_act
finally:
    api._config_de, alta.crear, alta.comprobar = _viejos

print()
if _fallos:
    print(f"FALLARON {len(_fallos)}:")
    for f in _fallos:
        print("  -", f)
    sys.exit(1)
print("TODO OK")
