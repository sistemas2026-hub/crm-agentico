# -*- coding: utf-8 -*-
"""
================================================================================
 QUE FOTO FRENA  --  17/11/2026
================================================================================
Cuenta, por requisito de la plantilla, cuantas veces la mirada a esa foto
levanto ATENCION, y cuantas ordenes estan HOY frenadas solo por eso. No
escribe nada: ni un evento, ni una transicion, ni una llamada al ISP.

POR QUE EXISTE
--------------
La OT que motivo esto salio con siete puntos en verde y dos interrogantes, y
uno de los dos era la foto obligatoria «Dano encontrado». Esa foto existe
para mostrar el elemento roto, y la regla 11 de `nucleo/canales/vision.py`
pide ATENCION cuando ve «material deteriorado». La foto que documenta el
problema es la que frena el cierre del arreglo.

El arreglo --una marca en la plantilla, como la que ya existe para
`es_captura`-- cuesta unas dos horas mas el trabajo de marcar cada plantilla.
Antes de gastarlas hay que saber cuantas ordenes frena de verdad: CLAUDE.md
§10, «medir antes de decidir». Una vista no es una medicion.

LO QUE MIDE, Y LO QUE NO PUEDE MEDIR
-------------------------------------
Parte 1, LA TASA, sobre todo el rango de dias: de las veces que se miro la
foto de un requisito, cuantas levantaron atencion. La tasa es lo que decide,
no el conteo: 23 de 25 es estructural --la foto levanta atencion por existir--
y 3 de 80 es un hallazgo real que hay que seguir viendo.

Parte 2, EL IMPACTO DE HOY, solo sobre las ordenes que siguen esperando:
cuantas quedarian en «se puede cerrar» si ese requisito dejara de frenar.
`RC.revisar` solo contesta por una orden completada en campo y sin validar
(`RC.aplica`), asi que de una orden ya cerrada no se puede saber el veredicto
que tuvo. Por eso la parte 2 es un piso, nunca el total historico.

SIN DATOS DEL CLIENTE, Y SIN LA PROSA DEL MODELO
-------------------------------------------------
Sale el titulo del requisito --que lo escribio la empresa en su plantilla, no
el cliente-- el numero de orden, y conteos. NUNCA el texto que el modelo
escribio mirando la foto: esa prosa sobrevive a `redactar()` cuando trae un
nombre propio o una direccion leida de la imagen, y esta salida se pega en un
chat. Es la leccion que el revisor de PII dejo en `por_que_no_cerro` el
12/11/2026, y aca no hay motivo para repetirla: el diagnostico no la necesita.

POR QUE ES SEGURO CORRERLO EN PRODUCCION
-----------------------------------------
`RC.revisar` solo lee la base. No llama al modelo ni a ninguna API externa, y
no es una opinion: Programacion lo llama en cada refresco, cada 15 segundos,
con cada supervisor que tenga la pantalla abierta. Si saliera a la red, esa
pantalla seria imposible. El cotejo con el ticket, que si usa el modelo, lo
calcula `tasks.revisar_el_cierre_ya` una vez y lo guarda; esto solo lo lee.

Uso, dentro del contenedor del backend (desde /app):
  python manage.py que_foto_frena --org <uuid>
  python manage.py que_foto_frena --org <uuid> --dias 90
================================================================================
"""
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from common.models import Org
from common.tasks import set_rls_context


def _ultimo_por_evidencia(analisis) -> list:
    """La ULTIMA mirada de cada foto, no todas las filas.

    MISMO CRITERIO QUE EL PUNTO QUE SE ESTA MIDIENDO (`inspeccion_visual`,
    nota del 11/11/2026, OT #200). La tabla es append-only: cada intento suma
    una fila, y contarlas todas haria que un intento fallido pesara para
    siempre aunque el siguiente hubiera leido la foto bien. Un instrumento
    que cuenta distinto que el camino que mide, mide otra cosa.
    """
    ultimo = {}
    for a in analisis:
        ultimo[a.evidencia_id] = a
    return list(ultimo.values())


def _titulos_de(orden) -> dict:
    """{requisito_id: titulo} de la plantilla de ESTA orden, o {}."""
    version = getattr(orden, "tipo_trabajo_version", None)
    esquema = (getattr(version, "esquema", None) or {}) if version else {}
    salida = {}
    for e in esquema.get("evidencias") or []:
        if isinstance(e, dict) and e.get("id"):
            salida[str(e["id"])] = str(e.get("titulo") or "").strip() or "(sin título)"
    return salida


def _clasificar(analisis) -> dict:
    """Por que estaria en «?» el punto de fotos, con el criterio de hoy.

    NO SE REIMPLEMENTA LA REGLA: se llaman las mismas funciones que usa
    `inspeccion_visual.punto_de_la_revision` (`es_de_catalogo`,
    `muestra_lo_pedido`, `pide_atencion`), y en el mismo orden, porque el
    orden importa: una foto de catalogo se saca de `con_atencion`, y una que
    muestra otra cosa solo cuenta si no levanto atencion.
    """
    from campo.tasks import es_de_catalogo, muestra_lo_pedido

    mirados = [a for a in analisis if a.texto]
    sin_mirar = [a for a in analisis if not a.texto]
    con_atencion = [a for a in mirados if a.pide_atencion]
    otra_cosa = [a for a in mirados
                 if a not in con_atencion
                 and muestra_lo_pedido(a.texto or "") is False]
    de_catalogo = [a for a in mirados if es_de_catalogo(a.texto or "") is True]
    con_atencion = [a for a in con_atencion if a not in de_catalogo]
    return {"mirados": mirados, "sin_mirar": sin_mirar,
            "con_atencion": con_atencion, "otra_cosa": otra_cosa,
            "de_catalogo": de_catalogo}


class Command(BaseCommand):
    help = ("Cuenta que foto de la plantilla levanta ATENCION y cuantas "
            "ordenes frena hoy. Solo lectura.")

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True,
                            help="UUID de la empresa.")
        parser.add_argument("--dias", type=int, default=60,
                            help="Cuantos dias hacia atras mira la tasa "
                                 "(por defecto 60).")

    def handle(self, *args, **opciones):
        from datetime import timedelta

        from campo import revision_del_cierre as RC
        from campo.inspeccion_visual import CLAVE as CLAVE_FOTOS
        from campo.models import AnalisisDeEvidencia, OrdenTrabajo

        try:
            org = Org.objects.get(pk=opciones["org"])
        except (Org.DoesNotExist, ValueError, TypeError) as e:
            raise CommandError(f"No se encontro esa empresa ({type(e).__name__})")
        set_rls_context(org.id)

        dias = max(1, opciones["dias"])
        desde = timezone.now() - timedelta(days=dias)

        # ------------------------------------------------------------------
        #  PARTE 1  --  LA TASA
        # ------------------------------------------------------------------
        filas = list(AnalisisDeEvidencia.objects.filter(
            org=org, created_at__gte=desde,
        ).select_related(
            "evidencia",
            "evidencia__orden_trabajo",
            "evidencia__orden_trabajo__tipo_trabajo_version",
        ).order_by("created_at"))

        #  Por orden y vuelta, porque asi lo agrupa el punto que se mide: una
        #  orden devuelta y rehecha tiene otras fotos, y el analisis de la
        #  vuelta anterior no dice nada de esta.
        por_orden = {}
        for a in filas:
            ev = a.evidencia
            orden = getattr(ev, "orden_trabajo", None)
            if orden is None:
                continue
            por_orden.setdefault((orden.id, a.vuelta), []).append(a)

        titulos_cache = {}
        conteo = {}      # (titulo, requisito_id) -> [miradas, con_atencion]
        for (orden_id, _vuelta), analisis in por_orden.items():
            orden = analisis[0].evidencia.orden_trabajo
            if orden.id not in titulos_cache:
                titulos_cache[orden.id] = _titulos_de(orden)
            titulos = titulos_cache[orden.id]
            c = _clasificar(_ultimo_por_evidencia(analisis))
            atencion = {a.evidencia_id for a in c["con_atencion"]}
            for a in c["mirados"]:
                req = str(getattr(a.evidencia, "requisito_id", "") or "(sin id)")
                clave = (titulos.get(req, req), req)
                par = conteo.setdefault(clave, [0, 0])
                par[0] += 1
                if a.evidencia_id in atencion:
                    par[1] += 1

        self.stdout.write("")
        self.stdout.write(f"QUE FOTO LEVANTA ATENCION  --  ultimos {dias} dias")
        self.stdout.write("=" * 72)
        if not conteo:
            self.stdout.write("No hay ninguna foto mirada en ese rango. "
                              "Probá con --dias mas alto.")
            return
        ordenado = sorted(conteo.items(), key=lambda kv: (-kv[1][1], -kv[1][0]))
        self.stdout.write(f"{'foto de la plantilla':<42}{'atención':>10}"
                          f"{'miradas':>9}{'tasa':>7}")
        self.stdout.write("-" * 72)
        for (titulo, _req), (miradas, atencion) in ordenado:
            tasa = f"{(100 * atencion / miradas):.0f}%" if miradas else "-"
            self.stdout.write(f"{titulo[:41]:<42}{atencion:>10}{miradas:>9}"
                              f"{tasa:>7}")
        self.stdout.write("")
        self.stdout.write("  La TASA es lo que decide, no el conteo: una foto que")
        self.stdout.write("  levanta atención casi siempre, la levanta por existir.")

        # ------------------------------------------------------------------
        #  PARTE 2  --  EL IMPACTO DE HOY
        # ------------------------------------------------------------------
        esperando = list(OrdenTrabajo.objects.filter(
            org=org,
            estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO,
            estado_validacion__in=(OrdenTrabajo.PENDIENTE,
                                   OrdenTrabajo.REQUIERE_REVISION),
        ).select_related("tipo_trabajo_version").order_by("-numero"))

        pendientes = RC.pendientes_de_medir(org)

        destraba = {}         # titulo -> [numeros de orden]
        frenadas_igual = {}   # titulo -> [numeros de orden]
        otros_motivos = 0
        for orden in esperando:
            try:
                rev = RC.revisar(orden, pendientes=pendientes)
            except Exception as e:                               # noqa: BLE001
                self.stdout.write(f"  OT #{orden.numero}: no se pudo revisar "
                                  f"({type(e).__name__})")
                continue
            if not rev or rev["veredicto"] != RC.REVISAR:
                continue
            interrogantes = {p["clave"] for p in rev["puntos"]
                             if p["ok"] is None}
            if CLAVE_FOTOS not in interrogantes:
                continue
            analisis = list(AnalisisDeEvidencia.objects.filter(
                org=org, evidencia__orden_trabajo=orden, vuelta=orden.vuelta,
            ).select_related("evidencia").order_by("created_at"))
            c = _clasificar(_ultimo_por_evidencia(analisis))
            if not c["con_atencion"]:
                #  El punto esta en «?» por otra cosa --una foto que no se
                #  pudo mirar, una de catalogo, una que muestra otra cosa--.
                #  Sacar la atencion no lo destraba.
                otros_motivos += 1
                continue
            if c["sin_mirar"] or c["otra_cosa"] or c["de_catalogo"]:
                otros_motivos += 1
                continue
            #  El punto de fotos esta en «?» SOLO por atencion. Si ademas hay
            #  otro punto en «?», la orden sigue frenada aunque la foto deje
            #  de frenar: se cuenta aparte, porque sumarla seria prometer un
            #  cierre que no va a pasar.
            solo_las_fotos = (interrogantes == {CLAVE_FOTOS})
            titulos = _titulos_de(orden)
            for a in c["con_atencion"]:
                req = str(getattr(a.evidencia, "requisito_id", "") or "(sin id)")
                titulo = titulos.get(req, req)
                destino = destraba if solo_las_fotos else frenadas_igual
                destino.setdefault(titulo, []).append(orden.numero)

        self.stdout.write("")
        self.stdout.write(f"QUE SE DESTRABA HOY  --  {len(esperando)} órdenes "
                          f"esperando")
        self.stdout.write("=" * 72)
        if not destraba and not frenadas_igual:
            self.stdout.write("Ninguna orden está frenada hoy por una foto que "
                              "pida atención.")
        for titulo, numeros in sorted(destraba.items(),
                                      key=lambda kv: -len(kv[1])):
            ots = ", ".join(f"#{n}" for n in sorted(set(numeros))[:12])
            self.stdout.write(f"  {len(set(numeros))} se cerrarían solas si "
                              f"«{titulo}» dejara de frenar")
            self.stdout.write(f"      {ots}")
        for titulo, numeros in sorted(frenadas_igual.items(),
                                      key=lambda kv: -len(kv[1])):
            self.stdout.write(f"  {len(set(numeros))} tienen «{titulo}» en "
                              f"atención pero quedan frenadas por otro punto")
        if otros_motivos:
            self.stdout.write(f"  {otros_motivos} están frenadas por las fotos, "
                              f"pero por otra cosa (no se pudo mirar, "
                              f"catálogo, muestra otra cosa)")
        self.stdout.write("")
        self.stdout.write("  Esta parte solo ve las órdenes que SIGUEN esperando.")
        self.stdout.write("  Una ya cerrada a mano no deja ver el veredicto que")
        self.stdout.write("  tuvo, así que este número es un piso, no el total.")
        self.stdout.write("")
