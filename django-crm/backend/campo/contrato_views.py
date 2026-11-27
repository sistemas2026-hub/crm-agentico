"""El contrato del cliente, desde la app y desde la plataforma (13/11/2026).

    GET  /api/campo/trabajos/<id>/contrato/   el borrador (o el ya firmado) y los servidores
    POST /api/campo/trabajos/<id>/contrato/   firmar: {cliente, plan, id_zona, gps, firma_png_base64}
    GET  /api/campo/contratos/<id>/pdf/       el PDF firmado
    POST /api/campo/contratos/<id>/anular/    {motivo}: deja el contrato sin efecto (25/11/2026)
    POST /api/campo/contratos/<id>/crear-en-el-isp/   pide (otra vez) crear al cliente en el ISP
    POST /api/campo/contratos/<id>/resolver-alta/     gestion dice si el cliente quedo creado
    GET  /api/campo/contrato/configuracion/   lo que la empresa pone en su contrato (gestion)
    PUT  /api/campo/contrato/configuracion/   {nit, servidores:[{id_zona,nombre}], texto_condiciones,
                                               datos_en_mayusculas, barrio_en_la_direccion,
                                               digitos_del_telefono}

Ver `campo/contrato.py` para el porque de cada decision.

FIRMAR EXIGE SEÑAL, Y ES A PROPOSITO. La app NO encola el contrato: crear un
cliente es algo que no se puede mandar «despues» sin que nadie mire, y esto es
el primer paso de ese alta. Sin red, la app lo dice y deja el boton para cuando
vuelva.
"""
from django.http import FileResponse, Http404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from campo.cuadrillas_views import _exigir_gestion
from campo.permissions import IsCampoAuthenticated

#: Cuantos servidores puede declarar una empresa. Son los del ISP, no miles.
MAXIMO_SERVIDORES = 20
MAXIMO_CONDICIONES = 20000


def _orden(request, pk):
    from campo.views import _obtener_orden_o_404

    return _obtener_orden_o_404(request, pk)


class ContratoDeLaOrdenView(APIView):
    permission_classes = [IsCampoAuthenticated]

    def get(self, request, pk):
        from campo.contrato import (ContratoDeServicio, configuracion_de,
                                    para_la_pantalla, vigente_de)

        orden = _orden(request, pk)
        config = configuracion_de(orden.org)
        firmado = vigente_de(orden)
        #  Sin firmar: el borrador ya con formato, y SOLO los servidores del
        #  plan (25/11/2026). Firmado: no hay nada que elegir.
        pantalla = ({"borrador": None, "servidores": config["servidores"],
                     "planes": [], "falta_cargar_servidores": False}
                    if firmado else para_la_pantalla(orden))
        return Response({
            "contrato": firmado.como_dict() if firmado else None,
            **pantalla,
            "condiciones_cargadas": bool(config["texto_condiciones"].strip()),
            "empresa": getattr(orden.org, "name", "") or "",
            #  Cuantos contratos de esta orden se anularon antes: la pantalla
            #  lo dice para que un borrador en blanco no parezca «nunca firmo».
            "anulados": ContratoDeServicio.objects.filter(
                orden=orden, estado=ContratoDeServicio.ANULADO).count(),
        })

    def post(self, request, pk):
        from campo.contrato import ContratoInvalido, firmar

        orden = _orden(request, pk)
        try:
            contrato, creado = firmar(orden, request.profile, request.data or {})
        except ContratoInvalido as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        #  FIRMAR Y CREAR AL CLIENTE SON DOS HECHOS (25/11/2026). El contrato
        #  ya quedo guardado; si la empresa lo tiene encendido, el alta en el
        #  ISP se pide ahora y corre DESPUES, en una tarea: la app espera 20
        #  segundos y el proveedor crea en segundo plano. Solo cuando el
        #  contrato se acaba de crear: un reintento de la firma no pide otra.
        if creado:
            from campo.contrato import configuracion_de
            from campo.services import alta_en_el_isp

            #  Si una persona valida la instalacion (26/11/2026), el alta NO
            #  sale al firmar: sale al «Finalizar trabajo» (campo/instalacion.py).
            config = configuracion_de(orden.org)
            if config["crear_en_el_isp"] and not config["validar_antes_de_activar"]:
                alta_en_el_isp.pedir_alta(contrato)
        return Response({"contrato": contrato.como_dict()},
                        status=status.HTTP_201_CREATED if creado else status.HTTP_200_OK)


class PdfDelContratoView(APIView):
    """El PDF firmado. Lo abre quien puede abrir la orden: su tecnico, o gestion."""

    permission_classes = [IsCampoAuthenticated]

    def get(self, request, pk):
        from campo.contrato import ContratoDeServicio

        org = getattr(request, "org", None)
        contrato = (ContratoDeServicio.objects.filter(pk=pk, org=org)
                    .select_related("orden").first()) if org else None
        if contrato is None or not contrato.pdf:
            raise Http404
        _orden(request, contrato.orden_id)   # 404 si quien pide no ve la orden
        respuesta = FileResponse(contrato.pdf.open("rb"), content_type="application/pdf")
        respuesta["Content-Disposition"] = f'inline; filename="{contrato.numero}.pdf"'
        respuesta["X-Content-Type-Options"] = "nosniff"
        respuesta["Cache-Control"] = "private, no-store"
        return respuesta


class AnularContratoView(APIView):
    """Deja un contrato sin efecto para que la orden firme otro (25/11/2026).

    Lo puede quien puede firmarlo: el tecnico de la orden, o gestion. El motivo
    es obligatorio. Uno que ya creo al cliente en el ISP se rechaza con 409:
    ver `campo.contrato.anular`.
    """

    permission_classes = [IsCampoAuthenticated]

    def post(self, request, pk):
        from campo.contrato import (ContratoDeServicio, ContratoInvalido,
                                    ContratoNoAnulable, anular)

        org = getattr(request, "org", None)
        contrato = (ContratoDeServicio.objects.filter(pk=pk, org=org)
                    .select_related("orden").first()) if org else None
        if contrato is None:
            raise Http404
        _orden(request, contrato.orden_id)   # 404 si quien pide no ve la orden
        #  Un cuerpo que no es un objeto (una lista, un texto) no trae motivo:
        #  se contesta «falta el motivo», no un error del servidor.
        cuerpo = request.data if isinstance(request.data, dict) else {}
        try:
            anular(contrato, request.profile, cuerpo.get("motivo"))
        except ContratoInvalido as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except ContratoNoAnulable as e:
            return Response({"detail": str(e)}, status=status.HTTP_409_CONFLICT)
        return Response({"contrato": contrato.como_dict()})


class CrearEnElIspView(APIView):
    """Pide (otra vez) que el cliente de un contrato se cree en el ISP (25/11/2026).

    Es el boton de una PERSONA: el alta sale sola al firmar, y esto es para
    cuando fallo --con su porque a la vista-- o para un contrato que se firmo
    antes de que la empresa lo encendiera. Lo puede quien puede firmarlo.

    NO CREA NADA EN ESTA PETICION: marca el alta como pedida y la encola.
    Contesta 202, y el contrato dice como va.
    """

    permission_classes = [IsCampoAuthenticated]

    def post(self, request, pk):
        from campo.contrato import ContratoDeServicio, configuracion_de
        from campo.services import alta_en_el_isp

        org = getattr(request, "org", None)
        contrato = (ContratoDeServicio.objects.filter(pk=pk, org=org)
                    .select_related("orden").first()) if org else None
        if contrato is None:
            raise Http404
        _orden(request, contrato.orden_id)   # 404 si quien pide no ve la orden

        if contrato.estado == ContratoDeServicio.EN_EL_ISP:
            return Response({"contrato": contrato.como_dict()})
        if contrato.estado != ContratoDeServicio.FIRMADO:
            return Response({"detail": "Ese contrato está anulado."},
                            status=status.HTTP_409_CONFLICT)
        if not configuracion_de(contrato.org)["crear_en_el_isp"]:
            return Response(
                {"detail": "Tu empresa no tiene encendido crear al cliente en el "
                           "sistema del proveedor desde aquí (Programación → El "
                           "contrato de instalación)."},
                status=status.HTTP_409_CONFLICT)
        if contrato.alta_estado == ContratoDeServicio.ALTA_POR_REVISAR:
            #  NADIE SABE SI EL CLIENTE QUEDO CREADO. Volver a pedirlo ahora
            #  podria crear otro: primero lo mira una persona de gestion.
            return Response(
                {"detail": "No se sabe si el cliente quedó creado. Antes de "
                           "volver a intentarlo, alguien de gestión tiene que "
                           "revisarlo en el proveedor (Instalaciones).",
                 "contrato": contrato.como_dict()},
                status=status.HTTP_409_CONFLICT)
        if not alta_en_el_isp.pedir_alta(contrato, por=request.profile):
            contrato.refresh_from_db()
            return Response({"detail": "El cliente ya se está creando. Espera a que termine.",
                             "contrato": contrato.como_dict()},
                            status=status.HTTP_409_CONFLICT)
        return Response({"contrato": contrato.como_dict()},
                        status=status.HTTP_202_ACCEPTED)


class ResolverAltaView(APIView):
    """Gestion dice si el cliente quedo creado en el ISP (25/11/2026).

    Es la unica salida de un alta `por_revisar`: el sistema ya dijo que no
    sabe, y adivinar seria o un cliente duplicado o el numero de otra persona
    en un contrato. La persona mira en el proveedor y contesta una de dos:

        {"quedo_creado": true,  "id_cliente": "<numero en el proveedor>"}
        {"quedo_creado": false}

    SOLO GESTION, y no el tecnico: es afirmar algo sobre el sistema del
    proveedor, y queda escrito quien lo afirmo.
    """

    permission_classes = [IsCampoAuthenticated]

    def post(self, request, pk):
        from campo.contrato import ContratoDeServicio
        from campo.services import alta_en_el_isp

        _exigir_gestion(request)
        org = getattr(request, "org", None)
        contrato = (ContratoDeServicio.objects.filter(pk=pk, org=org).first()
                    if org else None)
        if contrato is None:
            raise Http404
        cuerpo = request.data if isinstance(request.data, dict) else {}
        quedo = cuerpo.get("quedo_creado")
        if not isinstance(quedo, bool):
            return Response({"detail": "Di si el cliente quedó creado o no."},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            alta_en_el_isp.resolver(contrato, request.profile, quedo_creado=quedo,
                                    id_cliente=str(cuerpo.get("id_cliente") or ""))
        except alta_en_el_isp.ResolucionInvalida as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"contrato": contrato.como_dict()})


#: Cuantas reglas de abreviatura y cuantas formas por regla. Son las de una
#: direccion (calle, carrera, diagonal...), no un diccionario.
MAXIMO_REGLAS = 40
MAXIMO_FORMAS = 12


def _abreviaturas_validas(valor):
    """Las reglas limpias, o un texto de error. Una forma no puede estar en dos
    reglas: no se sabria en cual de las dos convertirla."""
    if not isinstance(valor, list) or len(valor) > MAXIMO_REGLAS:
        return None, f"Las abreviaturas son una lista de hasta {MAXIMO_REGLAS} reglas."
    limpias, vistas = [], set()
    for r in valor:
        if not isinstance(r, dict):
            return None, "Cada regla dice cómo lo escriben y cómo queda."
        queda = " ".join(str(r.get("como_queda") or "").split())
        formas = r.get("como_lo_escriben")
        if not queda or len(queda) > 20:
            return None, "Cada regla necesita cómo queda escrita (hasta 20 letras)."
        if not isinstance(formas, list) or not formas or len(formas) > MAXIMO_FORMAS:
            return None, f"«{queda}»: escribe de 1 a {MAXIMO_FORMAS} formas de escribirlo."
        propias = []
        for f in formas:
            f = str(f or "").strip().rstrip(".")
            if not f or len(f) > 20 or " " in f:
                return None, f"«{queda}»: cada forma es una palabra de hasta 20 letras."
            clave = f.upper()
            if clave in vistas:
                return None, f"«{f}» está en dos reglas: no se sabría cuál usar."
            vistas.add(clave)
            propias.append(f)
        limpias.append({"como_lo_escriben": propias, "como_queda": queda})
    return limpias, ""


def _servidores_validos(valor):
    """La lista tal como la guarda la base, o un texto de error."""
    if not isinstance(valor, list) or len(valor) > MAXIMO_SERVIDORES:
        return None, f"Los servidores son una lista de hasta {MAXIMO_SERVIDORES}."
    limpios, vistos = [], set()
    for s in valor:
        if not isinstance(s, dict):
            return None, "Cada servidor lleva su número de zona y su nombre."
        idz = s.get("id_zona")
        nombre = str(s.get("nombre") or "").strip()
        if isinstance(idz, bool) or not isinstance(idz, int) or idz <= 0:
            return None, "El número de zona de WispHub es un entero positivo."
        if not nombre or len(nombre) > 80:
            return None, "Cada servidor necesita un nombre de hasta 80 caracteres."
        if idz in vistos:
            return None, "Hay dos servidores con el mismo número de zona."
        vistos.add(idz)
        #  LA VLAN DEL SERVIDOR (26/11/2026), para activar la ONU: decision del
        #  usuario, «del servidor del contrato». Opcional.
        vlan = s.get("vlan")
        if vlan in (None, ""):
            limpios.append({"id_zona": idz, "nombre": nombre})
            continue
        if isinstance(vlan, bool) or not isinstance(vlan, int) or not 1 <= vlan <= 4094:
            return None, f"La VLAN de «{nombre}» es un número de 1 a 4094."
        limpios.append({"id_zona": idz, "nombre": nombre, "vlan": vlan})
    return limpios, ""


class ConfiguracionDeContratoView(APIView):
    permission_classes = [IsCampoAuthenticated]

    def get(self, request):
        from campo.contrato import configuracion_de

        _exigir_gestion(request)
        return Response(configuracion_de(request.profile.org))

    def put(self, request):
        from campo.contrato import (MAXIMO_DIGITOS_DE_TELEFONO,
                                    ConfiguracionDeContrato)

        _exigir_gestion(request)
        datos = request.data or {}
        cambios = {}
        if "nit" in datos:
            nit = datos["nit"]
            if not isinstance(nit, str) or len(nit.strip()) > 80:
                return Response({"detail": "El NIT es un texto de hasta 80 caracteres."},
                                status=status.HTTP_400_BAD_REQUEST)
            cambios["nit"] = nit.strip()
        if "servidores" in datos:
            limpios, error = _servidores_validos(datos["servidores"])
            if error:
                return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)
            cambios["servidores"] = limpios
        if "texto_condiciones" in datos:
            t = datos["texto_condiciones"]
            if not isinstance(t, str) or len(t) > MAXIMO_CONDICIONES:
                return Response({"detail": "Las condiciones son un texto de hasta "
                                           f"{MAXIMO_CONDICIONES} caracteres."},
                                status=status.HTTP_400_BAD_REQUEST)
            cambios["texto_condiciones"] = t.strip()
        #  COMO ESCRIBE LA EMPRESA LOS DATOS (25/11/2026). Un «si/no» es un
        #  booleano de verdad: "false" como texto es verdadero en Python, y
        #  guardarlo asi encenderia la costumbre que alguien quiso apagar.
        for campo, nombre in (("datos_en_mayusculas", "Los datos en mayúsculas"),
                              ("barrio_en_la_direccion", "El barrio pegado a la dirección"),
                              ("crear_en_el_isp", "Crear al cliente en el proveedor al firmar"),
                              ("activar_onu", "Activar la ONU desde la app"),
                              ("validar_antes_de_activar",
                               "Una persona valida la instalación antes de activarla")):
            if campo in datos:
                if not isinstance(datos[campo], bool):
                    return Response({"detail": f"«{nombre}» es sí o no."},
                                    status=status.HTTP_400_BAD_REQUEST)
                cambios[campo] = datos[campo]
        if "abreviaturas_de_direccion" in datos:
            reglas, error = _abreviaturas_validas(datos["abreviaturas_de_direccion"])
            if error:
                return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)
            cambios["abreviaturas_de_direccion"] = reglas
        if "digitos_del_telefono" in datos:
            n = datos["digitos_del_telefono"]
            if (isinstance(n, bool) or not isinstance(n, int)
                    or not 0 <= n <= MAXIMO_DIGITOS_DE_TELEFONO):
                return Response({"detail": "Los dígitos del teléfono son un número de 0 a "
                                           f"{MAXIMO_DIGITOS_DE_TELEFONO} (0 = no recortar)."},
                                status=status.HTTP_400_BAD_REQUEST)
            cambios["digitos_del_telefono"] = n

        fila, _ = ConfiguracionDeContrato.objects.get_or_create(org=request.profile.org)
        for campo, valor in cambios.items():
            setattr(fila, campo, valor)
        if cambios:
            fila.save(update_fields=list(cambios) + ["updated_at"])
        return Response(fila.como_dict())
