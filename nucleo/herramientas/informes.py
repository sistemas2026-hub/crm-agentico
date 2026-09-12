# -*- coding: utf-8 -*-
"""
================================================================================
 INFORMES EXPORTABLES  --  el resultado de un agregado, como archivo
================================================================================

Por que existe
--------------
PRD.md RF-12 pide exportar a Excel/PDF y seguia sin existir (agosto 2026):
'informe_materiales' es lo unico parecido a un informe, y es tipo 'batch' --
ni siquiera se puede invocar desde una conversacion (nucleo/modelo/motor.py
solo tiene ejecutor para 'http'). Este modulo NO inventa una fuente de datos
nueva: toma el mismo dict que ya devuelve nucleo/herramientas/agregado.py
('total', 'desglose'?, 'interpretacion', 'advertencia'?) y lo vuelca a un
archivo (Excel o PDF, mismo dato, distinto empaque). El codigo sigue
calculando (PRD 12.5); esto solo cambia como se presenta la salida.

Por que no ve el modelo el archivo
-----------------------------------
Igual que con cualquier otro dato: el modelo redacta a partir del MISMO
'total'/'desglose' que ya recibia en texto, mas un identificador de archivo
que el motor le agrega (ver motor.py). Nunca recibe los bytes ni decide su
contenido -- si lo decidiera, dos pedidos identicos podrian dar dos archivos
distintos, y ahi el 'informe' dejaria de ser confiable.

openpyxl es import perezoso (mismo patron que 'cryptography' en
requirements.txt): si falta el paquete, ejecutar() devuelve un error legible
en vez de romper el turno -- pero A DIFERENCIA de Pillow (que degrada
silenciosamente a guardar la foto sin comprimir), esto SI debe fallar visible:
el modelo pidio explicitamente un archivo, y entregar un total en texto en su
lugar sin avisar seria RF-07 (no inventar que se cumplio algo que no paso).
================================================================================
"""

from __future__ import annotations

import io


class ErrorInforme(Exception):
    """No se pudo generar el archivo -- motivo legible para el modelo."""


def generar_excel(interpretacion: str, resultado: dict) -> bytes:
    """
    (interpretacion, resultado) son los mismos que devuelve
    nucleo/herramientas/agregado.py::ejecutar(). 'resultado' NO debe traer
    'error' -- eso se verifica antes de llamar aca (ver motor.py).

    Una fila de titulo con la interpretacion, y despues:
      - si hay 'desglose': dos columnas, categoria y cantidad, ordenadas de
        mayor a menor (lo que alguien mira primero al abrir el archivo).
      - si no: una sola fila con el total.
    """
    try:
        from openpyxl import Workbook
    except ImportError as e:
        raise ErrorInforme("El servidor no tiene instalado lo necesario "
                          "para generar archivos Excel.") from e

    libro = Workbook()
    hoja = libro.active
    hoja.title = "Informe"

    hoja.append([interpretacion])
    hoja.merge_cells(start_row=1, start_column=1, end_row=1, end_column=2)
    hoja.append([])  # fila en blanco, separa el titulo de la tabla

    desglose = resultado.get("desglose")
    if desglose:
        hoja.append(["Categoria", "Cantidad"])
        for categoria, cantidad in sorted(desglose.items(), key=lambda kv: -kv[1]):
            hoja.append([categoria, cantidad])
    else:
        hoja.append(["Total", resultado.get("total")])

    for columna, ancho in (("A", 40), ("B", 14)):
        hoja.column_dimensions[columna].width = ancho

    buffer = io.BytesIO()
    libro.save(buffer)
    return buffer.getvalue()


def generar_pdf(interpretacion: str, resultado: dict) -> bytes:
    """
    Mismo contrato que generar_excel(): mismo 'resultado' ya calculado, sin
    'error', solo cambia el empaque. reportlab es pure-Python -- a diferencia
    de weasyprint (que exige Cairo/Pango del sistema), no complica la imagen
    de Docker con dependencias nativas.

    Titulo + tabla (categoria/cantidad si hay desglose, o una fila con el
    total) -- misma forma que la hoja de Excel, en PDF.
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    except ImportError as e:
        raise ErrorInforme("El servidor no tiene instalado lo necesario "
                          "para generar archivos PDF.") from e

    buffer = io.BytesIO()
    documento = SimpleDocTemplate(buffer, pagesize=letter,
                                  topMargin=54, bottomMargin=54)
    estilos = getSampleStyleSheet()
    piezas = [Paragraph(interpretacion, estilos["Heading2"]), Spacer(1, 16)]

    desglose = resultado.get("desglose")
    if desglose:
        filas = [["Categoría", "Cantidad"]]
        filas += [[categoria, str(cantidad)]
                 for categoria, cantidad in sorted(desglose.items(), key=lambda kv: -kv[1])]
        tabla = Table(filas, colWidths=[320, 100])
        tabla.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2f2f2f")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
        ]))
        piezas.append(tabla)
    else:
        piezas.append(Paragraph(f"Total: {resultado.get('total')}", estilos["Normal"]))

    documento.build(piezas)
    return buffer.getvalue()


MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MIME_PDF = "application/pdf"
