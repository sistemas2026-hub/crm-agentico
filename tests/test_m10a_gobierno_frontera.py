# -*- coding: utf-8 -*-
"""
================================================================================
 M10-A  --  gobierno, seguridad y frontera de ejecucion
================================================================================

Este archivo NO agrega un control nuevo. Fija por escrito la CLASIFICACION DE
RIESGO de cada herramienta de escritura y comprueba que el catalogo no se mueva
sin que alguien lo decida.

POR QUE UNA CLASIFICACION EN UNA PRUEBA Y NO EN EL CONFIG
---------------------------------------------------------
Porque el criterio es una decision de gobierno, no un dato del tenant, y
porque asi una herramienta nueva ROMPE esta prueba en vez de entrar en silencio.
Es el mismo mecanismo que el inventario de rutas de M09-F, que ya cazo cuatro
rutas nuevas en los ultimos pasos.

EL CRITERIO, Y POR QUE ES ESE
-----------------------------
Se clasifica por EFECTO REAL --que le pasa al mundo si la herramienta corre--
y no por el nombre:

  R0  lectura          'solo_lectura=True'. No cambia nada.
  R1  interno          escribe, pero 'tipo=interno': el motor lo resuelve solo,
                       sin salir a ninguna API. Reversible y sin tercero.
  R2  registro externo crea o modifica un REGISTRO en un sistema externo
                       (ticket, caso, tag, solicitud). Tiene efecto afuera,
                       pero se deshace con otra operacion de registro.
  R3  equipo fisico    actua sobre el EQUIPO EN CASA DEL CLIENTE. No se
                       deshace: un reinicio no se des-reinicia, y mientras
                       tanto el cliente no tiene servicio.
  R4  dinero           altera la CUENTA del cliente. Revertir un pago no es
                       una llamada de API, es una operacion contable.

R3 y R4 no estan arriba por ser "importantes" en abstracto: estan arriba porque
su efecto no lo puede deshacer el mismo sistema que lo produjo.

LO QUE ESTA PRUEBA ENCONTRO, Y NO ARREGLA
-----------------------------------------
Las barreras declaradas NO estan alineadas con el riesgo. 'aprobacion_humana'
es opt-in y nacio de un caso concreto (tickets de WispHub, 18/08/2026), asi que
quedo donde ese caso la pidio --las cuatro son R2-- y no donde el efecto es
peor. 'registrar_pago', la unica herramienta que toca dinero sin ninguna
barrera propia, es el ejemplo. Eso se REPORTA; ponerle un gate es una decision
de negocio, no una correccion tecnica.
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo.config import cargar_config                          # noqa: E402
from nucleo.seguridad import frontera                            # noqa: E402

CONFIG = cargar_config(RAIZ / "tenants" / "rapilink.config.yaml")

FALLOS: list[str] = []


def afirmar(condicion: bool, que: str, detalle: str = "") -> None:
    if condicion:
        print(f"  [ok]    {que}")
    else:
        FALLOS.append(que)
        print(f"  [FALLA] {que}")
        if detalle:
            print(f"          {detalle}")


def seccion(titulo: str) -> None:
    print()
    print("-" * 78)
    print(f"  {titulo}")
    print("-" * 78)


# =============================================================================
#  LA CLASIFICACION
# =============================================================================

R1_INTERNO = {
    "registrar_pedido_wifi",
    "reportar_comprobante_pago",
    "proponer_herramienta",
}

R2_REGISTRO_EXTERNO = {
    "actualizar_estado_ticket",
    "agendar_visita_internet",
    "agendar_visita_tecnica",
    "cancelar_solicitud_servicio",
    "cerrar_caso_crm",
    "cerrar_ticket_operativo",
    #  M06-F (22/09/2026): llegaron en origin despues de M10-A. Las dos
    #  registran afuera como sus hermanas: asignar_caso_crm como
    #  cerrar_caso_crm (el CRM), cerrar_ticket_operativo_estado como
    #  cerrar_ticket_operativo (el ticket del ISP).
    "asignar_caso_crm",
    "cerrar_ticket_operativo_estado",
    "completar_ticket_instalacion",
    "crear_caso_soporte",
    "crear_tag_crm",
    "crear_ticket",
    "crear_ticket_caso",
    "crear_ticket_instalacion",
    "importar_caso_externo",
    "reasignar_ticket_instalacion",
    "reconciliar_caso_externo",
    "registrar_solicitud_servicio",
    "responder_ticket",
    "responder_ticket_operativo",
    "sincronizar_respuestas_externas",
}

#  Las tres de SmartOLT. Actuan sobre la ONU en la casa del cliente.
R3_EQUIPO_FISICO = {
    "reiniciar_ont",
    "cambiar_tipo_onu",
    "activar_catv",
}

#  Las dos que mueven la cuenta del cliente.
R4_DINERO = {
    "registrar_pago",
    "agregar_promesa_pago",
    #  M06-F: registra una promesa (el efecto de agregar_promesa_pago) y ademas
    #  reactiva el servicio. Llego en origin despues de M10-A.
    "registrar_promesa_y_reactivar",
}

CLASES = {"R1": R1_INTERNO, "R2": R2_REGISTRO_EXTERNO,
          "R3": R3_EQUIPO_FISICO, "R4": R4_DINERO}


def clase_de(nombre: str) -> str | None:
    for etiqueta, conjunto in CLASES.items():
        if nombre in conjunto:
            return etiqueta
    return None


# =============================================================================
def main() -> int:
    herramientas = list(CONFIG.herramientas)
    escrituras = [h for h in herramientas if not h.solo_lectura]
    lecturas = [h for h in herramientas if h.solo_lectura]

    print("=" * 78)
    print("  M10-A  --  clasificacion de riesgo y frontera de ejecucion")
    print("=" * 78)
    print(f"  herramientas: {len(herramientas)}   "
          f"lectura (R0): {len(lecturas)}   escritura: {len(escrituras)}")

    # -------------------------------------------------------------- 1
    seccion("1. TODA ESCRITURA ESTA CLASIFICADA")
    sin_clasificar = sorted(h.nombre for h in escrituras
                            if clase_de(h.nombre) is None)
    afirmar(
        not sin_clasificar,
        "ninguna herramienta de escritura quedo sin clase de riesgo",
        f"sin clasificar: {sin_clasificar}. Agregar una herramienta obliga a "
        f"decidir su riesgo, no a heredarlo por descuido.")

    nombres = {h.nombre for h in escrituras}
    sobran = sorted(n for c in CLASES.values() for n in c if n not in nombres)
    afirmar(not sobran,
            "la clasificacion no nombra herramientas que ya no existen",
            f"sobran: {sobran}")

    # -------------------------------------------------------------- 2
    seccion("2. R0 ES R0: NINGUNA LECTURA ESCRIBE")
    lecturas_mal = sorted(h.nombre for h in lecturas
                          if clase_de(h.nombre) is not None)
    afirmar(not lecturas_mal,
            "ninguna herramienta de solo lectura aparece clasificada como escritura",
            f"{lecturas_mal}")
    afirmar(not any(frontera.escribe(h) for h in lecturas),
            "la frontera coincide: ninguna lectura cuenta como escritura")

    # -------------------------------------------------------------- 3
    seccion("3. LA FRONTERA CUBRE TODA ESCRITURA")
    sin_frontera = sorted(h.nombre for h in escrituras
                          if not frontera.escribe(h))
    afirmar(not sin_frontera,
            "toda herramienta de escritura pasa por la frontera de efecto externo",
            f"sin cubrir: {sin_frontera}")

    # -------------------------------------------------------------- 4
    seccion("4. NINGUNA HERRAMIENTA BORRA")
    #  La API de WispHub SI permite borrar un cliente
    #  (DELETE /api/clientes/{id}/perfil/, verificado end-to-end). La unica
    #  proteccion es que ninguna herramienta lo declare: el catalogo es lista
    #  blanca. Esto lo comprueba.
    borran = sorted(h.nombre for h in herramientas
                    if (getattr(h, "metodo", "") or "").upper() == "DELETE")
    afirmar(not borran,
            "ninguna herramienta declara DELETE",
            f"{borran} -- el catalogo es lista blanca y borrar no esta en ella")

    # -------------------------------------------------------------- 5
    seccion("5. R3 Y R4 NO PUEDEN SER INVOCADAS POR UN SERVICIO")
    #  'invocable_por_servicio' habilita la ruta interna /interno, que no pasa
    #  por una conversacion. Lo mas irreversible no debe tener esa puerta.
    expuestas = sorted(
        h.nombre for h in escrituras
        if clase_de(h.nombre) in ("R3", "R4")
        and getattr(h, "invocable_por_servicio", False))
    afirmar(not expuestas,
            "ninguna R3/R4 es invocable por la ruta interna de servicio",
            f"{expuestas}")

    # -------------------------------------------------------------- 6
    seccion("6. LAS BARRERAS DECLARADAS, TAL COMO ESTAN")
    por_clase: dict[str, list] = {}
    for h in escrituras:
        por_clase.setdefault(clase_de(h.nombre), []).append(h)

    print(f"  {'clase':6} {'n':>3}  {'aprobacion_humana':>18} {'exige_previas':>14}"
          f"   sin ninguna")
    for etiqueta in ("R1", "R2", "R3", "R4"):
        grupo = por_clase.get(etiqueta, [])
        aprob = [h.nombre for h in grupo if h.aprobacion_humana]
        prev = [h.nombre for h in grupo if getattr(h, "exige_previas", None)]
        solas = [h.nombre for h in grupo
                 if not h.aprobacion_humana and not getattr(h, "exige_previas", None)]
        print(f"  {etiqueta:6} {len(grupo):>3}  {len(aprob):>18} {len(prev):>14}"
              f"   {len(solas)}")

    #  Las tres R3 tienen previas: es el unico sitio donde barrera y riesgo
    #  coinciden hoy, y conviene que no se pierda.
    r3_sin_previas = sorted(h.nombre for h in por_clase.get("R3", [])
                            if not getattr(h, "exige_previas", None))
    afirmar(not r3_sin_previas,
            "las tres R3 (equipo fisico) conservan sus condiciones previas",
            f"sin previas: {r3_sin_previas}")

    #  Y el hallazgo que este paso existe para dejar por escrito. NO se
    #  convierte en una falla: poner un gate es decision de negocio. Pero si
    #  ALGUIEN se lo pone, esta linea lo celebra en vez de romperse.
    r4_sin_barrera = sorted(
        h.nombre for h in por_clase.get("R4", [])
        if not h.aprobacion_humana and not getattr(h, "exige_previas", None))
    print()
    if r4_sin_barrera:
        print(f"  [BRECHA CONOCIDA] R4 sin barrera propia: {r4_sin_barrera}")
        print( "                    Siguen protegidas por el interruptor y la")
        print( "                    frontera, pero no por un gate por herramienta.")
        print( "                    Ponerselo es una decision de negocio (M10-A §17).")
    else:
        print("  [ok]    todas las R4 tienen barrera propia")

    # -------------------------------------------------------------- 7
    seccion("7. 'requiere_confirmacion' NO ES UNA BARRERA DE EJECUCION")
    #  Lo declaran las 27 escrituras porque el validador lo exige para poder
    #  guardarse, y nunca se evalua en ejecucion. Confundirlo con un gate es
    #  exactamente el error que esta linea impide.
    con_confirmacion = [h.nombre for h in escrituras if h.requiere_confirmacion]
    afirmar(len(con_confirmacion) == len(escrituras),
            "'requiere_confirmacion' esta en TODAS las escrituras -- no distingue "
            "riesgo y no puede usarse como autorizacion",
            f"{len(con_confirmacion)} de {len(escrituras)}")

    # -------------------------------------------------------------- 8
    seccion("8. AUTONOMIA ES TECHO, NO AUTORIZACION")
    from nucleo.seguridad import interruptor
    #  'es_accion_autonoma' mira 'solo_lectura', NO 'requiere_confirmacion'.
    for h in escrituras[:3]:
        afirmar(interruptor.es_accion_autonoma(h),
                f"'{h.nombre}' cuenta como accion autonoma sin humano detras")
        afirmar(not interruptor.es_accion_autonoma(h, aprobada_por_humano=True),
                f"'{h.nombre}' deja de serlo cuando la aprobo una persona")
    for h in lecturas[:2]:
        afirmar(not interruptor.es_accion_autonoma(h),
                f"'{h.nombre}' (lectura) nunca cuenta como accion autonoma")

    # -------------------------------------------------------------- 9
    seccion("9. LA FRONTERA NO SE ABRE SOLA")
    afirmar(frontera.permiso_vigente() is None,
            "fuera de una puerta no hay permiso vigente")
    try:
        with frontera.humana("rapilink", "crear_ticket", actor="", evidencia="x"):
            afirmar(False, "humana() abrio sin actor")
    except frontera.AccionExternaNoAutorizada:
        afirmar(True, "humana() se niega a abrir sin actor identificado")
    try:
        with frontera.humana("rapilink", "crear_ticket", actor="ana",
                             evidencia=""):
            afirmar(False, "humana() abrio sin evidencia")
    except frontera.AccionExternaNoAutorizada:
        afirmar(True, "humana() se niega a abrir sin evidencia comprobable")
    try:
        with frontera.autonoma("", "crear_ticket"):
            afirmar(False, "autonoma() abrio sin tenant")
    except frontera.AccionExternaNoAutorizada:
        afirmar(True, "autonoma() se niega a abrir sin tenant valido")
    afirmar(frontera.permiso_vigente() is None,
            "despues de los intentos fallidos sigue sin haber permiso")

    # -------------------------------------------------------------- 10
    seccion("10. RESUMEN DE LA MATRIZ")
    for etiqueta in ("R1", "R2", "R3", "R4"):
        grupo = sorted(h.nombre for h in por_clase.get(etiqueta, []))
        print(f"  {etiqueta}: {len(grupo):>2}  {', '.join(grupo[:4])}"
              f"{' ...' if len(grupo) > 4 else ''}")

    print()
    print("=" * 78)
    if FALLOS:
        print(f"[FALLA] {len(FALLOS)} comprobacion(es):")
        for f in FALLOS:
            print(f"   - {f}")
        return 1
    print("[OK] El catalogo esta clasificado, la frontera lo cubre entero, y")
    print("     ninguna puerta se abre sola.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
