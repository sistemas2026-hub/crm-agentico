"""
Un articulo de la Base de conocimiento, como el .docx que el motor sabe leer.

POR QUE UN .DOCX  --  12/11/2026
--------------------------------
El corpus del asistente tiene UNA puerta de entrada: `POST /corpus/documentos`
del motor (nucleo/canales/api.py), que fragmenta, vectoriza y deja el
documento pendiente de aprobacion. Es la misma por la que entra un Documento
marcado `usar_en_asistente` (common/tasks.py::ingerir_documento_en_asistente).
Esa puerta solo acepta .docx, porque el fragmentador es especifico de Word.

Se podia abrir una segunda puerta en el motor ("ingerir texto"), pero eso es
justo lo que se pidio no hacer: dos caminos de ingesta divergen. Asi que el
articulo se escribe como el documento mas simple que el fragmentador entiende:

    tabla 1x1         el titulo (nucleo/ingesta/docx.py lo toma de ahi)
    tabla 2 filas     Código | Versión | Fecha  (los metadatos del documento)
    parrafos          el cuerpo, una linea por parrafo

Sin estilos, sin numeracion multinivel: todo cae en una seccion, que para un
articulo de una pantalla es lo correcto.

Es Python puro (zipfile + XML) a proposito: el backend no tiene python-docx,
y agregar una dependencia para escribir tres tablas no vale lo que cuesta.
La prueba (`tests/test_kb_docx_fragmentable.py`, en la raiz del repositorio)
no le cree a este archivo: pasa el resultado por el fragmentador REAL del motor
(nucleo/ingesta/docx.py::procesar) y comprueba que todo el cuerpo llegue.
"""

from __future__ import annotations

import io
import re
import zipfile
from xml.sax.saxutils import escape

_TIPOS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""

_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

#: Las etiquetas HTML que un editor pudo haber dejado en el cuerpo. El
#: fragmentador lee texto; una etiqueta suelta seria ruido en cada busqueda.
_ETIQUETA = re.compile(r"<[^>]+>")

#: Un titulo mas largo que esto el fragmentador no lo toma como titulo
#: (nucleo/ingesta/docx.py, `len(t) < 150`).
MAX_TITULO = 140


def _parrafo(texto: str) -> str:
    return (f'<w:p><w:r><w:t xml:space="preserve">{escape(texto)}</w:t></w:r></w:p>')


def _celda(texto: str) -> str:
    return f"<w:tc><w:tcPr/>{_parrafo(texto)}</w:tc>"


def _tabla(filas: list[list[str]]) -> str:
    cuerpo = "".join("<w:tr>" + "".join(_celda(c) for c in f) + "</w:tr>" for f in filas)
    return f"<w:tbl><w:tblPr/>{cuerpo}</w:tbl>"


#: Una linea que empieza como '1.1 ...' el fragmentador la toma por TITULO de
#: seccion (nucleo/ingesta/docx.py, RE_NUMERACION + multinivel), y una seccion
#: sin texto debajo no produce fragmento: la linea se perdia entera. Medido al
#: escribir esto: "1.1 No es una seccion" como ultima linea no llego al corpus.
_PARECE_TITULO = re.compile(r"^\d+(?:\.\d+)+")

#: Un caracter de ancho cero delante la saca del patron sin cambiar lo que se lee.
_NEUTRO = "⁠"


def lineas_del_cuerpo(descripcion: str) -> list[str]:
    """El cuerpo, sin etiquetas, una linea no vacia por parrafo."""
    texto = _ETIQUETA.sub(" ", str(descripcion or ""))
    lineas = [ln.strip() for ln in texto.splitlines() if ln.strip()]
    return [_NEUTRO + ln if _PARECE_TITULO.match(ln) else ln for ln in lineas]


def docx_de_articulo(*, codigo: str, version: int, titulo: str, descripcion: str,
                     fecha: str) -> bytes:
    """Los bytes del .docx. Determinista: el mismo articulo da los mismos bytes."""
    titulo = (str(titulo or "").strip() or codigo)[:MAX_TITULO]
    bloques = [
        _tabla([[titulo]]),
        _tabla([["Código", "Versión", "Fecha"], [codigo, str(version), fecha]]),
    ]
    bloques += [_parrafo(ln) for ln in lineas_del_cuerpo(descripcion)]
    documento = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{_W}"><w:body>{"".join(bloques)}</w:body></w:document>'
    )
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as z:
        # Fecha fija en cada entrada: sin esto el zip lleva la hora actual y
        # el mismo articulo daria bytes distintos (y otro hash) cada vez.
        for nombre, contenido in (("[Content_Types].xml", _TIPOS),
                                  ("_rels/.rels", _RELS),
                                  ("word/document.xml", documento)):
            info = zipfile.ZipInfo(nombre, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, contenido.encode("utf-8"))
    return salida.getvalue()
