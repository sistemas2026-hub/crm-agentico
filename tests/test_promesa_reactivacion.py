# -*- coding: utf-8 -*-
"""
================================================================================
 Promesa de pago CON reactivacion  --  la politica decide, no el modelo
================================================================================

    py -3.13 tests/test_promesa_reactivacion.py

Sin red y sin base: la politica es una funcion pura y por eso se puede probar
entera. Lo que toca WispHub se prueba aparte, con dobles.

LO QUE SE AFIRMA
  1. cada guarda, por separado, y que el MOTIVO que sale sea el correcto --
     no alcanza con "no elegible": quien lo lea tiene que saber por que;
  2. que "no se pudo leer" NUNCA caiga del lado de "elegible";
  3. que el modelo no pueda elegir entre promesa simple y reactivacion;
  4. que el resumen que ve quien aprueba nombre LOS DOS efectos;
  5. que un 2xx de WispHub no se confunda con "el servicio esta activo".
================================================================================
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

fallos: list[str] = []


def revisar(condicion, que, porque=""):
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}", flush=True)
    if not condicion:
        fallos.append(que)
        if porque:
            print(f"          {porque}", flush=True)


def titulo(t):
    print(f"\n{'=' * 76}\n  {t}\n{'=' * 76}", flush=True)


import yaml                                                       # noqa: E402

from nucleo.config.schema import PromesasPago, TenantConfig       # noqa: E402
from nucleo.facturacion import promesas                           # noqa: E402

HOY = date(2026, 9, 21)
POLITICA = PromesasPago(dias_maximos_promesa=15, monto_maximo_promesa=200000,
                        dias_entre_promesas=30)


def hechos(**cambios):
    """Un caso que SI es elegible. Cada prueba rompe una cosa."""
    base = {
        "cliente": {"estado": "Suspendido"},
        "facturas": [{"id_factura": 147121, "estado": "Pendiente de Pago",
                      "fecha_vencimiento": "2026-09-10", "total": 69900.0}],
        "fecha_limite": "2026-10-01",
        "promesa_previa": None,
    }
    base.update(cambios)
    return base


def ver(**cambios):
    return promesas.evaluar(hechos(**cambios), POLITICA, hoy=HOY)


# =============================================================================
titulo("1. el caso que SI procede")
# =============================================================================
v = ver()
revisar(v.elegible and v.resultado == promesas.ELEGIBLE,
        f"suspendido + una factura vencida + plazo y monto en regla ({v.resultado})")
revisar(v.datos.get("id_factura") == 147121 and v.datos.get("dias_de_plazo") == 10,
        f"y deja los datos de la decision ({v.datos})",
        "Sin ellos, quien apruebe no sabe sobre que factura ni por cuantos dias.")


# =============================================================================
titulo("2. cada guarda, con su motivo")
# =============================================================================
CASOS = [
    ("activo -> no hay nada que reactivar", "no_esta_suspendido",
     {"cliente": {"estado": "Activo"}}),
    ("cancelado tampoco", "no_esta_suspendido",
     {"cliente": {"estado": "Cancelado"}}),
    ("sin facturas pendientes", "sin_factura_pendiente",
     {"facturas": [{"id_factura": 1, "estado": "Pagada",
                    "fecha_vencimiento": "2026-08-10", "total": 10.0}]}),
    ("dos pendientes = deuda acumulada", "varias_pendientes",
     {"facturas": [
         {"id_factura": 1, "estado": "Pendiente de Pago",
          "fecha_vencimiento": "2026-08-10", "total": 69900.0},
         {"id_factura": 2, "estado": "Pendiente de Pago",
          "fecha_vencimiento": "2026-09-10", "total": 69900.0}]}),
    ("la factura todavia no vencio", "factura_no_vencida",
     {"facturas": [{"id_factura": 1, "estado": "Pendiente de Pago",
                    "fecha_vencimiento": "2026-09-30", "total": 69900.0}]}),
    ("pide mas plazo del permitido", "plazo_excedido",
     {"fecha_limite": "2026-11-30"}),
    ("la fecha que pide ya paso", "fecha_limite_pasada",
     {"fecha_limite": "2026-09-01"}),
    ("el monto supera el tope", "monto_excedido",
     {"facturas": [{"id_factura": 1, "estado": "Pendiente de Pago",
                    "fecha_vencimiento": "2026-09-10", "total": 500000.0}]}),
    ("ya le registramos una promesa hace poco", "promesa_reciente",
     {"promesa_previa": "2026-09-10"}),
]
for etiqueta, motivo, cambios in CASOS:
    v = ver(**cambios)
    revisar(v.resultado == promesas.NO_ELEGIBLE and v.motivo == motivo,
            f"{etiqueta} -> {v.resultado}/{v.motivo}")
    revisar(bool(v.detalle),
            f"   y lo explica en castellano ({v.detalle[:60]!r})",
            "Un codigo sin explicacion obliga a quien lo lee a abrir el codigo.")

# Justo en el limite: 15 dias exactos SI entra, 16 no.
revisar(ver(fecha_limite="2026-10-06").elegible,
        "el plazo maximo exacto (15 dias) entra")
revisar(ver(fecha_limite="2026-10-07").motivo == "plazo_excedido",
        "y uno mas, no")
# Una promesa vieja no estorba.
revisar(ver(promesa_previa="2026-07-01").elegible,
        "una promesa de hace 82 dias no bloquea (el minimo es 30)")


# =============================================================================
titulo("3. lo que NO se pudo leer nunca cae del lado del 'si'")
# =============================================================================
NO_SE_PUDO = [
    ("el cliente no se pudo leer", "sin_cliente", {"cliente": None}),
    ("vino vacio: tampoco se pudo leer", "sin_cliente", {"cliente": {}}),
    # Distinto del anterior: el cliente SI vino, pero sin el campo que decide.
    # Merece su propio motivo -- "no encontre al cliente" y "lo encontre y no
    # trae estado" mandan a mirar lugares distintos.
    ("vino, pero sin el campo 'estado'", "sin_estado",
     {"cliente": {"id_servicio": 6555, "nombre": "PRUEBA TEMPORAL"}}),
    ("las facturas no se pudieron leer", "sin_facturas", {"facturas": None}),
    ("la fecha limite no se entiende", "sin_fecha_limite",
     {"fecha_limite": "el proximo martes"}),
    ("la factura no trae vencimiento legible", "sin_vencimiento",
     {"facturas": [{"id_factura": 1, "estado": "Pendiente de Pago",
                    "fecha_vencimiento": "", "total": 69900.0}]}),
    ("el total no es un numero", "sin_monto",
     {"facturas": [{"id_factura": 1, "estado": "Pendiente de Pago",
                    "fecha_vencimiento": "2026-09-10", "total": "n/d"}]}),
]
for etiqueta, motivo, cambios in NO_SE_PUDO:
    v = ver(**cambios)
    revisar(v.resultado == promesas.NO_SE_PUDO and v.motivo == motivo,
            f"{etiqueta} -> {v.resultado}/{v.motivo}")
    revisar(not v.elegible, f"   y NO es elegible ({etiqueta})")

# El caso fino: no es lo mismo "consulte y no hay" que "no pude consultar".
sin_historial = hechos()
del sin_historial["promesa_previa"]
v = promesas.evaluar(sin_historial, POLITICA, hoy=HOY)
revisar(v.resultado == promesas.NO_SE_PUDO and v.motivo == "sin_historial",
        f"historial AUSENTE -> no_se_pudo ({v.motivo})",
        "None dice 'consulte y no hay'; ausente dice 'no pude consultar'. Si "
        "se trataran igual, un fallo de la base pareceria un cliente limpio.")
revisar(ver(promesa_previa=None).elegible,
        "y con historial en None (consultado, sin promesas) si procede")


# =============================================================================
titulo("4. el catalogo: dos acciones, y el modelo no elige entre ellas")
# =============================================================================
config = TenantConfig.model_validate(
    yaml.safe_load((RAIZ / "tenants" / "rapilink.config.yaml").read_text(encoding="utf-8")))
por_nombre = {h.nombre: h for h in config.herramientas}

simple = por_nombre.get("agregar_promesa_pago")
doble = por_nombre.get("registrar_promesa_y_reactivar")
revisar(simple is not None and doble is not None,
        "existen las DOS herramientas, separadas")

if doble is not None:
    revisar(doble.argumentos_fijos.get("accion") == 1,
            f"la de reactivar manda accion=1 fija ({doble.argumentos_fijos.get('accion')!r})")
    revisar("accion" not in doble.filtros_verificados
            and "accion" not in doble.requeridos
            and "accion" not in doble.argumentos_sobrescribibles,
            "y el modelo no la ve por ninguna de las tres puertas")
    revisar(doble.aprobacion_humana is True,
            "exige aprobacion humana",
            "Mientras WispHub no permita leer promesas vigentes, la persona que "
            "aprueba es lo unico que cubre ese punto ciego.")
    revisar(doble.roles_permitidos == ["facturacion"],
            f"y es interna, no del cliente final ({doble.roles_permitidos})")
    bajo = (doble.plantilla_resumen or "").lower()
    revisar("promesa" in bajo and ("reactiva" in bajo or "reactivar" in bajo),
            f"su resumen nombra LOS DOS efectos ({doble.plantilla_resumen!r})")

if simple is not None:
    revisar(simple.argumentos_fijos.get("accion") == 0,
            "y la simple sigue en accion=0")
    revisar("no reactiva" in (simple.plantilla_resumen or "").lower(),
            "diciendo que NO reactiva")

# Ninguna de las dos deja el interruptor a la vista.
for h in (simple, doble):
    if h is None:
        continue
    revisar("activar_servicio" not in str(h.filtros_verificados),
            f"'{h.nombre}': el enum 0/1 no aparece en lo que ve el modelo")


# =============================================================================
titulo("5. la politica no se inventa: sin valores, no se ofrece")
# =============================================================================
vacia = PromesasPago()
revisar(sorted(vacia.faltan_valores()) == ["dias_entre_promesas",
                                           "dias_maximos_promesa",
                                           "monto_maximo_promesa"],
        f"una politica vacia declara lo que le falta ({vacia.faltan_valores()})",
        "Cuantos dias de gracia da un ISP es una decision comercial. La "
        "plataforma no la puede tomar por el.")
revisar(config.promesas_pago.faltan_valores(),
        "y Rapilink todavia no la cargo: la accion NO se puede ofrecer aun")
revisar(POLITICA.faltan_valores() == [],
        "con los tres valores puestos, la politica esta completa")
revisar(PromesasPago(dias_maximos_promesa=1, monto_maximo_promesa=0,
                     dias_entre_promesas=0).faltan_valores() == [],
        "monto 0 es 'sin tope', no 'falta'",
        "None es 'nadie lo decidio'; 0 es 'se decidio que no hay tope'.")
revisar(vacia.requiere_aprobacion_humana is True,
        "y la aprobacion humana viene en true por defecto")


# =============================================================================
titulo("6. el resumen de aprobacion")
# =============================================================================
texto = promesas.resumen_de_aprobacion(ver().datos)
bajo = texto.lower()
revisar("promesa" in bajo, f"nombra la promesa ({texto[:50]}...)")
revisar("reactivar" in bajo or "reactiva" in bajo, "y la REACTIVACION")
revisar("suspendido" in bajo,
        "dice que el servicio esta hoy suspendido",
        "Es el hecho que justifica la accion; sin el, quien aprueba no puede "
        "saber si corresponde.")
revisar("vuelve a suspender" in bajo or "suspender" in bajo,
        "y que WispHub lo vuelve a suspender si no paga",
        "Es lo que le pone techo al riesgo. Quien aprueba tiene que saberlo.")
revisar("147121" in texto and "2026-10-01" in texto,
        "con la factura y la fecha concretas, no genericas")


# =============================================================================
titulo("7. aceptado NO es reactivado")
# =============================================================================
# WispHub responde 201 al crear la promesa. Eso dice que ACEPTO el pedido, no
# que el servicio quedo activo. Son tres hechos distintos y el contrato exige
# no mezclarlos.
fuente = (RAIZ / "nucleo" / "facturacion" / "promesas.py").read_text(encoding="utf-8")
codigo = "\n".join(l for l in fuente.splitlines() if not l.strip().startswith("#"))
revisar("requests" not in codigo and "http" not in codigo.lower().replace("https://", ""),
        "la politica no habla con nadie: recibe hechos ya leidos",
        "Asi se puede probar entera sin red, y asi la decision no depende de "
        "que la API conteste rapido.")
revisar("201" not in codigo and "status_code" not in codigo,
        "y no mira codigos de estado HTTP en ningun lado",
        "Confirmar la reactivacion es releer el cliente, no leer un 2xx.")



# =============================================================================
titulo("8. el productor: reune los hechos y NO propone si no procede")
# =============================================================================
# Hasta aca la politica era una funcion que nadie llamaba. Esto prueba la
# cadena real --catalogo, lecturas, evaluacion-- con dobles en lugar de red.
from nucleo.facturacion import politicas                          # noqa: E402

HERR = next(h for h in config.herramientas
            if h.nombre == "registrar_promesa_y_reactivar")

CLIENTE_OK = {"usuario": "prueba@rapilink-sas", "estado": "Suspendido"}
FACTURA_OK = {"id_factura": 147121, "estado": "Pendiente de Pago",
              "fecha_vencimiento": "2026-09-10", "total": 69900.0}
DETALLE_OK = {"id_factura": 147121, "cliente": {"usuario": "prueba@rapilink-sas"}}

COMPLETA = PromesasPago(dias_maximos_promesa=15, monto_maximo_promesa=200000,
                        dias_entre_promesas=30)


def lector(detalle=DETALLE_OK, cliente=CLIENTE_OK, facturas=(FACTURA_OK,),
           registro=None):
    """Un doble de las tres lecturas del catalogo. Anota a quien llamo."""
    def _leer(herr, args):
        if registro is not None:
            registro.append((herr.nombre, args))
        if herr.nombre == "consultar_factura_detalle":
            if isinstance(detalle, Exception):
                raise detalle
            return detalle
        if herr.nombre == "consultar_cliente":
            if isinstance(cliente, Exception):
                raise cliente
            return {"results": [cliente] if cliente else []}
        if herr.nombre == "consultar_facturas":
            if isinstance(facturas, Exception):
                raise facturas
            return {"results": list(facturas)}
        raise AssertionError(f"lectura inesperada: {herr.nombre}")
    return _leer


def correr(cfg=None, **kw):
    conf = cfg or config.model_copy(update={"promesas_pago": COMPLETA})
    registro = kw.pop("registro", None)
    historial = kw.pop("historial", lambda t, f: None)
    return politicas.evaluar(conf, "rapilink", HERR,
                             {"id_factura": 147121, "fecha_limite": "2026-10-01"},
                             leer=lector(registro=registro, **kw),
                             historial=historial)


# --- el camino feliz, y QUE lecturas hizo --------------------------------
llamadas = []
v = correr(registro=llamadas)
revisar(v is not None and v.elegible,
        f"con todo en regla, la politica dice que si ({v.resultado if v else None})")
revisar([n for n, _ in llamadas] == ["consultar_factura_detalle",
                                     "consultar_cliente", "consultar_facturas"],
        f"y leyo las tres, en orden ({[n for n, _ in llamadas]})",
        "La cadena empieza por la factura: es lo unico que trae la propuesta.")
revisar(llamadas[2][1] == {"cliente": "prueba@rapilink-sas", "estado": 1},
        f"las facturas se piden por SLUG y estado pendiente ({llamadas[2][1]})",
        "'id_servicio' esta medido como IGNORADO en ese listado: filtrar por el "
        "devolveria las facturas de todos los clientes.")

# --- una herramienta sin politica no paga nada ---------------------------
simple_h = next(h for h in config.herramientas if h.nombre == "agregar_promesa_pago")
revisar(politicas.evaluar(config, "rapilink", simple_h, {}, leer=None) is None,
        "una herramienta SIN politica declarada devuelve None",
        "Es lo que hace que esto sea aditivo: todo lo demas sigue igual.")

# --- si no hay politica cargada, no se propone ---------------------------
v = correr(cfg=config)          # Rapilink todavia no cargo los valores
revisar(v.resultado == promesas.NO_SE_PUDO and v.motivo == "politica_sin_cargar",
        f"sin valores del tenant no se propone ({v.motivo})")

# --- cada lectura que falla termina en NO_SE_PUDO ------------------------
for etiqueta, kw, motivo in (
        ("la factura no se pudo leer", {"detalle": RuntimeError("500")},
         "sin_cliente_de_la_factura"),
        ("la factura no dice de quien es", {"detalle": {"id_factura": 1}},
         "sin_cliente_de_la_factura"),
        ("el cliente no se pudo leer", {"cliente": RuntimeError("timeout")},
         "sin_cliente"),
        ("las facturas no se pudieron leer", {"facturas": RuntimeError("timeout")},
         "sin_facturas")):
    v = correr(**kw)
    revisar(v.resultado == promesas.NO_SE_PUDO and v.motivo == motivo,
            f"{etiqueta} -> {v.resultado}/{v.motivo}")

# --- el historial: consultado vs no consultado ---------------------------


def revienta(t, f):
    raise RuntimeError("base caida")


v = correr(historial=revienta)
revisar(v.resultado == promesas.NO_SE_PUDO and v.motivo == "sin_historial",
        f"si el historial no se puede consultar, NO se propone ({v.motivo})",
        "Una base caida no puede parecerse a un cliente sin promesas previas.")

v = correr(historial=lambda t, f: date(2026, 9, 15))
revisar(v.resultado == promesas.NO_ELEGIBLE and v.motivo == "promesa_reciente",
        f"y una promesa de hace 6 dias bloquea ({v.motivo})")

# --- el catalogo miente: lectura ausente o que escribe -------------------
sin_lectura = config.model_copy(update={"promesas_pago": COMPLETA})
herr_mala = HERR.model_copy(deep=True)
herr_mala.politica.lecturas["cliente"] = "no_existe_esta"
v = politicas.evaluar(sin_lectura, "rapilink", herr_mala, {"id_factura": 1},
                      leer=lector())
revisar(v.resultado == promesas.NO_SE_PUDO and "lectura_ausente" in v.motivo,
        f"una lectura declarada y ausente impide proponer ({v.motivo})",
        "Misma regla que X17: una comprobacion declarada que no puede correr "
        "nunca autoriza nada.")

herr_escribe = HERR.model_copy(deep=True)
herr_escribe.politica.lecturas["cliente"] = "agregar_promesa_pago"   # NO es lectura
v = politicas.evaluar(sin_lectura, "rapilink", herr_escribe, {"id_factura": 1},
                      leer=lector())
revisar(v.resultado == promesas.NO_SE_PUDO and "no_es_lectura" in v.motivo,
        f"y una que escribe, tampoco ({v.motivo})",
        "Comprobar no puede escribir: correria un efecto antes de decidir si "
        "se corre el efecto.")

herr_rara = HERR.model_copy(deep=True)
herr_rara.politica.nombre = "politica_que_no_existe"
v = politicas.evaluar(sin_lectura, "rapilink", herr_rara, {"id_factura": 1},
                      leer=lector())
revisar(v.resultado == promesas.NO_SE_PUDO and "desconocida" in v.motivo,
        f"una politica que el motor no conoce falla CERRADO ({v.motivo})")


# =============================================================================
titulo("9. el motor no propone lo que la politica rechaza")
# =============================================================================
from nucleo.modelo import motor                                   # noqa: E402

revisar(motor._politica_de(None, "rapilink", HERR, {}) is None,
        "sin config, el motor no evalua politica (y no rompe)")
revisar(motor._politica_de(config, "rapilink", simple_h, {}) is None,
        "una herramienta sin politica no la evalua")

salida = motor._no_se_propone(HERR, promesas.Veredicto(
    promesas.NO_ELEGIBLE, "varias_pendientes", "Tiene 3 facturas pendientes."))
revisar(salida.get("error") == "POLITICA_NO_ELEGIBLE",
        f"un rechazo devuelve error, no una propuesta ({salida.get('error')})")
revisar("3 facturas pendientes" in salida["instruccion_interna"],
        "y le pasa el MOTIVO al modelo, para que se lo diga a quien pregunto",
        "'No se pudo' no le sirve a nadie; 'tiene 3 facturas pendientes' si.")
revisar("no vuelvas a intentarlo" in salida["instruccion_interna"].lower(),
        "con la instruccion de no reintentar",
        "Sin eso el modelo lo propone otra vez y el colaborador ve el mismo "
        "rechazo tres veces seguidas.")

salida = motor._no_se_propone(HERR, promesas.Veredicto(
    promesas.NO_SE_PUDO, "sin_historial", "No se pudo consultar."))
revisar(salida.get("error") == "POLITICA_NO_SE_PUDO_COMPROBAR",
        f"y 'no se pudo' se distingue de 'no procede' ({salida.get('error')})",
        "Son cosas distintas: una la arregla el cliente pagando, la otra la "
        "arregla alguien mirando por que fallo la lectura.")

fuente_motor = (RAIZ / "nucleo" / "modelo" / "motor.py").read_text(encoding="utf-8")
cuerpo = fuente_motor[fuente_motor.index("def _ejecutar_propuesta_de_accion("):]
cuerpo = cuerpo[:cuerpo.index("\ndef ")]
revisar(cuerpo.index("_politica_de") < cuerpo.index("guardar_accion_propuesta"),
        "la politica corre ANTES de guardar la propuesta",
        "Al reves, quedaria una propuesta en la pantalla que nadie deberia "
        "aprobar -- y quien la vea no tiene como saberlo.")



# =============================================================================
titulo("10. el efecto, no la presencia: la propuesta NO se guarda")
# =============================================================================
# Las aserciones de arriba comprueban que las piezas existen y que el orden en
# el archivo es el correcto. Ninguna comprobaba que la guarda CORTE. Se noto
# con una mutacion: quitar el 'if' y el test seguia verde.
#
# Esto llama a la funcion real y espia la escritura.
from nucleo.persistencia import db as persistencia_real           # noqa: E402

guardadas = []


def _espia_guardar(*a, **k):
    guardadas.append(a)
    return ("accion-espia", False)


original = persistencia_real.guardar_accion_propuesta
politica_original = motor._politica_de
try:
    persistencia_real.guardar_accion_propuesta = _espia_guardar

    # --- la politica dice que NO -> no se guarda nada --------------------
    motor._politica_de = lambda *a, **k: promesas.Veredicto(
        promesas.NO_ELEGIBLE, "varias_pendientes", "Tiene 3 pendientes.")
    guardadas.clear()
    salida = motor._ejecutar_propuesta_de_accion(
        HERR, None, {"id_factura": 147121, "fecha_limite": "2026-10-01"},
        "rapilink", "facturacion", "quien", config=config)
    revisar(guardadas == [],
            f"con la politica en contra NO se guarda la propuesta ({len(guardadas)})",
            "Es la unica asercion que mide el EFECTO. Sin ella, quitar el 'if' "
            "del motor deja el test verde -- medido con una mutacion.")
    revisar(salida.get("error") == "POLITICA_NO_ELEGIBLE",
            f"y el modelo recibe el rechazo ({salida.get('error')})")
    revisar("accion_id" not in salida,
            "sin accion_id: no hay nada que aprobar")

    # --- no se pudo comprobar -> tampoco se guarda -----------------------
    motor._politica_de = lambda *a, **k: promesas.Veredicto(
        promesas.NO_SE_PUDO, "sin_historial", "No se pudo consultar.")
    guardadas.clear()
    salida = motor._ejecutar_propuesta_de_accion(
        HERR, None, {"id_factura": 147121, "fecha_limite": "2026-10-01"},
        "rapilink", "facturacion", "quien", config=config)
    revisar(guardadas == [],
            "y con 'no se pudo comprobar' tampoco",
            "Una propuesta en la pantalla ya viene con forma de algo aprobable. "
            "Quien la ve no tiene como saber que las comprobaciones no corrieron.")

    # --- la politica dice que SI -> se guarda ----------------------------
    # Control positivo. Sin esto, las dos de arriba pasarian igual si
    # '_ejecutar_propuesta_de_accion' estuviera rota y no guardara nunca.
    motor._politica_de = lambda *a, **k: promesas.Veredicto(promesas.ELEGIBLE)
    guardadas.clear()
    salida = motor._ejecutar_propuesta_de_accion(
        HERR, None, {"id_factura": 147121, "fecha_limite": "2026-10-01"},
        "rapilink", "facturacion", "quien", config=config)
    revisar(len(guardadas) == 1 and salida.get("accion_id") == "accion-espia",
            f"control positivo: con la politica a favor SI se guarda ({len(guardadas)})",
            "Si esto no guardara, las dos aserciones de arriba no medirian nada.")

    # --- y una herramienta SIN politica sigue funcionando igual ----------
    motor._politica_de = politica_original
    guardadas.clear()
    motor._ejecutar_propuesta_de_accion(
        simple_h, None, {"id_factura": 147121, "fecha_limite": "2026-10-01"},
        "rapilink", "facturacion", "quien", config=config)
    revisar(len(guardadas) == 1,
            "una herramienta sin politica se propone como siempre",
            "El enganche es ADITIVO: lo que no declara politica no cambia.")
finally:
    persistencia_real.guardar_accion_propuesta = original
    motor._politica_de = politica_original



# =============================================================================
titulo("11. al APROBAR se vuelve a leer todo")
# =============================================================================
# Entre proponer y aprobar pasa tiempo. Si la revalidacion usara los hechos
# guardados al proponer, no cubriria nada -- seria mirar una foto vieja y
# llamarla comprobacion.
from nucleo.relevo import revalidacion                            # noqa: E402

CONF_COMPLETA = config.model_copy(update={"promesas_pago": COMPLETA})
ACCION = {"herramienta": "registrar_promesa_y_reactivar",
          "argumentos": {"id_factura": 147121, "fecha_limite": "2026-10-01",
                         "accion": 1}}


def revalidar_con(**kw):
    historial = kw.pop("historial", lambda t, f: None)
    registro = kw.pop("registro", None)
    leer = lector(registro=registro, **kw)

    def politica(cfg, ten, herr, acc):
        return politicas.evaluar(cfg, ten, herr, acc.get("argumentos") or {},
                                 leer=leer, historial=historial)
    return revalidacion.revalidar(CONF_COMPLETA, "rapilink", HERR, ACCION,
                                  politica=politica)


llamadas = []
v = revalidar_con(registro=llamadas)
revisar(v.desenlace == revalidacion.CUMPLE,
        f"si todo sigue igual, cumple ({v.desenlace})")
revisar([n for n, _ in llamadas] == ["consultar_factura_detalle",
                                     "consultar_cliente", "consultar_facturas"],
        f"y volvio a leer las TRES fuentes ({len(llamadas)} lecturas)",
        "No se confia en los hechos de cuando se propuso: eso es justo lo que "
        "esta comprobacion existe para cubrir.")

# --- el cliente pago entre proponer y aprobar ----------------------------
v = revalidar_con(cliente={"usuario": "prueba@rapilink-sas", "estado": "Activo"})
revisar(v.desenlace == revalidacion.NO_CUMPLE and "no_esta_suspendido" in v.codigo,
        f"si ya pago y esta Activo -> NO CUMPLE ({v.codigo})",
        "Reactivar a quien ya tiene servicio no significa nada, y el efecto "
        "seria una promesa que nadie pidio.")

v = revalidar_con(facturas=())
revisar(v.desenlace == revalidacion.NO_CUMPLE and "sin_factura_pendiente" in v.codigo,
        f"si ya no tiene facturas pendientes -> NO CUMPLE ({v.codigo})")

# --- aparecio otra factura -----------------------------------------------
otra = dict(FACTURA_OK, id_factura=999)
v = revalidar_con(facturas=(FACTURA_OK, otra))
revisar(v.desenlace == revalidacion.NO_CUMPLE and "varias_pendientes" in v.codigo,
        f"si ahora tiene DOS pendientes -> NO CUMPLE ({v.codigo})",
        "La deuda acumulada la decide una persona, no una aprobacion de tramite.")

# --- la lectura falla -> no se ejecuta, y no se mata la accion ------------
for etiqueta, kw in (("el cliente no responde", {"cliente": RuntimeError("timeout")}),
                     ("las facturas no responden", {"facturas": RuntimeError("500")}),
                     ("la factura no responde", {"detalle": RuntimeError("500")})):
    v = revalidar_con(**kw)
    revisar(v.desenlace == revalidacion.NO_SE_PUDO,
            f"{etiqueta} -> NO SE PUDO ({v.codigo})",
            "Y NO_SE_PUDO no es NO_CUMPLE: la accion vuelve a pendiente en vez "
            "de morir. Puede seguir siendo valida.")

v = revalidar_con(historial=lambda t, f: date(2026, 9, 20))
revisar(v.desenlace == revalidacion.NO_CUMPLE and "promesa_reciente" in v.codigo,
        f"y si aparecio una promesa nuestra entremedio -> NO CUMPLE ({v.codigo})")

# --- una herramienta SIN politica no cambia de conducta ------------------
v = revalidacion.revalidar(CONF_COMPLETA, "rapilink", simple_h, ACCION)
revisar(v.desenlace == revalidacion.CUMPLE
        and v.codigo == "sin_revalidacion_declarada",
        f"sin politica ni revalidacion declarada, cumple como siempre ({v.codigo})",
        "El enganche es aditivo: no cambia lo que ya existia.")


# =============================================================================
titulo("12. aceptado, confirmado y no se sabe: tres cosas distintas")
# =============================================================================
ARGS = {"id_factura": 147121, "fecha_limite": "2026-10-01"}

ok, detalle = politicas.confirmar(CONF_COMPLETA, "rapilink", HERR, ARGS,
                                  leer=lector(cliente={"usuario": "x", "estado": "Activo"}))
revisar(ok is True and detalle == "Activo",
        f"POST aceptado + cliente Activo -> confirmado ({ok}, {detalle})")

ok, detalle = politicas.confirmar(CONF_COMPLETA, "rapilink", HERR, ARGS,
                                  leer=lector(cliente={"usuario": "x", "estado": "Suspendido"}))
revisar(ok is False and detalle == "Suspendido",
        f"POST aceptado + sigue Suspendido -> NO confirmado ({ok}, {detalle})",
        "Un 201 dice que el pedido se acepto, no que el servicio volvio.")

ok, detalle = politicas.confirmar(CONF_COMPLETA, "rapilink", HERR, ARGS,
                                  leer=lector(cliente=RuntimeError("timeout")))
revisar(ok is None,
        f"si no se pudo releer -> ni si ni no ({ok}, {detalle})",
        "None y False no se mezclan: uno manda a revisar la lectura, el otro a "
        "revisar por que el sistema externo no hizo lo que dijo.")

ok, detalle = politicas.confirmar(CONF_COMPLETA, "rapilink", simple_h, ARGS,
                                  leer=lector())
revisar(ok is None and detalle == "sin_politica",
        f"una herramienta sin politica no se confirma ({detalle})")

# El endpoint tiene que DISTINGUIR los tres, no colapsarlos en 'ok'.
fuente_api = (RAIZ / "nucleo" / "canales" / "api.py").read_text(encoding="utf-8")
bloque = fuente_api[fuente_api.index("# ---- PASO 3b"):]
bloque = bloque[:bloque.index("\n#: Lo que se le responde")]
revisar('salida["confirmado"] = confirmado' in bloque,
        "la respuesta lleva 'confirmado' aparte de 'ok'")
revisar("confirmado is False" in bloque and "confirmado is None" in bloque,
        "y distingue 'no quedo activo' de 'no se pudo comprobar'")
codigo_api = "\n".join(l for l in bloque.splitlines()
                       if not l.strip().startswith("#"))
revisar("reintent" not in codigo_api.lower().replace("reintenta:", "").replace("reintenta.", ""),
        "y en ningun lado reintenta el POST",
        "Maximo un POST por accion aprobada: WispHub no permite recuperar una "
        "promesa por referencia, asi que un segundo intento no se podria "
        "reconciliar con el primero.")


# =============================================================================
titulo("13. un solo efecto por accion aprobada")
# =============================================================================
# La garantia no la agrega esta fase: ya la da la reserva condicionada de B5
# (§9.3 paso 1). Se comprueba que siga estando, porque es de lo que depende
# todo lo de arriba.
fuente_db = (RAIZ / "nucleo" / "persistencia" / "db.py").read_text(encoding="utf-8")
cuerpo_reserva = fuente_db[fuente_db.index("def reservar_accion("):]
cuerpo_reserva = cuerpo_reserva[:cuerpo_reserva.index("\ndef ")]
revisar("estado = 'ejecutando'" in cuerpo_reserva
        and "and estado = 'pendiente'" in cuerpo_reserva,
        "la reserva es un UPDATE condicionado a 'pendiente'",
        "Es el candado: dos aprobaciones a la vez, y la segunda no encuentra "
        "nada que reservar.")

bloque_aprobar = fuente_api[fuente_api.index("# ---- PASO 1: reservar"):]
bloque_aprobar = bloque_aprobar[:bloque_aprobar.index("# ---- PASO 3b")]
revisar(bloque_aprobar.index("reservar_accion") < bloque_aprobar.index("revalidar"),
        "y se reserva ANTES de revalidar y de ejecutar",
        "Al reves, dos aprobaciones simultaneas revalidarian las dos y "
        "ejecutarian las dos.")



# =============================================================================
titulo("14. las dos cosas que las mutaciones destaparon")
# =============================================================================
# Dos mutaciones salieron VERDES: apagar la confirmacion del endpoint, y hacer
# que la revalidacion evaluara la politica sin los argumentos de la accion.
# Las dos pasaban porque estas pruebas miraban el TEXTO del archivo en vez de
# lo que las funciones devuelven. Se corrige ejercitandolas.
import ast as _ast                                                # noqa: E402

# --- 14a. la respuesta distingue las cuatro situaciones ------------------
from nucleo.canales import api as api_mod                         # noqa: E402

s = api_mod._salida_ejecutada_ok({"x": 1}, None, None)
revisar(s == {"ok": True, "estado": "ejecutada_ok", "resultado": {"x": 1}},
        "sin confirmacion declarada, la respuesta es la de siempre",
        "Las herramientas que no declaran politica no cambian de forma.")

s = api_mod._salida_ejecutada_ok({}, True, "Activo")
revisar(s["ok"] is True and s["confirmado"] is True and "mensaje" not in s,
        "confirmado -> ok y confirmado, sin advertencia")

s = api_mod._salida_ejecutada_ok({}, False, "Suspendido")
revisar(s["ok"] is True and s["confirmado"] is False and "NO se pudo verificar" in s["mensaje"],
        "aceptado pero NO activo -> ok True y confirmado False",
        "El pedido se acepto de verdad; lo que no ocurrio es el efecto. "
        "Mentir en 'ok' seria peor que el aviso.")

s = api_mod._salida_ejecutada_ok({}, None, "lectura_fallida:Timeout")
revisar(s["confirmado"] is None and "no se pudo comprobar" in s["mensaje"].lower(),
        "no se pudo releer -> confirmado None, y se dice")
revisar("NO se reintenta" in s["mensaje"],
        "y en los dos casos dudosos se dice que NO se reintenta",
        "Un segundo POST no se podria reconciliar con el primero: WispHub no "
        "permite recuperar una promesa por referencia.")

# --- 14b. el endpoint SI llama a confirmar -------------------------------
# Medido sobre el arbol de sintaxis, no buscando una cadena: el comentario que
# explica la confirmacion contiene la palabra y daria un falso verde.
fuente_api = (RAIZ / "nucleo" / "canales" / "api.py").read_text(encoding="utf-8")
arbol = _ast.parse(fuente_api)
llama_confirmar = False
for nodo in _ast.walk(arbol):
    if isinstance(nodo, _ast.FunctionDef) and "aprobar" in nodo.name:
        for hijo in _ast.walk(nodo):
            if isinstance(hijo, _ast.Call) and isinstance(hijo.func, _ast.Name):
                if hijo.func.id == "_confirmar_efecto":
                    llama_confirmar = True
revisar(llama_confirmar,
        "la ruta de aprobacion llama a la guarda de confirmacion",
        "Sin esto, 'confirmado' nunca se calcularia y la respuesta diria que "
        "se hizo apoyandose solo en el 2xx.")

# Pero el arbol ve la llamada aunque este MUERTA. Asi que la guarda se ejecuta.
llamadas_conf = []
real_confirmar = politicas.confirmar


def _espia_confirmar(cfg, ten, herr, args, **kw):
    llamadas_conf.append(herr.nombre)
    return True, "Activo"


try:
    politicas.confirmar = _espia_confirmar
    RESERVADA = {"argumentos": {"id_factura": 147121}}

    r = api_mod._confirmar_efecto(CONF_COMPLETA, "rapilink", HERR, RESERVADA, None)
    revisar(r == (True, "Activo") and llamadas_conf == ["registrar_promesa_y_reactivar"],
            f"con politica y sin error, SI se confirma ({r})")

    llamadas_conf.clear()
    r = api_mod._confirmar_efecto(CONF_COMPLETA, "rapilink", HERR, RESERVADA, "HTTP_500")
    revisar(r == (None, None) and llamadas_conf == [],
            "si el POST fallo, NO se relee",
            "Releer no cambiaria el desenlace y puede confundirlo: el efecto "
            "ya se sabe que no ocurrio, o que quedo incierto.")

    llamadas_conf.clear()
    r = api_mod._confirmar_efecto(CONF_COMPLETA, "rapilink", simple_h, RESERVADA, None)
    revisar(r == (None, None) and llamadas_conf == [],
            "y una herramienta sin politica tampoco",
            "No declara como comprobarse: inventar una comprobacion seria peor.")
finally:
    politicas.confirmar = real_confirmar

# --- 14c. la revalidacion pasa los argumentos DE LA ACCION ---------------
# Antes esto no se ejercitaba: el test inyectaba un doble de politica y la
# funcion real quedaba sin tocar.
vistos = {}
real_evaluar = politicas.evaluar


def _espia_evaluar(cfg, ten, herr, argumentos, **kw):
    vistos["argumentos"] = argumentos
    vistos["historial"] = kw.get("historial")
    return promesas.Veredicto(promesas.ELEGIBLE)


try:
    politicas.evaluar = _espia_evaluar
    revalidacion._evaluar_politica(
        CONF_COMPLETA, "rapilink", HERR,
        {"argumentos": {"id_factura": 147121, "fecha_limite": "2026-10-01"}})
finally:
    politicas.evaluar = real_evaluar

revisar(vistos.get("argumentos") == {"id_factura": 147121,
                                     "fecha_limite": "2026-10-01"},
        f"al revalidar se le pasan los argumentos de la accion ({vistos.get('argumentos')})",
        "De ahi sale sobre que factura es. Sin ellos la politica no sabria que "
        "mirar, y se dejaria pasar cualquier cosa.")
revisar(callable(vistos.get("historial")),
        "y el historial real de Dexter, no un doble vacio")



# =============================================================================
titulo("15. lo que SE ENVIA, no lo que se declara")
# =============================================================================
# La seccion 4 comprueba que 'argumentos_fijos' dice accion=1. Eso es el
# catalogo, no el efecto: entre lo declarado y lo enviado esta
# _resolver_argumentos, y es ahi donde los fijos pisan lo del modelo.
#
# La hermana simple ya se prueba asi en test_b5_promesa_accion.py; esta no se
# probaba, y era la que puede reactivar un servicio.
ACTIVA = 1

for etiqueta, propuesta in (
        ("el modelo no manda accion",
         {"id_factura": 147121, "fecha_limite": "2026-10-01"}),
        ("el modelo manda la simple",
         {"id_factura": 147121, "fecha_limite": "2026-10-01",
          "accion": "registrar_promesa"}),
        ("el modelo manda 0 crudo",
         {"id_factura": 147121, "fecha_limite": "2026-10-01", "accion": 0}),
        ("el modelo manda '0' como texto",
         {"id_factura": 147121, "fecha_limite": "2026-10-01", "accion": "0"}),
        ("el modelo inventa un valor",
         {"id_factura": 147121, "fecha_limite": "2026-10-01", "accion": "solo_registrar"}),
):
    args = motor._resolver_argumentos(HERR, None, propuesta)
    revisar(args.get("accion") == ACTIVA,
            f"{etiqueta} -> se envia accion={args.get('accion')!r}",
            "Los fijos pisan lo del modelo. Si esto fallara, el modelo podria "
            "convertir esta accion en la simple sin que nadie lo note -- y el "
            "cliente se quedaria sin internet despues de que le dijeron que "
            "se lo reconectaban.")

# Y los argumentos que SI decide el modelo llegan intactos.
args = motor._resolver_argumentos(
    HERR, None, {"id_factura": 147121, "fecha_limite": "2026-10-01",
                 "comentarios": "acordado por telefono"})
revisar(args.get("id_factura") == 147121
        and args.get("fecha_limite") == "2026-10-01"
        and args.get("comentarios") == "acordado por telefono",
        "y lo que el modelo si decide llega sin tocar")

# Las dos herramientas mandan valores OPUESTOS, y ninguna los mezcla.
args_simple = motor._resolver_argumentos(
    simple_h, None, {"id_factura": 1, "fecha_limite": "2026-10-01",
                     "accion": "registrar_promesa_y_activar_servicio"})
revisar(args_simple.get("accion") == 0,
        f"la simple sigue enviando 0 aunque le pidan la otra ({args_simple.get('accion')})",
        "Son dos acciones distintas justamente para que ninguna pueda "
        "convertirse en la otra.")

print()
if fallos:
    print(f"  {len(fallos)} FALLA(S):")
    for f in fallos:
        print(f"    - {f}")
    sys.exit(1)
print("  [OK] La politica decide con hechos, y quien aprueba ve los dos efectos.")
