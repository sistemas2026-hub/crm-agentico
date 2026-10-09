# -*- coding: utf-8 -*-
"""
================================================================================
 REGISTRAR UN RAZONAMIENTO  --  el unico escritor de la tabla
================================================================================

QUE HACE, Y QUE NO
------------------
Toma un Veredicto de 'cerebro.concluir()' y el analisis deterministico PREVIO,
y deja una fila. Nada mas.

NO decide, NO enriquece, NO lee el veredicto para cambiar nada. Si esta funcion
desapareciera, el ciclo seguiria produciendo exactamente las mismas propuestas:
lo unico que se perderia es la constancia. Esa separacion es deliberada --
registrar y enriquecer son dos permisos distintos y tienen que poder
habilitarse por separado (ver 'supervisor.CEREBRO_EN_EL_CICLO').

NUNCA LEVANTA, POR EL MISMO MOTIVO QUE 'enriquecer()'
----------------------------------------------------
El ciclo no puede depender de este registro para registrar una propuesta. Una
base lenta, una restriccion que choca, un campo que no cabe: todos terminan
igual -- se devuelve None y el ciclo sigue. Una propuesta que no se registra
porque fallo su bitacora seria el peor intercambio posible.

Por eso el 'except' es amplio a proposito, igual que en 'enriquecer()'. El
precio es que un fallo de escritura es silencioso para el ciclo; se paga con el
contador de 'observabilidad' y con la prueba que afirma que el ciclo termina su
trabajo igual.

LO QUE SE GUARDA DEL TEXTO LIBRE  --  decision y su motivo
----------------------------------------------------------
El Veredicto trae texto que ESCRIBIO EL MODELO ('hipotesis', 'recomendacion',
'inferencias', 'riesgos'). Ese texto puede mencionar datos de un cliente.

La garantia primaria no esta aqui: esta aguas arriba. Un hecho del cerebro solo
sobrevive a 'cerebro.validar()' si su fuente esta entre las herramientas
realmente consultadas, y esas herramientas ya entregan sus campos filtrados por
la lista blanca del rol 'supervisor_noc'. Un dato que la lista blanca no deja
pasar no llega al modelo, asi que no puede salir en su texto.

Sobre eso se agrega un cinturon: '_sin_identificadores()' borra los tres
identificadores que este proyecto trata como sensibles siempre que aparezcan
sueltos en texto libre. ES UNA LISTA NEGRA Y SE SABE: no reemplaza a
'nucleo/seguridad/redaccion.py' --que vive en el motor y es la autoridad-- ni
pretende ser la garantia. Es la segunda capa, no la primera, y existe porque
esta tabla se guarda para ANALIZARLA despues, que es un uso distinto al del
chat (donde el texto se le muestra a la persona que pregunto y ya).

Si la revision de privacidad decide que no se guarda texto libre del modelo,
se cambia 'GUARDAR_TEXTO_LIBRE' a False y la tabla queda con los campos
estructurados y los recuentos. El resto del plan sigue valiendo: se pierde el
matiz del porque, no la capacidad de comparar.
"""

import re

from django.utils import timezone

from operaciones.razonamiento_modelos import (
    FuenteRazonamiento,
    RazonamientoSupervisor,
)

#  Si pasa a False, los campos de texto libre se guardan vacios y solo quedan
#  los estructurados, los recuentos y los descartes. Decision de privacidad,
#  no de ingenieria: se cambia con una revision, no por conveniencia.
GUARDAR_TEXTO_LIBRE = True

#  Los tres identificadores que este proyecto no deja salir en claro. El orden
#  importa: el correo primero, porque un correo puede contener una secuencia de
#  digitos que los otros dos patrones cortarian por la mitad.
_PATRONES = (
    #  correo
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[correo]"),
    #  movil colombiano: 3 + 9 digitos, sin pegarse a un numero mas largo
    (re.compile(r"(?<!\d)3\d{9}(?!\d)"), "[telefono]"),
    #  documento: 6 a 11 digitos seguidos. Deliberadamente amplio -- en una
    #  bitacora, perder un numero de serie por exceso de celo cuesta menos que
    #  guardar una cedula.
    (re.compile(r"(?<!\d)\d{6,11}(?!\d)"), "[documento]"),
)

#  Tope por campo de texto. Un modelo que se va de largo no puede hacer crecer
#  una fila sin limite; y para comparar criterios alcanza de sobra.
TOPE_TEXTO = 2000
TOPE_LISTA = 20


def _sin_identificadores(texto: str) -> str:
    """Borra correos, moviles y documentos de un texto libre."""
    if not texto:
        return ""
    for patron, reemplazo in _PATRONES:
        texto = patron.sub(reemplazo, texto)
    return texto


def _texto(valor) -> str:
    """Un campo de texto libre, listo para guardar."""
    if not GUARDAR_TEXTO_LIBRE:
        return ""
    return _sin_identificadores(str(valor or ""))[:TOPE_TEXTO]


def _lista_de_texto(valores) -> list:
    """Una lista de cadenas, saneada y acotada."""
    if not GUARDAR_TEXTO_LIBRE:
        return []
    salida = []
    for v in (valores or [])[:TOPE_LISTA]:
        limpio = _sin_identificadores(str(v))[:TOPE_TEXTO]
        if limpio:
            salida.append(limpio)
    return salida


def _hechos(valores) -> list:
    """
    Los hechos, conservando su fuente.

    La fuente NO se sanea: es el nombre de una herramienta del catalogo, un
    valor cerrado, y es justamente lo que vuelve auditable al hecho. Lo que se
    sanea es el enunciado.
    """
    salida = []
    for h in (valores or [])[:TOPE_LISTA]:
        if isinstance(h, dict):
            salida.append({
                "fuente": str(h.get("fuente", ""))[:120],
                "dato": _texto(h.get("dato") or h.get("hecho") or ""),
            })
        else:
            salida.append({"fuente": "", "dato": _texto(h)})
    return salida


def registrar(org, veredicto, *, fuente=FuenteRazonamiento.CICLO,
              propuesta=None, situacion=None, analisis_previo=None,
              enriquecio=False, ahora=None):
    """
    Deja la fila. Devuelve el objeto, o None si no se pudo.

    SE REGISTRA TAMBIEN CUANDO NO CONCLUYE, y esa es la mitad del valor: un
    veredicto que no cierra es la medida de cuantas veces el cerebro se quedo
    corto y lo dijo. Filtrarlo dejaria la medicion sesgada hacia arriba.

    'analisis_previo' es el analisis deterministico ANTES del enriquecimiento.
    Pasarle el de despues romperia la unica comparacion que esta tabla
    habilita, y por eso hay una prueba que lo afirma sobre el efecto.
    """
    if veredicto is None:
        return None
    if propuesta is None and situacion is None:
        #  La restriccion de la base lo rechazaria; mejor no intentarlo y no
        #  dejar una excepcion en el log por algo que es un error de llamada.
        return None

    r = getattr(veredicto, "razonamiento", None)
    try:
        return RazonamientoSupervisor.objects.create(
            org=org,
            propuesta=propuesta,
            situacion=situacion,
            fuente=fuente,
            concluyente=bool(veredicto.concluyente),
            hechos=_hechos(veredicto.hechos),
            inferencias=_lista_de_texto(veredicto.inferencias),
            riesgos=_lista_de_texto(veredicto.riesgos),
            riesgo=veredicto.riesgo,
            hipotesis=_texto(veredicto.hipotesis),
            confianza=veredicto.confianza,
            recomendacion=_texto(veredicto.recomendacion),
            falta=_lista_de_texto(veredicto.falta),
            #  Los descartes NO pasan por el tope de texto libre: son la
            #  medicion de lo que el modelo intento afirmar sin base, y
            #  vaciarlos por una decision de privacidad dejaria la tabla sin
            #  su metrica mas incomoda. Se sanean igual.
            descartes=[_sin_identificadores(str(d))[:TOPE_TEXTO]
                       for d in (veredicto.descartes or [])[:TOPE_LISTA]],
            herramientas=list(r.herramientas_usadas) if r else [],
            vueltas=r.vueltas if r else 0,
            agotado=bool(r.agotado) if r else False,
            modelo=(r.modelo if r else "")[:120],
            proveedor=(r.proveedor if r else "")[:60],
            duracion_ms=max(0, int(r.duracion_ms)) if r else 0,
            analisis_deterministico=_previo(analisis_previo),
            enriquecio=bool(enriquecio),
            registrado_en=ahora or timezone.now(),
        )
    except Exception:                                        # noqa: BLE001
        #  Ver el encabezado: el ciclo no puede caerse por su bitacora.
        return None


#  Claves del analisis deterministico que se guardan como estado previo. Es
#  lista BLANCA y no negra por el mismo motivo de siempre: si manana el
#  analisis gana una clave con un dato sensible, queda fuera por defecto en vez
#  de entrar sin que nadie lo note.
CLAVES_DEL_PREVIO = (
    #  Del analisis de una señal del ciclo.
    "accion_propuesta", "prioridad", "nivel", "impacto", "motivo",
    "tipo_senal", "huella_condicion",
    #  De la salida del seguimiento de una situacion. Sin estas, el estado
    #  previo de un seguimiento quedaba VACIO y no habia con que comparar --
    #  justo lo que esta tabla existe para permitir.
    "veredicto", "porque", "afectados_registrados", "abonados_afectados",
    "delta", "concluyente",
)


def _previo(analisis) -> dict:
    """El analisis deterministico, acotado a lo comparable."""
    if not isinstance(analisis, dict):
        return {}
    salida = {}
    for clave in CLAVES_DEL_PREVIO:
        if clave in analisis:
            valor = analisis[clave]
            salida[clave] = (_sin_identificadores(valor)[:TOPE_TEXTO]
                             if isinstance(valor, str) else valor)
    return salida
