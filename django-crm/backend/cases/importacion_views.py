# -*- coding: utf-8 -*-
"""
Escritura de casos importados desde el sistema operativo del ISP.

WHY THIS IS NOT THE PUBLIC CASE API
-----------------------------------
The engine discovers tickets in the ISP's own system and needs to turn them
into cases. It could not use ``POST /api/cases/``: that endpoint's serializer
does not accept the ``external_*`` columns, and opening them there would make
every one of them editable by anyone who can create a case from the UI. The
identity of an external ticket is not user input.

So this is a second, deliberately narrow door. It accepts a fixed list of
fields and refuses everything else — including ``org``, ``stage``, ``parent``,
``closed_on`` and ``custom_fields`` — because a writer that silently ignores an
unexpected field is a writer whose contract nobody can trust.

THE ORG IS NEVER IN THE BODY
----------------------------
``request.org`` is resolved by ``common.middleware.get_company`` from the
credential itself: a signed JWT claim, or the PAT's own organisation. Taking an
org from the payload would hand the caller a way to write into another tenant,
which is exactly what the credential is supposed to decide. Every lookup below
is filtered by ``request.org`` for the same reason: the constraint is scoped
per org, so an unscoped query could find another tenant's row and "recognise"
it as already imported.

TWO OPERATIONS, DELIBERATELY SEPARATE
-------------------------------------
Discovery creates. Reconciliation updates external columns and nothing else.
They are separate views and not one with a flag because the field they must
never touch — ``status`` — is exactly the field the other one has to set. One
endpoint with a mode is one refactor away from letting a poll overwrite the
state a person decided.
"""

from __future__ import annotations

from django.db import IntegrityError, transaction
from rest_framework import status as http
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from cases.models import (EXTERNAL_AUTHOR_DEXTER, EXTERNAL_AUTHOR_TYPE, Case)
from common.models import Profile
from common.permissions import HasOrgContext
from common.utils import PRIORITY_CHOICE

# Lo que el descubrimiento puede escribir. Nada mas.
CAMPOS_DESCUBRIMIENTO = frozenset({
    "provider", "external_ticket_id", "external_service_id",
    "external_status", "external_status_at", "external_created_by",
    "external_created_by_type", "external_fetched_at",
    "assigned_to", "priority", "status", "name", "description",
})

# Lo que la reconciliacion puede escribir. 'status', 'assigned_to', 'stage' y
# 'priority' NO estan, y esa ausencia es el invariante entero de la fase.
CAMPOS_RECONCILIACION = frozenset({
    "external_status", "external_status_at", "external_fetched_at",
    "external_fetch_error", "external_created_by", "external_created_by_type",
})

# Con que estado puede NACER un caso importado. No es la lista completa de
# 'Case.status': un importador no tiene por que poder crear un caso ya
# cerrado o rechazado, y permitirlo abriria justo el camino que la decision
# de producto cerro (no traer historia resuelta).
ESTADOS_INICIALES = frozenset({"New", "Assigned"})

PRIORIDADES = frozenset(p[0] for p in PRIORITY_CHOICE)
TIPOS_DE_AUTOR = frozenset(t[0] for t in EXTERNAL_AUTHOR_TYPE)


def _error(detalle, codigo="DATOS_INVALIDOS", estado=http.HTTP_400_BAD_REQUEST):
    return Response({"error": codigo, "detalle": detalle}, status=estado)


def _campos_inesperados(cuerpo, permitidos):
    return sorted(set(cuerpo) - permitidos)


class ImportarCaseView(APIView):
    """
    POST /api/importacion/casos/

    Crea el caso de un ticket externo, o devuelve el que ya existe.

    Idempotente por ``(org, provider, external_ticket_id)``, que es la misma
    llave que sostiene el UNIQUE parcial de la base. Eso importa: la unicidad
    no la decide este codigo, la decide la constraint, y este codigo solo tiene
    que saber perder la carrera con elegancia.
    """

    permission_classes = (IsAuthenticated, HasOrgContext)

    def post(self, request):
        cuerpo = request.data if isinstance(request.data, dict) else {}
        sobra = _campos_inesperados(cuerpo, CAMPOS_DESCUBRIMIENTO)
        if sobra:
            return _error(f"campos no aceptados: {sobra}", "CAMPO_NO_PERMITIDO")

        proveedor = str(cuerpo.get("provider") or "").strip()
        ticket = str(cuerpo.get("external_ticket_id") or "").strip()
        if not proveedor or not ticket:
            # Los DOS, siempre. Es mas estricto que el CHECK de la base, y a
            # proposito: el modelo acepta las dos vacias porque asi son los
            # casos nativos, pero esta puerta no crea casos nativos. Si
            # aceptara el par vacio se volveria una segunda via para crear
            # casos normales -- una que no pasa por el serializer publico ni
            # por sus validaciones. Para eso ya esta POST /api/cases/.
            return _error("'provider' y 'external_ticket_id' son obligatorios: "
                          "esta ruta solo importa referencias externas",
                          "REFERENCIA_EXTERNA_INCOMPLETA")

        # --- validaciones que NO se delegan al motor -----------------------
        # El motor ya eligio responsable, y aun asi se comprueba aca: este es
        # el ultimo punto antes de la base, y confiar en el llamante porque es
        # "nuestro" es como se cruzan los tenants.
        perfil = None
        if cuerpo.get("assigned_to"):
            perfil = Profile.objects.filter(
                id=cuerpo["assigned_to"], org=request.org, is_active=True).first()
            if perfil is None:
                return _error(
                    "'assigned_to' no existe, no esta activo, o es de otra "
                    "organizacion", "RESPONSABLE_INVALIDO")

        prioridad = cuerpo.get("priority") or "Normal"
        if prioridad not in PRIORIDADES:
            return _error(f"'priority' invalida: {prioridad!r}", "PRIORIDAD_INVALIDA")

        estado = cuerpo.get("status") or "New"
        if estado not in ESTADOS_INICIALES:
            return _error(
                f"'status' inicial no permitido: {estado!r}. Permitidos: "
                f"{sorted(ESTADOS_INICIALES)}", "ESTADO_INICIAL_INVALIDO")

        tipo_autor = cuerpo.get("external_created_by_type") or ""
        if tipo_autor and tipo_autor not in TIPOS_DE_AUTOR:
            return _error(f"'external_created_by_type' invalido: {tipo_autor!r}",
                          "TIPO_DE_AUTOR_INVALIDO")

        nombre = (cuerpo.get("name") or "").strip()
        if not nombre:
            return _error("'name' es obligatorio", "NOMBRE_REQUERIDO")

        campos = {
            "org": request.org,
            "provider": proveedor,
            "external_ticket_id": ticket,
            "external_service_id": str(cuerpo.get("external_service_id") or ""),
            "external_status": str(cuerpo.get("external_status") or ""),
            "external_status_at": cuerpo.get("external_status_at") or None,
            "external_created_by": str(cuerpo.get("external_created_by") or ""),
            "external_created_by_type": tipo_autor,
            "external_fetched_at": cuerpo.get("external_fetched_at") or None,
            "name": nombre[:64],
            "description": cuerpo.get("description") or "",
            "priority": prioridad,
            "status": estado,
        }

        creado, caso = self._crear_o_recuperar(request.org, proveedor, ticket, campos)
        if caso is None:
            return _error("no se pudo crear ni recuperar el caso",
                          "CONFLICTO_IRRESOLUBLE", http.HTTP_409_CONFLICT)

        if creado and perfil is not None:
            # El M2M va despues del INSERT por fuerza. No abre ventana de
            # duplicacion: la identidad externa ya quedo puesta en el INSERT,
            # que es lo que la constraint mira.
            caso.assigned_to.add(perfil)

        return Response({
            "created": creado,
            "case_id": str(caso.id),
            "external_ticket_id": caso.external_ticket_id,
            "status": caso.status,
        }, status=http.HTTP_201_CREATED if creado else http.HTTP_200_OK)

    @staticmethod
    def _crear_o_recuperar(org, proveedor, ticket, campos):
        """
        Crea, o devuelve el que gano la carrera.

        El INSERT va envuelto en atomic(), y conviene ser exacto sobre que
        garantiza eso HOY y por que se deja igual.

        En PostgreSQL una violacion de constraint aborta la transaccion en
        curso: toda consulta posterior muere con InFailedSqlTransaction,
        incluida la relectura de abajo. Es el defecto que ya se pago una vez en
        las evidencias de campo.

        Aca ese escenario no se da todavia, y se comprobo: 'ATOMIC_REQUESTS'
        esta en False, asi que cada peticion corre en autocommit y el INSERT
        fallido es su propia transaccion -- la relectura funciona con envoltura
        o sin ella. Se midio quitando el atomic() y volviendo a correr la
        prueba de concurrencia contra Postgres real: sigue pasando.

        Se deja igual a proposito. El dia que alguien active ATOMIC_REQUESTS,
        o que este metodo se llame desde una transaccion mas grande, esta
        envoltura pasa a ser un SAVEPOINT y es lo unico que evita el 500. Es
        barato ahora y es la diferencia entre funcionar y no funcionar despues.

        Lo que la prueba de concurrencia SI demuestra es lo que importa: dos
        importaciones simultaneas del mismo ticket terminan en un solo caso,
        una con created=true y otra con created=false.
        """
        existente = Case.objects.filter(
            org=org, provider=proveedor, external_ticket_id=ticket).first()
        if existente is not None:
            # Ya estaba: no se toca NADA. Ni estado, ni responsable, ni el
            # texto que alguien pudo haber editado a mano. Lo que cambie del
            # lado del proveedor es asunto de la reconciliacion.
            return False, existente

        try:
            with transaction.atomic():
                return True, Case.objects.create(**campos)
        except IntegrityError:
            # Otro proceso lo creo entre el SELECT y el INSERT. Se relee: el
            # resultado correcto es el caso del ganador, no un error.
            return False, Case.objects.filter(
                org=org, provider=proveedor, external_ticket_id=ticket).first()


class TicketsConocidosView(APIView):
    """
    GET /api/importacion/tickets-conocidos/?provider=wisphub&ids=91865,91908

    Que sabe ya Dexter de estos tickets. Responde PERTENENCIA y nada mas.

    POR QUE EXISTE
    --------------
    El importador necesita dos cosas antes de decidir: si un ticket ya tiene
    caso (para cortarlo antes de gastar consultas de identidad) y si lo creamos
    nosotros (para clasificar la autoria). Las dos viven en tablas de Django --
    'case' y 'solicitudes_solicitudservicio'-- y el motor no las puede leer:
    corre con su propio usuario de base desde el incidente del 18/08/2026, en
    que compartia credencial con el CRM.

    La respuesta a eso NO es un GRANT. Darle SELECT sobre tablas de Django
    desharia esa separacion y ademas ataria 'nucleo/' al esquema interno de
    otra app -- el dia que 'solicitudes' renombre una columna, se rompe el
    importador. Esta ruta es el limite correcto: Django contesta lo que sabe,
    con la forma que el motor necesita, y por dentro puede cambiar lo que
    quiera.

    QUE NO DEVUELVE
    ---------------
    Nada de la solicitud ni del caso: ni cliente, ni notas, ni campos. Solo
    cuales de los ids preguntados estan en cada conjunto. Un endpoint que
    devolviera las filas seria una via para leer 'solicitudes' entera desde
    afuera, que es justo lo que se esta evitando.

    Es GET y no POST a proposito: no escribe, y con el vocabulario de alcances
    (common/scopes.py: 'read' cubre GET) alcanza con 'importacion:read'. Un
    POST habria exigido 'importacion:write' para una operacion que no escribe.
    """

    permission_classes = (IsAuthenticated, HasOrgContext)

    # Cuantos ids se pueden preguntar de una vez, y cuanto puede medir la
    # lista entera. Los dos limites hacen falta y miden cosas distintas: hoy
    # los ids del proveedor son numeros de cinco cifras, pero la columna admite
    # 64 caracteres, asi que "200 ids" puede ser 200 bytes o 13.000. El segundo
    # limite es el que evita depender de cuanto tolera cada proxy de la cadena,
    # que es justo lo que no se puede comprobar desde el codigo.
    MAX_IDS = 200
    MAX_LARGO_IDS = 4000

    def get(self, request):
        proveedor = (request.query_params.get("provider") or "").strip()
        if not proveedor:
            return _error("falta 'provider'", "PROVEEDOR_REQUERIDO")

        crudo = (request.query_params.get("ids") or "").strip()
        ids = [x.strip() for x in crudo.split(",") if x.strip()]
        if not ids:
            return _error("falta 'ids'", "IDS_REQUERIDOS")
        if len(ids) > self.MAX_IDS:
            return _error(f"maximo {self.MAX_IDS} ids por consulta, llegaron "
                          f"{len(ids)}", "DEMASIADOS_IDS")
        if len(crudo) > self.MAX_LARGO_IDS:
            return _error(f"la lista de ids mide {len(crudo)} caracteres y el "
                          f"maximo es {self.MAX_LARGO_IDS}",
                          "IDS_DEMASIADO_LARGOS")

        # Ambas consultas filtradas por request.org, que sale de la credencial.
        # Sin ese filtro, un ticket con el mismo numero en otro ISP se
        # reportaria como conocido y el importador lo saltearia -- un ticket
        # que nunca se importa, y en silencio.
        con_caso = set(Case.objects.filter(
            org=request.org, provider=proveedor, external_ticket_id__in=ids
        ).values_list("external_ticket_id", flat=True))

        # Las dos situaciones se distinguen a proposito, y no dan lo mismo:
        #
        #   el modulo no esta    despliegue legitimo sin 'solicitudes'. La
        #                        respuesta degrada a "ninguna", que clasifica
        #                        de mas como 'externo_desconocido' --
        #                        conservador, y nunca al reves.
        #
        #   la consulta fallo    tabla inexistente, permiso, esquema roto. Eso
        #                        NO se disfraza de "no instalado": se propaga,
        #                        porque el importador tiene que abortar el
        #                        ciclo en vez de clasificar mal en silencio.
        #                        Es exactamente el error que este endpoint vino
        #                        a resolver; taparlo aca lo volveria invisible.
        try:
            from solicitudes.models import SolicitudServicio
        except ImportError:
            creados_por_dexter = set()
        else:
            creados_por_dexter = set(SolicitudServicio.objects.filter(
                org=request.org, ticket_wisphub__in=ids
            ).values_list("ticket_wisphub", flat=True))

        return Response({
            "con_caso": sorted(con_caso),
            "creados_por_dexter": sorted(x for x in creados_por_dexter if x),
        }, status=http.HTTP_200_OK)


class CasosExternosView(APIView):
    """
    GET /api/importacion/casos/?provider=wisphub

    Los casos que ya llevan referencia externa, con lo que la reconciliacion
    necesita para decidir a cuales volver a preguntarles.

    Mismo motivo que 'tickets-conocidos': el motor no puede leer 'case', y la
    respuesta a eso no es un GRANT. Devuelve solo los campos que la politica
    usa -- estado propio, cierre, y los external_* que se van a comparar-- y
    nada del cliente ni del texto del caso.
    """

    permission_classes = (IsAuthenticated, HasOrgContext)

    CAMPOS = ("id", "external_ticket_id", "status", "closed_on",
              "external_status", "external_created_by",
              "external_created_by_type", "external_fetch_error")

    # Hoy son 16 casos y devolverlos todos no cuesta nada. Manana son miles, y
    # una consulta sin tope es de las que funcionan durante meses y despues
    # tumban el barrido en la hora pico. El orden va por 'external_ticket_id'
    # -- estable y unico dentro de (org, provider)-- para que paginar no
    # repita ni saltee filas, cosa que un orden por fecha no garantiza.
    LIMITE_POR_DEFECTO = 200
    LIMITE_MAXIMO = 500

    def get(self, request):
        proveedor = (request.query_params.get("provider") or "").strip()
        if not proveedor:
            return _error("falta 'provider'", "PROVEEDOR_REQUERIDO")

        try:
            limite = int(request.query_params.get("limit")
                         or self.LIMITE_POR_DEFECTO)
            desde = int(request.query_params.get("offset") or 0)
        except ValueError:
            return _error("'limit' y 'offset' tienen que ser enteros",
                          "PAGINACION_INVALIDA")
        if limite < 1 or limite > self.LIMITE_MAXIMO or desde < 0:
            return _error(f"'limit' entre 1 y {self.LIMITE_MAXIMO}, 'offset' "
                          f"no negativo", "PAGINACION_INVALIDA")

        base = Case.objects.filter(
            org=request.org, provider=proveedor
        ).exclude(external_ticket_id="").order_by("external_ticket_id")
        total = base.count()
        filas = base.values(*self.CAMPOS)[desde:desde + limite]

        return Response({
            "casos": [{k: (str(v) if k == "id" else v) for k, v in f.items()}
                      for f in filas],
            "total": total,
            "offset": desde,
            "limit": limite,
            # None cuando no queda nada: quien pagina no tiene que calcular el
            # final ni arriesgar una vuelta de mas.
            "next_offset": desde + limite if desde + limite < total else None,
        }, status=http.HTTP_200_OK)


class ReconciliarCaseView(APIView):
    """
    POST /api/importacion/casos/<uuid:pk>/reconciliar/

    Actualiza lo que dijo el proveedor. Nada mas.

    'status' y 'assigned_to' ni siquiera se ignoran: si llegan, la peticion se
    rechaza. Ignorarlos en silencio dejaria al llamante creyendo que los
    escribio, y el dia que alguien los mande por error querra saberlo.
    """

    permission_classes = (IsAuthenticated, HasOrgContext)

    def post(self, request, pk):
        cuerpo = request.data if isinstance(request.data, dict) else {}
        sobra = _campos_inesperados(cuerpo, CAMPOS_RECONCILIACION)
        if sobra:
            return _error(
                f"la reconciliacion no escribe {sobra}. Solo actualiza los "
                f"campos externos; el estado de Dexter lo decide una persona.",
                "CAMPO_NO_PERMITIDO")

        caso = Case.objects.filter(id=pk, org=request.org).first()
        if caso is None:
            # 404 y no 403 aunque exista en otra organizacion: quien no puede
            # verlo tampoco tiene por que enterarse de que existe.
            return _error("no existe", "CASO_NO_ENCONTRADO", http.HTTP_404_NOT_FOUND)

        tipo = cuerpo.get("external_created_by_type")
        if tipo and tipo not in TIPOS_DE_AUTOR:
            return _error(f"'external_created_by_type' invalido: {tipo!r}",
                          "TIPO_DE_AUTOR_INVALIDO")

        estado_previo = caso.status
        cambiados = []
        for campo in CAMPOS_RECONCILIACION:
            if campo not in cuerpo:
                continue
            valor = cuerpo[campo]

            if campo == "external_created_by_type":
                # Pegajoso TAMBIEN aca, no solo en el motor. Un caso que
                # sabemos que abrio Dexter no se degrada a 'externo_desconocido'
                # aunque el payload lo pida: el proveedor contesta SIEMPRE con
                # la cuenta compartida, tambien para lo nuestro. La evidencia
                # interna es mas especifica que esa identidad.
                if caso.external_created_by_type == EXTERNAL_AUTHOR_DEXTER \
                        and valor != EXTERNAL_AUTHOR_DEXTER:
                    continue

            if campo == "external_status" and not valor:
                # Una lectura que no trajo estado no borra el que ya habia:
                # perder un dato externo bueno por una respuesta pobre es peor
                # que quedarse con el anterior.
                continue

            if getattr(caso, campo) != valor:
                setattr(caso, campo, valor)
                cambiados.append(campo)

        if cambiados:
            caso.save(update_fields=cambiados + ["updated_at"])

        # No es una comprobacion decorativa: es el invariante de la fase, y se
        # afirma sobre la fila releida, no sobre la intencion del codigo.
        caso.refresh_from_db()
        assert caso.status == estado_previo, "la reconciliacion movio Case.status"

        return Response({
            "case_id": str(caso.id),
            "external_ticket_id": caso.external_ticket_id,
            "actualizados": sorted(cambiados),
            "status": caso.status,
            "external_status": caso.external_status,
        }, status=http.HTTP_200_OK)
