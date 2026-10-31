# -*- coding: utf-8 -*-
"""
================================================================================
 EL SONDEO DE FUENTES  --  consultar, fechar, guardar, comparar. Nada mas.
================================================================================

QUE HACE ESTE MODULO
--------------------
Le pregunta a las fuentes que ya vencieron, escribe como salio cada una, guarda
un resumen acotado y deja disponible la diferencia contra el ciclo anterior.

QUE NO HACE, Y ES LA MITAD DEL DISENO
-------------------------------------
No decide. No crea Situaciones Operativas, no crea propuestas, no corre el ciclo
del Supervisor, no escala, no toca un caso y no llama a nada que produzca un
efecto afuera. Un cambio de +11 ONUs caidas en un PON queda ESCRITO y
disponible; que eso sea un incidente lo decidira el bloque siguiente.

La separacion no es burocracia: si detectar y leer vivieran juntos, un tablero
en rojo no distinguiria "la red se cayo" de "SmartOLT no contesta", que es
exactamente el error que esta capa existe para hacer imposible.

LA REGLA QUE ORDENA TODO
------------------------
Una fuente que falla NO es una fuente sin novedades. Se escribe en tres lugares
distintos --'estado', 'frescura' y 'concluyente'-- para que ningun lector pueda
leer un cero sin ver al lado de donde salio.

EL TIEMPO LO MIDE EL SCHEDULER; EL TURNO DE CADA FUENTE, ESTA CAPA
-----------------------------------------------------------------
'sondear()' no duerme, no cicla y no se agenda. Corre una vez, cuando alguien
la llama. Quien la llama es el scheduler de 'nucleo/programador/' --el unico del
sistema-- a traves de la ruta HTTP del Supervisor. Lo unico que hace esta capa
es elegir, de las fuentes activas, cuales ya vencieron segun su propia
frecuencia. Eso permite SmartOLT cada 5 minutos y M03 cada hora con un solo
temporizador.
================================================================================
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from operaciones.fuentes_modelos import (EstadoLectura, Frescura, Fuente,
                                         FuenteEstado, FuenteSnapshot)

#  Cuantos snapshots se conservan por organizacion y fuente. Dos alcanzarian
#  para comparar con el anterior; se guardan mas para poder mirar atras cuando
#  algo ya paso, que es cuando siempre se quiere. No es un archivo historico:
#  'podar()' los recorta en cada escritura, asi que la tabla no crece sin techo.
SNAPSHOTS_QUE_SE_CONSERVAN = 20

#  Cuanto puede crecer el resumen de una captura. No es un limite estetico: un
#  adaptador que devuelva de golpe la fuente entera llenaria la tabla de datos
#  que nadie pidio, y el tope lo convierte en un error visible en vez de en una
#  factura de almacenamiento.
TOPE_CLAVES_DEL_RESUMEN = 500


class Lectura:
    """
    Lo que devuelve un adaptador de fuente. Una sola forma para las seis.

    Es deliberadamente tonta: no consulta nada, no escribe nada y no sabe de
    frescura. La arma el adaptador y la interpreta 'registrar()'. Tener una sola
    forma es lo que permite que SmartOLT --que sale por HTTP a un tercero-- y
    M03 --que es una consulta al ORM-- se traten igual aguas abajo.

    'dato_en' es el campo que casi nadie puebla y casi siempre importa: es de
    cuando es el DATO segun la fuente, no cuando lo leimos. Si la fuente no lo
    dice se deja en None y la frescura queda DESCONOCIDA; poner 'ahora' seria
    afirmar que el dato es de ahora sin que nadie lo haya dicho.
    """

    __slots__ = ("estado", "datos", "registros", "dato_en", "esquema",
                 "tipo_consulta", "error_tecnico", "motivo_no_disponible")

    def __init__(self, estado, *, datos=None, registros=None, dato_en=None,
                 esquema="", tipo_consulta="", error_tecnico="",
                 motivo_no_disponible=""):
        if estado not in EstadoLectura.TODOS:
            raise ValueError(f"estado de lectura desconocido: {estado!r}")
        self.estado = estado
        self.datos = datos if datos is not None else {}
        self.registros = registros
        self.dato_en = dato_en
        self.esquema = esquema
        self.tipo_consulta = tipo_consulta
        self.error_tecnico = error_tecnico
        self.motivo_no_disponible = motivo_no_disponible


# =============================================================================
#  FRESCURA
# =============================================================================

def frescura_de(lectura: Lectura, estado_fuente: FuenteEstado, ahora) -> str:
    """
    Que tan viejo es el dato. Eje aparte del estado de la lectura.

    Las cuatro salidas, y por que cada una:

      SIN_DATO      no hay nada que fechar. Es el caso de un error, de una
                    fuente no disponible, y tambien de una consulta que salio
                    bien y vino vacia: no hay dato cuya edad discutir.
      DESCONOCIDA   hay dato y la fuente NO dice de cuando es. Se dice que no se
                    sabe. El atajo tentador --tomar 'ahora'-- convertiria
                    cualquier dato en fresco por definicion.
      VIEJA         la antiguedad pasa el tope configurado de ESTA fuente.
      FRESCA        entra en el tope.
    """
    if lectura.estado in (EstadoLectura.ERROR, EstadoLectura.NO_DISPONIBLE,
                          EstadoLectura.NO_CONSULTADA):
        return Frescura.SIN_DATO
    if lectura.dato_en is None:
        #  Una consulta que trajo registros pero no los fecha es DESCONOCIDA;
        #  una que no trajo nada no tiene dato que fechar.
        if lectura.estado == EstadoLectura.CON_DATOS:
            return Frescura.DESCONOCIDA
        return Frescura.SIN_DATO

    tope = estado_fuente.antiguedad_maxima_segundos
    antiguedad = (ahora - lectura.dato_en).total_seconds()
    #  Un 'dato_en' en el FUTURO no es fresco por ser reciente: es un reloj
    #  desfasado, y presentarlo como fresco esconde el problema. Se trata como
    #  desconocido, que es lo que de verdad se sabe de el.
    if antiguedad < 0:
        return Frescura.DESCONOCIDA
    return Frescura.FRESCA if antiguedad <= tope else Frescura.VIEJA


def _vacio_es_inconcluso(lectura: Lectura, estado_fuente: FuenteEstado,
                         ahora) -> bool:
    """
    Si un vacio de esta fuente, en este momento, no significa nada todavia.

    Existe por un dato medido de un tercero: 'get_outage_pons' de SmartOLT
    agrupa con 2 a 5 minutos de retraso, informado por sus desarrolladores (ver
    .claude/skills/smartolt-api). En esa ventana, una respuesta vacia NO prueba
    que no haya una caida de red; prueba que el proveedor no la agrupo aun.

    La ventana se cuenta desde el ULTIMO EXITO de la fuente, no desde el
    arranque del proceso: lo que importa es cuanto hace que tenemos una lectura
    buena, no cuanto hace que estamos corriendo.
    """
    ventana = estado_fuente.ventana_inconclusa_segundos
    if not ventana or lectura.estado != EstadoLectura.SIN_REGISTROS:
        return False
    #  Sin un exito previo no hay desde cuando contar: la primera lectura vacia
    #  de una fuente con ventana es inconclusa, que es el lado prudente.
    if estado_fuente.ultimo_exito_en is None:
        return True
    return (ahora - estado_fuente.ultimo_exito_en).total_seconds() < ventana


# =============================================================================
#  REGISTRO DE UNA LECTURA
# =============================================================================

def registrar(estado_fuente: FuenteEstado, lectura: Lectura, *,
              inicio, ahora=None, ejecucion_id=None) -> FuenteSnapshot:
    """
    Escribe como salio una consulta y guarda su captura. Devuelve el snapshot.

    Las dos escrituras van en UNA transaccion a proposito: un estado que diga
    'con_datos' sin su captura al lado dejaria al proximo ciclo comparando
    contra un snapshot que no es el que produjo ese estado, y la diferencia
    saldria mal sin que nada avise.
    """
    ahora = ahora or timezone.now()

    #  El vacio se reinterpreta ANTES de calcular frescura: si resulta
    #  inconcluso, no es una lectura sin registros sino una que no concluye.
    if _vacio_es_inconcluso(lectura, estado_fuente, ahora):
        lectura.estado = EstadoLectura.INCONCLUSA

    frescura = frescura_de(lectura, estado_fuente, ahora)
    datos = _acotar(lectura.datos)

    with transaction.atomic():
        snap = FuenteSnapshot.objects.create(
            org=estado_fuente.org,
            fuente=estado_fuente.fuente,
            capturado_en=ahora,
            dato_en=lectura.dato_en,
            estado=lectura.estado,
            frescura=frescura,
            datos=datos,
            esquema=lectura.esquema or "sin_esquema",
            tipo_consulta=lectura.tipo_consulta,
            registros=lectura.registros,
            error_tecnico=lectura.error_tecnico,
            ejecucion_id=ejecucion_id,
        )

        estado_fuente.ultima_consulta_inicio = inicio
        estado_fuente.ultima_consulta_fin = ahora
        estado_fuente.estado = lectura.estado
        estado_fuente.frescura = frescura
        estado_fuente.registros = lectura.registros
        estado_fuente.dato_en = lectura.dato_en
        estado_fuente.error_tecnico = lectura.error_tecnico
        estado_fuente.motivo_no_disponible = lectura.motivo_no_disponible
        estado_fuente.ejecucion_id = ejecucion_id
        estado_fuente.tipo_consulta = lectura.tipo_consulta
        estado_fuente.esquema = lectura.esquema or ""
        #  La proxima vez se calcula desde AHORA y no desde la vencida: si una
        #  fuente estuvo caida dos horas, encadenar desde el vencimiento viejo
        #  dispararia una ráfaga de consultas para "ponerse al dia" contra un
        #  tercero que acaba de volver.
        estado_fuente.proxima_consulta_en = (
            ahora + timezone.timedelta(
                seconds=estado_fuente.frecuencia_segundos))

        #  Un exito es haber podido PREGUNTAR, no haber encontrado algo: una
        #  fuente vacia contesto perfectamente. Lo que rompe la racha es no
        #  poder preguntar.
        if lectura.estado in (EstadoLectura.CON_DATOS,
                              EstadoLectura.SIN_REGISTROS,
                              EstadoLectura.INCONCLUSA):
            estado_fuente.ultimo_exito_en = ahora
            estado_fuente.fallos_consecutivos = 0
        elif lectura.estado == EstadoLectura.ERROR:
            estado_fuente.fallos_consecutivos += 1

        estado_fuente.save()
        podar(estado_fuente.org_id, estado_fuente.fuente)

    return snap


def _acotar(datos):
    """
    Un resumen que crecio de mas se corta y lo DICE, en vez de entrar callado.

    Se marca con '_truncado' para que quien lo lea sepa que esta mirando una
    parte. Un recorte silencioso haria que la comparacion entre ciclos
    informara diferencias que son del recorte y no del mundo.
    """
    if not isinstance(datos, dict):
        return {"_invalido": f"el adaptador no devolvio un objeto: "
                             f"{type(datos).__name__}"}
    if len(datos) <= TOPE_CLAVES_DEL_RESUMEN:
        return datos
    recortado = dict(list(datos.items())[:TOPE_CLAVES_DEL_RESUMEN])
    recortado["_truncado"] = (
        f"el resumen traia {len(datos)} claves y el tope es "
        f"{TOPE_CLAVES_DEL_RESUMEN}")
    return recortado


def podar(org_id, fuente: str) -> int:
    """
    Deja solo los ultimos snapshots de esa organizacion y fuente.

    Borra por 'pk in (subconsulta)' y no por fecha: un corte por fecha dejaria
    cero filas si una fuente estuvo quieta mucho tiempo, y justamente ahi es
    cuando hace falta el snapshot anterior para comparar.
    """
    ids_que_quedan = list(
        FuenteSnapshot.objects
        .filter(org_id=org_id, fuente=fuente)
        .order_by("-capturado_en")
        .values_list("pk", flat=True)[:SNAPSHOTS_QUE_SE_CONSERVAN])
    borrados, _ = (FuenteSnapshot.objects
                   .filter(org_id=org_id, fuente=fuente)
                   .exclude(pk__in=ids_que_quedan)
                   .delete())
    return borrados


# =============================================================================
#  COMPARACION ENTRE CICLOS
# =============================================================================

def ultimo_snapshot(org, fuente: str, *, excluir=None):
    """El snapshot mas reciente de esa fuente, o None."""
    q = FuenteSnapshot.objects.filter(org=org, fuente=fuente)
    if excluir is not None:
        q = q.exclude(pk=excluir)
    return q.order_by("-capturado_en").first()


def comparar(anterior, actual) -> dict:
    """
    La diferencia entre dos capturas de la MISMA fuente. Datos, no veredictos.

    Devuelve que claves aparecieron, cuales desaparecieron y, en las que estan
    en las dos, como cambio cada metrica numerica. El ejemplo del bloque --PON
    1/3 paso de 1 afectado a 12-- sale como {'afectados': {'antes': 1,
    'ahora': 12, 'delta': 11}}.

    DOS COSAS QUE NO HACE, Y LAS DOS A PROPOSITO
    --------------------------------------------
    1. No juzga. '+11 afectados' es un hecho; que sea un incidente lo decide
       otra capa con otras reglas.
    2. No compara capturas de ESQUEMAS distintos. Si el adaptador cambio de
       forma entre dos ciclos, la diferencia seria del cambio de forma y no del
       mundo -- se devuelve 'comparable: False' con el motivo, que es un
       resultado honesto, no un fallo.
    """
    if anterior is None:
        return {"comparable": False, "motivo": "no hay captura anterior"}
    if actual is None:
        return {"comparable": False, "motivo": "no hay captura actual"}
    if anterior.esquema != actual.esquema:
        return {"comparable": False,
                "motivo": f"esquemas distintos: '{anterior.esquema}' vs "
                          f"'{actual.esquema}'"}
    #  Comparar contra una lectura que no concluye produciria un delta
    #  inventado: si SmartOLT fallo, "0 afectados" no era un cero del mundo.
    for cual, snap in (("anterior", anterior), ("actual", actual)):
        if snap.estado in EstadoLectura.NO_CONCLUYENTES:
            return {"comparable": False,
                    "motivo": f"la captura {cual} no es concluyente "
                              f"({snap.estado})"}

    antes = anterior.datos if isinstance(anterior.datos, dict) else {}
    ahora_ = actual.datos if isinstance(actual.datos, dict) else {}
    claves_antes, claves_ahora = set(antes), set(ahora_)

    cambios = {}
    for clave in sorted(claves_antes & claves_ahora):
        d = _delta(antes[clave], ahora_[clave])
        if d:
            cambios[clave] = d

    return {
        "comparable": True,
        "desde": anterior.capturado_en.isoformat(),
        "hasta": actual.capturado_en.isoformat(),
        "aparecieron": sorted(claves_ahora - claves_antes),
        "desaparecieron": sorted(claves_antes - claves_ahora),
        "cambiaron": cambios,
    }


def _delta(antes, ahora_) -> dict:
    """Como cambio una entrada. Solo las metricas numericas tienen delta."""
    if isinstance(antes, dict) and isinstance(ahora_, dict):
        salida = {}
        for metrica in sorted(set(antes) | set(ahora_)):
            a, b = antes.get(metrica), ahora_.get(metrica)
            if a == b:
                continue
            fila = {"antes": a, "ahora": b}
            if isinstance(a, (int, float)) and isinstance(b, (int, float)) \
                    and not isinstance(a, bool) and not isinstance(b, bool):
                fila["delta"] = b - a
            salida[metrica] = fila
        return salida
    if antes != ahora_:
        return {"antes": antes, "ahora": ahora_}
    return {}


# =============================================================================
#  EL SONDEO
# =============================================================================

def vencidas(org, ahora=None):
    """
    Las fuentes activas de esta organizacion que ya tocan.

    'proxima_consulta_en' nulo cuenta como vencida: es una fuente que nunca se
    consulto, y la primera vez tiene que ser ahora y no dentro de un intervalo.
    """
    ahora = ahora or timezone.now()
    from django.db.models import Q
    return list(FuenteEstado.objects
                .filter(org=org, activa=True)
                .filter(Q(proxima_consulta_en__isnull=True)
                        | Q(proxima_consulta_en__lte=ahora))
                .order_by("fuente"))


def sondear(org, *, ahora=None, ejecucion_id=None, adaptadores=None) -> dict:
    """
    Una pasada: consultar las fuentes vencidas y dejar todo escrito.

    Devuelve un informe de CONTEOS y estados, sin datos de cliente: lo lee el
    scheduler y termina en el log del motor.

    UNA FUENTE QUE REVIENTA NO SE LLEVA A LAS DEMAS
    ----------------------------------------------
    Cada adaptador corre en su propio try. Si SmartOLT levanta, se escribe su
    ERROR y se sigue con Dexter -- al reves, una excepcion de la primera fuente
    dejaria a las otras cinco en 'no_consultada' sin que nada lo explique, y un
    tablero mostraria cinco fuentes mudas por culpa de una.

    DEL ERROR SE GUARDA EL TIPO Y EL MENSAJE, NUNCA EL RASTRO
    --------------------------------------------------------
    Un traceback de una llamada HTTP trae la URL, y la URL de una consulta a
    SmartOLT lleva el identificador del equipo de un cliente. Misma regla que
    'nucleo/observabilidad/registro.py' y que el latido del bloque anterior.
    """
    from operaciones import fuentes_adaptadores

    ahora = ahora or timezone.now()
    #  'is None' y NO 'or': un diccionario VACIO es un valor legitimo --"este
    #  despliegue no sabe consultar ninguna fuente"-- y con 'or' caia al mapa
    #  real y consultaba todo. Lo encontro test_21.
    if adaptadores is None:
        adaptadores = fuentes_adaptadores.POR_FUENTE
    informe = {"organizacion": str(org.id), "sondeadas": 0, "por_fuente": {},
               "escrituras_externas": 0}

    for estado_fuente in vencidas(org, ahora):
        inicio = timezone.now()
        adaptador = adaptadores.get(estado_fuente.fuente)
        if adaptador is None:
            #  Una fila para una fuente que este despliegue no sabe consultar.
            #  No es un error de la fuente: es una fila que sobra, y se dice
            #  asi en vez de contarla como fallo del tercero.
            lectura = Lectura(
                EstadoLectura.NO_DISPONIBLE,
                motivo_no_disponible=(
                    f"este despliegue no tiene adaptador para "
                    f"'{estado_fuente.fuente}'"),
                tipo_consulta="sin_adaptador")
        else:
            try:
                lectura = adaptador(org, estado_fuente, ahora)
            except Exception as e:                               # noqa: BLE001
                lectura = Lectura(
                    EstadoLectura.ERROR,
                    error_tecnico=f"{type(e).__name__}: {_primera_linea(e)}",
                    tipo_consulta="excepcion")

        snap = registrar(estado_fuente, lectura, inicio=inicio, ahora=ahora,
                         ejecucion_id=ejecucion_id)
        previo = ultimo_snapshot(org, estado_fuente.fuente, excluir=snap.pk)
        diff = comparar(previo, snap)

        informe["sondeadas"] += 1
        informe["por_fuente"][estado_fuente.fuente] = {
            "estado": snap.estado,
            "frescura": snap.frescura,
            "registros": snap.registros,
            "concluyente": estado_fuente.concluyente,
            "dato_en": snap.dato_en.isoformat() if snap.dato_en else None,
            "proxima_consulta_en": (
                estado_fuente.proxima_consulta_en.isoformat()
                if estado_fuente.proxima_consulta_en else None),
            "cambio": {
                "comparable": diff.get("comparable", False),
                "motivo": diff.get("motivo", ""),
                "aparecieron": len(diff.get("aparecieron") or []),
                "desaparecieron": len(diff.get("desaparecieron") or []),
                "cambiaron": len(diff.get("cambiaron") or {}),
            },
        }

    return informe


def _primera_linea(e: BaseException) -> str:
    """El mensaje sin cuerpos largos ni rastro: la URL no viaja a la base."""
    return (str(e).splitlines()[0][:300] if str(e) else "")


# =============================================================================
#  ALTA DE FUENTES
# =============================================================================

#  Los valores con los que nace cada fuente. Son SEMILLA, no politica: se
#  editan por fila desde operacion. Lo unico que no se mueve de aqui es
#  'activa', que nace en False para las seis -- ver FuenteEstado.
SEMILLA = {
    #  5 minutos es el objetivo del bloque. La ventana de 5 minutos es la
    #  latencia de agregacion que informo el proveedor: dentro de ella, un
    #  vacio es inconcluso y no "no hay caidas".
    Fuente.SMARTOLT: {"frecuencia_segundos": 300,
                      "antiguedad_maxima_segundos": 900,
                      "ventana_inconclusa_segundos": 300},
    #  WispHub: la frecuencia queda declarada para cuando se habilite. Hoy su
    #  adaptador contesta NO_DISPONIBLE con el motivo medido.
    Fuente.WISPHUB: {"frecuencia_segundos": 900,
                     "antiguedad_maxima_segundos": 3600,
                     "ventana_inconclusa_segundos": 0},
    Fuente.DEXTER: {"frecuencia_segundos": 300,
                    "antiguedad_maxima_segundos": 900,
                    "ventana_inconclusa_segundos": 0},
    #  SLA, M02 y M03 se derivan de filas propias: el dato es tan nuevo como la
    #  consulta, asi que la antiguedad maxima es holgada a proposito.
    Fuente.SLA: {"frecuencia_segundos": 600,
                 "antiguedad_maxima_segundos": 1800,
                 "ventana_inconclusa_segundos": 0},
    Fuente.M02: {"frecuencia_segundos": 900,
                 "antiguedad_maxima_segundos": 3600,
                 "ventana_inconclusa_segundos": 0},
    Fuente.M03: {"frecuencia_segundos": 3600,
                 "antiguedad_maxima_segundos": 7200,
                 "ventana_inconclusa_segundos": 0},
}


def asegurar_fuentes(org) -> list:
    """
    Crea las filas que falten para esta organizacion. Idempotente.

    No activa ninguna: las seis nacen apagadas. Llamarla dos veces no cambia
    nada, y NO reescribe la configuracion de una fila que ya existe -- si
    alguien subio la frecuencia de SmartOLT desde operacion, una llamada a esto
    no se la pisa.
    """
    creadas = []
    for fuente in Fuente.TODAS:
        _, creada = FuenteEstado.objects.get_or_create(
            org=org, fuente=fuente,
            defaults=SEMILLA.get(fuente, {}))
        if creada:
            creadas.append(fuente)
    return creadas
