# -*- coding: utf-8 -*-
"""
================================================================================
 LO QUE PASA EN CAMPO SE ESCRIBE EN EL TICKET DEL ISP, SIN CERRARLO -- 06/11/2026
================================================================================
El usuario, describiendo como ya trabajan: *"actualmente en wisphub el tecnico
envia por wisphub el reporte por el ticket y le pide al encargado revisar y el
deja escrito en el ticket la revision"*.

Hasta hoy el ticket del ISP **no se enteraba de nada hasta el cierre**. Si el
Supervisor tardaba dos dias, quien miraba WispHub veia un ticket "Nuevo" con el
plazo vencido mientras el trabajo ya estaba hecho. Es el mismo defecto que
`campo/devolver_al_ticket.py` arreglo el 02/11 del lado del CRM y que nadie
habia extendido al proveedor.

POR QUE UN MODULO APARTE DE `cierre_por_validacion`
--------------------------------------------------
Comparte el molde --herramienta operativa del catalogo, puerta autonoma,
exencion nombrada, idempotencia, firma-- pero responde otra pregunta. Aquella
CIERRA; esta ANOTA y deja el ticket En Progreso. Meterlas juntas obligaria a
`ResultadoCierreTicket` a significar dos cosas, y el dia que una de las dos
cambie de reglas la otra se arrastra.

LA CLAVE IDEMPOTENTE CUENTA LAS VUELTAS, Y ES EL PUNTO FINO
-----------------------------------------------------------
Un reintento no puede publicar dos notas iguales. Pero esto SI tiene que poder
escribir varias veces en el mismo ticket:

    vuelta 1  el tecnico manda su reporte          -> una nota
              el Supervisor lo devuelve            -> otra nota
    vuelta 2  el tecnico manda el reporte de nuevo -> otra nota mas

Las tres son legitimas y ninguna es un duplicado. Si la clave fuera solo la
orden --como en el cierre, donde una orden se cierra una vez y nada mas-- la
segunda y la tercera se descartarian EN SILENCIO con 'operacion ya ejecutada',
y el ticket se quedaria con el primer reporte para siempre. Por eso la clave
lleva `momento` y `vuelta`, y por eso las dos son obligatorias.

LO QUE NO HACE
--------------
**No cierra el ticket.** El estado lo fija la herramienta
(`argumentos_fijos: ticket-estado: "2"`, En Progreso) y esta ruta no lo acepta
como argumento. Cerrar es la otra puerta, con su propia exencion.

**No redacta.** El texto llega armado por el CRM a partir de la PLANTILLA de la
orden (`campo/services/cierre_en_isp.py::resumen_de`, que pasa cada valor por
`tapar`). El modelo no escribe aca, y esa es justamente la premisa de la
exencion que abre esta puerta: ver `frontera.NOTA_DE_CAMPO_EN_EL_TICKET`.

**No promete que el tercero lo aplico.** Si la llamada salio y la respuesta se
perdio, nadie sabe si WispHub la escribio. Es el limite que
`asistente.operaciones_externas` tiene documentado y no se arregla aca.
================================================================================
"""
from __future__ import annotations

from dataclasses import dataclass

#: Quien pide la anotacion, para la bitacora de ejecucion autonoma.
ACTOR = "campo"

#: Como se firma cada momento DENTRO del texto.
#
#  Hace falta porque el proveedor firma toda respuesta con la cuenta de la API
#  key --verificado: quedan como 'Rapilink SAS - admin@...' sin importar quien
#  las origino-- asi que sin el nombre adentro del texto el historico del
#  ticket dice que contesto el sistema. Ver `operativo._firmado`.
FIRMA_DE_CAMPO = "Tecnico de campo (Dexter)"
FIRMA_DEL_SUPERVISOR = "Supervisor de Dexter"

#  ---------------------------------------------------------------------------
#   LOS MOMENTOS
#  ---------------------------------------------------------------------------
#  Cerrado a proposito: el `momento` entra en la CLAVE idempotente, asi que un
#  valor libre significaria que quien llama puede fabricarse una clave nueva
#  por intento. Eso seria un identificador unico, no una clave idempotente --
#  la misma leccion que CLAUDE.md §12 dejo escrita para `origen`.
REPORTE_DEL_TECNICO = "reporte_del_tecnico"
DEVUELTA_AL_TECNICO = "devuelta_al_tecnico"

#: El Supervisor reviso y NO cerro, pero tampoco devolvio: quedo una duda que
#: solo una persona puede resolver.
#
#  POR QUE UN TERCER MOMENTO Y NO REUSAR LA DEVOLUCION  --  06/11/2026
#  -------------------------------------------------------------------
#  Porque son hechos distintos y el ticket tiene que distinguirlos. «Vuelve a
#  campo» le dice al tecnico que hay algo que rehacer; «quedo para revision»
#  dice que nadie encontro un error y que una persona va a mirar. Usar el
#  mismo momento para los dos, ademas de mentir, compartiria la clave
#  idempotente: una orden que primero queda en duda y despues se devuelve
#  escribiria una sola vez.
REVISION_SIN_CIERRE = "revision_sin_cierre"

MOMENTOS = {
    REPORTE_DEL_TECNICO: FIRMA_DE_CAMPO,
    DEVUELTA_AL_TECNICO: FIRMA_DEL_SUPERVISOR,
    REVISION_SIN_CIERRE: FIRMA_DEL_SUPERVISOR,
}

#  Codigos del resultado. 'ANOTADA' es el unico que afirma que el texto quedo
#  escrito del otro lado; los demas dicen por que no, y 'INCIERTO' dice que no
#  se sabe, que no es lo mismo que 'no'.
ANOTADA = "anotada"
YA_ANOTADA = "ya_anotada"
SIN_HERRAMIENTA = "sin_herramienta"
NO_AUTORIZADA = "no_autorizada"
FALTAN_DATOS = "faltan_datos"
MOMENTO_DESCONOCIDO = "momento_desconocido"
FALLO = "fallo"
INCIERTO = "incierto"
#: No se ejecuto, y se sabe que no: la base no contesto, falta la migracion,
#: o el registro dijo que no. Distinto de INCIERTO, donde la llamada pudo
#: haber salido.
NO_EJECUTADA = "no_ejecutada"
#: La vuelta no es un entero. Se dice aparte de FALTAN_DATOS porque la causa
#: es otra: no es que no vino, es que no se puede usar como clave.
VUELTA_INVALIDA = "vuelta_invalida"
#: La herramienta que anota pide lo mismo que la que cierra. Falla cerrado:
#: ver `_pide_lo_mismo_que_el_cierre`.
ANOTARIA_UN_CIERRE = "anotaria_un_cierre"


@dataclass
class ResultadoNota:
    codigo: str
    detalle: str = ""
    referencia: str = ""

    @property
    def anotada(self) -> bool:
        """Solo cuando el texto quedo escrito. 'ya_anotada' tambien cuenta: el
        efecto que se pidio existe del otro lado, y es lo que importa."""
        return self.codigo in (ANOTADA, YA_ANOTADA)

    def como_dict(self) -> dict:
        return {"codigo": self.codigo, "anotada": self.anotada,
                "detalle": self.detalle, "referencia": self.referencia}


def _herramienta_que_anota(config):
    """La que el tenant declare con 'responde_ticket_operativo'.

    LA CAPACIDAD, NO EL NOMBRE: cada empresa llama a sus herramientas como
    quiere, y el nucleo no conoce a ningun cliente (CLAUDE.md §3.1). Mismo
    criterio que `_herramienta_de_cierre`.
    """
    for h in getattr(config, "herramientas", None) or []:
        if getattr(h, "responde_ticket_operativo", False):
            return h
    return None


def _pide_lo_mismo_que_el_cierre(config, herr) -> bool:
    """Si la herramienta que ANOTA le pide al proveedor lo mismo que la que
    CIERRA.

    POR QUE EXISTE  --  H7, auditoria de frontera 06/11/2026
    -------------------------------------------------------
    La ruta del motor rechaza que quien llama elija el estado del ticket, y el
    docstring afirma que "esto no puede convertirse en un cierre". Eso era
    cierto por la peticion y falso por la CONFIGURACION: el estado sale de
    `argumentos_fijos` del catalogo, y un tenant que pusiera ahi el estado de
    cierre cerraria tickets por la exencion de la nota -- salteandose la
    exencion del cierre, que es otra, y su nivel.

    COMO SE DECIDE SIN CONOCER A WISPHUB. El nucleo no puede saber que "4"
    significa cerrado: eso es del proveedor y cada ISP tiene los suyos
    (CLAUDE.md §3.1). Lo que SI puede es comparar las dos herramientas del
    MISMO tenant: si la que anota le manda al proveedor exactamente lo mismo
    que la que cierra, entonces hace lo mismo, se llame como se llame. El
    conocimiento del proveedor se queda donde vive, que es la configuracion.

    Devuelve False cuando el tenant no declara ninguna herramienta de cierre:
    sin con que comparar no se puede afirmar que sean iguales, y esto acota,
    no autoriza.
    """
    cierre = next((h for h in getattr(config, "herramientas", None) or []
                   if getattr(h, "cierra_ticket_operativo", False)), None)
    if cierre is None or cierre is herr:
        return False
    fijos_nota = dict(getattr(herr, "argumentos_fijos", None) or {})
    fijos_cierre = dict(getattr(cierre, "argumentos_fijos", None) or {})
    if not fijos_nota or not fijos_cierre:
        return False
    return fijos_nota == fijos_cierre


def anotar(config, tenant: str, *, orden_id: str, ticket: str, texto: str,
           momento: str, vuelta, actor: str = "") -> ResultadoNota:
    """Escribe `texto` en el ticket del ISP y lo deja En Progreso.

    Por la puerta AUTONOMA, con la exencion `NOTA_DE_CAMPO_EN_EL_TICKET`: a lo
    sumo una vez por (orden, momento, vuelta).

    `vuelta` identifica el ciclo. Es obligatoria por la misma razon por la que
    `revision` lo es en el cierre, pero al reves: alla sirve para que la
    auditoria pueda mirar, aca para que una escritura legitima no se confunda
    con un reintento.
    """
    from nucleo.herramientas import http as ejecutor_http
    from nucleo.seguimiento.operativo import _firmado
    from nucleo.seguridad import frontera, idempotencia
    from nucleo.seguridad import techo as techos

    orden_id = str(orden_id or "").strip()
    ticket = str(ticket or "").strip()
    texto = str(texto or "").strip()
    momento = str(momento or "").strip()
    #  LA VUELTA SE NORMALIZA A ENTERO  --  H5, auditoria de frontera
    #  06/11/2026
    #
    #  Antes era `str(vuelta).strip()`, y con eso `1`, `"1"`, `" 1 "`, `1.0`,
    #  `True`, `"1.0"` y `"01"` producian hasta CINCO claves distintas para la
    #  misma vuelta -- medido con una sonda. Este modulo cierra esa puerta para
    #  `momento` con el motivo escrito arriba, y la dejaba abierta para el otro
    #  campo de la misma clave. Hoy la garantia la aportaba enteramente el
    #  llamador (`nota_al_isp._vuelta_de` manda un int); un segundo llamador,
    #  o un cliente JSON que mande `1.0`, duplicaba la nota sin que nada avise.
    #
    #  `bool` se rechaza aparte: en Python `True` es un entero y pasaria como
    #  vuelta 1, que no es un ciclo que nadie pidio.
    if isinstance(vuelta, bool):
        vuelta = None
    try:
        vuelta = "" if vuelta is None else str(int(str(vuelta).strip()))
    except (TypeError, ValueError):
        return ResultadoNota(
            VUELTA_INVALIDA,
            f"la vuelta tiene que ser un entero y llego {vuelta!r}: entra en "
            f"la clave que evita publicar dos veces, y un valor libre deja "
            f"fabricar una clave nueva por intento")

    if not orden_id or not ticket or not texto or not vuelta:
        return ResultadoNota(
            FALTAN_DATOS,
            "hacen falta la orden, el ticket, el texto y la vuelta: sin la "
            "ultima, el segundo reporte de la misma orden se descartaria como "
            "si fuera un reintento")
    if momento not in MOMENTOS:
        return ResultadoNota(
            MOMENTO_DESCONOCIDO,
            f"'{momento}' no es un momento que este codigo declare "
            f"({sorted(MOMENTOS)}). Un momento libre dejaria fabricar una "
            f"clave nueva por intento, que no es una clave idempotente")

    herr = _herramienta_que_anota(config)
    if herr is None:
        return ResultadoNota(
            SIN_HERRAMIENTA,
            "el tenant no declara ninguna herramienta con "
            "'responde_ticket_operativo'")

    #  ANTES DE ARMAR NADA (H7): si esta herramienta le pide al proveedor lo
    #  mismo que la que cierra, no es una nota -- y saldria por la exencion
    #  equivocada.
    if _pide_lo_mismo_que_el_cierre(config, herr):
        return ResultadoNota(
            ANOTARIA_UN_CIERRE,
            f"'{herr.nombre}' le manda al proveedor lo mismo que la "
            f"herramienta de cierre: eso cerraria el ticket por la exencion "
            f"de las notas, que no es la del cierre ni exige su nivel")

    argumentos = dict(herr.argumentos_fijos or {})
    argumentos.update({"id_ticket": ticket,
                       "respuesta": _firmado(texto, _firma_de(momento, actor))})

    origen = f"nota_de_campo:{orden_id}|{momento}|{vuelta}"
    #  LA CLAVE LLEVA EL MOMENTO Y LA VUELTA. Ver la cabecera: sin eso, el
    #  reporte de la vuelta 2 se descarta en silencio.
    clave = f"nota_de_campo:{orden_id}|{momento}|{vuelta}|{herr.nombre}"

    def _hacer():
        return ejecutor_http.ejecutar(herr, argumentos, tenant,
                                      variables_tenant=config.variables_tenant)

    try:
        #  El nivel y el efecto salen del CATALOGO: nadie que llame puede
        #  bajarse la exigencia.
        with frontera.autonoma(tenant, herr.nombre, origen=origen, actor=ACTOR,
                               nivel_requerido=techos.nivel_requerido_de(herr),
                               efecto_externo=frontera.efecto_externo(herr),
                               exencion=frontera.NOTA_DE_CAMPO_EN_EL_TICKET):
            #  LA APROBACION, PREGUNTADA ANTES DE RECLAMAR LA CLAVE. El ultimo
            #  metro la vuelve a comprobar --ahi vive el control-- pero si se
            #  llegara hasta alla, el rechazo quemaria el intento como
            #  'OPERACION_FALLIDA_PREVIA' y esta nota no se podria reintentar
            #  nunca. Misma leccion que el cierre (H1, 30/10/2026).
            if (getattr(herr, "aprobacion_humana", False)
                    and not frontera.exime_la_aprobacion(
                        herr, frontera.NOTA_DE_CAMPO_EN_EL_TICKET)):
                raise frontera.AccionExternaNoAutorizada(
                    herr.nombre, frontera.APROBACION_REQUERIDA,
                    f"'{herr.nombre}' declara aprobacion humana y el tenant no "
                    f"la eximio para las notas de campo: agregar "
                    f"'aprobacion_humana_salvo: "
                    f"[{frontera.NOTA_DE_CAMPO_EN_EL_TICKET}]' a la herramienta")
            resultado = idempotencia.ejecutar(
                tenant, herr.nombre, argumentos, origen, _hacer, clave=clave)
    except frontera.AccionExternaNoAutorizada as e:
        return ResultadoNota(NO_AUTORIZADA, f"{e.codigo}: {e.motivo}",
                             referencia=origen)
    except Exception as e:                                      # noqa: BLE001
        #  Sin `str(e)`: por tipo y nada mas (CLAUDE.md §5). Un mensaje de
        #  excepcion de un cliente HTTP puede traer la URL con la clave.
        import requests

        #  UN TIMEOUT NO ES UN FALLO  --  H4, auditoria de frontera 06/11/2026
        #
        #  Si la llamada salio y la respuesta se perdio, el texto puede estar
        #  escrito del otro lado. La cabecera de este modulo lo declara con
        #  todas las letras y el codigo lo negaba: devolvia 'fallo', que afirma
        #  que no paso nada. Es la misma distincion que ya hacia
        #  `cierre_por_validacion` (30/10/2026) y que la copia perdio.
        #
        #  Importa para el dia que alguien construya un reintento: sobre
        #  'fallo' reintentaria y publicaria dos veces; sobre 'incierto' tiene
        #  que ir a mirar el sistema del ISP.
        if isinstance(e, (requests.exceptions.Timeout,
                          requests.exceptions.ConnectionError)):
            return ResultadoNota(
                INCIERTO,
                f"{type(e).__name__}: no se sabe si quedo escrito en el ISP; "
                f"hay que mirarlo en su sistema", referencia=origen)
        return ResultadoNota(FALLO, f"{type(e).__name__} al anotar en el ticket",
                             referencia=origen)

    if not resultado.ejecutada:
        codigo = resultado.codigo or resultado.decision or ""
        if codigo in (idempotencia.EN_CURSO, idempotencia.FALLIDA_PREVIA,
                      idempotencia.CLAVE_REUTILIZADA):
            #  NO SE SABE, que no es 'no'. Si la llamada salio y la respuesta
            #  se perdio, el texto puede estar escrito del otro lado.
            return ResultadoNota(
                INCIERTO,
                f"{codigo}: no se sabe si quedo escrito en el ISP; hay que "
                f"mirarlo en su sistema", referencia=origen)
        #  LA RAMA POR DEFECTO ES NEGATIVA  --  H1, auditoria de frontera
        #  06/11/2026
        #
        #  Antes era al reves, y eso producia un FALSO VERDE medido con una
        #  sonda: `idempotencia.ejecutar` devuelve `ejecutada=False` tambien
        #  con SIN_REGISTRO --la base no contesta-- y CONTROL_AUSENTE --falta
        #  la migracion de `asistente.operaciones_externas`--. En los dos el
        #  efecto NO OCURRIO: cero llamadas al ISP. Con la rama optimista por
        #  defecto, los dos salian como 'ya_anotada' -> anotada=True -> la
        #  ruta contestaba HTTP 200, el CRM se quedaba tranquilo y el ticket
        #  de WispHub no se enteraba nunca.
        #
        #  El modulo del que esto se copio hace lo contrario
        #  (`cierre_por_validacion.py`: NO_EJECUTADA / cerrado=False). Al
        #  copiarlo se invirtio la rama por defecto, que es justo el lado
        #  donde la equivocacion afirma un efecto que no paso.
        #
        #  SOLO 'repetida' afirma que el efecto existe. Es la unica decision
        #  del registro que significa "esto ya se hizo y salio bien"; todo lo
        #  demas, conocido o no, es que no se hizo.
        #  `hubo_respuesta` es la propiedad del propio `Resultado`
        #  (idempotencia.py:123-125): `ejecutada or decision == "repetida"`.
        #  Se usa esa y no una lista de codigos a mano, para que el dia que
        #  el registro agregue una decision nueva, la clasificacion viva en
        #  un solo lugar y no en dos que se desincronizan.
        if resultado.hubo_respuesta:
            return ResultadoNota(YA_ANOTADA, codigo or "ya estaba anotada",
                                 referencia=origen)
        return ResultadoNota(
            NO_EJECUTADA,
            f"{codigo or 'sin codigo'}: no se ejecuto y nada quedo escrito "
            f"en el ISP", referencia=origen)

    return ResultadoNota(ANOTADA, referencia=origen)


def _firma_de(momento: str, actor: str) -> str:
    """Con que nombre queda firmado el texto adentro del ticket.

    El `actor` --el nombre de quien lo hizo-- solo se usa en el reporte del
    tecnico, que es donde hoy una persona firma a mano en WispHub. En la
    devolucion no: ahi decide el Supervisor, y poner el nombre de quien
    apreto el boton diria algo que no es.

    Nunca un correo: el CRM manda el NOMBRE y cae a vacio cuando no lo tiene
    (ver `cierre_en_isp`), asi que aca un `actor` vacio usa la firma del
    momento y no se inventa nada.
    """
    #  `.get` Y NO `MOMENTOS[momento]`  --  06/11/2026
    #
    #  Lo encontro una mutacion: al desactivar el chequeo de `momento` de mas
    #  arriba, esta linea levantaba `KeyError` ANTES del `try` que envuelve el
    #  resto, asi que el modulo salia con una excepcion cruda en vez de un
    #  codigo. Hoy no puede pasar --el momento se valida antes-- pero eso es
    #  una invariante que vive en OTRA funcion, y el dia que alguien la mueva
    #  el sintoma es un 500 del motor y no un 400 con su motivo.
    #
    #  El fallback NO inventa una firma: queda la del Supervisor, que es la
    #  mas conservadora de las dos --no le atribuye a nadie un reporte que no
    #  escribio-- y de todos modos un momento sin declarar no llega hasta aca.
    base = MOMENTOS.get(momento) or FIRMA_DEL_SUPERVISOR
    actor = (actor or "").strip()
    if momento == REPORTE_DEL_TECNICO and actor:
        return f"{actor} ({base})"
    return base
