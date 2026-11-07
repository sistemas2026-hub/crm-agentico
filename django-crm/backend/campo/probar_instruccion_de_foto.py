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


class GuardarInstruccionDeFotoView(APIView):
    """Escribe la instruccion probada en la plantilla. Publica una version.

    `POST /api/campo/evidencias/<pk>/guardar-instruccion/`
    `{"instrucciones": "Resultado del test con los tres numeros legibles."}`

    EL FRONTEND NO ARMA EL ESQUEMA, y es a proposito. La alternativa era
    mandarle la definicion entera desde el navegador para que la reenviara;
    cualquier campo que se perdiera en ese viaje de ida y vuelta se perderia
    de la plantilla. Aca solo viaja el texto, y el esquema se lee, se cambia
    en un punto y se vuelve a publicar.

    SOBRE LA ULTIMA VERSION PUBLICADA, NO LA DE LA ORDEN. La orden congela su
    version (`tipo_trabajo_version` es PROTECT) y escribir ahi no cambiaria
    nada para las ordenes futuras, que es justamente lo que se quiere
    arreglar. Consecuencia que hay que decirle a quien guarda: la orden que
    tiene abierta adelante NO cambia.
    """

    permission_classes = [IsCampoAuthenticated]

    def post(self, request, pk):
        from campo import plantillas as P
        from campo.cuadrillas_views import _exigir_gestion
        from campo.models import EvidenciaTrabajo
        from campo.plantillas_views import _ordenes_vivas

        negado = _exigir_gestion(request)
        if negado:
            return negado

        instrucciones = str(request.data.get("instrucciones") or "").strip()
        if not instrucciones:
            return Response({"error": "FALTA_INSTRUCCION"}, status=400)
        if len(instrucciones) > MAX_INSTRUCCION:
            return Response({"error": "INSTRUCCION_LARGA"}, status=400)

        evidencia = (EvidenciaTrabajo.objects
                     .select_related("orden_trabajo__tipo_trabajo_version__work_type")
                     .filter(org=request.org, pk=pk).first())
        if evidencia is None:
            return Response({"detail": "No encontrada."}, status=404)

        version_de_la_orden = evidencia.orden_trabajo.tipo_trabajo_version
        tipo = version_de_la_orden.work_type
        vigente = P.ultima_publicada(tipo)
        if vigente is None:
            return Response(
                {"error": "SIN_PLANTILLA",
                 "detalle": "este tipo de trabajo no tiene ninguna version "
                            "publicada"}, status=409)

        definicion, motivos = P.leer_definicion(vigente.esquema)
        if motivos:
            #  NO SE PUBLICA LO QUE NO SE PUDO LEER ENTERO. Una plantilla
            #  armada a mano puede tener cosas que el editor no entiende;
            #  republicarla desde una lectura parcial las borraria. Es la
            #  misma razon por la que el editor "no la abre" en vez de
            #  reescribirla (plantillas.py, cabecera).
            return Response(
                {"error": "PLANTILLA_NO_EDITABLE", "motivos": motivos,
                 "detalle": "esta plantilla tiene algo que el editor no puede "
                            "leer; cambiarla desde aca borraria eso"},
                status=409)

        encontrada = False
        for e in definicion.get("evidencias") or []:
            if isinstance(e, dict) and e.get("id") == evidencia.requisito_id:
                e["instrucciones"] = instrucciones
                encontrada = True
                break
        if not encontrada:
            return Response(
                {"error": "REQUISITO_AUSENTE",
                 "detalle": f"la version publicada ya no pide "
                            f"'{evidencia.requisito_id}'"}, status=409)

        try:
            nueva, cambio = P.publicar(tipo, definicion)
        except P.ErrorPlantilla as e:
            return Response({"error": e.codigo, "detalle": e.mensaje},
                            status=400)

        #  LO QUE HAY QUE DECIRLE A QUIEN GUARDA: las ordenes vivas conservan
        #  su version. Sin este dato alguien cree que el cambio ya llego a la
        #  calle, y mira la orden que tiene delante esperando que cambie.
        return Response({
            "guardado": True,
            "version": nueva.version,
            "cambio": cambio,
            "ordenes_vivas": _ordenes_vivas(tipo),
            #  `False` cuando el esquema quedo igual: publicar es idempotente
            #  por hash y no crea una version repetida.
            "mismo_esquema": not cambio,
            "la_orden_de_esta_foto_no_cambia": (
                version_de_la_orden.version != nueva.version),
        })
