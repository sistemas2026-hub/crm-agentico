# -*- coding: utf-8 -*-
"""
================================================================================
 ACTIVAR LA ONU DE UNA INSTALACION DESDE LA APP  --  26/11/2026
================================================================================
El usuario: «en el paso 3, instalacion, cuando se ponga el serial, como se hace
para que se active la ONU en SmartOLT enseguida». Decidio:

* un boton «Activar ONU» despues del serial, construido APAGADO (la empresa lo
  enciende en Programacion) y probado una vez con su permiso;
* la VLAN sale del SERVIDOR del contrato (se carga junto a cada servidor);
* la zona la sugiere el barrio del contrato y el tecnico la confirma.

El motor hace la parte peligrosa (`nucleo/seguimiento/activar_onu.py`): solo
escribe si el proveedor lista la ONU esperando autorizacion, por la puerta
humana, con la clave del pedido, y confirma leyendo. Aca queda el pedido, quien
lo hizo y como termino, para que el tecnico lo vea y la oficina pueda mirarlo.

UN PEDIDO EN VUELO NO SE DUPLICA: mientras uno este pedido o en curso, pedir
otra vez devuelve ese. Cada pedido nuevo es otro numero (otra clave en el
motor), y el motor igual empieza mirando si la ONU ya estaba autorizada.
================================================================================
"""
from __future__ import annotations

import logging
import os
import re
import unicodedata

import requests
from django.db import models

from common.base import BaseModel
from common.models import Org, Profile

logger = logging.getLogger(__name__)

#: Cuantos pedidos admite una orden (el motor acepta el mismo tope).
MAXIMO_DE_PEDIDOS = 20
ESPERA_DE_LA_BUSQUEDA = 60
ESPERA_DEL_PEDIDO = 150
ESPERA_DE_LA_COMPROBACION = 40


class ActivacionDeOnu(BaseModel):
    PEDIDA = "pedida"
    EN_CURSO = "en_curso"
    ACTIVADA = "activada"
    YA_ESTABA = "ya_estaba"
    NO_ESPERA = "no_espera"
    FALLIDA = "fallida"
    NO_SALIO = "no_salio"
    POR_REVISAR = "por_revisar"
    ESTADOS = ((PEDIDA, "Pedida"), (EN_CURSO, "En curso"), (ACTIVADA, "Activada"),
               (YA_ESTABA, "Ya estaba activada"), (NO_ESPERA, "No aparece esperando"),
               (FALLIDA, "El proveedor la rechazó"), (NO_SALIO, "No salió"),
               (POR_REVISAR, "Por revisar"))
    EN_VUELO = (PEDIDA, EN_CURSO)

    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name="activaciones_de_onu")
    orden = models.ForeignKey("campo.OrdenTrabajo", on_delete=models.CASCADE,
                              related_name="activaciones_de_onu")
    serial = models.CharField(max_length=32)
    zona = models.CharField(max_length=80, blank=True, default="")
    vlan = models.PositiveIntegerField(null=True, blank=True)
    intento = models.PositiveSmallIntegerField(default=1)
    estado = models.CharField(max_length=20, choices=ESTADOS, default=PEDIDA)
    detalle = models.TextField(blank=True, default="")
    olt = models.CharField(max_length=20, blank=True, default="")
    placa = models.CharField(max_length=20, blank=True, default="")
    puerto = models.CharField(max_length=20, blank=True, default="")
    #  LA UBICACION EN SMARTOLT (26/11/2026): con la ONU activada, se le
    #  escriben las coordenadas del contrato. «guardada» / «no_guardada».
    ubicacion_en_smartolt = models.CharField(max_length=20, blank=True, default="")
    pedida_por = models.ForeignKey(Profile, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="activaciones_de_onu_pedidas")

    class Meta:
        db_table = "campo_activacion_de_onu"
        ordering = ("-created_at",)

    def como_dict(self) -> dict:
        return {"id": str(self.id), "serial": self.serial, "zona": self.zona, "vlan": self.vlan,
                "intento": self.intento, "estado": self.estado,
                "estado_etiqueta": self.get_estado_display(), "detalle": self.detalle,
                "olt": self.olt, "placa": self.placa, "puerto": self.puerto,
                "en_vuelo": self.estado in self.EN_VUELO,
                "pedida_en": self.created_at.isoformat() if self.created_at else None}


# =============================================================================
#  LO QUE SE LE PREGUNTA AL MOTOR
# =============================================================================
class NoSePuedeActivar(ValueError):
    """El pedido no se hace. El texto es para el tecnico."""


def _motor():
    base = (os.environ.get("MOTOR_URL", "") or "http://motor:5000").rstrip("/")
    cabeceras = {"Content-Type": "application/json"}
    token = os.environ.get("MOTOR_SERVICE_TOKEN")
    if token:
        cabeceras["X-Servicio-Token"] = token
    return base, cabeceras


def _llamar(org_id, ruta: str, cuerpo: dict, espera: int) -> dict | None:
    """Lo que contesto el motor, o None si no contesto algo legible."""
    from operaciones import areas_del_tenant

    tenant = areas_del_tenant.tenant_de(org_id)
    if not tenant:
        return None
    base, cabeceras = _motor()
    try:
        r = requests.post(f"{base}{ruta}", params={"tenant": tenant}, json=cuerpo,
                          headers=cabeceras, timeout=espera)
        datos = r.json() if r.content else {}
    except Exception as e:                                       # noqa: BLE001
        #  POR TIPO Y SIN `str(e)`: el mensaje de un cliente HTTP trae la URL.
        logger.warning("activar_onu: el motor no contesto (%s)", type(e).__name__)
        return None
    if not isinstance(datos, dict) or not datos.get("estado"):
        logger.warning("activar_onu: el motor respondio %s sin estado", r.status_code)
        return None
    return datos


def serial_limpio(valor) -> str:
    s = re.sub(r"\s+", "", str(valor or "")).upper()
    return s if re.fullmatch(r"[A-Z0-9:-]{6,32}", s) else ""


def _llano(texto) -> str:
    t = unicodedata.normalize("NFKD", str(texto or ""))
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return " ".join(re.sub(r"[^A-Z0-9]+", " ", t.upper()).split())


def sugerir_zona(barrio, zonas: list[str]) -> str:
    """La zona de la red que mas se parece al barrio del contrato, o "".

    Decision del usuario (26/11/2026): la sugiere el barrio y el tecnico la
    confirma. Por eso es una SUGERENCIA y puede quedar vacia: igual, la
    contiene, o comparte la mayoria de las palabras. No adivina con menos.
    """
    b = _llano(barrio)
    if not b or not zonas:
        return ""
    llanas = {z: _llano(z) for z in zonas}
    for z, l in llanas.items():
        if l == b:
            return z
    contienen = [z for z, l in llanas.items() if l and (l in b or b in l)]
    if len(contienen) == 1:
        return contienen[0]
    pb = set(b.split())
    puntajes = {z: len(pb & set(l.split())) / len(pb | set(l.split()))
                for z, l in llanas.items() if l}
    mejor = max(puntajes.values(), default=0.0)
    empatadas = [z for z, p in puntajes.items() if p == mejor]
    #  EMPATE NO ES SUGERENCIA: «Villa Adela» se parece igual a «VILLA ADELA 1»
    #  y a «VILLA ADELA 2», y elegir una seria adivinar. Elige el tecnico.
    return empatadas[0] if mejor >= 0.5 and len(empatadas) == 1 else ""


def _contrato_y_vlan(orden):
    """El contrato vigente de la orden y la VLAN de su servidor."""
    from campo.contrato import ContratoDeServicio, configuracion_de, vigente_de

    contrato = vigente_de(orden)
    if contrato is None or contrato.estado == ContratoDeServicio.ANULADO:
        raise NoSePuedeActivar("Primero crea el contrato: de ahí salen el nombre del "
                               "cliente y el servidor.")
    id_zona = (contrato.datos or {}).get("servidor", {}).get("id_zona")
    servidor = next((s for s in configuracion_de(orden.org)["servidores"]
                     if s.get("id_zona") == id_zona), None)
    return contrato, (servidor or {}).get("vlan"), (servidor or {}).get("nombre", "")


def buscar(orden, serial) -> dict:
    """SOLO LEE: si la ONU espera, en que puerto, la zona sugerida y la VLAN."""
    s = serial_limpio(serial)
    if not s:
        raise NoSePuedeActivar("Ese serial no tiene forma de serial.")
    contrato, vlan, servidor = _contrato_y_vlan(orden)
    datos = _llamar(orden.org_id, "/interno/onu/buscar", {"serial": s}, ESPERA_DE_LA_BUSQUEDA)
    if datos is None:
        raise NoSePuedeActivar("No se pudo preguntar por la ONU. Intenta de nuevo con señal.")
    zonas = [z for z in (datos.get("zonas") or []) if isinstance(z, str)]
    return {**{k: datos.get(k, "") for k in ("estado", "olt", "placa", "puerto", "tipo", "motivo")},
            "zonas": zonas,
            "zona_sugerida": sugerir_zona((contrato.datos or {}).get("cliente", {}).get("barrio"),
                                          zonas),
            "vlan": vlan, "servidor": servidor}


def ultima(orden) -> ActivacionDeOnu | None:
    return ActivacionDeOnu.objects.filter(orden=orden).order_by("-created_at").first()


def pedir(orden, profile, *, serial, zona) -> ActivacionDeOnu:
    """Pide la activacion. Valida aca lo que se puede validar sin red."""
    from campo.contrato import configuracion_de

    if not configuracion_de(orden.org).get("activar_onu"):
        raise NoSePuedeActivar("Tu empresa todavía no encendió «Activar ONU» desde la app.")
    s = serial_limpio(serial)
    if not s:
        raise NoSePuedeActivar("Ese serial no tiene forma de serial.")
    zona = " ".join(str(zona or "").split())[:80]
    if not zona:
        raise NoSePuedeActivar("Elige la zona de la ONU.")
    contrato, vlan, servidor = _contrato_y_vlan(orden)
    if not vlan:
        raise NoSePuedeActivar(f"Falta la VLAN del servidor «{servidor}» en Programación "
                               "(El contrato de instalación).")
    en_vuelo = (ActivacionDeOnu.objects.filter(orden=orden, estado__in=ActivacionDeOnu.EN_VUELO)
                .order_by("-created_at").first())
    if en_vuelo is not None:
        return en_vuelo
    intento = ActivacionDeOnu.objects.filter(orden=orden).count() + 1
    if intento > MAXIMO_DE_PEDIDOS:
        raise NoSePuedeActivar("Esta orden ya hizo demasiados pedidos. Que la oficina la mire.")
    a = ActivacionDeOnu.objects.create(org=orden.org, orden=orden, serial=s, zona=zona,
                                       vlan=int(vlan), intento=intento, pedida_por=profile)
    from campo.tasks import activar_onu_en_la_red

    try:
        activar_onu_en_la_red.delay(str(orden.org_id), str(a.id))
    except Exception as e:                                       # noqa: BLE001
        logger.warning("activar_onu: no se pudo encolar (%s)", type(e).__name__)
        a.estado, a.detalle = ActivacionDeOnu.NO_SALIO, "No se pudo encolar el pedido."
        a.save(update_fields=["estado", "detalle", "updated_at"])
    return a


_FINALES = {"activada": ActivacionDeOnu.ACTIVADA, "ya_estaba": ActivacionDeOnu.YA_ESTABA,
            "no_espera": ActivacionDeOnu.NO_ESPERA, "fallo": ActivacionDeOnu.FALLIDA,
            "bloqueado": ActivacionDeOnu.NO_SALIO, "datos_invalidos": ActivacionDeOnu.NO_SALIO,
            "sin_herramienta": ActivacionDeOnu.NO_SALIO,
            "no_se_pudo_comprobar": ActivacionDeOnu.NO_SALIO}


def _anotar(a: ActivacionDeOnu, datos: dict) -> None:
    a.estado = _FINALES.get(str(datos.get("estado")), ActivacionDeOnu.EN_CURSO)
    a.detalle = str(datos.get("motivo") or "")[:500]
    for campo in ("olt", "placa", "puerto"):
        if datos.get(campo):
            setattr(a, campo, str(datos[campo])[:20])
    a.save(update_fields=["estado", "detalle", "olt", "placa", "puerto", "updated_at"])
    if a.estado == ActivacionDeOnu.ACTIVADA:
        ubicacion_en_smartolt(a)


def ejecutar(a: ActivacionDeOnu) -> None:
    """La vuelta que pide. Si el motor no contesta, NO es «fallo»: pudo haber
    salido, asi que queda en curso y la siguiente vuelta comprueba."""
    contrato, _, _ = _contrato_y_vlan(a.orden)
    cliente = (contrato.datos or {}).get("cliente", {})
    nombre = f"{cliente.get('nombre', '')} {cliente.get('apellido', '')}".strip()
    actor = (a.pedida_por.user.email if a.pedida_por and a.pedida_por.user_id else "tecnico")
    datos = _llamar(a.org_id, f"/interno/orden/{a.orden_id}/activar-onu",
                    {"actor": actor, "intento": a.intento,
                     "datos": {"serial": a.serial, "zona": a.zona, "vlan": a.vlan,
                               "nombre": nombre}}, ESPERA_DEL_PEDIDO)
    if datos is None:
        a.estado, a.detalle = ActivacionDeOnu.EN_CURSO, "Se pidió y no se sabe todavía cómo quedó."
        a.save(update_fields=["estado", "detalle", "updated_at"])
        return
    _anotar(a, datos)


def comprobar(a: ActivacionDeOnu) -> None:
    datos = _llamar(a.org_id, "/interno/onu/comprobar", {"serial": a.serial},
                    ESPERA_DE_LA_COMPROBACION)
    if datos and datos.get("estado") == "activada":
        a.estado, a.detalle = ActivacionDeOnu.ACTIVADA, ""
        a.save(update_fields=["estado", "detalle", "updated_at"])
        ubicacion_en_smartolt(a)


def rendirse(a: ActivacionDeOnu) -> None:
    a.estado = ActivacionDeOnu.POR_REVISAR
    a.detalle = ("No se pudo confirmar si la ONU quedó activada. Que la oficina la mire en "
                 "SmartOLT antes de volver a pedirla.")
    a.save(update_fields=["estado", "detalle", "updated_at"])


def ubicacion_en_smartolt(a: "ActivacionDeOnu") -> str:
    """Con la ONU ACTIVADA, sus coordenadas en SmartOLT: las del contrato --las
    que el tecnico confirmo o corrigio en el mapa-- (el usuario, 26/11/2026:
    «que las mismas coordenadas tambien las ponga en SmartOLT»).

    Va por el camino ya medido de «guardar ubicacion» (`ubicacion_al_isp`),
    identificando la ONU SOLO por su serial: escribe en SmartOLT y no en el
    proveedor de clientes, que ya las recibio al crear la instalacion. Puerta
    humana de quien activo la ONU. Nunca levanta: activar la ONU no se rompe
    por esto. Devuelve como quedo («guardada», «no_guardada» o «»).
    """
    try:
        from campo.contrato import vigente_de
        from campo.services import ubicacion_al_isp

        if a.estado != ActivacionDeOnu.ACTIVADA or a.ubicacion_en_smartolt == "guardada":
            return a.ubicacion_en_smartolt
        contrato = vigente_de(a.orden)
        gps = (contrato.datos or {}).get("gps") if contrato is not None else None
        if not isinstance(gps, dict) or gps.get("lat") in (None, "") or gps.get("lng") in (None, ""):
            return ""
        r = ubicacion_al_isp.guardar_ubicacion(
            a.orden, latitud=gps.get("lat"), longitud=gps.get("lng"), profile=a.pedida_por,
            identificadores={"sn_onu": a.serial})
        a.ubicacion_en_smartolt = "guardada" if r.get("guardada") else "no_guardada"
        a.save(update_fields=["ubicacion_en_smartolt", "updated_at"])
        return a.ubicacion_en_smartolt
    except Exception as e:                                       # noqa: BLE001
        logger.warning("activar_onu: no se pudo guardar la ubicacion en SmartOLT (%s)",
                       type(e).__name__)
        return ""
