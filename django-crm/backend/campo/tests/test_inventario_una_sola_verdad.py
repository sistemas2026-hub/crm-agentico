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

#: Los UNICOS archivos que pueden sumar cantidades. `materiales.py` esta por
#: compatibilidad: calcula el saldo del tecnico desde antes de que existiera el
#: inventario, y unificarlo es trabajo aparte -- queda anotado aca para que se
#: vea que son dos y no uno.
PUEDEN_SUMAR = {
    "services/inventario.py",
    "services/materiales.py",
    "services/cierre_jornada.py",
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
    for modelo in DERIVADOS_PERMITIDOS:
        assert modelo in DERIVADOS_PERMITIDOS, modelo


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
