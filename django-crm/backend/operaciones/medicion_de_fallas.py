"""
================================================================================
 LA MEDICION DE LAS FALLAS PENDIENTES  --  16/10/2026, Fase 3
================================================================================

QUE HACE
--------
Para cada lectura pendiente de una falla de servicio, le pide al motor el
estado del equipo ('diagnosticar_servicio') y lo deja escrito en la propuesta,
como pieza de evidencia propia ('paso_a_despacho.FUENTE_MEDICION').
'paso_a_despacho.decidir' decide la regla 1 con esa pieza.

POR QUE EXISTE
--------------
Medido el 16/10/2026: la lectura del ticket clasificaba el equipo con lo que
devuelve el endpoint liviano ('contexto_del_caso': Online u Offline, sin
causa) y con claves que el clasificador no lee. Ninguna falla salia
verificada, y la regla 1 no podia dejar pasar nada. 'diagnosticar_servicio'
es la medicion que ya usa el cierre de desincronizados: trae el estado, la
causa de la caida y la señal ya clasificada contra el rango de la guia.

POR QUE ES UNA FASE PROPIA, Y NO EL FINAL DE LA LECTURA
------------------------------------------------------
'_leer_tickets_abiertos' sale temprano cuando no hay nada nuevo que leer, y
es justo entonces cuando las fallas viejas, ya leidas, necesitan medirse. Es
el error que el ciclo ya documento cuatro veces: poner algo en una rama a la
que los casos que importan no llegan.

LO QUE NO HACE
--------------
- No llama al modelo: medir no es leer.
- No acepta ni rechaza nada: escribe una pieza, y el paso decide despues.
- No gasta una llamada en un caso que no puede pasar: cerrado, o sin una
  copia fresca de WispHub.
- No escribe 'str(e)' ni el detalle de un error: el texto de una excepcion de
  red trae la URL, y la URL lleva el identificador del equipo.
- No guarda un error como medicion (16/10/2026): el motor caido no dice nada
  del equipo, y con la regla de la Fase 4 una falla "sin poder medir" pasa.
  La falla espera, y la vuelta siguiente lo intenta de nuevo.

LO QUE FRENA SE VUELVE A MEDIR  --  18/10/2026, correccion 2 del usuario
------------------------------------------------------------------------
Hasta ese dia una medicion concluyente no se repetia nunca, y el usuario
encontro el costo: una intermitencia medida de noche (-23 dBm, en rango) se
quedaba frenada aunque de dia la señal cayera a -29. Las dos mediciones que
frenan una falla --en linea con la señal en rango, y caida sin energia-- se
vuelven a medir HASTA 'REMEDICIONES_MAXIMAS' veces, separadas
'MINUTOS_PARA_REMEDIR_LO_QUE_FRENA', y cada medicion deja su resumen en el
HISTORIAL de la pieza ('paso_a_despacho.HORAS_DEL_HISTORIAL'): SmartOLT no da
la serie en numeros, solo una imagen.

NO ES POLLING, Y POR ESO TIENE TOPE  --  auditor independiente, 19/10/2026.
La medicion usa 'get_onu_full_status_info', que el proveedor autoriza para
"investigar un problema que reporto un usuario" y prohibe usar en polling
(skill smartolt-api). La primera version re-medía cada tres horas mientras la
propuesta viviera --hasta siete dias--, y eso es polling. Dos re-mediciones a
ocho horas, mas la original, son tres puntos en un dia: cubren la noche y el
dia, que es lo que hace falta para ver la oscilacion del caso 2, y quedan
como parte de investigar ese reclamo.

LA RE-MEDICION NUNCA REEMPLAZA A LA PIEZA. Va al historial, y la medicion
que decide se elige AL DECIDIR ('paso_a_despacho.la_medicion_vigente'): con
la tarea de las correcciones delegada, la mas reciente; sin ella, la de
siempre, y lo que la re-medicion haria pasar se cuenta en sombra. Hasta el
19/10/2026 la tarea la hacia reemplazar, y el auditor de frontera midio el
costo: quitada la tarea, la pieza nueva seguia decidiendo por la Fase 4.
================================================================================
"""

import logging
import math
import re
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

logger = logging.getLogger(__name__)

#:  Cuanto se espera para volver a intentar una medicion que no se pudo hacer.
#:  UNA VEZ POR DIA: el proveedor pide no repetir consultas ni hacerlas en
#:  masa (skill smartolt-api), y la propuesta vence a los 7 dias, asi que una
#:  falla que no se pudo medir se reintenta a lo sumo seis veces. No sale de
#:  una medicion: se cambia si el usuario lo pide.
HORAS_PARA_REINTENTAR = 24

#:  Cuanto se espera para volver a medir lo que no se pudo medir UNA vez  --
#:  17/10/2026. De esa segunda medicion depende que la falla pase
#:  ('paso_a_despacho.VUELTAS_SIN_MEDIR_PARA_PASAR'), asi que se pide en la
#:  vuelta siguiente y no al dia. 30 minutos: menos que lo que separan dos
#:  vueltas del reloj --una por hora, y la lectura de la primera puede tardar
#:  hasta veinte minutos--, y mas que lo que separan dos clics seguidos en
#:  "Correr ciclo", que no tienen que contar como dos vueltas.
MINUTOS_PARA_REINTENTAR_SIN_MEDIR = 30

#:  Cada cuanto se vuelve a medir una falla que la medicion FRENA, y cuantas
#:  veces  --  18/10/2026, correccion 2 del usuario; acotado el 19/10 (ver el
#:  encabezado: no es polling). Con la original, tres mediciones a ocho horas
#:  cubren el dia y la noche: la señal del caso 2 oscilaba entre -23 de noche y
#:  -29 de dia. Lo eligio el asistente; se cambia si el usuario lo pide.
MINUTOS_PARA_REMEDIR_LO_QUE_FRENA = 480
REMEDICIONES_MAXIMAS = 2

#:  Cuantas mediciones anteriores guarda la pieza. Doce entran holgadas en las
#:  24 horas a una cada tres, y ponen techo al tamaño de la evidencia.
MAXIMO_DEL_HISTORIAL = 12

#  El vocabulario cerrado de lo que se guarda. Lo que devuelva el motor fuera
#  de estas listas se guarda como "no se sabe", nunca tal cual.
_ESTADOS = ("en_linea", "caido")
_CAUSAS = ("sin_energia", "fibra", "otra")
_SENALES = ("buena", "debil", "sin_dato")

#  EL MOTIVO DEL MOTOR, CON FORMA CERRADA  --  revisor de PII, 16/10/2026.
#  Hoy el motor manda frases fijas ("el proveedor optico no respondio"). Nada
#  lo garantizaba de este lado: si un dia pusiera 'str(e)' en el motivo, la
#  URL con el serial terminaria en la propuesta y en el log. Se acepta solo lo
#  que tiene la forma de una frase; lo demas se guarda generico. No es una
#  copia de la lista del motor: un motivo nuevo con la misma forma pasa.
#  Coma y punto SI (la frase mas comun del motor, "no esta registrado en
#  SmartOLT, asi que...", lleva coma: auditor de frontera, 16/10); lo que
#  arman una URL o una excepcion --dos puntos, barra, igual, parentesis,
#  signo de pregunta, arroba-- NO.
_FORMA_DE_MOTIVO = re.compile(r"^[a-z0-9áéíóúñü ,.;_'-]{1,160}$", re.IGNORECASE)
_MOTIVO_GENERICO = "el motor no dijo por que en una forma conocida"
#  Y aunque tenga forma de frase, un serial de ONU suelto no entra: cuatro
#  letras del fabricante y ocho hexadecimales (auditor independiente, 16/10).
_PARECE_UN_SERIAL = re.compile(r"\b[a-z]{4}[0-9a-f]{8}\b", re.IGNORECASE)


def _medir_con_el_motor(org, id_servicio):
    """La medicion de verdad: la misma herramienta que usa el cierre."""
    from operaciones import chat_herramientas

    return chat_herramientas.diagnosticar_servicio(org, id_servicio=id_servicio)


def es_concluyente(medicion) -> bool:
    """
    Si la medicion dijo algo FIRME del equipo: en linea con su nivel, o caido
    con una causa. Lo concluyente no se vuelve a medir.

    Un caido sin causa ni señal puede ser un 200 del proveedor sin datos --el
    motor convierte en 'caido' cualquier estado que no sea 'online'--, y un en
    linea sin nivel, una respuesta incompleta. Contarlas como concluyentes las
    dejaba fijas los siete dias de la propuesta (auditor independiente,
    16/10): se vuelven a medir al dia, como lo que no se pudo medir.
    """
    m = medicion or {}
    if m.get("estado") == "en_linea":
        return (m.get("senal") in ("buena", "debil")
                and isinstance(m.get("senal_dbm"), (int, float)))
    if m.get("estado") == "caido":
        return m.get("causa_caida") in _CAUSAS
    return False


def de_la_respuesta(respuesta) -> dict | None:
    """
    Lo que se guarda de una respuesta del motor: claves fijas y vocabulario
    cerrado. Ni el serial, ni el detalle de un error, ni nada que no se use.

    UN ERROR NO ES UNA MEDICION, y devuelve None  --  16/10/2026. Hasta la
    Fase 3 se guardaba como "no se pudo medir", y con la regla de la Fase 4
    eso pasa: con el motor caido una vuelta, las fallas pasaban en la
    siguiente sin volver a medirse, con el equipo en rango inclusive (auditor
    de frontera: 5 de 5 asi). Lo que el PROVEEDOR no pudo medir no es un
    error: el motor lo contesta con estado 'desconocido' y su motivo.
    """
    from operaciones import paso_a_despacho as pad

    if not isinstance(respuesta, dict) or not respuesta or respuesta.get("error"):
        return None
    r = respuesta
    estado = str(r.get("estado") or "")
    causa = str(r.get("causa_caida") or "")
    senal = str(r.get("senal") or "")
    dbm = r.get("senal_dbm")
    if not (isinstance(dbm, (int, float)) and not isinstance(dbm, bool)
            and math.isfinite(dbm)):
        dbm = None
        #  Sin numero no hay clasificacion que sostener: "fuera del rango"
        #  sin el nivel contradeciria al motivo, que dice que no lo trajo.
        if senal in ("buena", "debil"):
            senal = "sin_dato"
    return {
        "medido_con": pad.MEDIDO_CON,
        #  'desconocido' es lo que el motor dice cuando no pudo medir, y
        #  siempre lo escribe. Cualquier otra cosa --vacio incluido-- es un
        #  estado que no se entiende, y el paso no decide con el.
        "estado": (estado if estado in _ESTADOS
                   else pad.ESTADO_DESCONOCIDO if estado == pad.ESTADO_DESCONOCIDO
                   else pad.ESTADO_NO_RECONOCIDO),
        "causa_caida": causa if causa in _CAUSAS else "",
        "senal": senal if senal in _SENALES else "sin_dato",
        #  Un numero de verdad, o nada (arriba). Un NaN haria fallar el
        #  guardado en JSONB: no quedaria la pieza y se pediria cada vuelta.
        "senal_dbm": float(dbm) if dbm is not None else None,
        #  EL NIVEL QUE RECIBE LA OLT (tanda 2, 19/10/2026): solo informa, en el
        #  doble diagnostico. Llega solo si la lista blanca de 'supervisor_noc'
        #  lo deja pasar; mientras tanto es None, y nada cambia.
        "senal_olt_dbm": _nivel_finito(r.get("senal_olt_dbm")),
        #  El motivo del motor cuando no pudo medir: texto fijo de su codigo
        #  ('diagnostico_servicio._resolver_serial' y '_sin_resolver').
        "motivo": _motivo(r.get("motivo")),
    }


def _nivel_finito(valor):
    """Un numero de verdad, o None: un NaN haria fallar el guardado en JSONB."""
    if (isinstance(valor, (int, float)) and not isinstance(valor, bool)
            and math.isfinite(valor)):
        return float(valor)
    return None


def _motivo(crudo) -> str:
    """El motivo del motor si tiene forma de frase fija; si no, uno generico."""
    texto = str(crudo or "").strip()
    if not texto:
        return ""
    if not _FORMA_DE_MOTIVO.match(texto) or _PARECE_UN_SERIAL.search(texto):
        return _MOTIVO_GENERICO
    return texto


def _dato(m: dict, ahora=None) -> str:
    """
    La frase que lee una persona. Fija, y nunca empieza como una lectura.

    LLEVA CUANDO SE MIDIO. El panel muestra cada pieza en "Hechos observados"
    sin su hora, y una medicion de hace seis dias se leia como el estado de hoy
    (auditor independiente, 16/10). En la hora del servidor, dicha: mostrarla en
    la hora de cada empresa es del panel.
    """
    cuando = ""
    if ahora is not None:
        cuando = (f" ({timezone.localtime(ahora).strftime('%d/%m %H:%M')} "
                  f"{timezone.get_current_timezone_name()})")
    return f"medicion del equipo{cuando}: " + _lo_que_dice(m)


def _lo_que_dice(m: dict) -> str:
    from operaciones import paso_a_despacho as pad

    if m.get("estado") == pad.ESTADO_NO_RECONOCIDO:
        return "volvio con un estado que no se reconoce; se vuelve a medir"
    nivel = (f" ({m['senal_dbm']} dBm)"
             if isinstance(m.get("senal_dbm"), (int, float)) else "")
    if nivel and isinstance(m.get("senal_olt_dbm"), (int, float)):
        nivel = f" ({m['senal_dbm']} dBm; la OLT recibe {m['senal_olt_dbm']} dBm)"
    if m.get("estado") == "en_linea":
        if m.get("senal") == "debil":
            return f"en linea, señal fuera del rango de la guia{nivel}"
        if m.get("senal") == "buena":
            return f"en linea, señal dentro del rango{nivel}"
        return "en linea, sin dato de señal"
    if m.get("estado") == "caido":
        if not m.get("causa_caida"):
            return "caido, sin causa ni señal"
        return {
            "sin_energia": "caido, sin energia (dying-gasp)",
            "fibra": "caido, perdio la señal optica (LOS/LOF)",
        }.get(m.get("causa_caida"), "caido, por otra causa")
    n = pad.intentos_sin_medir(m)
    if 0 < n < pad.VUELTAS_SIN_MEDIR_PARA_PASAR:
        return "no se pudo medir; se vuelve a intentar en la vuelta siguiente"
    if n:
        return f"no se pudo medir en {n} vueltas seguidas"
    return "no se pudo medir"


def _sin_id_de_servicio() -> dict:
    from operaciones import paso_a_despacho as pad

    return {"medido_con": pad.MEDIDO_CON, "estado": "desconocido",
            "causa_caida": "", "senal": "sin_dato", "senal_dbm": None,
            "motivo": "el caso no tiene el id de servicio del proveedor"}


def _vieja(medicion: dict, ahora) -> bool:
    from operaciones import paso_a_despacho as pad

    cuando = parse_datetime(str(medicion.get("observado_en") or ""))
    if cuando is None:
        return True
    if 0 < pad.intentos_sin_medir(medicion) < pad.VUELTAS_SIN_MEDIR_PARA_PASAR:
        espera = MINUTOS_PARA_REINTENTAR_SIN_MEDIR * 60
    else:
        espera = HORAS_PARA_REINTENTAR * 3600
    return (ahora - cuando).total_seconds() >= espera


def _ultima_vez(medicion: dict) -> str:
    """Cuando se midio por ultima vez esta pieza: la medicion que decide, o la
    re-medicion mas nueva, la que sea posterior. Texto ISO, como se guarda."""
    return max(str(medicion.get("observado_en") or ""),
               str(medicion.get("remedida_en") or ""))


def _veces_remedida(medicion: dict) -> int:
    n = (medicion or {}).get("remedida_veces")
    return n if isinstance(n, int) and not isinstance(n, bool) and n > 0 else 0


def _toca_remedir(medicion: dict, ahora) -> bool:
    if _veces_remedida(medicion) >= REMEDICIONES_MAXIMAS:
        return False
    cuando = parse_datetime(_ultima_vez(medicion))
    if cuando is None:
        return True
    return ((ahora - cuando).total_seconds()
            >= MINUTOS_PARA_REMEDIR_LO_QUE_FRENA * 60)


def candidatas(org, ahora) -> list:
    """
    Las pendientes de falla que hay que medir, en el orden en que se miden:
    primero las que nunca se midieron, la mas nueva primero --asi la falla
    del dia pasa ese dia--; despues las que no se pudieron medir hace mas de
    'HORAS_PARA_REINTENTAR', la de intento mas viejo primero; y al final las
    que la medicion frena y toca volver a medir (18/10/2026), la medida hace
    mas tiempo primero.

    Una medicion concluyente no se repite, SALVO las dos que frenan una falla
    ('paso_a_despacho.la_medicion_frena'): ver el encabezado. Un caso que no
    puede pasar no se mide: seria gastar una consulta al proveedor en algo que
    no va a ningun lado.
    """
    from operaciones import paso_a_despacho as pad
    from operaciones.models import PropuestaSupervisor as P

    nuevas, reintentos, remediciones = [], [], []
    pendientes = (P.objects
                  .filter(org=org, tipo_senal=P.TICKET_SIN_DIAGNOSTICO,
                          estado=P.PROPUESTA, origen_tipo="case")
                  .order_by("-created_at"))
    for p in pendientes:
        lectura = pad._ultima_lectura_con_grupo(p)
        if not lectura or lectura.get("grupo") != pad.FALLA_DE_SERVICIO:
            continue
        medicion = pad.ultima_medicion(p)
        if pad.es_un_error_guardado(medicion):
            #  Un error guardado antes del 16/10 no es una medicion: se pide
            #  como si nunca se hubiera medido, en esta misma vuelta.
            medicion = None
        remedir = False
        if medicion is not None and es_concluyente(medicion):
            if not (pad.la_medicion_frena(medicion)
                    and _toca_remedir(medicion, ahora)):
                continue
            remedir = True
        elif medicion is not None and not _vieja(medicion, ahora):
            continue
        caso = pad.caso_de(p)
        if pad.por_que_el_caso_no_puede_pasar(caso, ahora):
            continue
        if medicion is None:
            nuevas.append((p, caso))
        elif remedir:
            remediciones.append((p, caso, _ultima_vez(medicion)))
        else:
            reintentos.append((p, caso, str(medicion.get("observado_en") or "")))
    reintentos.sort(key=lambda x: x[2])
    remediciones.sort(key=lambda x: x[2])
    return (nuevas + [(p, caso) for p, caso, _ in reintentos]
            + [(p, caso) for p, caso, _ in remediciones])


def _resumen(medicion: dict, observado_en: str) -> dict:
    """Lo que queda de una medicion en el historial: las claves que deciden."""
    from operaciones import paso_a_despacho as pad

    salida = {c: medicion.get(c) for c in pad.CLAVES_DEL_HISTORIAL}
    salida["observado_en"] = observado_en
    return salida


def _historial(entradas, ahora) -> list:
    """Las mediciones de las ultimas horas, en orden, y con techo. Una entrada
    sin fecha que se entienda no se guarda: no se podria decir si es de hoy."""
    from operaciones import paso_a_despacho as pad

    vigentes = []
    for h in entradas or []:
        if not isinstance(h, dict):
            continue
        cuando = parse_datetime(str(h.get("observado_en") or ""))
        if cuando is None or timezone.is_naive(cuando):
            continue
        if ahora - cuando > timedelta(hours=pad.HORAS_DEL_HISTORIAL):
            continue
        vigentes.append((cuando, h))
    vigentes.sort(key=lambda x: x[0])
    return [h for _, h in vigentes][-MAXIMO_DEL_HISTORIAL:]


def _reemplazar_la_pieza(fresca, pieza) -> None:
    from operaciones import paso_a_despacho as pad

    resto = [x for x in (fresca.evidencia or [])
             if not (isinstance(x, dict)
                     and x.get("fuente") == pad.FUENTE_MEDICION)]
    fresca.evidencia = [*resto, pieza]
    fresca.save(update_fields=["evidencia", "updated_at"])


def escribir(propuesta, medicion: dict, ahora) -> bool:
    """
    Deja la medicion en la propuesta, reemplazando la anterior. Devuelve si
    escribio.

    La llamada de red ya ocurrio, afuera: aca solo se bloquea la fila, se
    vuelve a mirar que siga pendiente y se reescribe la evidencia de ESA fila.
    Mismo patron que 'paso_a_despacho.anotar_por_que_se_queda'.

    UNA RE-MEDICION (18/10/2026) es la de una pieza que FRENA, y NUNCA la
    reemplaza: va al historial, y la pieza que decide no cambia (ver el
    encabezado). Una re-medicion que NO MIDIO tampoco entra al historial:
    sin esto, dos vueltas del proveedor caido convertian una falla con la
    señal en rango en "no se pudo medir en dos vueltas", que pasa.
    """
    from operaciones import paso_a_despacho as pad
    from operaciones import supervisor as sup
    from operaciones.models import PropuestaSupervisor as P

    with transaction.atomic():
        fresca = (P.objects.select_for_update()
                  .filter(pk=propuesta.pk, estado=P.PROPUESTA).first())
        if fresca is None:
            return False
        medicion = dict(medicion)
        anterior = pad.ultima_medicion(fresca)
        if es_concluyente(anterior) and pad.la_medicion_frena(anterior):
            sigue = dict(anterior)
            sigue["remedida_en"] = ahora.isoformat()
            #  Cuenta tambien la que no midio: el tope es de consultas al
            #  proveedor, no de respuestas.
            sigue["remedida_veces"] = _veces_remedida(anterior) + 1
            if es_concluyente(medicion):
                sigue["historial"] = _historial(
                    [*(anterior.get("historial") or []),
                     _resumen(medicion, ahora.isoformat())], ahora)
            _reemplazar_la_pieza(fresca, sigue)
            return True
        if medicion.get("estado") == pad.ESTADO_DESCONOCIDO:
            #  LAS VUELTAS SEGUIDAS SIN PODER MEDIR  --  17/10/2026. Se cuentan
            #  aca, con la fila bloqueada, mirando la medicion que se reemplaza:
            #  si tambien era un "no se pudo medir", suma; si no, empieza de
            #  nuevo. El paso deja pasar recien a la segunda.
            medicion["intentos_sin_medir"] = (
                pad.intentos_sin_medir(pad.ultima_medicion(fresca)) + 1)
        pieza = sup._observacion(pad.FUENTE_MEDICION, fresca.origen_id,
                                 _dato(medicion, ahora), ahora)
        pieza.update(medicion)
        #  LA SERIE SIGUE  --  18/10/2026: lo que la pieza anterior ya traia,
        #  mas ella misma si dijo algo firme del equipo.
        previas = [*((anterior or {}).get("historial") or [])]
        if es_concluyente(anterior):
            previas.append(_resumen(anterior,
                                    str(anterior.get("observado_en") or "")))
        historial = _historial(previas, ahora)
        if historial:
            pieza["historial"] = historial
        _reemplazar_la_pieza(fresca, pieza)
    return True


def medir_fallas_pendientes(org, *, desatendido: bool = False, medir=None,
                            presupuesto_=None) -> dict:
    """
    Mide las fallas pendientes que lo necesitan, hasta el presupuesto.
    Devuelve conteos para el log.

    'medir' SE INYECTA, como 'diagnosticar' en 'diagnostico_optico.enriquecer':
    este modulo decide QUE se mide y que se guarda, no como se habla con el
    motor. Y una prueba no puede depender de que haya un SmartOLT del otro
    lado.

    EL PRESUPUESTO SE CREA ACA, Y CON LA HORA DE AHORA. 'presupuesto' corta en
    'ahora + segundos', y cuando esta fase corre la lectura ya tardo hasta
    veinte minutos: con la hora del ciclo naceria vencido y no mediria nada,
    sin un solo error. Es otra instancia del presupuesto del modulo optico, con
    su mismo tope, y no el mismo: el cierre corre antes y en un dia de atraso
    se lo comeria entero.
    """
    from operaciones import diagnostico_optico as optico
    from operaciones import paso_a_despacho as pad
    from operaciones import supervisor as sup

    medir = medir or _medir_con_el_motor
    p = (presupuesto_ if presupuesto_ is not None
         else optico.presupuesto(desatendido=desatendido))
    informe = {"candidatas": 0, "medidas": 0, "concluyentes": 0,
               "sin_medicion": 0, "sin_id_de_servicio": 0,
               "sin_presupuesto": 0, "errores": 0,
               #  Las que se volvieron a medir porque frenaban (18/10/2026).
               #  Tambien cuentan en 'medidas'.
               "remedidas": 0}

    ahora = timezone.now()
    cola = candidatas(org, ahora)
    informe["candidatas"] = len(cola)
    for i, (propuesta, caso) in enumerate(cola):
        id_servicio = str(getattr(caso, "external_service_id", "") or "").strip()
        es_remedicion = pad.la_medicion_frena(pad.ultima_medicion(propuesta))
        try:
            if not id_servicio:
                #  Sin el id no hay a quien preguntarle: se anota sin gastar
                #  presupuesto, y se reintenta cuando toque.
                if escribir(propuesta, _sin_id_de_servicio(), timezone.now()):
                    informe["sin_id_de_servicio"] += 1
                continue
            if not sup._hay_presupuesto(p):
                #  Sin presupuesto NO se escribe nada: "no se midio en esta
                #  vuelta" no dice nada del equipo, y la que sigue lo intenta.
                informe["sin_presupuesto"] = len(cola) - i
                break
            sup._gastar(p)
            try:
                respuesta = medir(org, id_servicio)
            except Exception as e:                               # noqa: BLE001
                respuesta = {"error": type(e).__name__}
            medicion = de_la_respuesta(respuesta)
            if medicion is None:
                #  Un error no deja pieza: la falla espera, sin pasar, y la
                #  vuelta siguiente lo intenta de nuevo ('de_la_respuesta').
                informe["errores"] += 1
                continue
            if escribir(propuesta, medicion, timezone.now()):
                informe["medidas"] += 1
                informe["remedidas"] += int(es_remedicion)
                informe["concluyentes" if es_concluyente(medicion)
                        else "sin_medicion"] += 1
        except Exception as e:                                   # noqa: BLE001
            #  Una propuesta que no se pudo escribir no corta la fase.
            informe["errores"] += 1
            logger.warning("Supervisor: no se pudo guardar una medicion (%s)",
                           type(e).__name__)
    return informe
