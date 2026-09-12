# -*- coding: utf-8 -*-
"""
Que hace el backend cuando WeasyPrint no puede cargarse.

    uv run pytest invoices/tests/test_pdf_dependencia.py --no-cov -v

POR QUE EXISTE
--------------
WeasyPrint es un paquete de Python que carga librerias NATIVAS (GTK/Pango/
Cairo) por ctypes al importarse. Si el paquete esta pero las nativas faltan, no
lanza ImportError: lanza OSError. El 'except ImportError' original no lo
atrapaba, asi que 'import invoices.pdf' reventaba y se llevaba puesto a
cualquiera que lo importara -- Django dejaba de cargar entero.

Medido: sin el arreglo, 'import invoices.pdf' sube
'OSError: cannot load library libgobject-2.0-0'.

LO QUE ESTO NO ES
-----------------
No es hacer opcional una dependencia. WeasyPrint sigue siendo obligatorio para
emitir PDF, y una instalacion rota sigue siendo una instalacion rota: lo que
cambia es que se entera por un log en ERROR y por un mensaje accionable al
pedir un PDF, en vez de por un backend que no levanta.

Por eso hay una prueba del log: degradar en silencio seria peor que caerse.
"""

import importlib
import logging

import pytest


def test_con_weasyprint_sano_no_se_degrada_nada(monkeypatch):
    """Si la libreria carga, el modulo queda completo y no registra nada.

    Es el camino de produccion: en el Docker soportado las nativas estan, el
    try funciona, y este cambio no altera absolutamente ningun comportamiento.
    """
    import invoices.pdf as pdf

    if not pdf.WEASYPRINT_AVAILABLE:
        pytest.skip(
            "WeasyPrint no carga en esta maquina (faltan las nativas GTK). "
            "Esta prueba afirma el camino sano y corre en el Docker soportado.")

    assert pdf.MOTIVO_SIN_WEASYPRINT == ""
    assert hasattr(pdf, "HTML")
    assert hasattr(pdf, "default_url_fetcher")
    # No levanta: hay con que renderizar.
    pdf.check_weasyprint()


def test_sin_las_librerias_nativas_el_modulo_igual_importa(monkeypatch, caplog):
    """El caso que tumbaba Django: paquete presente, nativas ausentes.

    Se simula haciendo que el import de weasyprint lance OSError, que es
    exactamente lo que hace ctypes cuando no encuentra libgobject.
    """
    import builtins

    real_import = builtins.__import__

    def falla_al_cargar(nombre, *args, **kwargs):
        if nombre.startswith("weasyprint"):
            raise OSError("cannot load library 'libgobject-2.0-0': error 0x7e")
        return real_import(nombre, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", falla_al_cargar)

    with caplog.at_level(logging.ERROR, logger="invoices.pdf"):
        modulo = importlib.reload(importlib.import_module("invoices.pdf"))

    try:
        # 1. El modulo importa. Esto es lo unico que impedia arrancar.
        assert modulo.WEASYPRINT_AVAILABLE is False

        # 2. Y NO en silencio: queda registrado, en ERROR, diciendo que pasa.
        assert caplog.records, "la instalacion rota no dejo ningun rastro"
        texto = " ".join(r.getMessage() for r in caplog.records)
        assert "librerias nativas" in texto
        assert "INSTALACION ROTA" in texto, (
            "el log tiene que decir que esto es una instalacion rota y no una "
            "dependencia opcional")
        assert "libgobject" in texto, "el log no dice cual libreria falto"

        # 3. Y el motivo queda guardado para el mensaje de uso.
        assert "nativas" in modulo.MOTIVO_SIN_WEASYPRINT

        # 4. Pedir un PDF falla con un mensaje que dice que hacer.
        with pytest.raises(ImportError) as exc:
            modulo.check_weasyprint()
        assert "pip install weasyprint" in str(exc.value)
        assert "nativas" in str(exc.value)
    finally:
        # Dejar el modulo como estaba para el resto de la suite.
        monkeypatch.undo()
        importlib.reload(importlib.import_module("invoices.pdf"))


def test_sin_el_paquete_instalado_el_mensaje_es_otro(monkeypatch, caplog):
    """ImportError y OSError son problemas distintos y se dicen distinto.

    "no lo instalaste" y "lo instalaste mal" llevan a acciones diferentes;
    mezclarlos en un solo mensaje manda a la persona equivocada a buscar.
    """
    import builtins

    real_import = builtins.__import__

    def no_instalado(nombre, *args, **kwargs):
        if nombre.startswith("weasyprint"):
            raise ImportError("No module named 'weasyprint'")
        return real_import(nombre, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_instalado)

    with caplog.at_level(logging.ERROR, logger="invoices.pdf"):
        modulo = importlib.reload(importlib.import_module("invoices.pdf"))

    try:
        assert modulo.WEASYPRINT_AVAILABLE is False
        texto = " ".join(r.getMessage() for r in caplog.records)
        assert "no esta instalado" in texto
        assert "librerias nativas" not in texto, (
            "confunde 'no lo instalaste' con 'lo instalaste mal'")
        assert "no esta instalado" in modulo.MOTIVO_SIN_WEASYPRINT
    finally:
        monkeypatch.undo()
        importlib.reload(importlib.import_module("invoices.pdf"))


def test_el_log_no_expone_nada_sensible(monkeypatch, caplog):
    """El detalle que se registra es el de la libreria, no el del entorno.

    Un traceback de carga puede arrastrar rutas del servidor; lo que se
    registra es el mensaje de la excepcion, que nombra la libreria que falta.
    """
    import builtins

    real_import = builtins.__import__

    def falla(nombre, *args, **kwargs):
        if nombre.startswith("weasyprint"):
            raise OSError("cannot load library 'libgobject-2.0-0'")
        return real_import(nombre, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", falla)
    with caplog.at_level(logging.ERROR, logger="invoices.pdf"):
        importlib.reload(importlib.import_module("invoices.pdf"))

    try:
        texto = " ".join(r.getMessage() for r in caplog.records)
        for prohibido in ("PASSWORD", "SECRET_KEY", "DBPASSWORD", "Traceback"):
            assert prohibido not in texto, f"el log filtro {prohibido}"
    finally:
        monkeypatch.undo()
        importlib.reload(importlib.import_module("invoices.pdf"))
