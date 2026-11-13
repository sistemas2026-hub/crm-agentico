# -*- coding: utf-8 -*-
"""
================================================================================
 EL CONTRATO DEL CLIENTE, CREADO DESDE LA APP  --  13/11/2026
================================================================================

Decision del usuario: *«ahora el tecnico crearia el contrato desde la app de
dexter»*. Hasta hoy el tecnico, parado en la casa del cliente, entraba a WispHub
y llenaba A MANO nombre, apellido, cedula, plan, direccion, coordenadas, el
tecnico y la fecha. Todo eso ya esta en la plataforma antes de que llegue: lo
lleno el cliente en la solicitud (`solicitudes.SolicitudServicio`).

QUE HACE ESTE ARCHIVO, Y QUE TODAVIA NO
---------------------------------------
* Arma el BORRADOR del contrato de una orden: los datos del cliente salen de su
  solicitud --encontrada por el ticket del ISP que la solicitud creo--, y si no
  hay solicitud, de lo que la orden ya sabe del cliente.
* Guarda el contrato FIRMADO: los datos tal como quedaron, el servidor elegido,
  la firma del cliente y una huella. La firma vive SOLO dentro del PDF, igual
  que las fotos del expediente de la solicitud: un objeto que proteger, no dos.
* NO da de alta el cliente en WispHub todavia. La API exige IP y el usuario
  todavia tiene que decir como se asigna (SPEC/objetivos/
  agente-de-campo-para-instalaciones.md, «Lo que falta del usuario»). El
  contrato queda `firmado` y la pantalla lo dice; el alta es la fase 2.

LA FIRMA NO VA A WISPHUB POR API PORQUE WISPHUB NO TIENE DONDE
--------------------------------------------------------------
Medido el 13/11/2026 sobre su especificacion: no hay recurso de contratos,
firmas ni documentos del cliente. Lo que si acepta es `archivo` en la respuesta
de un ticket, y ese camino ya lleva las fotos de campo
(`nucleo/seguimiento/nota_en_el_ticket.py`, que admite PDF). El contrato
firmado viajara por ahi cuando exista el alta.

POR QUE LAS CONDICIONES NO ESTAN ESCRITAS ACA
---------------------------------------------
Son el contrato de cada empresa (permanencia, comodato, mora...). Se cargan como
texto desde la plataforma (`ConfiguracionDeContrato.texto_condiciones`) y van
tal cual al PDF. Un texto legal escrito en codigo seria el de una empresa
imponiendose a todas (CLAUDE.md §3.3).
================================================================================
"""
from __future__ import annotations

import base64
import hashlib
import json
from io import BytesIO

from django.db import models
from django.utils import timezone

from common.base import BaseModel
from common.models import Org

#: Lo minimo para que un contrato identifique a alguien y a un lugar.
CAMPOS_OBLIGATORIOS = ("nombre", "numero_documento", "direccion")

#: Los datos del cliente que el contrato lleva, en el orden de la pantalla.
CAMPOS_DEL_CLIENTE = ("nombre", "apellido", "tipo_documento", "numero_documento",
                      "telefono", "correo", "direccion", "barrio")

#: Tope del texto de cada campo: es un contrato, no un ensayo, y una cadena de
#: 10.000 caracteres en «nombre» rompe el PDF antes que cualquier otra cosa.
LARGO_MAXIMO = 160

#: La firma llega como PNG. Mas de esto no es una firma.
FIRMA_MAXIMA = 1024 * 1024
_PNG = b"\x89PNG\r\n\x1a\n"


class ConfiguracionDeContrato(BaseModel):
    """Lo que cada empresa pone en su contrato. Editable desde Programacion."""

    org = models.OneToOneField(Org, on_delete=models.CASCADE,
                               related_name="configuracion_contrato")
    nit = models.CharField(max_length=80, blank=True, default="")

    #: LOS SERVIDORES ENTRE LOS QUE ELIGE EL TECNICO. El usuario, 13/11/2026:
    #: «zona es el servidor, asi que debe mostrar los dos y ahi se elige». Cada
    #: uno es `{"id_zona": int, "nombre": str}`: el id es el de `/api/zonas/`
    #: de WispHub, NO el de `/api/router/` -- son catalogos con ids distintos
    #: aunque se llamen igual (skill de WispHub, «CRITICO»).
    servidores = models.JSONField(default=list, blank=True)

    texto_condiciones = models.TextField(blank=True, default="")

    class Meta:
        db_table = "campo_configuracion_contrato"
        verbose_name = "Configuración del contrato"

    def como_dict(self) -> dict:
        return {"nit": self.nit, "servidores": list(self.servidores or []),
                "texto_condiciones": self.texto_condiciones}


VACIA = {"nit": "", "servidores": [], "texto_condiciones": ""}


def configuracion_de(org) -> dict:
    fila = ConfiguracionDeContrato.objects.filter(org=org).first()
    return fila.como_dict() if fila else dict(VACIA)


class ContratoDeServicio(BaseModel):
    """Un contrato firmado en la casa del cliente. No se edita: se firma una vez."""

    FIRMADO = "firmado"            # existe y tiene firma; el alta en el ISP falta
    EN_EL_ISP = "en_el_isp"        # el cliente quedo creado en WispHub
    ESTADOS = ((FIRMADO, "Firmado"), (EN_EL_ISP, "Creado en el ISP"))

    org = models.ForeignKey(Org, on_delete=models.CASCADE,
                            related_name="contratos_de_servicio")
    #: PROTECT y no CASCADE: borrar una orden no puede borrar un contrato que
    #: un cliente firmo.
    orden = models.ForeignKey("campo.OrdenTrabajo", on_delete=models.PROTECT,
                              related_name="contratos")
    solicitud = models.ForeignKey("solicitudes.SolicitudServicio",
                                  on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name="contratos")
    numero = models.CharField(max_length=40)
    #: Los datos TAL COMO SE FIRMARON. Si despues se corrige la solicitud, el
    #: contrato no cambia: es lo que el cliente acepto ese dia.
    datos = models.JSONField(default=dict)
    pdf = models.FileField(upload_to="contratos/%Y/%m/", null=True, blank=True)
    huella = models.CharField(max_length=64)
    estado = models.CharField(max_length=20, choices=ESTADOS, default=FIRMADO)
    servicio_isp = models.CharField(max_length=64, blank=True, default="")
    firmado_por = models.ForeignKey("common.Profile", on_delete=models.SET_NULL,
                                    null=True, blank=True,
                                    related_name="contratos_firmados")
    firmado_en = models.DateTimeField()

    class Meta:
        db_table = "campo_contrato_de_servicio"
        verbose_name = "Contrato de servicio"
        constraints = [
            #  UNO POR ORDEN. Un segundo envio del mismo telefono (sin señal,
            #  reintento) devuelve el que ya existe en vez de crear otro.
            models.UniqueConstraint(fields=["orden"], name="un_contrato_por_orden"),
        ]

    def como_dict(self) -> dict:
        return {
            "id": str(self.id),
            "numero": self.numero,
            "estado": self.estado,
            "estado_etiqueta": self.get_estado_display(),
            "servicio_isp": self.servicio_isp or None,
            "firmado_en": self.firmado_en.isoformat(),
            "cliente": (self.datos or {}).get("cliente", {}),
            "servidor": (self.datos or {}).get("servidor", {}),
            "plan": (self.datos or {}).get("plan", ""),
            "huella": self.huella,
            "tiene_pdf": bool(self.pdf),
        }


# =============================================================================
#  DE DONDE SALEN LOS DATOS
# =============================================================================
def _tickets_de(orden) -> set[str]:
    """Los ids de ticket del ISP con los que esta orden se puede reconocer."""
    ids = set()
    ref = str(getattr(orden, "origen_ref", "") or "").strip().lstrip("#")
    if ref and getattr(orden, "origen_tipo", "") in ("ticket", "case", ""):
        ids.add(ref)
    caso = getattr(orden, "caso", None)
    externo = str(getattr(caso, "external_ticket_id", "") or "").strip().lstrip("#")
    if externo:
        ids.add(externo)
    return ids


def solicitud_de_la_orden(orden):
    """La solicitud del cliente de esta orden, o None.

    Se reconoce por el ticket del ISP: la solicitud CREO ese ticket
    (`SolicitudServicio.ticket_wisphub`) y la orden nacio de el. Filtra por la
    empresa de la orden: un id de ticket repetido entre empresas no une a ciegas.
    Una solicitud cancelada o sin factibilidad no sirve para un contrato.
    """
    from solicitudes.models import SolicitudServicio

    ids = _tickets_de(orden)
    if not ids:
        return None
    return (SolicitudServicio.objects
            .filter(org=orden.org, ticket_wisphub__in=ids)
            .exclude(estado__in=[SolicitudServicio.CANCELADA,
                                 SolicitudServicio.SIN_FACTIBILIDAD])
            .order_by("-created_at").first())


def borrador(orden) -> dict:
    """Lo que la pantalla del contrato muestra antes de firmar."""
    s = solicitud_de_la_orden(orden)
    if s is not None:
        cliente = {
            "nombre": s.nombre, "apellido": s.apellido,
            "tipo_documento": s.tipo_documento or "CC",
            "numero_documento": s.numero_documento, "telefono": s.telefono,
            "correo": s.correo, "direccion": s.direccion, "barrio": s.barrio,
        }
        gps = ({"lat": s.gps_lat, "lng": s.gps_lng,
                "precision_m": s.gps_precision_m} if s.gps_lat and s.gps_lng else None)
        autorizaciones = {
            "habeas_data": bool(s.autoriza_habeas_data),
            "centrales_de_riesgo": bool(s.autoriza_centrales_riesgo),
            "aceptadas_en": s.enviada_en.isoformat() if s.enviada_en else None,
        }
        return {"origen": "solicitud", "solicitud_id": str(s.id),
                "cliente": cliente, "plan": s.plan_interesado, "gps": gps,
                "autorizaciones": autorizaciones}

    #  SIN SOLICITUD: lo que la orden ya sabe. El nombre viene entero en un
    #  solo campo; el tecnico lo separa si hace falta. Sin autorizaciones: no
    #  hay donde las haya aceptado, y el contrato lo dira.
    return {
        "origen": "orden", "solicitud_id": None,
        "cliente": {"nombre": orden.cliente_nombre, "apellido": "",
                    "tipo_documento": "CC", "numero_documento": "",
                    "telefono": orden.cliente_telefono, "correo": "",
                    "direccion": orden.cliente_direccion, "barrio": ""},
        "plan": "", "gps": None, "autorizaciones": None,
    }


# =============================================================================
#  FIRMAR
# =============================================================================
class ContratoInvalido(ValueError):
    """Lo que el telefono mando no alcanza para un contrato. El texto se le
    muestra al tecnico tal cual."""


def _texto(valor) -> str:
    return str(valor or "").strip()[:LARGO_MAXIMO]


def _firma_de(cuerpo: dict) -> bytes:
    crudo = str(cuerpo.get("firma_png_base64") or "")
    if "," in crudo and crudo.startswith("data:"):
        crudo = crudo.split(",", 1)[1]
    try:
        firma = base64.b64decode(crudo, validate=True)
    except (ValueError, TypeError):
        raise ContratoInvalido("La firma no llegó bien. Pídele al cliente que firme otra vez.")
    if not firma.startswith(_PNG) or len(firma) > FIRMA_MAXIMA:
        raise ContratoInvalido("La firma no llegó bien. Pídele al cliente que firme otra vez.")
    return firma


def _gps_de(cuerpo: dict) -> dict | None:
    g = cuerpo.get("gps")
    if not isinstance(g, dict):
        return None
    try:
        lat, lng = float(g["lat"]), float(g["lng"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180) or (lat == 0 and lng == 0):
        return None   # 0,0 es el golfo de Guinea, no una casa
    out = {"lat": round(lat, 6), "lng": round(lng, 6)}
    try:
        out["precision_m"] = int(float(g.get("precision_m") or 0))
    except (TypeError, ValueError):
        pass
    return out


def firmar(orden, profile, cuerpo: dict) -> tuple["ContratoDeServicio", bool]:
    """Crea el contrato firmado de la orden. Devuelve (contrato, creado).

    Idempotente por orden: si ya hay uno, se devuelve ese y `creado=False`.
    """
    from campo.marca_de_agua import nombre_para_la_marca

    existente = ContratoDeServicio.objects.filter(orden=orden).first()
    if existente is not None:
        return existente, False

    base = borrador(orden)
    llegado = cuerpo.get("cliente") if isinstance(cuerpo.get("cliente"), dict) else {}
    #  LO QUE MANDA EL TELEFONO GANA SOBRE EL BORRADOR: el tecnico tiene el
    #  documento delante y pudo corregir un dato mal escrito en la solicitud.
    cliente = {c: _texto(llegado.get(c, base["cliente"].get(c, ""))) for c in CAMPOS_DEL_CLIENTE}
    faltan = [c for c in CAMPOS_OBLIGATORIOS if not cliente[c]]
    if faltan:
        nombres = {"nombre": "el nombre", "numero_documento": "el documento",
                   "direccion": "la dirección"}
        raise ContratoInvalido("Falta " + ", ".join(nombres[c] for c in faltan) + ".")

    plan = _texto(cuerpo.get("plan") or base.get("plan"))
    if not plan:
        raise ContratoInvalido("Falta el plan.")

    config = configuracion_de(orden.org)
    try:
        id_zona = int(cuerpo.get("id_zona"))
    except (TypeError, ValueError):
        id_zona = None
    servidor = next((s for s in config["servidores"]
                     if isinstance(s, dict) and s.get("id_zona") == id_zona), None)
    if servidor is None:
        raise ContratoInvalido("Elige el servidor." if config["servidores"]
                               else "Tu empresa todavía no cargó sus servidores.")

    firma = _firma_de(cuerpo)
    ahora = timezone.now()
    datos = {
        "cliente": cliente,
        "plan": plan,
        "servidor": {"id_zona": servidor["id_zona"], "nombre": servidor.get("nombre", "")},
        "gps": _gps_de(cuerpo) or base.get("gps"),
        "autorizaciones": base.get("autorizaciones"),
        "tecnico": nombre_para_la_marca(profile),
        "orden_numero": orden.numero,
        "origen": base["origen"],
    }
    canonico = json.dumps(datos, sort_keys=True, ensure_ascii=False).encode("utf-8")
    huella = hashlib.sha256(canonico + hashlib.sha256(firma).digest()).hexdigest()
    numero = f"C-{ahora:%Y}-{orden.numero:06d}"

    contrato = ContratoDeServicio(
        org=orden.org, orden=orden,
        solicitud_id=base.get("solicitud_id"),
        numero=numero, datos=datos, huella=huella,
        firmado_por=profile, firmado_en=ahora,
    )
    pdf = armar_pdf(contrato, firma, config)
    contrato.pdf.save(f"{numero}.pdf", pdf, save=False)
    try:
        contrato.save()
    except Exception:
        #  Otro envio del mismo contrato gano la carrera: la restriccion
        #  `un_contrato_por_orden` lo freno. Se devuelve el que quedo.
        ganador = ContratoDeServicio.objects.filter(orden=orden).first()
        if ganador is not None:
            return ganador, False
        raise
    return contrato, True


# =============================================================================
#  EL PDF
# =============================================================================
def _fecha_bogota(cuando) -> tuple[str, str]:
    from zoneinfo import ZoneInfo

    local = cuando.astimezone(ZoneInfo("America/Bogota"))
    return local.strftime("%d/%m/%Y"), local.strftime("%H:%M")


def armar_pdf(contrato: "ContratoDeServicio", firma: bytes, config: dict):
    """El contrato en PDF, con el mismo motor que el expediente de la solicitud."""
    from django.core.files.base import ContentFile
    from django.template.loader import render_to_string
    from weasyprint import HTML
    from weasyprint.text.fonts import FontConfiguration

    from solicitudes.pdf import _data_uri, _logo_de

    d = contrato.datos
    fecha, hora = _fecha_bogota(contrato.firmado_en)
    aut = d.get("autorizaciones") or {}
    aceptadas = ""
    if aut.get("aceptadas_en"):
        from datetime import datetime
        aceptadas = _fecha_bogota(datetime.fromisoformat(aut["aceptadas_en"]))[0]
    gps = d.get("gps") or {}
    contexto = {
        "empresa": contrato.org.name, "nit": config.get("nit", ""),
        "logo": _logo_de(contrato.org),
        "numero": contrato.numero, "orden": d.get("orden_numero"),
        "fecha": fecha, "hora": hora,
        "c": d["cliente"], "plan": d["plan"], "servidor": d["servidor"],
        "tecnico": d.get("tecnico", ""),
        "autorizaciones": aut, "aceptadas_en": aceptadas,
        "condiciones": config.get("texto_condiciones", ""),
        "gps": (f"{gps['lat']}, {gps['lng']}" + (f" (±{gps['precision_m']} m)"
                if gps.get("precision_m") else "")) if gps.get("lat") is not None else "",
        "firma": _data_uri(firma, "image/png"),
        "huella": contrato.huella,
    }
    html = render_to_string("campo/contrato.html", contexto)
    salida = BytesIO()
    HTML(string=html).write_pdf(salida, font_config=FontConfiguration())
    return ContentFile(salida.getvalue())
