# -*- coding: utf-8 -*-
"""
================================================================================
 ¿LA COMPRESION ES LA QUE DEJA CIEGO AL ANALISIS?  --  06/11/2026
================================================================================
El usuario, mirando la revision de una orden: fotos marcadas "no es lo que se
pidio" que SI mostraban lo pedido. Cuatro de cuatro.

LA HIPOTESIS, Y POR QUE NO ALCANZA CON TENERLA
-----------------------------------------------
La foto que el modelo mira no es la que tomo el tecnico. Pasa por DOS
recompresiones encadenadas:

    la app del tecnico   imageQuality 85, max 1920 px
    el motor, al mirarla 1600 px, calidad 80

Para leer la etiqueta de un router eso da igual. Para leer la pantalla LCD de
un medidor optico --numeros chicos, poco contraste, reflejos-- cada paso
cuesta. Pero es una hipotesis: en otras fotos el modelo SI leyo
"1550 nm, -2.10 dBm", asi que estamos en el margen y no se sabe de que lado.

QUE HACE ESTE COMANDO
---------------------
Analiza LA MISMA evidencia dos veces, cambiando solo la compresion:

    como hoy    1600 px / calidad 80
    sin degradar 2048 px / calidad 92

Mismo modelo, misma instruccion de la plantilla, misma foto. Si la segunda la
lee y la primera no, la hipotesis esta demostrada y el arreglo son dos
numeros. Si las dos fallan, el problema es la foto o la instruccion, y
recomprimir menos solo gastaria tokens.

LA FOTO NO SE MUEVE DE PRODUCCION. Se lee donde esta y se manda al mismo
motor de siempre, que es el unico que tiene la credencial del proveedor. No
se descarga, no se copia, no se imprime: de la imagen solo salen los dos
textos que el modelo devuelve.

CUESTA DOS LLAMADAS AL MODELO, que se cobran. Por eso pide la evidencia a
mano en vez de barrer todas.

COMO SE USA

    python manage.py comparar_calidad_vision --org <uuid> --evidencia <uuid>
    python manage.py comparar_calidad_vision --org <uuid> --ultima-con-atencion

Para ver candidatas:

    python manage.py comparar_calidad_vision --org <uuid> --listar
================================================================================
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

#: Lo que se compara. El primero tiene que ser el de hoy, para que la primera
#: linea de la salida sea siempre "lo que esta pasando ahora".
VARIANTES = (
    ("como hoy", 0, 0),          # 0 = los de `media.py`: 1600 / 80
    ("sin degradar", 2048, 92),
)


class Command(BaseCommand):
    help = "Analiza una evidencia con dos calidades y compara que ve el modelo."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True)
        parser.add_argument("--evidencia", default="")
        parser.add_argument("--ultima-con-atencion", action="store_true")
        parser.add_argument("--listar", action="store_true")

    def handle(self, *args, **options):
        from django.core.exceptions import ValidationError

        from campo.analisis_de_evidencia import AnalisisDeEvidencia
        from campo.models import EvidenciaTrabajo
        from common.models import Org

        try:
            org = Org.objects.get(pk=options["org"])
        except (Org.DoesNotExist, ValidationError, ValueError, TypeError):
            raise CommandError(
                f"{options['org']!r} no es una organizacion valida. Para verlas:\n"
                f"  python manage.py shell -c \"from common.models import Org; "
                f"[print(o.id, o.name) for o in Org.objects.all()]\"")

        if options["listar"]:
            filas = (AnalisisDeEvidencia.objects
                     .filter(org=org, pide_atencion=True)
                     .order_by("-created_at")[:15])
            if not filas:
                self.stdout.write("No hay analisis que pidan atencion.")
                return
            self.stdout.write("Evidencias cuyo analisis pidio atencion:\n")
            for f in filas:
                self.stdout.write(
                    f"  {f.evidencia_id}  {f.created_at:%Y-%m-%d %H:%M}")
            return

        if options["ultima_con_atencion"]:
            fila = (AnalisisDeEvidencia.objects
                    .filter(org=org, pide_atencion=True)
                    .order_by("-created_at").first())
            if fila is None:
                raise CommandError(
                    "no hay ningun analisis que pida atencion en esta empresa")
            evidencia_id = fila.evidencia_id
        elif options["evidencia"]:
            evidencia_id = options["evidencia"]
        else:
            raise CommandError(
                "falta --evidencia <uuid>, --ultima-con-atencion o --listar")

        try:
            evidencia = EvidenciaTrabajo.objects.select_related(
                "orden_trabajo").get(pk=evidencia_id, org=org)
        except (EvidenciaTrabajo.DoesNotExist, ValidationError, ValueError):
            raise CommandError(f"no existe la evidencia {evidencia_id!r} en esta "
                               f"empresa")

        self._comparar(org, evidencia)

    # ------------------------------------------------------------------
    def _comparar(self, org, evidencia):
        import requests

        from campo import inspeccion_visual as IV
        from operaciones.areas_del_tenant import tenant_de

        tenant = tenant_de(org.id)
        if not tenant:
            raise CommandError("esta empresa no esta conectada a ningun tenant")
        if not IV._esta_habilitado(tenant):
            raise CommandError(
                "esta empresa no tiene habilitado que se miren las fotos: "
                "nada que comparar")

        contenido = IV._bytes_de(evidencia)
        if contenido is None:
            raise CommandError("no se pudo leer el archivo de la evidencia")
        motivo = IV.se_puede_mirar(contenido)
        if motivo:
            raise CommandError(motivo)

        pie = IV.que_tenia_que_mostrar(evidencia)
        base, cabeceras = IV._motor()

        self.stdout.write(f"\n  evidencia : {evidencia.id}")
        self.stdout.write(f"  requisito : {evidencia.requisito_id}")
        self.stdout.write(f"  original  : {len(contenido) // 1024} KB")
        self.stdout.write(f"  se pidio  : {pie or '(la plantilla no lo dice)'}")
        self.stdout.write("")

        textos = {}
        for etiqueta, lado, calidad in VARIANTES:
            datos = {"pie": pie}
            if lado:
                datos["lado"] = str(lado)
            if calidad:
                datos["calidad"] = str(calidad)
            try:
                r = requests.post(
                    f"{base}/interno/vision/analizar-evidencia",
                    params={"tenant": tenant},
                    files={"imagen": ("evidencia.jpg", contenido, "image/jpeg")},
                    data=datos, headers=cabeceras,
                    timeout=IV.TIMEOUT_SEGUNDOS)
                cuerpo = r.json() if r.content else {}
            except Exception as e:                            # noqa: BLE001
                self.stdout.write(f"  [{etiqueta}] no se pudo: {type(e).__name__}")
                continue
            if not isinstance(cuerpo, dict):
                cuerpo = {}
            texto = str(cuerpo.get("texto") or "").strip()
            textos[etiqueta] = texto
            medida = f"{lado or 1600} px / calidad {calidad or 80}"
            self.stdout.write(self.style.MIGRATE_HEADING(
                f"  ===== {etiqueta}  ({medida}) ====="))
            self.stdout.write(f"  estado : {cuerpo.get('estado')}  "
                              f"tokens: {cuerpo.get('tokens')}  "
                              f"segundos: {cuerpo.get('segundos')}")
            if cuerpo.get("motivo"):
                self.stdout.write(f"  motivo : {cuerpo['motivo']}")
            for linea in (texto or "(sin texto)").splitlines():
                self.stdout.write(f"    {linea}")
            self.stdout.write("")

        #  EL VEREDICTO, QUE ES LO QUE SE VINO A BUSCAR. Se mira la marca que
        #  el propio analisis escribe --«MUESTRA: si/no»-- y no el parecido de
        #  los textos: dos redacciones distintas pueden decir lo mismo.
        #  SE REUSA EL PARSER DE PRODUCCION, no uno nuevo  --  06/11/2026
        #
        #  La primera version de este comando tenia el suyo, binario, y leia
        #  "MUESTRA: no se sabe" como un "no". El resultado fue un veredicto
        #  falso --"resultado raro"-- en la primera medicion de verdad.
        #
        #  `tasks.muestra_lo_pedido` ya resuelve los TRES valores, y su
        #  comentario advierte exactamente este error: «"no se sabe" ANTES que
        #  "no": empieza igual, y mirar "no" primero convertiria todo
        #  "no se sabe" en un "no corresponde"». Escribir otro parser al lado
        #  fue perder esa leccion.
        from campo.tasks import muestra_lo_pedido

        def muestra(texto: str) -> str:
            return {True: "si", False: "no", None: "no se sabe"}[
                muestra_lo_pedido(texto)]

        hoy = muestra(textos.get("como hoy", ""))
        alta = muestra(textos.get("sin degradar", ""))
        self.stdout.write(self.style.MIGRATE_HEADING("  ===== VEREDICTO ====="))
        self.stdout.write(f"  como hoy     -> MUESTRA: {hoy}")
        self.stdout.write(f"  sin degradar -> MUESTRA: {alta}")
        if hoy != "si" and alta == "si":
            self.stdout.write(self.style.SUCCESS(
                "  LA COMPRESION ES LA CULPABLE: la misma foto, sin degradar, "
                "SI muestra lo que se pidio."))
        elif hoy == alta:
            self.stdout.write(
                "  La compresion NO cambia el veredicto en esta foto. Si el "
                "analisis se equivoca, mirar la foto o la instruccion de la "
                "plantilla, no la calidad.")
        elif hoy == "si" and alta == "no se sabe":
            #  Pasa, y no es un error: con mas resolucion el modelo ve mejor y
            #  se vuelve MAS cauto. Un "si" sobre una foto degradada puede ser
            #  confianza que la imagen no sostiene.
            self.stdout.write(
                "  Con mas calidad el modelo es MAS cauto, no menos: afirmaba "
                "y ahora dice que no se sabe. No es la compresion lo que falla; "
                "la foto no alcanza para afirmar lo que se pidio.")
        else:
            self.stdout.write(
                f"  Sin conclusion con una sola foto (hoy={hoy}, alta={alta}): "
                f"probar con otra, preferentemente de una medicion, donde "
                f"'muestra lo pedido' es binario.")
        self.stdout.write(
            "\n  OJO: esto es UNA foto. Un caso no demuestra la regla; si "
            "confirma, repetir con dos o tres mas antes de cambiar el default.")
