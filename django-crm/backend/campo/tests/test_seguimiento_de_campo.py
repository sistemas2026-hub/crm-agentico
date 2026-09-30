# -*- coding: utf-8 -*-
"""La bitacora de una intervencion: INICIO, AVANCE, BLOQUEO y CIERRE.

LO QUE ESTAS PRUEBAS DEFIENDEN
------------------------------
Cuatro cosas, y las cuatro nacieron de una decision escrita que alguien podria
reinterpretar en la sesion siguiente:

  1. **el evento se lee con SU esquema, no con el vigente.** Es la que importa
     mas: si la lectura dependiera del `WorkTypeVersion` de hoy, un AVANCE de hace
     tres años cambiaria de significado --o se quedaria mudo-- sin que nadie lo
     toque. La prueba cambia la version del tipo de trabajo DESPUES de registrar y
     exige que el evento diga exactamente lo mismo;

  2. **los campos los declara el tipo de trabajo.** Ni un dBm, ni un PLC en el
     codigo. La prueba declara campos propios de una empresa inventada y exige que
     el formulario los devuelva, y que un campo que no existe se rechace;

  3. **una declaracion humana se guarda con quien la afirmo.** "Servicio validado"
     no puede quedar como si el sistema lo hubiera medido;

  4. **registrar un bloqueo NO mueve el estado operativo.** La maquina de estados
     es la de `transiciones.py` y sigue siendo la unica que decide. Esta prueba
     existe para que la fase siguiente no la rompa sin darse cuenta.

Y una que tapa un hueco real del validador: un campo obligatorio AUSENTE del
diccionario no lo caza `validar_campos_tecnicos`, porque solo recorre las claves
que llegan. Eso esta bien para el guardado parcial del telefono y mal para un
reporte, asi que se exige aca.
"""

import pytest
from rest_framework.test import APIClient

from campo.models import (
    AsignacionTrabajo,
    EventoTrabajo,
    OrdenTrabajo,
    WorkType,
    WorkTypeVersion,
)
from campo.services import seguimiento_campo as seg
from common.models import Profile
from common.serializer import OrgAwareRefreshToken

pytestmark = pytest.mark.django_db


#: Un tipo de trabajo de una empresa inventada, con SUS campos. El punto es que
#: ninguno de estos nombres esta en el codigo del motor.
ESQUEMA_CON_SEGUIMIENTO = {
    "pasos": [],
    "campos": [],
    "evidencias": [],
    "seguimiento": {
        "inicio": {
            "campos": [
                {
                    "id": "punto_intervenido",
                    "titulo": "Punto intervenido",
                    "tipo": "texto",
                    "reglas": {"required": True},
                },
                {
                    "id": "nivel_inicial_1550",
                    "titulo": "Nivel inicial 1550 nm (dBm)",
                    "tipo": "decimal",
                    "reglas": {"required": True, "min": -30, "max": 0},
                },
            ],
            "evidencias": [
                {"id": "foto_punto", "titulo": "Foto del punto", "tipo": "foto"}
            ],
        },
        "avance": {
            "campos": [
                {
                    "id": "validaciones",
                    "titulo": "Validaciones realizadas",
                    "tipo": "texto",
                    "reglas": {"required": True},
                },
                {
                    "id": "nivel_actual",
                    "titulo": "Nivel actual (dBm)",
                    "tipo": "decimal",
                    "reglas": {"required": False},
                },
            ]
        },
        "bloqueo": {
            "campos": [
                {
                    "id": "categoria",
                    "titulo": "Categoría",
                    "tipo": "seleccion",
                    "reglas": {
                        "required": True,
                        "options": ["material", "acceso", "permiso", "red"],
                    },
                },
                {
                    "id": "necesita_de_noc",
                    "titulo": "Qué se necesita del NOC",
                    "tipo": "texto",
                    "reglas": {"required": True},
                },
            ]
        },
        "cierre": {
            "campos": [
                {
                    "id": "falla_encontrada",
                    "titulo": "Falla encontrada",
                    "tipo": "texto",
                    "reglas": {"required": True},
                },
                {
                    "id": "servicio_validado",
                    "titulo": "¿El servicio quedó funcionando?",
                    "tipo": "booleano",
                    "reglas": {"required": True},
                    "declaracion": True,
                },
            ]
        },
    },
}


def _cliente(user, org, profile):
    c = APIClient()
    t = OrgAwareRefreshToken.for_user_and_org(user, org, profile)
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {t.access_token}")
    return c


def _ruta(orden):
    return f"/api/campo/trabajos/{orden.id}/seguimiento/"


@pytest.fixture
def tecnico(org_a, django_user_model):
    user = django_user_model.objects.create_user(
        email="tecnico.seg@test.com", password="testpass123"
    )
    profile = Profile.objects.create(user=user, org=org_a, role="USER", is_active=True)
    return user, profile


@pytest.fixture
def version_con_seguimiento(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="corte_fibra", nombre="Corte de fibra")
    return WorkTypeVersion.objects.create(
        work_type=wt,
        version=1,
        schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema=ESQUEMA_CON_SEGUIMIENTO,
        schema_hash="hash-v1",
    )


@pytest.fixture
def version_sin_seguimiento(org_a):
    """Un tipo de trabajo que no declara nada: tiene que funcionar igual."""
    wt = WorkType.objects.create(org=org_a, codigo="simple", nombre="Trabajo simple")
    return WorkTypeVersion.objects.create(
        work_type=wt,
        version=1,
        schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "campos": [], "evidencias": []},
    )


def _orden(org, version, profile, numero=9001, estado=OrdenTrabajo.EN_SITIO):
    o = OrdenTrabajo.objects.create(
        org=org,
        numero=numero,
        tipo_trabajo_version=version,
        cliente_nombre="Beatriz Pinzon",
        cliente_direccion="Calle 50 # 10-20",
        estado_operativo=estado,
        revision=1,
    )
    AsignacionTrabajo.objects.create(
        orden=o, profile=profile, rol="tecnico", es_principal=True
    )
    return o


@pytest.fixture
def orden(org_a, version_con_seguimiento, tecnico):
    return _orden(org_a, version_con_seguimiento, tecnico[1])


# --------------------------------------------------------------------------- #
# A. El formulario sale del tipo de trabajo
# --------------------------------------------------------------------------- #

def test_a_el_formulario_lo_declara_el_tipo_de_trabajo(orden):
    f = seg.formulario_de(orden, seg.INICIO)
    assert [c["id"] for c in f["campos"]] == ["punto_intervenido", "nivel_inicial_1550"]
    assert f["declarado_por_el_tipo_de_trabajo"] is True
    assert f["tipo_evento"] == "inicio_campo"
    assert [e["id"] for e in f["evidencias"]] == ["foto_punto"]


def test_b_sin_declaracion_se_usa_el_minimo_generico(org_a, version_sin_seguimiento, tecnico):
    """Y el minimo NO trae campos de ningun ISP: una nota en palabras."""
    o = _orden(org_a, version_sin_seguimiento, tecnico[1], numero=9002)
    f = seg.formulario_de(o, seg.AVANCE)
    assert [c["id"] for c in f["campos"]] == ["nota"]
    assert f["declarado_por_el_tipo_de_trabajo"] is False

    b = seg.formulario_de(o, seg.BLOQUEO)
    # Un bloqueo sin "que necesito del NOC" no es accionable: vuelve a ser un
    # mensaje de chat.
    assert "necesita_de_noc" in [c["id"] for c in b["campos"]]


def test_c_ningun_campo_de_rapilink_vive_en_el_codigo():
    """La guarda de la decision 2, sobre el modulo entero.

    Se mira el AST y NO el texto del archivo, por una razon que este repositorio
    ya pago una vez: un grep sobre el fuente tambien lee los comentarios, y los
    comentarios de ese servicio NOMBRAN los campos prohibidos justamente para
    explicar por que no van en el codigo. Una guarda que se rompe con su propia
    documentacion enseña a borrar la documentacion.

    Asi que se revisan solo los literales de texto y los nombres del codigo
    ejecutable: las docstrings se descartan explicitamente.
    """
    import ast
    import inspect

    PROHIBIDOS = ("1550", "1490", "plc", "dbm", "sn_onu", "rapilink")

    arbol = ast.parse(inspect.getsource(seg))

    # Las docstrings son documentacion, no comportamiento: se sacan de la revision.
    docstrings = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            cuerpo = getattr(nodo, "body", [])
            if (cuerpo and isinstance(cuerpo[0], ast.Expr)
                    and isinstance(cuerpo[0].value, ast.Constant)
                    and isinstance(cuerpo[0].value.value, str)):
                docstrings.add(id(cuerpo[0].value))

    sospechosos = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
            if id(nodo) in docstrings:
                continue
            texto = nodo.value.lower()
            for prohibido in PROHIBIDOS:
                if prohibido in texto:
                    sospechosos.append(f"literal {nodo.value!r} (linea {nodo.lineno})")
        elif isinstance(nodo, ast.Name):
            nombre = nodo.id.lower()
            for prohibido in PROHIBIDOS:
                if prohibido in nombre:
                    sospechosos.append(f"nombre {nodo.id} (linea {nodo.lineno})")

    assert not sospechosos, (
        "El servicio trae datos de una empresa concreta en su codigo; eso lo "
        "declara el tipo de trabajo: " + "; ".join(sospechosos)
    )


def test_c2_la_guarda_de_arriba_si_caza_un_campo_metido_en_el_codigo():
    """Verificacion en negativo de la guarda anterior.

    Una guarda que nunca vio un caso malo no prueba nada: se le da un modulo con
    el defecto adentro --y con la misma palabra en su docstring, que NO debe
    contar-- y tiene que encontrar exactamente uno.
    """
    import ast

    fuente = (
        '"""Este modulo habla de PLC y de 1550 nm en su docstring."""\n'
        'MINIMO = [{"id": "nivel_1550", "tipo": "decimal"}]\n'
    )
    arbol = ast.parse(fuente)
    docstrings = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.Module, ast.ClassDef, ast.FunctionDef)):
            cuerpo = getattr(nodo, "body", [])
            if (cuerpo and isinstance(cuerpo[0], ast.Expr)
                    and isinstance(cuerpo[0].value, ast.Constant)
                    and isinstance(cuerpo[0].value.value, str)):
                docstrings.add(id(cuerpo[0].value))

    hallados = [
        n.value for n in ast.walk(arbol)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
        and id(n) not in docstrings and "1550" in n.value.lower()
    ]
    assert hallados == ["nivel_1550"], hallados


def test_d_un_momento_inventado_se_rechaza(orden):
    with pytest.raises(seg.SeguimientoInvalido) as e:
        seg.registrar(orden, profile=None, momento="pausa", respuestas={})
    assert "no es un momento" in str(e.value)


# --------------------------------------------------------------------------- #
# E-H. Lo que se exige antes de escribir
# --------------------------------------------------------------------------- #

def test_e_un_obligatorio_ausente_se_caza(orden, tecnico):
    """El hueco del validador: solo recorre las claves que LLEGAN."""
    with pytest.raises(seg.SeguimientoInvalido) as e:
        seg.registrar(
            orden, profile=tecnico[1], momento=seg.INICIO,
            respuestas={"punto_intervenido": "CTO-045"},  # falta el nivel
        )
    assert "nivel_inicial_1550" in e.value.errores
    assert EventoTrabajo.objects.filter(tipo="inicio_campo").count() == 0


def test_f_un_campo_que_no_existe_en_el_esquema_se_rechaza(orden, tecnico):
    with pytest.raises(seg.SeguimientoInvalido) as e:
        seg.registrar(
            orden, profile=tecnico[1], momento=seg.AVANCE,
            respuestas={"validaciones": "revise el PLC", "inventado": 1},
        )
    assert "inventado" in e.value.errores


def test_g_una_regla_del_tipo_de_trabajo_se_aplica(orden, tecnico):
    """El rango lo puso la empresa, y se respeta."""
    with pytest.raises(seg.SeguimientoInvalido) as e:
        seg.registrar(
            orden, profile=tecnico[1], momento=seg.INICIO,
            respuestas={"punto_intervenido": "CTO-045", "nivel_inicial_1550": -99},
        )
    assert "nivel_inicial_1550" in e.value.errores


def test_h_no_se_cierra_lo_que_nunca_se_inicio(orden, tecnico):
    with pytest.raises(seg.SeguimientoInvalido) as e:
        seg.registrar(
            orden, profile=tecnico[1], momento=seg.CIERRE,
            respuestas={"falla_encontrada": "empalme roto", "servicio_validado": True},
        )
    assert "nunca se inició" in str(e.value)


def test_i_no_hay_dos_inicios(orden, tecnico):
    seg.registrar(
        orden, profile=tecnico[1], momento=seg.INICIO,
        respuestas={"punto_intervenido": "CTO-045", "nivel_inicial_1550": -4.8},
    )
    with pytest.raises(seg.SeguimientoInvalido) as e:
        seg.registrar(
            orden, profile=tecnico[1], momento=seg.INICIO,
            respuestas={"punto_intervenido": "CTO-045", "nivel_inicial_1550": -4.8},
        )
    assert "ya tiene un INICIO" in str(e.value)


# --------------------------------------------------------------------------- #
# J. LA PRUEBA QUE MAS IMPORTA: el evento se lee con su propio esquema
# --------------------------------------------------------------------------- #

def test_j_un_avance_viejo_se_sigue_leyendo_igual_tras_cambiar_el_tipo(
    orden, tecnico, version_con_seguimiento
):
    """Se registra, se cambia el tipo de trabajo, y el evento dice lo mismo.

    Sin el snapshot, 'validaciones' se quedaria sin titulo --o peor, tomaria el de
    otro campo-- y un reporte de hace años cambiaria de significado sin que nadie
    lo toque.
    """
    seg.registrar(
        orden, profile=tecnico[1], momento=seg.INICIO,
        respuestas={"punto_intervenido": "CTO-045", "nivel_inicial_1550": -4.8},
    )
    seg.registrar(
        orden, profile=tecnico[1], momento=seg.AVANCE,
        respuestas={"validaciones": "conectores, patch cord y salida del PLC",
                    "nivel_actual": -4.6},
    )
    antes = seg.linea_de_tiempo(orden)
    avance_antes = [e for e in antes["eventos"] if e["tipo"] == "avance_campo"][0]

    # AHORA CAMBIA EL TIPO DE TRABAJO, tres veces.
    #
    # Se crean versiones NUEVAS y no se muta la publicada: el modelo lo prohibe a
    # proposito --una plantilla publicada es inmutable-- y ese es justamente el
    # camino real. La orden se reapunta a la ultima, que es lo que pasa cuando
    # alguien la migra o la corrige.
    ultima = None
    for n in (2, 3, 4):
        ultima = WorkTypeVersion.objects.create(
            work_type=version_con_seguimiento.work_type,
            version=n,
            schema_version=1,
            estado=WorkTypeVersion.PUBLICADA,
            esquema={
                "pasos": [], "campos": [], "evidencias": [],
                "seguimiento": {
                    "avance": {
                        "campos": [
                            {"id": "otra_cosa", "titulo": f"Otra cosa v{n}",
                             "tipo": "texto", "reglas": {}}
                        ]
                    }
                },
            },
        )
    orden.tipo_trabajo_version = ultima
    orden.save(update_fields=["tipo_trabajo_version", "updated_at"])

    orden.refresh_from_db()
    despues = seg.linea_de_tiempo(orden)
    avance_despues = [e for e in despues["eventos"] if e["tipo"] == "avance_campo"][0]

    assert avance_despues["detalle"] == avance_antes["detalle"]
    titulos = {d["id"]: d["titulo"] for d in avance_despues["detalle"]}
    assert titulos["validaciones"] == "Validaciones realizadas"
    assert titulos["nivel_actual"] == "Nivel actual (dBm)"
    assert all(d["en_el_esquema_de_entonces"] for d in avance_despues["detalle"])

    # Y el formulario de HOY si cambia: es lo que se le pide a quien reporta ahora.
    assert [c["id"] for c in seg.formulario_de(orden, seg.AVANCE)["campos"]] == ["otra_cosa"]


# --------------------------------------------------------------------------- #
# K-L. La declaracion humana y el estado
# --------------------------------------------------------------------------- #

def test_k_servicio_validado_queda_como_declaracion_con_su_autor(orden, tecnico):
    _, prof = tecnico
    seg.registrar(
        orden, profile=prof, momento=seg.INICIO,
        respuestas={"punto_intervenido": "CTO-045", "nivel_inicial_1550": -4.8},
    )
    ev = seg.registrar(
        orden, profile=prof, momento=seg.CIERRE,
        respuestas={"falla_encontrada": "empalme roto", "servicio_validado": True},
    )
    d = ev.datos["declaraciones"]["servicio_validado"]
    assert d["valor"] is True
    assert d["declarado_por"] == str(prof.id)
    assert d["declarado_por_nombre"]
    assert d["declarado_en"]
    # Escrito en el DATO, no solo en la pantalla.
    assert d["es_declaracion_humana"] is True
    # Y 'falla_encontrada', que no es declaracion, no se guarda como si lo fuera.
    assert "falla_encontrada" not in ev.datos["declaraciones"]


def test_l_un_bloqueo_no_mueve_el_estado_operativo(orden, tecnico):
    """Decision 1: la maquina de estados sigue siendo la unica que decide."""
    antes = orden.estado_operativo
    revision_antes = orden.revision
    seg.registrar(
        orden, profile=tecnico[1], momento=seg.BLOQUEO,
        respuestas={"categoria": "acceso", "necesita_de_noc": "coordinar el poste"},
    )
    orden.refresh_from_db()
    assert orden.estado_operativo == antes
    assert orden.revision == revision_antes


# --------------------------------------------------------------------------- #
# M-N. La linea de tiempo
# --------------------------------------------------------------------------- #

def test_m_la_linea_de_tiempo_es_una_sola(orden, tecnico, org_a):
    """Mezcla los cuatro nuevos con los que ya se escribian, en orden."""
    EventoTrabajo.objects.create(
        org=org_a, orden=orden, tipo="orden_creada", profile=tecnico[1], datos={}
    )
    seg.registrar(
        orden, profile=tecnico[1], momento=seg.INICIO,
        respuestas={"punto_intervenido": "CTO-045", "nivel_inicial_1550": -4.8},
    )
    EventoTrabajo.objects.create(
        org=org_a, orden=orden, tipo="correccion_requerida", profile=tecnico[1],
        datos={"estado_anterior": "completada_campo", "estado_nuevo": "correccion_requerida"},
    )
    seg.registrar(
        orden, profile=tecnico[1], momento=seg.AVANCE,
        respuestas={"validaciones": "revise la entrada"},
    )

    t = seg.linea_de_tiempo(orden)
    tipos = [e["tipo"] for e in t["eventos"]]
    assert tipos == ["orden_creada", "inicio_campo", "correccion_requerida", "avance_campo"]

    # Los de seguimiento traen detalle; los otros, el cambio de estado.
    por_tipo = {e["tipo"]: e for e in t["eventos"]}
    assert por_tipo["inicio_campo"]["detalle"]
    assert por_tipo["correccion_requerida"]["estado_nuevo"] == "correccion_requerida"
    assert "detalle" not in por_tipo["correccion_requerida"]
    assert por_tipo["orden_creada"]["etiqueta"] == "Orden creada"
    assert por_tipo["inicio_campo"]["etiqueta"] == "INICIO"

    assert t["ultimo_reporte"]["tipo"] == "avance_campo"
    assert t["momentos_registrados"] == ["avance_campo", "inicio_campo"]


def test_n_sin_reportes_el_ultimo_reporte_es_nulo_y_no_cero(orden):
    """'Todavia no reporto' y 'reporto hace 0 minutos' no son lo mismo."""
    t = seg.linea_de_tiempo(orden)
    assert t["ultimo_reporte"] is None
    assert t["momentos_registrados"] == []


def test_o_las_dos_horas_se_guardan_separadas(orden, tecnico):
    """La del telefono y la del servidor. Confundirlas es lo que haria que un
    tecnico sin señal parezca uno que no reporta."""
    ev = seg.registrar(
        orden, profile=tecnico[1], momento=seg.INICIO,
        respuestas={"punto_intervenido": "CTO-045", "nivel_inicial_1550": -4.8},
        capturado_en_dispositivo="2026-09-29T08:14:00-05:00",
    )
    assert ev.datos["capturado_en_dispositivo"] == "2026-09-29T08:14:00-05:00"
    assert ev.datos["recibido_en_servidor"]
    assert ev.datos["capturado_en_dispositivo"] != ev.datos["recibido_en_servidor"]


# --------------------------------------------------------------------------- #
# P-T. Por la API
# --------------------------------------------------------------------------- #

def test_p_el_tecnico_registra_un_inicio_por_la_api(orden, org_a, tecnico):
    user, prof = tecnico
    c = _cliente(user, org_a, prof)
    r = c.post(
        _ruta(orden),
        {"momento": "inicio",
         "respuestas": {"punto_intervenido": "CTO-045", "nivel_inicial_1550": -4.8}},
        format="json",
    )
    assert r.status_code == 201, r.data
    assert r.data["tipo"] == "inicio_campo"
    assert r.data["etiqueta"] == "INICIO"


def test_q_un_reporte_incompleto_devuelve_422_y_dice_que_campo(orden, org_a, tecnico):
    """422 y no 400: el cuerpo esta bien formado; el contenido no se puede aceptar."""
    user, prof = tecnico
    r = _cliente(user, org_a, prof).post(
        _ruta(orden),
        {"momento": "inicio", "respuestas": {"punto_intervenido": "CTO-045"}},
        format="json",
    )
    assert r.status_code == 422
    assert "nivel_inicial_1550" in r.data["campos"]


def test_r_el_get_trae_la_linea_de_tiempo_y_los_cuatro_formularios(orden, org_a, tecnico):
    user, prof = tecnico
    c = _cliente(user, org_a, prof)
    c.post(
        _ruta(orden),
        {"momento": "inicio",
         "respuestas": {"punto_intervenido": "CTO-045", "nivel_inicial_1550": -4.8}},
        format="json",
    )
    r = c.get(_ruta(orden))
    assert r.status_code == 200
    assert sorted(r.data["formularios"].keys()) == ["avance", "bloqueo", "cierre", "inicio"]
    assert r.data["eventos"][0]["tipo"] == "inicio_campo"
    # La pantalla dibuja los campos del tipo de trabajo, sin saberlos de antemano.
    ids = [c_["id"] for c_ in r.data["formularios"]["bloqueo"]["campos"]]
    assert ids == ["categoria", "necesita_de_noc"]


def test_s_el_mismo_reporte_con_la_misma_clave_no_se_escribe_dos_veces(
    orden, org_a, tecnico
):
    """La cola offline reintenta; la bitacora no puede contar dos hechos."""
    user, prof = tecnico
    c = _cliente(user, org_a, prof)
    cuerpo = {"momento": "avance", "respuestas": {"validaciones": "revise el empalme"}}
    uno = c.post(_ruta(orden), cuerpo, format="json", HTTP_IDEMPOTENCY_KEY="wamid-1")
    dos = c.post(_ruta(orden), cuerpo, format="json", HTTP_IDEMPOTENCY_KEY="wamid-1")
    assert uno.status_code == 201
    assert dos.status_code in (200, 201)
    assert EventoTrabajo.objects.filter(orden=orden, tipo="avance_campo").count() == 1


def test_t_otra_empresa_recibe_404_y_nunca_403(orden, org_b, django_user_model):
    user = django_user_model.objects.create_user(
        email="curiosa.seg@empresa.com", password="testpass123"
    )
    prof_b = Profile.objects.create(user=user, org=org_b, role="ADMIN", is_active=True)
    c = _cliente(user, org_b, prof_b)
    assert c.get(_ruta(orden)).status_code == 404
    r = c.post(_ruta(orden), {"momento": "avance", "respuestas": {"validaciones": "x"}},
               format="json")
    assert r.status_code == 404


def test_u_un_tecnico_no_asignado_no_puede_reportar(orden, org_a, django_user_model):
    user = django_user_model.objects.create_user(
        email="ajeno.seg@test.com", password="testpass123"
    )
    prof = Profile.objects.create(user=user, org=org_a, role="USER", is_active=True)
    r = _cliente(user, org_a, prof).post(
        _ruta(orden), {"momento": "avance", "respuestas": {"validaciones": "x"}},
        format="json",
    )
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# V-X. Los reportes fuera de orden: se aceptan y se dicen
# --------------------------------------------------------------------------- #

def test_v_un_avance_sin_inicio_se_acepta_pero_se_avisa(orden, tecnico):
    """No se rechaza, y no se calla.

    Un reporte que se pierde es peor que uno desordenado: el tecnico esta en la
    calle y no tiene por que pelear con el formulario. Pero quien lea la ficha
    despues necesita saber que falta la condicion inicial.
    """
    seg.registrar(
        orden, profile=tecnico[1], momento=seg.AVANCE,
        respuestas={"validaciones": "ya habia empezado cuando me acorde de reportar"},
    )
    t = seg.linea_de_tiempo(orden)
    assert t["momentos_registrados"] == ["avance_campo"]
    assert any("sin un INICIO" in a for a in t["avisos"])


def test_w_con_el_inicio_primero_no_hay_avisos(orden, tecnico):
    seg.registrar(
        orden, profile=tecnico[1], momento=seg.INICIO,
        respuestas={"punto_intervenido": "CTO-045", "nivel_inicial_1550": -4.8},
    )
    seg.registrar(
        orden, profile=tecnico[1], momento=seg.AVANCE,
        respuestas={"validaciones": "revise el empalme"},
    )
    assert seg.linea_de_tiempo(orden)["avisos"] == []


def test_x_un_inicio_llegado_tarde_lo_dice_y_no_reordena(orden, tecnico):
    """El orden que se muestra es el real."""
    seg.registrar(
        orden, profile=tecnico[1], momento=seg.AVANCE,
        respuestas={"validaciones": "primero reporte el avance"},
    )
    seg.registrar(
        orden, profile=tecnico[1], momento=seg.INICIO,
        respuestas={"punto_intervenido": "CTO-045", "nivel_inicial_1550": -4.8},
    )
    t = seg.linea_de_tiempo(orden)
    tipos = [e["tipo"] for e in t["eventos"] if e["es_seguimiento"]]
    # No se reordena para que parezca prolijo.
    assert tipos == ["avance_campo", "inicio_campo"]
    assert any("después de otro reporte" in a for a in t["avisos"])
