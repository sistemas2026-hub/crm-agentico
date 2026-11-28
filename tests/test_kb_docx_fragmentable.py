# -*- coding: utf-8 -*-
"""
El .docx de un articulo de la Base de conocimiento, por el fragmentador REAL.

    PYTHONIOENCODING=utf-8 py -3.13 tests/test_kb_docx_fragmentable.py

12/11/2026. El backend escribe el articulo como .docx a mano (zipfile + XML,
django-crm/backend/cases/kb_docx.py) para entrar al corpus por la misma puerta
que un Documento. Esta prueba no le cree a ese archivo: lo pasa por
nucleo/ingesta/docx.py::procesar y mira lo que sale -- codigo, version, titulo
y que TODO el cuerpo quede en algun fragmento. Asi se encontro que una linea
'1.1 ...' se perdia entera (el fragmentador la tomaba por titulo de seccion).
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo.ingesta.docx import PerfilDocumento, procesar  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "kb_docx", RAIZ / "django-crm" / "backend" / "cases" / "kb_docx.py")
kb_docx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(kb_docx)

fallas = []


def revisar(condicion, que):
    print(f"  [{'ok' if condicion else 'FALLA'}] {que}")
    if not condicion:
        fallas.append(que)


CUERPO = ("Paso 1: desenchufe la ONT.\n<b>Paso 2</b>: espere 30 s & vuelva a enchufar.\n\n"
          "1.1 Si la luz LOS sigue roja, avise.")
datos = kb_docx.docx_de_articulo(codigo="KB-abc123", version=3,
                                 titulo="Cómo reiniciar la ONT", descripcion=CUERPO,
                                 fecha="2026-11-12")

revisar(datos == kb_docx.docx_de_articulo(codigo="KB-abc123", version=3,
                                          titulo="Cómo reiniciar la ONT",
                                          descripcion=CUERPO, fecha="2026-11-12"),
        "determinista: el mismo articulo da los mismos bytes (mismo hash)")

perfiles = {
    "perfil por defecto": None,
    # Como lo declara una empresa con tildes en la tabla de metadatos.
    "metadatos con tildes": PerfilDocumento(campos_metadatos=("Código", "Versión", "Fecha")),
}
with tempfile.TemporaryDirectory() as carpeta:
    ruta = Path(carpeta) / "KB-abc123-v3.docx"
    ruta.write_bytes(datos)
    for nombre, perfil in perfiles.items():
        doc = procesar(ruta, perfil=perfil)
        texto = "\n".join(f.contenido for f in doc.fragmentos)
        revisar(doc.codigo == "KB-abc123" and doc.version == "3",
                f"{nombre}: codigo y version salen de la tabla de metadatos")
        revisar(doc.titulo == "Cómo reiniciar la ONT", f"{nombre}: el titulo es el del articulo")
        revisar(all(p in texto for p in ("desenchufe la ONT", "espere 30 s & vuelva",
                                         "Si la luz LOS sigue roja")),
                f"{nombre}: todo el cuerpo llega a algun fragmento, incluida la linea '1.1'")
        revisar("<b>" not in texto, f"{nombre}: sin etiquetas HTML")

print()
if fallas:
    print(f"FALLAS ({len(fallas)})")
    sys.exit(1)
print("OK: el articulo se fragmenta entero por la misma puerta que un documento")
