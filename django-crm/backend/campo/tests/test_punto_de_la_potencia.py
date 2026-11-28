# -*- coding: utf-8 -*-
"""
================================================================================
 EL SEPTIMO PUNTO: LA FOTO CONTRA EL REPORTE  --  07/11/2026
================================================================================
`test_potencia_de_la_foto` mide el extractor. Esta mide el PUNTO: que la
revision del cierre lo incluya, que no pueda frenar un cierre, y que no
aparezca cuando no hay con que comparar.

LA REGLA QUE NO SE NEGOCIA
--------------------------
Vale `True` o `None`, NUNCA `False`. Un `False` se convierte en NO_CERRAR y
ademas alimenta el cierre autonomo del Supervisor. Una lectura que un modelo
hizo de una pantalla fotografiada no puede frenar el trabajo de un tecnico
(CLAUDE.md §4: crecer en alcance, no en autonomia).
================================================================================
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db

ANALISIS_70 = ('La pantalla se lee: 1310 nm, "Lo" y -70.00 dBm; no hay luces '
               "indicadoras visibles. MUESTRA: si ATENCION: no")
#  LOS 7.943 µW NO SON DECORACION: son los que le corresponden a -21.0 dBm
#  (`10*log10(7.943/1000) = -21.0`). La version anterior decia «0.682 uW»,
#  copiado de una foto que resulto ser la imagen promocional del fabricante,
#  y esos µW son -31.7 dBm. Desde que el codigo cruza las dos unidades
#  (12/11/2026), una pantalla imposible se descarta -- y estas guardas,
#  que miden el camino bueno, quedaban en rojo por su propio dato.
ANALISIS_21 = ("En el display aparecen 1550 nm, la lectura -21.0 dBm con "
               "7.943 uW y 2 KHz. MUESTRA: si ATENCION: no")


def _armar(org_a, user_profile, numero, potencia, analisis,
           requisito="medicion_al_llegar", campo="potencia_al_llegar"):
    """Una orden con su reporte de cierre y el analisis de UNA foto."""
    from campo.analisis_de_evidencia import AnalisisDeEvidencia
    from campo.models import (EventoTrabajo, EvidenciaTrabajo, OrdenTrabajo,
                              WorkType, WorkTypeVersion)

    wt = WorkType.objects.create(org=org_a, codigo=f"p{numero}",
                                 nombre="Soporte", labor="correctivo")
    version = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "evidencias": [],
                 "campos": [{"id": campo, "tipo": "decimal",
                             "titulo": "Potencia"}]})
    orden = OrdenTrabajo.objects.create(
        org=org_a, numero=numero, tipo_trabajo_version=version,
        cliente_nombre="MARIO SABANAGRANDE",
        estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO,
        #  'aplica()' pide las DOS cosas: terminada en campo y sin validar.
        #  Sin el segundo estado la revision devuelve None y la guarda del
        #  veredicto medía un andamio, no el codigo.
        estado_validacion=OrdenTrabajo.PENDIENTE,
        origen_sistema="manual", contexto={})
    cierre = EventoTrabajo.objects.create(
        org=org_a, orden=orden, #  'cierre_campo', que es el tipo que '_cierre_de_esta_vuelta' busca.
        #  Con 'cierre_enviado' la revision no encontraba el reporte y el
        #  punto no aparecia: la guarda media el andamio.
        tipo="cierre_campo",
        datos={"vuelta": 1, "respuestas": {campo: potencia},
               "definicion": [{"id": campo}]})
    if analisis is not None:
        ev = EvidenciaTrabajo.objects.create(
            org=org_a, orden_trabajo=orden, requisito_id=requisito, vuelta=1,
            storage_key=f"{requisito}-{numero}.jpg",
            nombre_original="IMG.jpg", mime_type="image/jpeg", bytes=9,
            sha256=f"{numero}".ljust(64, "z")[:64],
            estado_archivo=EvidenciaTrabajo.VERIFICADO)
        AnalisisDeEvidencia.objects.create(
            org=org_a, evidencia=ev, vuelta=1,
            origen=AnalisisDeEvidencia.IA, texto=analisis, motivo="ok",
            pide_atencion=False, modelo="x", segundos=1, tokens=1)
    return orden, cierre


def _punto(orden, cierre):
    from campo.revision_del_cierre import _potencia

    return _potencia(orden, cierre)


# ---------------------------------------------------------------------------
#  EL CASO DEL USUARIO
# ---------------------------------------------------------------------------

def test_cuando_NO_COINCIDEN_el_punto_lo_dice(org_a, user_profile):
    """LA OT #187: la foto marca -70.0 y el tecnico escribio -21.0.

    49 dBm de diferencia no es ruido de medicion.
    """
    orden, cierre = _armar(org_a, user_profile, 187, "-21.0", ANALISIS_70)

    p = _punto(orden, cierre)

    assert p is not None
    assert p["clave"] == "potencia"
    assert "-70.0" in p["texto"] and "-21.0" in p["texto"], p["texto"]


def test_cuando_NO_COINCIDEN_el_punto_NO_puede_decir_que_no(org_a,
                                                            user_profile):
    """LA REGLA QUE NO SE NEGOCIA.

    `False` se convierte en NO_CERRAR y alimenta el cierre autonomo. Una
    lectura de un modelo sobre una pantalla fotografiada no frena a un
    tecnico: pide que lo mire una persona, que es todo su alcance.
    """
    orden, cierre = _armar(org_a, user_profile, 188, "-21.0", ANALISIS_70)

    assert _punto(orden, cierre)["ok"] is None


def test_cuando_COINCIDEN_el_punto_queda_en_verde(org_a, user_profile):
    orden, cierre = _armar(org_a, user_profile, 189, "-21.4", ANALISIS_21)

    p = _punto(orden, cierre)

    assert p["ok"] is True, p


# ---------------------------------------------------------------------------
#  CUANDO NO HAY CON QUE COMPARAR, EL PUNTO NO APARECE
# ---------------------------------------------------------------------------

def test_sin_FOTO_analizada_el_punto_no_aparece(org_a, user_profile):
    """Un punto que siempre dice «no se sabe» entrena a ignorarlo."""
    orden, cierre = _armar(org_a, user_profile, 190, "-21.0", analisis=None)

    assert _punto(orden, cierre) is None


def test_sin_NUMERO_del_tecnico_el_punto_no_aparece(org_a, user_profile):
    """Una plantilla que no pregunta la potencia, o un campo vacio."""
    orden, cierre = _armar(org_a, user_profile, 191, "", ANALISIS_21)

    assert _punto(orden, cierre) is None


def test_sin_CIERRE_el_punto_no_aparece(org_a, user_profile):
    orden, _c = _armar(org_a, user_profile, 192, "-21.0", ANALISIS_21)

    assert _punto(orden, None) is None


def test_una_foto_que_el_modelo_NO_SUPO_LEER_no_acusa(org_a, user_profile):
    """Sin numero en la foto no hay juicio que hacer.

    Es la diferencia entre «no se pudo verificar» y «el tecnico mintio», y
    aca se elige la primera sin dudar.
    """
    orden, cierre = _armar(org_a, user_profile, 193, "-21.0",
                           "Se ve un medidor, la pantalla esta borrosa.")

    assert _punto(orden, cierre) is None


def test_el_numero_se_lee_venga_COMO_TEXTO_O_COMO_NUMERO(org_a, user_profile):
    """El campo es `decimal`, pero el JSON del cierre guarda lo que entro.

    Leer solo uno de los dos formatos es que el punto desaparezca sin motivo
    visible la mitad de las veces.
    """
    o1, c1 = _armar(org_a, user_profile, 194, "-21.0", ANALISIS_21)
    o2, c2 = _armar(org_a, user_profile, 195, -21.0, ANALISIS_21)
    o3, c3 = _armar(org_a, user_profile, 196, "-21,0", ANALISIS_21)

    assert _punto(o1, c1)["ok"] is True
    assert _punto(o2, c2)["ok"] is True
    assert _punto(o3, c3)["ok"] is True, "la coma decimal no se leyo"


# ---------------------------------------------------------------------------
#  EN LA REVISION ENTERA
# ---------------------------------------------------------------------------

def test_el_punto_ENTRA_en_la_revision(org_a, user_profile):
    """Que la funcion exista no alcanza: tiene que estar en `revisar()`.

    Es el defecto que CLAUDE.md §6 llama «codigo construido no es codigo que
    corre»: el reloj de tareas colgaba de un bloque que gunicorn nunca
    ejecuta, y la reconciliacion estaba probada y sin llamador.
    """
    from campo.revision_del_cierre import revisar

    orden, _c = _armar(org_a, user_profile, 197, "-21.0", ANALISIS_70)

    r = revisar(orden)

    assert r is not None, "la revision no aplica a esta orden"
    claves = [p["clave"] for p in r["puntos"]]
    assert "potencia" in claves, claves


def test_una_DIFERENCIA_no_baja_el_veredicto_a_NO_CERRAR(org_a, user_profile):
    """El efecto sobre el VEREDICTO, no solo sobre el punto.

    Es donde se vuelve peligroso: NO_CERRAR devuelve la orden al tecnico. Con
    la foto discrepando, el veredicto puede ser REVISAR --que alguien lo
    mire-- y nunca NO_CERRAR por esta sola razon.
    """
    from campo.revision_del_cierre import revisar

    orden, _c = _armar(org_a, user_profile, 198, "-21.0", ANALISIS_70)

    #  SOBRE EL PUNTO DENTRO DE LA REVISION, no sobre el veredicto global:
    #  en este andamio el checklist ya esta en False --la plantilla pide
    #  evidencias que la orden no tiene-- y afirmar sobre el veredicto
    #  mediria ese otro punto. Lo que no puede pasar es que la potencia
    #  APORTE un False.
    p = next(x for x in revisar(orden)["puntos"] if x["clave"] == "potencia")
    assert p["ok"] is not False, p


# ---------------------------------------------------------------------------
#  EL MODELO LE CORRE LA COMA  --  08/11/2026
#
#  Medido en tres ordenes seguidas de produccion (186, 198 y 204): la pantalla
#  del medidor dice -21.0 dBm y el analisis leyo -2.10 dBm, las dos veces, en
#  los dos momentos. El usuario lo confirmo mirando la foto: el tecnico
#  escribe bien.
#
#  Y este punto saltaba en TODAS las ordenes. Un «?» que aparece siempre
#  enseña a ignorarlo -- lo dice el encabezado de `_potencia`, y estaba
#  pasando.
#
#  El limite sale de la PLANTILLA (`reglas.min/max`, lo que el formulario
#  acepta), no de una constante nueva: ya esta declarado, ya varia por
#  empresa, y un -2.10 esta fuera de lo que un tecnico siquiera podria
#  escribir.
# ---------------------------------------------------------------------------

def _orden_con_limites(org, numero, *, escrito, en_la_foto, limites=(-60.0, -8.0)):
    from campo.models import (AnalisisDeEvidencia, EventoTrabajo,
                              EvidenciaTrabajo, OrdenTrabajo, WorkType,
                              WorkTypeVersion)

    campo = {"id": "potencia_al_salir", "tipo": "decimal",
             "titulo": "Potencia al salir", "unidad": "dBm"}
    if limites is not None:
        campo["reglas"] = {"min": limites[0], "max": limites[1]}
    wt = WorkType.objects.create(org=org, codigo=f"coma{numero}",
                                 nombre="Soporte", labor="correctivo")
    version = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "evidencias": [], "campos": [campo]})
    orden = OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=version,
        cliente_nombre="MARIO SABANAGRANDE",
        estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO,
        origen_sistema="manual", contexto={},
        datos={"potencia_al_salir": escrito})
    cierre = EventoTrabajo.objects.create(
        org=org, orden=orden, tipo="cierre_campo",
        datos={"vuelta": 1, "respuestas": {"solucion": "x"}})
    ev = EvidenciaTrabajo.objects.create(
        org=org, orden_trabajo=orden, requisito_id="medicion_al_salir",
        vuelta=orden.vuelta, sha256=f"c{numero}".ljust(64, "x")[:64],
        storage_key=f"k/c{numero}", nombre_original="m.jpg",
        mime_type="image/jpeg", bytes=1,
        estado_archivo=EvidenciaTrabajo.RECIBIDO)
    #  EL µW TIENE QUE CORRESPONDER AL dBm  --  12/11/2026
    #
    #  Este helper ponia «0.682 uW» fijo para cualquier dBm. Ese numero
    #  salio de copiar el texto de una foto real, que resulto ser la imagen
    #  promocional del fabricante con valores decorativos: 0.682 µW son
    #  -31.7 dBm y no coinciden con ningun escrito de estas guardas.
    #
    #  No molestaba hasta que el codigo empezo a CRUZAR las dos unidades
    #  (`PF.coherente_con_los_microwatts`). Con el µW fijo, las siete
    #  guardas de este archivo se pusieron en rojo -- y tenian razon: una
    #  pantalla que dice -21.0 dBm y 0.682 µW es imposible.
    #
    #  Se calcula desde el dBm para que la pantalla de prueba sea una
    #  pantalla posible. Una guarda con datos fisicamente imposibles mide
    #  lo que el codigo hace con basura, no lo que hace con una medicion.
    import math as _m

    _dbm = float(str(en_la_foto).replace(",", "."))
    _uw = 10 ** (_dbm / 10.0) * 1000.0
    AnalisisDeEvidencia.objects.create(
        org=org, evidencia=ev, vuelta=orden.vuelta,
        texto=f"se lee 1550 nm, {en_la_foto} dBm y {_uw:.3f} uW")
    return orden, cierre


def test_una_lectura_IMPOSIBLE_no_dispara_el_punto(org_a):
    """El caso exacto de produccion: -2.10 leido, -21.0 escrito."""
    from campo.revision_del_cierre import _potencia

    orden, cierre = _orden_con_limites(org_a, 901, escrito="-21.0",
                                       en_la_foto="-2.10")

    assert _potencia(orden, cierre) is None, (
        "el punto salto con una lectura que la plantilla ni siquiera "
        "aceptaria como respuesta")


def test_una_diferencia_REAL_sigue_disparando(org_a):
    """No se apago el punto: se apago el falso positivo."""
    from campo.revision_del_cierre import _potencia

    orden, cierre = _orden_con_limites(org_a, 902, escrito="-21.0",
                                       en_la_foto="-35.0")

    p = _potencia(orden, cierre)
    assert p is not None and p["ok"] is None, p
    assert "-35" in p["texto"] and "-21" in p["texto"], p["texto"]


def test_las_dos_que_COINCIDEN_siguen_dando_que_si(org_a):
    from campo.revision_del_cierre import _potencia

    orden, cierre = _orden_con_limites(org_a, 903, escrito="-21.0",
                                       en_la_foto="-21.0")

    assert _potencia(orden, cierre)["ok"] is True


def test_SIN_limites_declarados_no_se_filtra_nada(org_a):
    """Se prefiere una comparacion de mas a decidir por una empresa que no
    declaro nada."""
    from campo.revision_del_cierre import _potencia

    orden, cierre = _orden_con_limites(org_a, 904, escrito="-21.0",
                                       en_la_foto="-2.10", limites=None)

    assert _potencia(orden, cierre) is not None


def test_los_BORDES_del_rango_declarado_se_comparan(org_a):
    """-8 y -60 son valores que el formulario acepta: no se descartan."""
    from campo.revision_del_cierre import _potencia

    orden, cierre = _orden_con_limites(org_a, 905, escrito="-21.0",
                                       en_la_foto="-8")

    assert _potencia(orden, cierre) is not None


def test_el_rango_ESCRITO_AL_REVES_funciona_igual(org_a):
    """En dBm el «minimo» es el mas negativo, y quien configura puede
    cargarlo en cualquier orden. Pedirle que adivine la convencion es el
    mismo error que `_en_rango` ya evita con su propio `min`/`max`.

    Medido el 08/11/2026: sin esta guarda, la mutacion que quita el ordenado
    sobrevive a las quince de este archivo."""
    from campo.revision_del_cierre import _potencia

    #  CON UNA LECTURA BUENA, no con una imposible. La primera version de
    #  esta guarda uso -2.10 y la mutacion sobrevivia igual: sin ordenar, el
    #  rango queda vacio y descarta TODO, incluido el -2.10 -- el resultado
    #  coincidia por accidente. Lo que el desorden rompe es lo contrario:
    #  pierde las lecturas VALIDAS.
    orden, cierre = _orden_con_limites(org_a, 906, escrito="-35.0",
                                       en_la_foto="-21.0",
                                       limites=(-8.0, -60.0))   # al reves

    p = _potencia(orden, cierre)
    assert p is not None, (
        "con el rango cargado al reves se descarto una lectura que esta "
        "dentro de lo que la empresa acepta")
    assert "-21" in p["texto"] and "-35" in p["texto"], p["texto"]


def test_AL_LLEGAR_sin_limites_propios_usa_los_del_otro_campo(org_a):
    """EL HUECO QUE EL USUARIO ENCONTRO  --  08/11/2026.

    `potencia_al_llegar` no declara `min`/`max` --al llegar puede no haber
    señal-- asi que el filtro no filtraba nada ahi, y el punto salto con «la
    foto marca -5.0 dBm y el reporte dice -50.0: 45.0 de diferencia». El
    arreglo cubria al salir y no al llegar.

    Los dos campos son LA MISMA MEDICION: mismo instrumento, mismo equipo,
    dos momentos. No se inventa un rango -- se usa el que la empresa ya
    declaro para la otra mitad.
    """
    from campo.models import (AnalisisDeEvidencia, EventoTrabajo,
                              EvidenciaTrabajo, OrdenTrabajo, WorkType,
                              WorkTypeVersion)
    from campo.revision_del_cierre import _potencia

    #  Tal como esta en produccion: al llegar sin limites, al salir con ellos.
    campos = [
        {"id": "potencia_al_llegar", "tipo": "decimal",
         "titulo": "Potencia al llegar", "unidad": "dBm",
         "reglas": {"required": False}},
        {"id": "potencia_al_salir", "tipo": "decimal",
         "titulo": "Potencia al salir", "unidad": "dBm",
         "reglas": {"min": -60.0, "max": -8.0, "required": True}},
    ]
    wt = WorkType.objects.create(org=org_a, codigo="llegar907",
                                 nombre="Soporte", labor="correctivo")
    version = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "evidencias": [], "campos": campos})
    orden = OrdenTrabajo.objects.create(
        org=org_a, numero=907, tipo_trabajo_version=version,
        cliente_nombre="MARIO SABANAGRANDE",
        estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO,
        origen_sistema="manual", contexto={},
        datos={"potencia_al_llegar": "-50.0"})
    cierre = EventoTrabajo.objects.create(
        org=org_a, orden=orden, tipo="cierre_campo",
        datos={"vuelta": 1, "respuestas": {"solucion": "x"}})
    ev = EvidenciaTrabajo.objects.create(
        org=org_a, orden_trabajo=orden, requisito_id="medicion_al_llegar",
        vuelta=orden.vuelta, sha256="l907".ljust(64, "x")[:64],
        storage_key="k/l907", nombre_original="m.jpg",
        mime_type="image/jpeg", bytes=1,
        estado_archivo=EvidenciaTrabajo.RECIBIDO)
    AnalisisDeEvidencia.objects.create(
        org=org_a, evidencia=ev, vuelta=orden.vuelta,
        texto="se lee 1550 nm, -5.00 dBm y 0.000 uW")

    assert _potencia(orden, cierre) is None, (
        "el -5.00 de la foto de llegada no se filtro: ese campo no declara "
        "limites y no se cayo a los del campo gemelo")
