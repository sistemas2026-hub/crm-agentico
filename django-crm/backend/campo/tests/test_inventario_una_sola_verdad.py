# -*- coding: utf-8 -*-
"""
Guarda de arquitectura: la existencia se calcula en UN lugar, y no se guarda.

QUE DEFIENDE, Y POR QUE HACE FALTA UNA GUARDA Y NO UNA COSTUMBRE
---------------------------------------------------------------
La decision que ordena este modulo es que la existencia de cualquier ubicacion
sale de UNA resta, en UNA funcion. De ahi salio descartar los dos libros: el dia
que haya dos codigos que cuenten lo mismo, van a diferir, y nadie va a saber cual
de los dos numeros es el bueno.

Eso no lo protege nada mas que esta prueba. Un `disponible` agregado con la mejor
intencion --"para no recalcular en cada pantalla"-- cabe en una linea, pasa
cualquier revision distraida, y rompe la propiedad entera sin que ninguna otra
prueba se ponga en rojo: seguiria dando el numero correcto hasta el primer
movimiento que llegue tarde.

Es la misma forma que `tests/test_nucleo_sin_tenants.py` usa para que el motor no
conozca a un cliente: recorre el codigo y FALLA NOMBRANDO el archivo.

LA EXCEPCION DECLARADA
----------------------
`UbicacionDeActivo` SI guarda un derivado --donde esta un aparato ahora-- y esta
permitida a proposito: un puntero al presente no es un contador acumulado, es
reconstruible, y hay una prueba que lo reconcilia contra el libro
(test_inventario_ciclo.py::test_a5_...). La excepcion vive en esta lista y no en
la cabeza de nadie.
"""

import re
from pathlib import Path

CAMPO = Path(__file__).resolve().parent.parent

#: Nombres de campo que serian un contador guardado. No es una lista de palabras
#: prohibidas por estetica: cada uno de estos, como columna, produce dos fuentes
#: de verdad para la misma pregunta.
CAMPOS_PROHIBIDOS = (
    "disponible",
    "stock",
    "stock_actual",
    "existencia_actual",
    "saldo_actual",
    "cantidad_disponible",
)

#: Los UNICOS archivos que pueden sumar cantidades.
#:
#: `materiales.py` estuvo aca "por compatibilidad: calcula el saldo del tecnico
#: desde antes de que existiera el inventario, y unificarlo es trabajo aparte".
#: ESO YA NO ES CIERTO desde el 28/09/2026: `saldo_de` llama a
#: `inventario.existencia(custodia)` y no suma nada por su cuenta. Las dos
#: aritmeticas SI llegaron a diferir --48 contra 52 tras un conteo fisico-- y por
#: eso se unifico. Sigue en la lista porque suma otras dos cosas que no son la
#: existencia: `entregado_a` (lo que dice el acta firmada, que no baja cuando el
#: material se gasta) y `movido_por` (cuanto movio una persona, por tipo).
PUEDEN_SUMAR = {
    "services/inventario.py",
    "services/materiales.py",
    "services/cierre_jornada.py",
    # Agregado el 28/09/2026 al construir la Fase 2, y ESTA GUARDA LO EXIGIO:
    # fallo nombrando las dos lineas --`reservado()` y el reporte de consumo por
    # material-- a las dos horas de haberse escrito, contra su propio autor. Es
    # justo lo que tenia que hacer.
    #
    # Suma dos cosas que NO son la existencia:
    #   reservado()               lo comprometido, que sale de las reservas y no
    #                             de los movimientos
    #   consumo_por_material()    un reporte: agrupa consumos por material sobre
    #                             una ventana de tiempo
    # Ninguna de las dos es un segundo calculo de existencia --esa sigue viniendo
    # de `inventario.py::existencia`-- y `libre()` la LLAMA en vez de recalcularla.
    "services/inventario_operacion.py",
}

#: Donde SI se guarda un derivado, con su justificacion escrita.
DERIVADOS_PERMITIDOS = {
    "UbicacionDeActivo": "puntero al presente, reconciliado contra el libro",
    "ActaDeDevolucion": "congela totales al confirmarse: es lo que dos personas "
                        "acordaron ese dia",
}


def _archivos_py():
    for p in sorted(CAMPO.rglob("*.py")):
        rel = p.relative_to(CAMPO).as_posix()
        if rel.startswith("tests/") or rel.startswith("migrations/"):
            continue
        yield rel, p.read_text(encoding="utf-8", errors="replace")


def test_ningun_modelo_guarda_un_contador_de_existencia():
    """Un campo `disponible` es una segunda verdad sobre la misma pregunta."""
    culpables = []
    for rel, texto in _archivos_py():
        for prohibido in CAMPOS_PROHIBIDOS:
            # Solo como DEFINICION de campo: `disponible = models.X(...)`. Una
            # variable local con ese nombre es inocua y marcarla seria ruido que
            # ensena a ignorar la guarda.
            patron = rf"^\s+{re.escape(prohibido)}\s*=\s*models\."
            for i, linea in enumerate(texto.splitlines(), 1):
                if re.match(patron, linea):
                    culpables.append(f"{rel}:{i}  {linea.strip()}")
    assert not culpables, (
        "hay un contador de existencia guardado como campo:\n  "
        + "\n  ".join(culpables)
        + "\n\nLa existencia se CALCULA (services/inventario.py::existencia). Un"
          " contador y un movimiento que llega ocho horas tarde se desincronizan"
          " en cuanto alguien reintenta."
    )


def test_solo_los_servicios_declarados_suman_cantidades():
    """Un segundo lugar que sume es un segundo numero que puede diferir."""
    culpables = []
    for rel, texto in _archivos_py():
        if rel in PUEDEN_SUMAR:
            continue
        for i, linea in enumerate(texto.splitlines(), 1):
            if re.search(r'Sum\(\s*["\']cantidad["\']\s*\)', linea):
                culpables.append(f"{rel}:{i}  {linea.strip()}")
    assert not culpables, (
        "hay un calculo de cantidades fuera de los servicios declarados:\n  "
        + "\n  ".join(culpables)
        + f"\n\nLos unicos que pueden sumar son {sorted(PUEDEN_SUMAR)}. Si hace"
          " falta otro, agregarlo A ESTA LISTA con su motivo -- que es lo que"
          " obliga a justificarlo en vez de que aparezca solo."
    )


def test_la_excepcion_del_puntero_esta_declarada_y_reconciliada():
    """El derivado permitido tiene que seguir teniendo quien lo verifique.

    Si alguien borra la prueba de reconciliacion, `UbicacionDeActivo` pasa a ser
    un dato guardado que nadie puede comprobar -- o sea lo que este proyecto
    prohibe-- y la excepcion deja de estar justificada.
    """
    prueba = CAMPO / "tests" / "test_inventario_ciclo.py"
    texto = prueba.read_text(encoding="utf-8", errors="replace")
    assert "posicion_recalculada" in texto, (
        "desaparecio la reconciliacion del puntero contra el libro. Sin ella "
        "UbicacionDeActivo es un contador guardado con otro nombre, y la "
        "excepcion que lo permite ya no vale."
    )
    # Antes esto decia `for modelo in DERIVADOS_PERMITIDOS: assert modelo in
    # DERIVADOS_PERMITIDOS`, que es verdad por construccion y no mide nada -- una
    # tautologia sobrevive intacta a cualquier cambio de conducta, que es justo el
    # defecto que este proyecto ya se cobro tres veces el mismo dia. Lo que hay
    # que comprobar es que cada excepcion siga EXISTIENDO y siga teniendo su
    # motivo escrito: una lista que nombra un modelo borrado permite algo que ya
    # no existe, y un motivo vacio es una excepcion sin justificar.
    definidos = {}
    for rel, texto in _archivos_py():
        for modelo in DERIVADOS_PERMITIDOS:
            if re.search(r"^class " + re.escape(modelo) + r"\(", texto, re.M):
                definidos[modelo] = rel
    faltan = sorted(set(DERIVADOS_PERMITIDOS) - set(definidos))
    assert not faltan, (
        f"la lista de derivados permitidos nombra modelos que ya no existen: "
        f"{faltan}. Una excepcion a una regla de arquitectura que apunta a nada "
        f"deja la puerta abierta sin que nadie la vea."
    )
    sin_motivo = sorted(m for m, motivo in DERIVADOS_PERMITIDOS.items()
                        if not (motivo or "").strip())
    assert not sin_motivo, (
        f"estos derivados estan permitidos sin decir por que: {sin_motivo}."
    )


def test_existencia_vive_en_un_solo_lugar():
    """Una sola definicion de `def existencia(`."""
    definiciones = []
    for rel, texto in _archivos_py():
        for i, linea in enumerate(texto.splitlines(), 1):
            if re.match(r"^def existencia\(", linea):
                definiciones.append(f"{rel}:{i}")
    assert len(definiciones) == 1, (
        f"`existencia()` esta definida {len(definiciones)} veces: {definiciones}."
        " Tiene que haber una, y servir igual para una bodega y para un tecnico."
    )


# ---------------------------------------------------------------------------
# Y UNA QUE ES ARITMETICA SOBRE DATOS, NO GREP SOBRE TEXTO
# ---------------------------------------------------------------------------
#
# Las cuatro de arriba recorren el codigo. Ninguna cazo el defecto mas grave que
# tuvo este modulo --un consumo que no restaba de ninguna ubicacion-- porque
# comprobaban que `existencia()` estuviera definida UNA vez, no que los
# movimientos tuvieran direccion. Una guarda de texto no puede ver eso: el codigo
# que no escribe una columna se ve igual que el que no la necesita.

import pytest  # noqa: E402

from campo.inventario import UbicacionInventario  # noqa: E402
from campo.models import MaterialCatalogo, MovimientoDeMaterial  # noqa: E402
from campo.services import inventario as inv  # noqa: E402
from campo.services import inventario_operacion as op  # noqa: E402
from campo.services.materiales import registrar_movimiento, saldo_de  # noqa: E402


@pytest.mark.django_db
def test_ningun_movimiento_queda_sin_direccion(org_a, user_profile):
    """Un movimiento sin origen NI destino no resta ni suma en ninguna parte.

    ES EL DEFECTO 1 CONVERTIDO EN PROPIEDAD, para cualquier escritor futuro.
    `registrar_movimiento` --el camino de la app del tecnico-- no escribia ninguna
    de las dos, asi que la existencia de una custodia solo podia subir y la
    pantalla mostraba material que ya estaba instalado en casas de clientes. Cada
    escritor nuevo del libro puede repetir el error; esta prueba ejercita LOS
    NUEVE caminos que existen hoy y mira el dato, no el codigo.

    Los dos nulls legitimos son de UN lado cada uno: una ENTRADA no tiene origen
    interno y un CONSUMO no tiene destino interno. Los dos a la vez, nunca.
    """
    from campo.models import OrdenTrabajo, WorkType, WorkTypeVersion

    bodega = UbicacionInventario.objects.create(
        org=org_a, tipo=UbicacionInventario.BODEGA, nombre="Bodega de la guarda")
    otra = UbicacionInventario.objects.create(
        org=org_a, tipo=UbicacionInventario.BODEGA, nombre="Bodega Norte")
    material = MaterialCatalogo.objects.create(
        org=org_a, codigo="GUARDA-1", nombre="Conector de la guarda")
    wt = WorkType.objects.create(org=org_a, codigo="g", nombre="Guarda")
    ver = WorkTypeVersion.objects.create(
        work_type=wt, version=1, estado=WorkTypeVersion.PUBLICADA, esquema={})
    orden = OrdenTrabajo.objects.create(
        org=org_a, numero=9900, tipo_trabajo_version=ver,
        cliente_nombre="Guarda", cliente_direccion="Calle 0")

    # Todos los caminos que escriben el libro hoy.
    inv.registrar_entrada(org=org_a, material=material, cantidad=100,
                          ubicacion_destino=bodega, origen_ref="GUARDA")
    op.registrar_compra(org=org_a, ubicacion_destino=bodega, referencia="F-G",
                        lineas=[{"material": material, "cantidad": 10,
                                 "costo_unitario": "5"}])
    op.trasladar(org=org_a, ubicacion_origen=bodega, ubicacion_destino=otra,
                 lineas=[{"material": material, "cantidad": 5}],
                 referencia="T-G")
    inv.despachar(org=org_a, ubicacion_origen=bodega,
                  profile_destino=user_profile, acta="ACTA-GUARDA",
                  lineas=[{"material": material, "cantidad": 20}])
    registrar_movimiento(org=org_a, profile=user_profile, material=material,
                         tipo=MovimientoDeMaterial.CONSUMO, cantidad=3,
                         idempotency_key="guarda-consumo", orden=orden)
    registrar_movimiento(org=org_a, profile=user_profile, material=material,
                         tipo=MovimientoDeMaterial.DEVOLUCION, cantidad=2,
                         idempotency_key="guarda-devolucion")
    registrar_movimiento(org=org_a, profile=user_profile, material=material,
                         tipo=MovimientoDeMaterial.AJUSTE, cantidad="-4",
                         idempotency_key="guarda-ajuste")
    conteo = op.abrir_conteo(org=org_a, ubicacion=bodega)
    op.anotar_conteo(conteo, material=material, cantidad=50, motivo="guarda")
    op.cerrar_conteo(conteo)
    inv.recibir_devolucion(org=org_a, profile_origen=user_profile,
                           ubicacion_destino=bodega, referencia="D-G",
                           lineas=[{"material": material, "cantidad": 1}])

    huerfanos = list(
        MovimientoDeMaterial.objects.filter(
            org=org_a, ubicacion_origen__isnull=True,
            ubicacion_destino__isnull=True,
        ).values_list("tipo", "cantidad", "idempotency_key")
    )
    assert not huerfanos, (
        "estos movimientos no salen ni entran a ninguna ubicacion, asi que no "
        f"cambian ninguna existencia: {huerfanos}. Un movimiento sin direccion es "
        "una fila que dice que algo paso y no lo refleja en ningun saldo."
    )

    # Y el saldo del tecnico ES la existencia de su custodia: un solo numero.
    custodia = inv.ubicacion_de_tecnico(user_profile, org_a, crear=False)
    assert saldo_de(user_profile, material) == inv.existencia(custodia, material)
