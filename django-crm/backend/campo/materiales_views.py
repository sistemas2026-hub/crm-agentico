# -*- coding: utf-8 -*-
"""
La API de materiales: qué llevo encima y qué gasté.

DOS NIVELES DE IDEMPOTENCIA, Y HACEN FALTA LOS DOS
--------------------------------------------------
``@manejar_idempotencia`` protege la petición HTTP: el mismo ``Idempotency-Key``
devuelve la respuesta guardada sin volver a ejecutar nada. Es el mecanismo que
ya usa el resto de campo.

La ``clave`` que viaja en el cuerpo protege el **hecho**: aunque la petición
cambie de forma —otro reintento, otro lote, otra versión de la app— un consumo
con la misma clave sigue siendo el mismo consumo. Esa es la que impide
descontar dos veces un conector.

El primero es una optimización; el segundo es la regla. Por eso el segundo vive
en una restricción de la base y no solo en este archivo.

POR QUÉ ESTE ENDPOINT CASI NUNCA DEVUELVE 400
---------------------------------------------
Porque lo que recibe ya pasó. Un consumo sin saldo entra con estado
``descuadre`` y responde 201, no 400: el material ya se usó, y negarse a
guardarlo solo borraría el único registro que existe de eso. Lo que el cliente
recibe es **con qué estado entró**, para poder mostrarlo.

Se rechaza lo que no se puede interpretar —un material que no existe, un tipo
de movimiento inventado, una cantidad que no es número— porque ahí no hay
ningún hecho que preservar, solo una petición mal armada.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from campo.models import MaterialCatalogo, MovimientoDeMaterial, OrdenTrabajo
from campo.permissions import IsCampoAuthenticated
from campo.services.idempotencia import manejar_idempotencia
from campo.services.materiales import (
    ConsumoInvalido,
    kit_de,
    materiales_sin_cuadrar,
    regla_para,
    registrar_movimiento,
)


def _numero(valor: Decimal) -> str:
    """Un decimal como texto, sin ceros de más.

    Va como texto y no como float a propósito: 42.5 metros de fibra en coma
    flotante deja de ser 42.5 en cuanto alguien suma, y un saldo que no cuadra
    por milésimas es indistinguible de un descuadre real.
    """
    return format(valor.normalize(), "f") if valor is not None else "0"


class MovimientoEntradaSerializer(serializers.Serializer):
    """Lo que el teléfono manda por cada movimiento."""

    clave = serializers.CharField(max_length=128)
    material = serializers.CharField(
        max_length=64, help_text="El código del material, no su id interno."
    )
    tipo = serializers.ChoiceField(
        choices=[t[0] for t in MovimientoDeMaterial.TIPOS],
        default=MovimientoDeMaterial.CONSUMO,
    )
    cantidad = serializers.DecimalField(max_digits=12, decimal_places=3)
    serie = serializers.CharField(
        max_length=128, required=False, allow_blank=True, default=""
    )
    orden_id = serializers.UUIDField(required=False, allow_null=True)
    ocurrido_en = serializers.DateTimeField(
        required=False,
        allow_null=True,
        help_text=(
            "Cuándo pasó en la calle, según el reloj del teléfono. Si no "
            "viene, se usa la hora de llegada, que para un movimiento offline "
            "es una mentira piadosa: mejor que el cliente la mande."
        ),
    )
    motivo = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        help_text=(
            "Lo que escribe el tecnico cuando usa mas de lo habitual. Se "
            "guarda aparte del motivo que escribe el servidor: cuando hay que "
            "reconstruir que paso, importa quien dijo cada cosa."
        ),
    )
    datos = serializers.JSONField(required=False, default=dict)

    def validate_cantidad(self, valor):
        # Una cantidad negativa no es un error de saldo sino de forma: para
        # devolver está el tipo `devolucion`, que es explícito y se puede leer
        # en un listado sin tener que interpretar el signo.
        if valor <= 0:
            raise serializers.ValidationError(
                "La cantidad tiene que ser mayor que cero. Para devolver "
                "material, usá el tipo 'devolucion'."
            )
        return valor


class KitView(APIView):
    """``GET /api/campo/kit/`` — lo que este técnico tiene a cargo."""

    permission_classes = [IsCampoAuthenticated]

    def get(self, request):
        profile = request.profile
        org = profile.org

        materiales = []
        for fila in kit_de(profile, org):
            material = fila["material"]
            # La regla viaja con el material para que la app pueda avisar
            # ANTES de registrar, sin señal y sin preguntarle al servidor.
            # Sin esto el aviso solo llegaria al sincronizar, horas despues,
            # cuando ya no sirve para nada.
            regla = regla_para(org=org, material=material, orden=None)
            materiales.append({
                "codigo": material.codigo,
                "nombre": material.nombre,
                "categoria": material.categoria,
                "clase": material.clase,
                "unidad": material.unidad,
                "regla": None if regla is None else {
                    "cantidad_habitual": (
                        _numero(regla.cantidad_habitual)
                        if regla.cantidad_habitual is not None else None
                    ),
                    "maximo": (
                        _numero(regla.maximo) if regla.maximo is not None else None
                    ),
                    "exige_motivo": regla.exige_motivo_sobre_habitual,
                    "bloquea": regla.bloquea_sobre_maximo,
                },
                "recibido": _numero(fila["recibido"]),
                "consumido": _numero(fila["consumido"]),
                "devuelto": _numero(fila["devuelto"]),
                "disponible": _numero(fila["disponible"]),
                "series": fila["series"],
                "acta": fila["acta"],
                "entregado_en": (
                    fila["entregado_en"].isoformat() if fila["entregado_en"] else None
                ),
            })

        sin_cuadrar = [
            {
                "id": str(m.id),
                "material": m.material.codigo,
                "tipo": m.tipo,
                "cantidad": _numero(m.cantidad),
                "serie": m.serie,
                "estado": m.estado,
                "motivo": m.motivo,
                "orden_numero": m.orden.numero if m.orden else None,
                "ocurrido_en": m.ocurrido_en.isoformat(),
            }
            for m in materiales_sin_cuadrar(profile, org)
        ]

        return Response({
            "materiales": materiales,
            # Se entrega junto con el kit y no en otro endpoint porque es la
            # misma pregunta: "¿cómo voy?". Separarlo obligaría a la app a
            # pedir dos veces para poder responderla.
            "sin_cuadrar": sin_cuadrar,
            "server_time": timezone.now().isoformat(),
        })


class MovimientosMaterialView(APIView):
    """``POST /api/campo/materiales/movimientos/`` — registrar lo que se gastó.

    Acepta uno o varios movimientos en la misma petición. Un lote no es un
    capricho: una cuadrilla sin señal acumula varios y los manda todos juntos
    al reconectar, y hacerlo de a uno multiplica los viajes justo cuando la
    conexión es peor.

    Cada movimiento se resuelve por separado y trae su propio resultado: que
    uno quede en descuadre no invalida a los demás.
    """

    permission_classes = [IsCampoAuthenticated]

    @manejar_idempotencia
    def post(self, request):
        profile = request.profile
        org = profile.org

        crudos = request.data.get("movimientos")
        if crudos is None:
            crudos = [request.data]
        if not isinstance(crudos, list):
            return Response(
                {"error": "FORMATO_INVALIDO",
                 "detalle": "Se esperaba un movimiento o una lista."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = MovimientoEntradaSerializer(data=crudos, many=True)
        serializer.is_valid(raise_exception=True)

        codigos = {d["material"] for d in serializer.validated_data}
        catalogo = {
            m.codigo: m
            for m in MaterialCatalogo.objects.filter(org=org, codigo__in=codigos)
        }
        desconocidos = sorted(codigos - set(catalogo))
        if desconocidos:
            # Acá sí se rechaza: no hay hecho que preservar si no se sabe de
            # qué material habla. Y se nombran todos de una vez, para que la
            # app no descubra el siguiente en el reintento.
            return Response(
                {
                    "error": "MATERIAL_DESCONOCIDO",
                    "detalle": (
                        "Estos códigos no están en el catálogo de la empresa: "
                        + ", ".join(desconocidos)
                    ),
                    "codigos": desconocidos,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        resultados = []
        with transaction.atomic():
            for datos in serializer.validated_data:
                orden = None
                orden_id = datos.get("orden_id")
                if orden_id:
                    # Una orden de otra organización no existe para este
                    # técnico: el movimiento entra igual, sin atar, en vez de
                    # fallar entero. El material se gastó de todos modos.
                    orden = OrdenTrabajo.objects.filter(
                        id=orden_id, org=org
                    ).first()

                try:
                    movimiento, era_nuevo = registrar_movimiento(
                        org=org,
                        profile=profile,
                        material=catalogo[datos["material"]],
                        tipo=datos["tipo"],
                        cantidad=datos["cantidad"],
                        idempotency_key=datos["clave"],
                        serie=datos.get("serie") or "",
                        orden=orden,
                        ocurrido_en=datos.get("ocurrido_en"),
                        motivo_tecnico=datos.get("motivo") or "",
                        datos=datos.get("datos") or {},
                    )
                except ConsumoInvalido as e:
                    # No se puede interpretar como un hecho: un consumo que no
                    # dice en que trabajo, un equipo sin su numero, o una
                    # cantidad que la empresa decidio no aceptar.
                    #
                    # El lote NO se cae por esto: el resto son hechos que si
                    # se pueden guardar, y tirarlos castigaria una jornada
                    # entera por una linea mal armada.
                    resultados.append({
                        "clave": datos["clave"],
                        "id": None,
                        "estado": "rechazado",
                        "motivo": str(e),
                        "cantidad": _numero(datos["cantidad"]),
                        "duplicado": False,
                    })
                    continue

                resultados.append({
                    "clave": datos["clave"],
                    "id": str(movimiento.id),
                    "estado": movimiento.estado,
                    "motivo": movimiento.motivo,
                    "avisos": movimiento.datos.get("avisos", []),
                    "cantidad": _numero(movimiento.cantidad),
                    "duplicado": not era_nuevo,
                })

        return Response(
            {
                "resultados": resultados,
                "server_time": timezone.now().isoformat(),
            },
            status=status.HTTP_201_CREATED,
        )
