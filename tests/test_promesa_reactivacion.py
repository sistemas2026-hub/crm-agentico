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

print()
if fallos:
    print(f"  {len(fallos)} FALLA(S):")
    for f in fallos:
        print(f"    - {f}")
    sys.exit(1)
print("  [OK] La politica decide con hechos, y quien aprueba ve los dos efectos.")
