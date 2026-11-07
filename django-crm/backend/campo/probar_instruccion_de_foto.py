# -*- coding: utf-8 -*-
"""
================================================================================
 PROBAR LA INSTRUCCION DE UNA FOTO ANTES DE GUARDARLA  --  06/11/2026
================================================================================
El usuario, despues de ver cuatro fotos marcadas "no es lo que se pidio":
*"hagamoslo mas facil [...] que uno le indique por texto asi como ahora y
guarde eso"*.

Hoy la instruccion de cada foto --"Tenia que mostrar: Pantalla del medidor con
la lectura legible"-- se edita a ciegas en /supervisor-noc/plantillas y hay que
esperar a que una orden NUEVA la use para saber si sirve. Con esta ruta se
prueba contra la foto que ya fallo, en el momento, y recien despues se guarda.

POR QUE ACA Y NO EN EL CHAT DE /asistente
------------------------------------------
Medido el 06/11/2026, no supuesto. El chat manda `proposito=asistente_interno`
fijo (`routes/api/asistente/+server.js`), que resuelve a otra instruccion:

    evidencia_campo    2652 caracteres, CON las reglas MUESTRA/ATENCION
    asistente_interno  1123 caracteres, SIN ellas

Las reglas de MUESTRA y ATENCION son las que producen el veredicto que falla.
Afinar el texto contra el prompt del chat seria medir un camino que en
produccion no corre -- "un instrumento solo mide el camino que recorre"
(CLAUDE.md §6). Ademas, en el chat habria que subir otra foto: probar con una
distinta de la que fallo es probar otra cosa.

LO QUE ESTA RUTA NO HACE
------------------------
**No guarda nada.** Ni la instruccion --eso lo hace publicar la plantilla, que
versiona-- ni el analisis. `inspeccion_visual.analizar` no escribe, y eso es
lo que hace seguro probar: un ensayo no puede dejar un veredicto falso en la
bitacora de la orden ni mover la revision del Supervisor.

**No elige el texto.** Devuelve lo que el modelo contesto con la redaccion que
se le dio. Si conviene guardarla lo decide la persona.

CUESTA UNA LLAMADA AL MODELO, que se cobra. El tope de gasto del tenant la
frena como a cualquier otra (`consumo.estado_del_gasto`, en la ruta del
motor); no hay limite por persona.
================================================================================
"""
from __future__ import annotations

from rest_framework.response import Response
from rest_framework.views import APIView

from campo.permissions import IsCampoAuthenticated

#: El mismo tope que el campo de la plantilla (`plantillas.MAX_TEXTO_LARGO`).
#: Se repite aca a proposito: si se probara un texto mas largo del que se
#: puede guardar, el ensayo aprobaria algo que despues no entra.
MAX_INSTRUCCION = 400


class ProbarInstruccionDeFotoView(APIView):
    """Que ve el modelo en ESTA foto con ESTA instruccion.

    `POST /api/campo/evidencias/<pk>/probar-instruccion/`
    `{"instrucciones": "Resultado del test con los tres numeros legibles."}`

    Siempre 200 cuando se pudo preguntar. Que el modelo no pueda mirar la foto
    es una respuesta, no un error de esta peticion.
    """

    permission_classes = [IsCampoAuthenticated]

    def post(self, request, pk):
        from campo import inspeccion_visual as IV
        from campo.cuadrillas_views import _exigir_gestion
        from campo.models import EvidenciaTrabajo
        from campo.tasks import muestra_lo_pedido

        #  GATE DE GESTION, el mismo que guardar la plantilla
        #  (`plantillas_views`). Probar y guardar detras de puertas distintas
        #  dejaria a alguien afinando un texto que despues no puede aplicar.
        negado = _exigir_gestion(request)
        if negado:
            return negado

        instrucciones = str(request.data.get("instrucciones") or "").strip()
        if not instrucciones:
            return Response(
                {"error": "FALTA_INSTRUCCION",
                 "detalle": "hace falta el texto que se quiere probar"},
                status=400)
        if len(instrucciones) > MAX_INSTRUCCION:
            return Response(
                {"error": "INSTRUCCION_LARGA",
                 "detalle": f"el campo de la plantilla admite "
                            f"{MAX_INSTRUCCION} caracteres y este tiene "
                            f"{len(instrucciones)}: probarlo aprobaria un "
                            f"texto que despues no se puede guardar"},
                status=400)

        evidencia = (EvidenciaTrabajo.objects
                     .select_related("orden_trabajo")
                     .filter(org=request.org, pk=pk).first())
        if evidencia is None:
            return Response({"detail": "No encontrada."}, status=404)

        r = IV.analizar(evidencia, instrucciones)

        return Response({
            "estado": r.get("estado"),
            "texto": r.get("texto") or "",
            "motivo": r.get("motivo") or "",
            #  TRES VALORES, por el parser de produccion. Un binario leeria
            #  "no se sabe" como "no" -- paso el 06/11/2026 y dio un veredicto
            #  falso.
            "corresponde": muestra_lo_pedido(r.get("texto") or ""),
            #  EL PIE ARMADO, no el texto que se escribio. Produccion envuelve
            #  con "Esta foto tenia que mostrar: <titulo>." y ese prefijo es
            #  portante: dispara las reglas 7 y 12. Mostrarlo es la unica
            #  forma de que quien prueba vea lo que de verdad viajo.
            "se_le_pidio": IV.que_tenia_que_mostrar(evidencia, instrucciones),
            "tokens": r.get("tokens") or 0,
            "segundos": r.get("segundos") or 0,
        })
