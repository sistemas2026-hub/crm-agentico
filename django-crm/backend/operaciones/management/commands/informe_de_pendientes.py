"""
Lista, sin escribir nada, las lecturas de ticket pendientes del Supervisor
NOC: en qué grupo cayó cada una, qué midió el equipo, cómo está el caso, por
qué se queda, cuántas veces se leyó y qué descartó el modelo.

    python manage.py informe_de_pendientes --org <id>

POR QUÉ EXISTE
--------------
El 17/10/2026 la vuelta de las :07 no pasó ninguno de 64 pendientes, y el log
solo dice cuántos por motivo. Para decidir si una regla es demasiado estricta
hace falta ver los tickets uno por uno. ESO LO CALCULA EL CÓDIGO, con las
reglas reales de 'paso_a_despacho': el informe es para que una persona
decida, no para que adivine sumando a mano.

SIN DATOS DEL CLIENTE. Va el número del ticket y lo que el Supervisor
escribió, tapado: nunca el asunto, la descripción, el nombre ni el teléfono.
Es una salida pensada para pegarse en una conversación.

EL CONTEXTO RLS SE FIJA ACÁ, como en 'propuestas_fuera_de_area': un comando
no pasa por el middleware, y sin él las tablas devuelven 0 filas sin error.

LAS CORRECCIONES DEL USUARIO (18/10/2026). "pasan hoy" usa lo que esté
delegado; si las correcciones no lo están, la columna "con correcciones" dice
cuáles pasarían con ellas y por cuál. Es la sombra del ciclo, caso por caso.
"""

import re
import zoneinfo
from collections import Counter

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from common.models import Org
from common.tasks import set_rls_context
from operaciones import diagnostico_de_ticket as dxt
from operaciones import lectura_de_ticket, tareas_delegadas
from operaciones import paso_a_despacho as pad
from operaciones.models import PropuestaSupervisor
from operaciones.razonamiento_modelos import FuenteRazonamiento, RazonamientoSupervisor

_DIJO = re.compile(r"'(\w+)' con un valor que no esta declarado \(dijo '([^']*)'\)")


def _lecturas(propuesta):
    """
    Cuántas veces el modelo leyó este ticket, y qué descartó la última vez.

    El descarte es lo que 'cerebro.validar' tiró por no estar en la lista
    (por ejemplo "grupo='Obra_de_red'"): es la diferencia entre "el modelo no
    supo" y "el modelo lo dijo con otra forma", y la segunda se arregla sin
    tocar las reglas. El texto ya viene sin identificadores, lo sanea
    'razonamiento.registrar'.
    """
    filas = (RazonamientoSupervisor.objects
             .filter(propuesta=propuesta,
                     fuente=FuenteRazonamiento.LECTURA_TICKET)
             .order_by("-registrado_en", "-created_at"))
    cuantas = filas.count()
    ultima = filas.first()
    if ultima is None or not ultima.descartes:
        return cuantas, "-"
    partes = []
    for d in ultima.descartes[:3]:
        m = _DIJO.search(str(d))
        partes.append(f"{m.group(1)}='{m.group(2)}'" if m else str(d)[:40])
    return cuantas, "; ".join(partes)[:70]


_GRUPO = {
    pad.FALLA_DE_SERVICIO: "falla",
    pad.TRABAJO_PEDIDO: "trabajo",
    pad.OBRA_DE_RED: "obra",
    pad.NADA_LO_MIDE: "nada_mide",
    pad.NI_CLIENTE_NI_RED: "ni_cli_red",
}

#  De qué frase del motivo del caso sale cada etiqueta corta.
_CASO = (
    ("cerrado en Dexter", "cerrado Dexter"),
    ("no esta abierto en Dexter", "rechazado/duplicado"),
    ("cerrado en WispHub", "cerrado WispHub"),
    ("no figura en curso", "no en curso WispHub"),
    ("no consta cuando", "sin copia WispHub"),
    ("sin actualizarse", "copia vieja"),
    ("fallo", "lectura fallida"),
    ("inactivo", "inactivo/fusionado"),
)


def _caso_corto(porque, caso):
    if porque is None:
        return "abierto"
    for frase, etiqueta in _CASO:
        if frase in porque:
            if etiqueta == "cerrado Dexter":
                cuando = getattr(caso, "resolved_at", None) or getattr(
                    caso, "closed_on", None)
                if cuando:
                    dias = (timezone.now().date() - cuando.date()).days
                    return f"cerrado Dexter {dias}d"
            return etiqueta
    return "no pasa"


def _medicion_corta(m):
    if not m:
        return "sin medir"
    estado = m.get("estado") or "?"
    if estado == "en_linea":
        dbm = m.get("senal_dbm")
        nivel = f" {dbm}dBm" if isinstance(dbm, (int, float)) else ""
        return f"en linea/{m.get('senal') or 'sin_dato'}{nivel}"
    if estado == "caido":
        return f"caido/{m.get('causa_caida') or 'sin causa'}"
    if estado == pad.ESTADO_NO_RECONOCIDO:
        return "no entendida"
    if pad.es_un_error_guardado(m):
        return "error del motor"
    return "no se pudo medir"


def _por_que_corto(d, grupo, medicion):
    if d.pasa:
        return "PASA"
    if d.puerta == pad.PUERTA_CASO:
        return "caso"
    if not grupo:
        return "sin grupo"
    if grupo in (pad.NADA_LO_MIDE, pad.NI_CLIENTE_NI_RED):
        return "siempre persona"
    if not medicion:
        return "sin medir"
    if pad.es_un_error_guardado(medicion):
        return "error del motor"
    if medicion.get("estado") == pad.ESTADO_NO_RECONOCIDO:
        return "no entendida"
    if medicion.get("estado") == "en_linea":
        return "en rango" if medicion.get("senal") == "buena" else "sin nivel"
    if medicion.get("estado") == "caido":
        causa = medicion.get("causa_caida")
        return {"fibra": "LOS", "sin_energia": "sin energia",
                "otra": "caido otra causa"}.get(causa, "caido sin datos")
    return "no se pudo medir, reintenta"


def _lectura_corta(lectura):
    """Con que version de la lectura se decidio: 'v1', 'v2', o 'v2+corr' si se
    leyo con las instrucciones de las correcciones del usuario."""
    if not lectura:
        return "-"
    version = lectura.get("version")
    if not (isinstance(version, int) and version >= dxt.VERSION_DE_LA_LECTURA):
        return "v1"
    if lectura.get("instrucciones") == dxt.CON_LAS_CORRECCIONES:
        return f"v{version}+corr"
    return f"v{version}"


def _remedida_corta(medicion, zona) -> str:
    """Cuantas veces se re-midio, y la ultima re-medicion que dijo algo: la
    serie que decide la correccion 2 y que la columna 'medicion' no muestra
    --esa es la medicion que decide sin las correcciones--."""
    from django.utils.dateparse import parse_datetime

    m = medicion or {}
    veces = m.get("remedida_veces")
    veces = veces if isinstance(veces, int) and veces > 0 else 0
    serie = [h for h in (m.get("historial") or []) if isinstance(h, dict)]
    if not veces and not serie:
        return "-"
    texto = f"{veces}x"
    if serie:
        ultima = serie[-1]
        if ultima.get("estado") == "caido":
            dato = f"caido/{ultima.get('causa_caida') or 'sin causa'}"
        else:
            dbm = ultima.get("senal_dbm")
            nivel = f" {dbm}" if isinstance(dbm, (int, float)) else ""
            dato = f"{ultima.get('senal') or 'sin_dato'}{nivel}"
        cuando = parse_datetime(str(ultima.get("observado_en") or ""))
        hora = cuando.astimezone(zona).strftime("%d/%m %H:%M") if cuando else "?"
        texto += f" · {dato} · {hora}"
    return texto


def _hipotesis(propuesta):
    for pieza in reversed(propuesta.evidencia or []):
        if not isinstance(pieza, dict) or pieza.get("fuente") != dxt.FUENTE:
            continue
        dato = str(pieza.get("dato") or "")
        if dato.startswith(dxt.ETIQUETA_LECTURA):
            texto = dato[len(dxt.ETIQUETA_LECTURA):]
            texto = texto.split(" (confianza ")[0]
            return lectura_de_ticket.tapar(texto)[:70]
    return "(sin hipotesis)"


class Command(BaseCommand):
    help = ("Lista las lecturas de ticket pendientes del Supervisor NOC y qué "
            "pasaría con cada cambio de regla. No escribe nada.")

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True,
                            help="id (UUID) de la organización")

    def handle(self, *args, **options):
        try:
            org = Org.objects.get(pk=options["org"])
        except (Org.DoesNotExist, ValueError, ValidationError):
            raise CommandError("No existe una organización con ese id.")
        set_rls_context(org.id)
        ahora = timezone.now()
        try:
            zona = zoneinfo.ZoneInfo(getattr(org, "timezone", "") or "UTC")
        except Exception:                                        # noqa: BLE001
            zona = zoneinfo.ZoneInfo("UTC")
        try:
            con = bool(tareas_delegadas.esta_delegada(org, pad.TAREA_CORRECCIONES))
        except Exception:                                        # noqa: BLE001
            con = False

        pendientes = (PropuestaSupervisor.objects
                      .filter(org=org, estado=PropuestaSupervisor.PROPUESTA,
                              tipo_senal=PropuestaSupervisor.TICKET_SIN_DIAGNOSTICO,
                              origen_tipo="case")
                      .order_by("created_at"))

        filas, motivos, casos, pasarian = [], Counter(), Counter(), Counter()
        pasan = 0
        for p in pendientes:
            caso = pad.caso_de(p)
            lectura = pad._ultima_lectura_con_grupo(p) or {}
            grupo = str(lectura.get("grupo") or "")
            conf = str(lectura.get(pad.CONFIANZA_DEL_GRUPO) or "-")
            medicion = pad.ultima_medicion(p)
            d = pad.evaluar(p, ahora, correcciones=con)
            por_que = _por_que_corto(d, grupo, medicion)
            sombra = "-"
            if not con and not d.pasa and d.puerta != pad.PUERTA_CASO:
                d2 = pad.evaluar(p, ahora, correcciones=True)
                if d2.pasa:
                    sombra = f"PASA ({d2.regla or '?'})"
                    pasarian[d2.regla or "?"] += 1
            caso_corto = _caso_corto(
                pad.por_que_el_caso_no_puede_pasar(caso, ahora), caso)
            pasan += d.pasa
            motivos[por_que] += 1
            casos[caso_corto.split(" ")[0] + (" Dexter" if "Dexter" in caso_corto else "")] += 1
            edad = (ahora - p.created_at).days
            leidas, descarte = _lecturas(p)
            filas.append((
                getattr(caso, "external_ticket_id", "") or "?",
                f"{edad}d", _GRUPO.get(grupo, "sin grupo"), conf,
                caso_corto, _medicion_corta(medicion),
                _remedida_corta(medicion, zona), por_que, sombra,
                str(leidas), _lectura_corta(lectura), descarte, _hipotesis(p)))

        cab = ("ticket", "edad", "grupo", "conf", "caso", "medicion",
               "re-medida", "por que se queda", "con correcciones", "leidas",
               "lectura", "descarte del modelo", "hipotesis (tapada)")
        anchos = [max(len(str(f[i])) for f in [cab, *filas]) for i in range(len(cab))]
        linea = lambda f: "  ".join(str(v).ljust(a) for v, a in zip(f, anchos))  # noqa: E731
        self.stdout.write(linea(cab))
        self.stdout.write("-" * (sum(anchos) + 2 * (len(cab) - 1)))
        for f in filas:
            self.stdout.write(linea(f))
        self.stdout.write("")
        self.stdout.write(f"pendientes={len(filas)} · pasan hoy={pasan}")
        self.stdout.write(
            "correcciones: encendidas" if con else
            f"correcciones: en sombra · pasarian con ellas={sum(pasarian.values())} "
            f"{dict(pasarian)}")
        self.stdout.write(f"por que se quedan: {dict(motivos)}")
        self.stdout.write(f"casos: {dict(casos)}")
