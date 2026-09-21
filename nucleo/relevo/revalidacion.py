# -*- coding: utf-8 -*-
"""
================================================================================
 La revalidacion de una accion aprobable  (contrato §3.7, T13, X17)
================================================================================

Entre que la IA propone una escritura y que una persona la aprueba pasa tiempo,
y el mundo se mueve: el ticket que se iba a responder lo cerro otro tecnico, la
factura que iba a recibir una promesa ya se pago, el servicio se dio de baja.
Ejecutar la propuesta tal cual seria escribir sobre un mundo que ya no existe.

Asi que al aprobar se vuelve a mirar, con una LECTURA declarada en el catalogo
del tenant, y solo se ejecuta si lo que devuelve sigue cumpliendo lo que se
declaro.

LA ASIMETRIA QUE GOBIERNA TODO EL MODULO
----------------------------------------
Hay tres desenlaces, no dos, y confundir los dos ultimos es el error caro:

    CUMPLE       la condicion se comprobo y se cumple    -> ejecutar
    NO CUMPLE    se comprobo y NO se cumple              -> vencida
    NO SE PUDO   la API no respondio, dio timeout, la
                 herramienta no existe                   -> NO se ejecuta,
                                                            vuelve a pendiente

"No se pudo comprobar" no es "se cumple". Tratarlo como tal ejecutaria a ciegas
justo cuando el sistema externo esta en problemas, que es el peor momento
posible. Y tampoco es "no se cumple": la accion puede seguir siendo valida, asi
que no se la mata -- vuelve a 'pendiente' y el operador reintenta.

Es la misma regla que el resto del sistema (X17, y la misma forma de
'desconocida' en B4): no saber no es lo mismo que saber que no.
"""

from __future__ import annotations

from nucleo.observabilidad.registro import registrar

#: Los tres desenlaces. No hay un cuarto, y no hay un booleano: un booleano
#: obligaria a decidir de que lado cae "no se pudo comprobar", y las dos
#: respuestas estan mal.
CUMPLE = "cumple"
NO_CUMPLE = "no_cumple"
NO_SE_PUDO = "no_se_pudo"


class Veredicto:
    """El resultado de revalidar, con su motivo legible."""

    __slots__ = ("desenlace", "codigo", "detalle")

    def __init__(self, desenlace: str, codigo: str = "", detalle: str = ""):
        self.desenlace = desenlace
        self.codigo = codigo
        self.detalle = detalle

    @property
    def puede_ejecutar(self) -> bool:
        return self.desenlace == CUMPLE

    def __repr__(self) -> str:
        return f"Veredicto({self.desenlace}, {self.codigo!r})"


def _buscar(resultado, campo: str):
    """
    El valor de 'campo' en lo que devolvio la lectura.

    Acepta rutas con punto ('servicio.estado') y, si la respuesta es una lista
    --o trae 'results'/'data', que es como contestan casi todas las APIs de
    este dominio-- mira el PRIMER elemento. Es lo que hace falta para las
    cuatro revalidaciones del contrato, y es explicito: una respuesta con
    varios elementos no se recorre entera buscando uno que cumpla, porque eso
    convertiria "alguno cumple" en "cumple" sin que nadie lo haya declarado.
    """
    actual = resultado
    if isinstance(actual, dict):
        for envoltorio in ("results", "data", "items"):
            if envoltorio in actual and isinstance(actual[envoltorio], list):
                actual = actual[envoltorio]
                break
    if isinstance(actual, list):
        if not actual:
            return None, False
        actual = actual[0]
    for parte in campo.split("."):
        if not isinstance(actual, dict) or parte not in actual:
            return None, False
        actual = actual[parte]
    return actual, True


def _mismo(a, b) -> bool:
    """
    Igualdad tolerante al tipo: la API devuelve 4 y el catalogo declara "4".

    Comparar sin esto haria fallar una condicion correcta, y una condicion que
    falla sin motivo bloquea una accion valida -- el operador ve "ya no aplica"
    de algo que si aplica, y no tiene como saber que fue un problema de tipos.
    """
    if a is None or b is None:
        return a is b
    if isinstance(a, bool) or isinstance(b, bool):
        return bool(a) is bool(b)
    if str(a) == str(b):
        return True
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return False


def _compara(valor, operador: str, esperado) -> bool:
    if operador == "igual_a":
        return _mismo(valor, esperado)
    if operador == "distinto_de":
        return not _mismo(valor, esperado)
    if operador == "en":
        return any(_mismo(valor, x) for x in (esperado or []))
    if operador == "no_en":
        return not any(_mismo(valor, x) for x in (esperado or []))
    try:
        if operador == "menor_que":
            return float(valor) < float(esperado)
        if operador == "mayor_que":
            return float(valor) > float(esperado)
    except (TypeError, ValueError):
        return False
    return False


def _argumentos_de(plantilla: dict, argumentos: dict) -> tuple[dict, str | None]:
    """
    Los argumentos de la lectura, tomados de la propuesta.

    Un marcador que la propuesta no tiene NO se manda vacio: se informa y la
    revalidacion queda como 'no se pudo'. Mandar un argumento vacio es
    preguntarle otra cosa a la API y creerle la respuesta.
    """
    resueltos = {}
    for clave, referencia in (plantilla or {}).items():
        if isinstance(referencia, str) and referencia.startswith("{") and referencia.endswith("}"):
            nombre = referencia[1:-1]
            if nombre not in (argumentos or {}):
                return {}, f"falta_argumento:{nombre}"
            resueltos[clave] = argumentos[nombre]
        else:
            resueltos[clave] = referencia
    return resueltos, None


def _evaluar_politica(config, tenant, herramienta, accion):
    """La politica de plataforma, con los hechos LEIDOS DE NUEVO.

    Se le pasan los argumentos de la accion --de ahi sale sobre que factura
    es-- y nada mas: todo lo demas se vuelve a leer. Ese es el punto de
    revalidar.
    """
    from nucleo.facturacion import politicas
    from nucleo.persistencia import db as persistencia

    return politicas.evaluar(
        config, tenant, herramienta, accion.get("argumentos") or {},
        historial=persistencia.ultima_promesa_registrada)


def revalidar(config, tenant: str, herramienta, accion: dict, *, leer=None,
              politica=None) -> Veredicto:
    """
    Corre la revalidacion declarada por 'herramienta' para esta accion.

    'leer' se inyecta (por defecto, el ejecutor HTTP del catalogo) para poder
    probar las condiciones sin red: lo que hay que proteger es la REGLA de que
    desenlace produce cada respuesta, no la mecanica del HTTP.

    Una herramienta SIN revalidacion declarada devuelve CUMPLE. No es un hueco:
    mientras la medicion ON vs OFF siga, el contrato manda que el validador
    este en modo advertencia y que esas acciones sigan el flujo actual mas las
    guardas que no dependen de config (Q3, §3.7). Lo que no puede pasar --y no
    pasa-- es que una revalidacion DECLARADA se saltee por no poder correr.
    """
    # ---- la politica de plataforma, si la herramienta declara una ----------
    # Va PRIMERO y es la comprobacion ancha: mira si la accion sigue
    # correspondiendo --el cliente pago, aparecio otra factura, ya hay una
    # promesa-- mientras que 'aprobacion.revalidar' mira una condicion puntual
    # declarada en el catalogo. Las dos hacen falta y ninguna reemplaza a la
    # otra.
    #
    # NO SE CONFIA EN LOS HECHOS DE CUANDO SE PROPUSO. Entre proponer y
    # aprobar pasa tiempo: eso es lo que esta funcion existe para cubrir, y
    # una politica que se evaluara con los datos guardados no cubriria nada.
    if getattr(herramienta, "politica", None) is not None:
        v = (politica or _evaluar_politica)(config, tenant, herramienta, accion)
        if v is not None:
            from nucleo.facturacion import promesas

            if v.resultado == promesas.NO_SE_PUDO:
                return Veredicto(NO_SE_PUDO, f"politica:{v.motivo}", v.detalle)
            if v.resultado != promesas.ELEGIBLE:
                return Veredicto(NO_CUMPLE, f"politica:{v.motivo}", v.detalle)

    aprobacion = getattr(herramienta, "aprobacion", None)
    if aprobacion is None or aprobacion.revalidar is None:
        return Veredicto(CUMPLE, "sin_revalidacion_declarada")

    plan = aprobacion.revalidar
    lectura = next((h for h in config.herramientas if h.nombre == plan.herramienta), None)
    if lectura is None:
        # Declarada y ausente: NO se ejecuta (X17). Que el catalogo haya
        # cambiado no autoriza a saltear la comprobacion.
        return Veredicto(NO_SE_PUDO, f"herramienta_ausente:{plan.herramienta}")
    if not lectura.solo_lectura:
        # Revalidar no puede escribir: correria un efecto antes de decidir si
        # se corre el efecto.
        return Veredicto(NO_SE_PUDO, f"revalidacion_no_es_lectura:{plan.herramienta}")

    argumentos = accion.get("argumentos") or {}
    args, falta = _argumentos_de(plan.argumentos, argumentos)
    if falta:
        return Veredicto(NO_SE_PUDO, falta)

    if leer is None:
        from nucleo.herramientas import http as herramientas_http

        def leer(h, a):
            return herramientas_http.ejecutar(h, a, tenant, config.variables_tenant)

    try:
        resultado = leer(lectura, args)
    except Exception as e:
        # Solo la clase del error, nunca el cuerpo: la respuesta de la API
        # puede traer datos del cliente y esto termina en un evento durable.
        registrar("acciones", "no se pudo revalidar la accion", tenant=tenant, error=e)
        return Veredicto(NO_SE_PUDO, f"lectura_fallida:{type(e).__name__}")

    for condicion in plan.condiciones:
        if condicion.valor_de_propuesta is not None:
            if condicion.valor_de_propuesta not in argumentos:
                return Veredicto(NO_SE_PUDO,
                                 f"falta_argumento:{condicion.valor_de_propuesta}")
            esperado = argumentos[condicion.valor_de_propuesta]
        else:
            esperado = condicion.valor

        valor, encontrado = _buscar(resultado, condicion.campo)
        if not encontrado:
            # El campo no vino. No se puede afirmar que la condicion se cumple
            # ni que no: es 'no se pudo'.
            return Veredicto(NO_SE_PUDO, f"campo_ausente:{condicion.campo}")
        if not _compara(valor, condicion.operador, esperado):
            return Veredicto(
                NO_CUMPLE, f"{condicion.campo}:{condicion.operador}",
                f"'{condicion.campo}' ya no cumple lo que se esperaba al proponer.")

    return Veredicto(CUMPLE)
