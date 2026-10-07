# -*- coding: utf-8 -*-
"""
================================================================================
 LA CONSTANCIA DEL RAZONAMIENTO  --  afirmando sobre el efecto
================================================================================

QUE SE VIGILA AQUI, Y QUE NO
----------------------------
Ninguna de estas pruebas comprueba que un campo EXISTA o que una funcion este
declarada. Eso ya costo caro en este proyecto: una prueba que afirmaba que una
variable existiera sobrevivio intacta a una inversion completa de la conducta.
Todas afirman sobre lo que QUEDA en la base despues de correr el camino real.

LA MAS IMPORTANTE ES 'test_5'
-----------------------------
Guardar el analisis deterministico YA ENRIQUECIDO es el fallo que no se nota:
la tabla se llena, los numeros salen, los tableros funcionan, y la comparacion
da coincidencia del 100% porque se compara el resultado contra si mismo. Un
indicador perfecto y completamente falso. 'test_5' fuerza un enriquecimiento
real y afirma que lo guardado es el motivo de ANTES.

EL MODELO NO SE LLAMA NUNCA
---------------------------
Todo entra por 'pedir', la puerta inyectable de 'cerebro.razonar'. Sin red, sin
clave y sin varianza: estas son guardas, no instrumentos.
"""

import uuid

import pytest
from django.utils import timezone

from operaciones import razonamiento, supervisor
from operaciones.cerebro import Razonamiento, Veredicto
from operaciones.models import PropuestaSupervisor
from operaciones.razonamiento_modelos import (
    FuenteRazonamiento,
    RazonamientoSupervisor,
)
from operaciones.situaciones_modelos import Confianza, Riesgo

pytestmark = pytest.mark.django_db


# =============================================================================
#  ANDAMIO
# =============================================================================

def _veredicto(**kw):
    """Un veredicto completo, con razonamiento, listo para guardar."""
    base = dict(
        hechos=[{"fuente": "afectados_situacion", "dato": "4 ONT en el pon 4/14"}],
        inferencias=["el patron apunta a la acometida"],
        riesgos=["clientes del mismo pon sin reclamo todavia"],
        riesgo=Riesgo.ALTO,
        hipotesis="corte en la acometida del pon 4/14",
        confianza=Confianza.MEDIA,
        recomendacion="revisar la caja antes de despachar cuatro visitas",
        falta=["no pudo confirmar corte de energia en el sector"],
        concluyente=True,
        descartes=["la caja fue intervenida la semana pasada"],
        razonamiento=Razonamiento(
            contenido="{}",
            consultadas=[{"nombre": "afectados_situacion", "argumentos": {},
                         "hubo_error": False}],
            modelo="deepseek-chat", proveedor="deepseek",
            vueltas=2, agotado=False, duracion_ms=7400),
    )
    base.update(kw)
    return Veredicto(**base)


ANALISIS = {
    "accion_propuesta": "agrupar_casos",
    "motivo": "cuatro casos abiertos en la misma zona",
    "prioridad": 10,
    "impacto": "4 clientes",
    "nivel": PropuestaSupervisor.NIVEL_RECOMENDAR,
    "tipo_senal": PropuestaSupervisor.CASO_ANTIGUO,
    "huella_condicion": "zona:CANDELARIA2|pon:4-14",
}


class _SenalFalsa:
    """Un doble con los mismos atributos que 'supervisor.Senal' usa de verdad."""

    tipo = PropuestaSupervisor.CASO_ANTIGUO
    evidencia = {"pon": "4/14", "casos": 4}
    huella = ""


def _propuesta(org):
    return PropuestaSupervisor.objects.create(
        org=org, tipo_senal=PropuestaSupervisor.CASO_ANTIGUO, origen_tipo="situacion",
        origen_id=str(uuid.uuid4()), accion_propuesta="agrupar_casos",
        motivo="cuatro casos abiertos en la misma zona",
        evidencia=[{"fuente": "regla", "dato": "4 casos"}],
        prioridad=10, impacto="4 clientes",
        nivel_autonomia_requerido=PropuestaSupervisor.NIVEL_RECOMENDAR,
        huella_condicion=f"h-{uuid.uuid4().hex[:10]}",
        conocimiento_version="hab-2026.10-14",
        expira_en=timezone.now() + timezone.timedelta(hours=12))


def _con_banderas(monkeypatch, registra, enriquece):
    monkeypatch.setattr(supervisor, "CEREBRO_REGISTRA", registra)
    monkeypatch.setattr(supervisor, "CEREBRO_EN_EL_CICLO", enriquece)


def _concluye_con(monkeypatch, veredicto):
    """Hace que 'cerebro.concluir' devuelva ese veredicto, sin tocar el modelo."""
    from operaciones import cerebro
    monkeypatch.setattr(cerebro, "concluir", lambda *a, **k: veredicto)
    monkeypatch.setattr(cerebro, "contexto_para", lambda *a, **k: "contexto")


# =============================================================================
#  1 · APAGADO NO ESCRIBE NADA
# =============================================================================

def test_1_apagado_no_escribe_ninguna_fila(org_a, monkeypatch):
    """
    Con las dos banderas en False no se escribe NADA.

    Es la afirmacion que permite desplegar sin miedo: el codigo llega a
    produccion y la tabla se queda vacia hasta que alguien decida.
    """
    org = org_a
    _con_banderas(monkeypatch, registra=False, enriquece=False)
    _concluye_con(monkeypatch, _veredicto())

    aporte = supervisor.razonar_sobre(org, _SenalFalsa(), dict(ANALISIS))
    aporte.dejar_constancia(org, propuesta=_propuesta(org))

    assert RazonamientoSupervisor.objects.filter(org=org).count() == 0
    #  Y ni siquiera llamo al cerebro: el veredicto no viajo.
    assert aporte.veredicto is None


# =============================================================================
#  2 · SOLO REGISTRA: ESCRIBE, Y NO TOCA LA PROPUESTA
# =============================================================================

def test_2_solo_registra_deja_el_analisis_intacto(org_a, monkeypatch):
    """
    En 'solo registra' se escribe la fila Y el analisis sale IDENTICO.

    Se afirma identidad de objeto, no igualdad: si el camino hiciera una copia
    por el medio, una comparacion por valor igual pasaria y el dia que esa
    copia se modifique nadie se entera.
    """
    org = org_a
    _con_banderas(monkeypatch, registra=True, enriquece=False)
    _concluye_con(monkeypatch, _veredicto())

    entrada = dict(ANALISIS)
    aporte = supervisor.razonar_sobre(org, _SenalFalsa(), entrada)

    assert aporte.analisis is entrada
    assert aporte.enriquecio is False

    fila = aporte.dejar_constancia(org, propuesta=_propuesta(org))
    assert fila is not None
    assert fila.enriquecio is False
    assert RazonamientoSupervisor.objects.filter(org=org).count() == 1


def test_2b_solo_registra_no_cambia_ningun_campo_de_la_propuesta(org_a, monkeypatch):
    """
    La propuesta creada despues del razonamiento es campo por campo la misma
    que sin cerebro. Se compara contra una propuesta de referencia construida
    con el analisis original.
    """
    org = org_a
    _con_banderas(monkeypatch, registra=True, enriquece=False)
    _concluye_con(monkeypatch, _veredicto())

    entrada = dict(ANALISIS)
    salida = supervisor.razonar_sobre(org, _SenalFalsa(), entrada).analisis

    for clave, valor in ANALISIS.items():
        assert salida[clave] == valor, f"'{clave}' cambio en 'solo registra'"


# =============================================================================
#  3 · UN VEREDICTO QUE NO CIERRA TAMBIEN SE REGISTRA
# =============================================================================

def test_3_lo_no_concluyente_tambien_queda(org_a, monkeypatch):
    """
    Un veredicto no concluyente se guarda, marcado como tal.

    Filtrarlo seria sesgar la medicion hacia arriba: se perderia justamente el
    numero de veces que el cerebro se quedo corto y lo dijo en vez de inventar,
    que es la mitad del valor de esta tabla.
    """
    org = org_a
    _con_banderas(monkeypatch, registra=True, enriquece=False)
    _concluye_con(monkeypatch, _veredicto(
        concluyente=False,
        falta=["no pudo leer el estado de la OLT"],
        hipotesis="", confianza=Confianza.SIN_HIPOTESIS))

    aporte = supervisor.razonar_sobre(org, _SenalFalsa(), dict(ANALISIS))
    fila = aporte.dejar_constancia(org, propuesta=_propuesta(org))

    assert fila is not None, "un veredicto sin concluir tiene que quedar"
    assert fila.concluyente is False
    assert fila.falta == ["no pudo leer el estado de la OLT"]


# =============================================================================
#  4 · LOS DESCARTES QUEDAN GUARDADOS
# =============================================================================

def test_4_lo_descartado_queda_registrado(org_a, monkeypatch):
    """
    Lo que 'validar()' le quito al modelo por no tener fuente queda en la fila.

    Es la metrica mas incomoda y la que no puede perderse: cuenta las veces que
    el modelo afirmo algo que ninguna herramienta respaldaba. Un numero que
    suba aqui es motivo para NO subir autonomia.
    """
    org = org_a
    _con_banderas(monkeypatch, registra=True, enriquece=False)
    _concluye_con(monkeypatch, _veredicto(
        descartes=["la caja fue intervenida la semana pasada",
                   "el tecnico ya paso por ahi"]))

    aporte = supervisor.razonar_sobre(org, _SenalFalsa(), dict(ANALISIS))
    fila = aporte.dejar_constancia(org, propuesta=_propuesta(org))

    assert len(fila.descartes) == 2
    assert "la caja fue intervenida la semana pasada" in fila.descartes
    assert fila.intento_afirmar_sin_base is True


# =============================================================================
#  5 · EL ESTADO PREVIO ES EL DE ANTES  --  la prueba que mas importa
# =============================================================================

def test_5_guarda_el_analisis_de_antes_no_el_enriquecido(org_a, monkeypatch):
    """
    Con el cerebro enriqueciendo, lo guardado es el motivo PREVIO.

    SI ESTO FALLA, TODA LA MEDICION ES FALSA Y PARECE CORRECTA: la tabla se
    llena, los tableros funcionan, y la comparacion da coincidencia siempre
    porque se compara el resultado contra si mismo.

    Por eso no se afirma que exista una copia: se fuerza un enriquecimiento que
    CAMBIA el motivo, y se afirma que lo guardado no es el motivo nuevo.
    """
    org = org_a
    _con_banderas(monkeypatch, registra=True, enriquece=True)
    _concluye_con(monkeypatch, _veredicto(
        recomendacion="revisar la acometida del pon antes de las visitas"))

    entrada = dict(ANALISIS)
    motivo_original = entrada["motivo"]

    aporte = supervisor.razonar_sobre(org, _SenalFalsa(), entrada)

    #  Precondicion de la prueba: si el enriquecimiento no cambio nada, esta
    #  prueba no estaria midiendo lo que dice medir.
    assert aporte.analisis["motivo"] != motivo_original, (
        "el enriquecimiento no cambio el motivo: la prueba no prueba nada")

    fila = aporte.dejar_constancia(org, propuesta=_propuesta(org))

    assert fila.analisis_deterministico["motivo"] == motivo_original
    assert fila.analisis_deterministico["motivo"] != aporte.analisis["motivo"]
    assert fila.enriquecio is True


def test_5b_el_previo_solo_trae_las_claves_declaradas(org_a, monkeypatch):
    """
    El estado previo es lista BLANCA: una clave nueva del analisis no entra
    sola. Si manana el analisis gana un campo con un dato sensible, queda
    fuera por defecto en vez de colarse sin que nadie lo note.
    """
    org = org_a
    _con_banderas(monkeypatch, registra=True, enriquece=False)
    _concluye_con(monkeypatch, _veredicto())

    entrada = dict(ANALISIS)
    entrada["cedula_del_cliente"] = "1234567890"

    aporte = supervisor.razonar_sobre(org, _SenalFalsa(), entrada)
    fila = aporte.dejar_constancia(org, propuesta=_propuesta(org))

    assert "cedula_del_cliente" not in fila.analisis_deterministico
    assert "motivo" in fila.analisis_deterministico


# =============================================================================
#  6 · SI LA ESCRITURA FALLA, EL CICLO TERMINA IGUAL
# =============================================================================

def test_6_un_fallo_al_guardar_no_rompe_el_ciclo(org_a, monkeypatch):
    """
    La bitacora no puede tumbar al ciclo.

    Se rompe la escritura a proposito y se afirma que 'dejar_constancia'
    devuelve None sin levantar -- la propuesta ya esta creada y el ciclo sigue.
    Lo que se pierde es la constancia, no el trabajo.
    """
    org = org_a
    _con_banderas(monkeypatch, registra=True, enriquece=False)
    _concluye_con(monkeypatch, _veredicto())

    def revienta(*a, **k):
        raise RuntimeError("la base no responde")

    monkeypatch.setattr(RazonamientoSupervisor.objects, "create", revienta)

    aporte = supervisor.razonar_sobre(org, _SenalFalsa(), dict(ANALISIS))
    fila = aporte.dejar_constancia(org, propuesta=_propuesta(org))

    assert fila is None
    assert RazonamientoSupervisor.objects.filter(org=org).count() == 0


# =============================================================================
#  7 · LA INVARIANTE DE LAS BANDERAS
# =============================================================================

def test_7_enriquecer_implica_registrar(monkeypatch):
    """
    No existe 'enriquece sin dejar constancia'.

    Es la cuarta combinacion que la tabla de banderas declara imposible, y la
    razon de que exista esta pieza: un cerebro influyendo en propuestas sin que
    despues se pueda comparar con que criterio lo hizo.
    """
    monkeypatch.setattr(supervisor, "CEREBRO_REGISTRA", False)
    monkeypatch.setattr(supervisor, "CEREBRO_EN_EL_CICLO", True)
    assert supervisor._el_cerebro_corre() is True


def test_7b_el_enriquecimiento_sigue_apagado():
    """
    LA MITAD QUE IMPORTA DE ESTA GUARDA, y por que cambio.

    Nacio afirmando que las DOS banderas estaban apagadas, porque entonces lo
    que se defendia era "llega inerte". El 07/10/2026 se encendio 'CEREBRO_
    REGISTRA' por decision explicita: el cerebro razona y guarda, sin tocar la
    propuesta.

    Lo que esta guarda sigue defendiendo --y es la mitad valiosa-- es que
    'CEREBRO_EN_EL_CICLO' NO se encienda sin que alguien lo note. Esa es la que
    deja al cerebro modificando propuestas, y encenderla exige antes la medicion
    que el registro esta produciendo.

    Se leen los valores del modulo, no los parcheados: es el unico test del
    archivo que mira las constantes, y mira las que de verdad se despliegan.
    """
    assert supervisor.CEREBRO_EN_EL_CICLO is False, (
        "el enriquecimiento se encendio sin pasar por aqui: eso deja al cerebro "
        "modificando el motivo y el impacto de propuestas reales")
    #  Y la invariante sigue valiendo: enriquecer implica registrar, nunca al
    #  reves. Con el registro encendido esto es trivialmente cierto, y se afirma
    #  igual para que siga siendo cierto si alguien lo apaga.
    assert supervisor._el_cerebro_corre() is True


# =============================================================================
#  8 · PII  --  el cinturon sobre el texto libre
# =============================================================================

def test_8_los_identificadores_no_quedan_en_claro(org_a, monkeypatch):
    """
    Un documento, un movil y un correo sueltos en el texto del modelo no
    quedan guardados en claro.

    NO ES LA GARANTIA PRINCIPAL y el modulo lo dice: la lista blanca de campos
    por rol ya impide que esos datos lleguen al modelo. Esto es la segunda
    capa, y se prueba igual porque una segunda capa que no funciona es peor que
    ninguna -- da la tranquilidad sin dar la proteccion.
    """
    org = org_a
    _con_banderas(monkeypatch, registra=True, enriquece=False)
    _concluye_con(monkeypatch, _veredicto(
        recomendacion="contactar al 3014567890 o a juan@correo.com, cc 1098765432",
        hipotesis="el cliente 1098765432 reporto el corte",
        confianza=Confianza.BAJA))

    aporte = supervisor.razonar_sobre(org, _SenalFalsa(), dict(ANALISIS))
    fila = aporte.dejar_constancia(org, propuesta=_propuesta(org))

    assert "3014567890" not in fila.recomendacion
    assert "juan@correo.com" not in fila.recomendacion
    assert "1098765432" not in fila.recomendacion
    assert "1098765432" not in fila.hipotesis
    #  Y lo que no es un identificador sobrevive: la frase sigue siendo util.
    assert "contactar al" in fila.recomendacion


def test_8b_el_saneo_no_borra_la_fuente_de_un_hecho(org_a, monkeypatch):
    """
    La fuente de un hecho es el nombre de una herramienta del catalogo, un
    valor cerrado -- y es justamente lo que vuelve auditable al hecho. Sanearla
    romperia la trazabilidad para proteger algo que no es un dato personal.
    """
    org = org_a
    _con_banderas(monkeypatch, registra=True, enriquece=False)
    _concluye_con(monkeypatch, _veredicto(
        hechos=[{"fuente": "consultar_tickets_de_cliente",
                 "dato": "el equipo reporto dying-gasp"}]))

    aporte = supervisor.razonar_sobre(org, _SenalFalsa(), dict(ANALISIS))
    fila = aporte.dejar_constancia(org, propuesta=_propuesta(org))

    assert fila.hechos[0]["fuente"] == "consultar_tickets_de_cliente"


# =============================================================================
#  9 · LA RESTRICCION DE LA BASE
# =============================================================================

def test_9_una_fila_huerfana_no_se_crea(org_a, monkeypatch):
    """
    Sin propuesta ni situacion no hay fila: 'registrar' se niega antes de
    llegar a la base, para no dejar una excepcion en el log por un error de
    llamada. El CheckConstraint la rechazaria igual -- la regla vive en los dos
    lados a proposito.
    """
    org = org_a
    assert razonamiento.registrar(
        org, _veredicto(), fuente=FuenteRazonamiento.CICLO) is None
    assert RazonamientoSupervisor.objects.filter(org=org).count() == 0


def test_9b_la_hipotesis_sin_confianza_la_rechaza_la_base(org_a):
    """
    La garantia 3 del cerebro, impuesta por la tabla: una hipotesis sin
    confianza declarada, o una confianza sin hipotesis, son las dos formas de
    presentar una sospecha como un hecho.
    """
    from django.db.utils import IntegrityError

    org = org_a
    with pytest.raises(IntegrityError):
        RazonamientoSupervisor.objects.create(
            org=org, propuesta=_propuesta(org),
            hipotesis="algo paso en el pon",
            confianza=Confianza.SIN_HIPOTESIS,
            registrado_en=timezone.now())


# =============================================================================
#  10 · EL CAMINO REAL  --  un ciclo completo deja su fila
# =============================================================================

def test_10_el_ciclo_completo_deja_constancia_por_propuesta(org_a, monkeypatch):
    """
    CODIGO CONSTRUIDO NO ES CODIGO QUE CORRE.

    Las pruebas de arriba ejercitan 'razonar_sobre' y 'dejar_constancia'
    directamente. Esta recorre '_correr_ciclo', que es la topologia real, y
    afirma que por cada propuesta registrada quedo su razonamiento. Es la
    unica que caza el olvido de llamar a 'dejar_constancia' en el ciclo.
    """
    org = org_a
    _con_banderas(monkeypatch, registra=True, enriquece=False)
    _concluye_con(monkeypatch, _veredicto())

    senal = supervisor.Senal(
        tipo=PropuestaSupervisor.CASO_ANTIGUO, origen_tipo="case",
        origen_id=str(uuid.uuid4()),
        evidencia=[{"fuente": "regla", "dato": "4 casos en el pon 4/14",
                    "observado_en": timezone.now().isoformat()}],
        datos={"pon": "4/14", "clasificacion": supervisor.OBSERVADO},
        huella=f"caso_antiguo|{uuid.uuid4().hex[:8]}")

    monkeypatch.setattr(supervisor, "detectar", lambda *a, **k: [senal])
    monkeypatch.setattr(supervisor, "analizar", lambda *a, **k: dict(ANALISIS))

    supervisor._correr_ciclo(org, timezone.now())

    propuestas = PropuestaSupervisor.objects.filter(org=org).count()
    filas = RazonamientoSupervisor.objects.filter(org=org).count()

    assert propuestas >= 1, "el ciclo no registro ninguna propuesta"
    assert filas == propuestas, (
        f"{propuestas} propuesta(s) y {filas} razonamiento(s): el ciclo no "
        f"esta dejando constancia por cada una")


# =============================================================================
#  11 · ANTECEDENTES  --  lo que separa un agente de un motor de ciclo
# =============================================================================

def test_11_sin_antecedentes_devuelve_vacio(org_a):
    """
    La primera vez no hay nada que contar, y el vacio tambien es informacion:
    condicion nueva no es condicion sana.
    """
    from operaciones import cerebro
    assert cerebro.antecedentes_de(org_a, "huella-que-nadie-vio") == ""
    assert cerebro.antecedentes_de(org_a, "") == ""


def test_11b_trae_lo_que_se_propuso_y_como_termino(org_a, user_profile):
    """
    La segunda vez que aparece la misma condicion, el cerebro tiene que saber
    que paso la primera. Se afirma sobre el TEXTO que se le va a dar, no sobre
    que la funcion exista.
    """
    from operaciones import cerebro

    p = _propuesta(org_a)
    huella = p.huella_condicion

    from operaciones.gobierno_modelos import DecisionSupervisor
    DecisionSupervisor.objects.create(
        org=org_a, propuesta=p, recomendacion=p.accion_propuesta,
        tipo="rechazo", actor=user_profile, decidida_en=timezone.now(),
        motivo="no era la caja", resultado="no_funciono",
        resultado_en=timezone.now(),
        resultado_evidencia="la caja estaba bien, era el equipo del cliente")

    texto = cerebro.antecedentes_de(org_a, huella)

    assert "agrupar_casos" in texto, "no dice QUE se propuso"
    assert "rechazo" in texto, "no dice QUE decidio la persona"
    assert "no_funciono" in texto, "no dice COMO termino"
    assert "la caja estaba bien" in texto, "no trae la evidencia del resultado"
    #  Y la instruccion de que no repita lo que ya fallo:
    assert "ya se rechazo o no funciono" in texto


def test_11c_el_nombre_del_cliente_no_viaja(org_a, user_profile):
    """
    Misma regla que 'CAMPOS_QUE_NO_VIAJAN': lo que cambia el razonamiento es
    que se propuso y como salio, no de quien era el servicio.
    """
    from operaciones import cerebro

    p = _propuesta(org_a)
    p.motivo = "el cliente Mario Sabanagrande reporto sin servicio"
    p.save()

    texto = cerebro.antecedentes_de(org_a, p.huella_condicion)
    assert "Mario" not in texto
    assert "Sabanagrande" not in texto


def test_11d_un_fallo_al_consultarlos_no_rompe_el_razonamiento(org_a, monkeypatch):
    """
    Degradar, no romper: sin antecedentes el cerebro razona como razonaba antes
    de que esto existiera.
    """
    from operaciones import cerebro
    from operaciones.models import PropuestaSupervisor

    def revienta(*a, **k):
        raise RuntimeError("la base no responde")

    monkeypatch.setattr(PropuestaSupervisor.objects, "filter", revienta)
    assert cerebro.antecedentes_de(org_a, "cualquiera") == ""


def test_11e_los_antecedentes_llegan_al_cerebro(org_a, monkeypatch):
    """
    CODIGO CONSTRUIDO NO ES CODIGO QUE CORRE.

    Las tres de arriba prueban la funcion. Esta prueba que el CICLO se la pasa:
    se intercepta 'concluir' y se afirma que la entrada trae el bloque. Es la
    unica que caza el olvido de cablearla.
    """
    from operaciones import cerebro

    p = _propuesta(org_a)
    recibido = {}

    def espiar(org, *, instrucciones, entrada, **k):
        recibido["entrada"] = entrada
        return _veredicto()

    _con_banderas(monkeypatch, registra=True, enriquece=False)
    monkeypatch.setattr(cerebro, "concluir", espiar)
    monkeypatch.setattr(cerebro, "contexto_para", lambda *a, **k: "panorama")

    senal = supervisor.Senal(
        tipo=PropuestaSupervisor.CASO_ANTIGUO, origen_tipo="case",
        origen_id=str(uuid.uuid4()), evidencia=[], datos={},
        huella=p.huella_condicion)

    supervisor.razonar_sobre(org_a, senal, dict(ANALISIS))

    assert "== ANTECEDENTES ==" in recibido["entrada"], (
        "el ciclo no le esta pasando los antecedentes al cerebro")
    assert "agrupar_casos" in recibido["entrada"]
