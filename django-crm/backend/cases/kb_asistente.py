"""
Un articulo aprobado y publicado entra al corpus del asistente; despublicado, sale.

UNA SOLA BASE DE CONOCIMIENTO  --  12/11/2026
---------------------------------------------
La auditoria del menu (SPEC/AUDITORIA_MENU_2026-11-12.md) encontro dos bases:
Documentos, que el RAG del motor SI lee (marcar `usar_en_asistente` ->
common/tasks.py::ingerir_documento_en_asistente -> POST /corpus/documentos), y
la Base de conocimiento (/solutions), que nadie leia -- y cuya pantalla decia
"los clientes lo ven".

Ahora la segunda entra por la MISMA puerta que la primera:

  * aprobado Y publicado  -> se escribe como .docx (cases/kb_docx.py) y se
    manda a POST /corpus/documentos, igual que un documento. El motor lo deja
    'pendiente'; aca se aprueba en el acto (POST /corpus/.../aprobar), porque
    publicar un articulo aprobado YA es la decision humana que esa aprobacion
    representa: la tomo alguien con permiso de publicar (kb_access).
  * despublicado, desaprobado o borrado -> POST /corpus/documentos/<id>/retirar,
    que lo deja 'obsoleto' (no se borra: se puede reconstruir con que version
    se respondio).
  * editado estando publicado -> version nueva en el corpus y retiro de la
    anterior. Una version aprobada alla es inmutable (VersionAprobadaInmutable)
    y una retirada no revive con la misma version: cada ingesta es una version.

POR QUE SEÑALES Y NO LAS VISTAS
-------------------------------
Hay cuatro caminos que cambian lo que deberia estar en el corpus (publicar,
despublicar, PATCH/PUT de estado o texto, borrar) y alguno mas que vendra. Una
señal post_save/post_delete los cubre a todos con una sola regla. La tarea
escribe su resultado con `.update()`, que NO dispara señales: no hay bucle.

NO DUPLICA LA INGESTA. Fragmentar, vectorizar, versionar y aprobar los hace el
motor, por el mismo endpoint que los Documentos. Aca solo se arma el archivo y
se lo entrega. La tarea vive en este archivo nuevo y no en common/tasks.py
porque ese archivo es de otro frente de trabajo; usa su `_motor()` para saber
la empresa de la organizacion, sin copiarlo.
"""

from __future__ import annotations

import hashlib
import logging

from celery import shared_task
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone

from cases.kb_docx import docx_de_articulo
from cases.models import Solution

logger = logging.getLogger(__name__)

#: Los estados que ve la pantalla del articulo (mismo vocabulario que Document).
PENDIENTE = "pendiente"
PROCESANDO = "procesando"
OK = "ok"
ERROR = "error"
RETIRADO = "retirado"


def debe_estar_en_el_corpus(sol) -> bool:
    """Aprobado Y publicado. Cualquiera de los dos que falte, afuera."""
    return sol.status == "approved" and bool(sol.is_published)


def huella(sol) -> str:
    """Lo que, si cambia, obliga a volver a ingerir: titulo, cuerpo y roles."""
    crudo = "\x1f".join([sol.title or "", sol.description or "", sol.roles_asistente or ""])
    return hashlib.sha256(crudo.encode("utf-8")).hexdigest()


def codigo_de(sol) -> str:
    """El codigo del documento en el corpus. Estable por articulo."""
    return f"KB-{sol.id.hex[:12]}"


def _encolar(tarea, *args):
    """Despues del commit, y sin hacer fracasar el guardado si el broker cae.

    Mismo patron que common/views/document_views.py::_encolar_ingesta: el
    articulo ya quedo bien guardado; la ingesta se puede reintentar.
    """

    def _mandar():
        try:
            tarea.delay(*args)
        except Exception:
            logger.exception("No se pudo encolar la ingesta del articulo %s", args[0])

    transaction.on_commit(_mandar)


@receiver(post_save, sender=Solution)
def articulo_guardado(sender, instance, **kwargs):
    sol = instance
    if debe_estar_en_el_corpus(sol):
        if sol.huella_corpus != huella(sol) or sol.estado_ingesta == RETIRADO \
                or not sol.corpus_document_id:
            Solution.objects.filter(pk=sol.pk).update(
                estado_ingesta=PENDIENTE, ingesta_actualizada_en=timezone.now())
            _encolar(ingerir_articulo_en_asistente, str(sol.pk), str(sol.org_id))
        return
    if sol.corpus_document_id and sol.estado_ingesta != RETIRADO:
        _encolar(retirar_articulo_del_asistente, str(sol.pk), str(sol.org_id),
                 str(sol.corpus_document_id))


@receiver(post_delete, sender=Solution)
def articulo_borrado(sender, instance, **kwargs):
    if instance.corpus_document_id and instance.estado_ingesta != RETIRADO:
        _encolar(retirar_articulo_del_asistente, str(instance.pk),
                 str(instance.org_id), str(instance.corpus_document_id))


def _guardar(sol_id, **campos):
    """Escribe el resultado sin disparar la señal (y sin pisar otros campos)."""
    campos["ingesta_actualizada_en"] = timezone.now()
    Solution.objects.filter(pk=sol_id).update(**campos)


def _motor(org_id):
    from common.tasks import _motor as motor_de_la_org

    return motor_de_la_org(org_id)


def _error_de(respuesta) -> str:
    """El mensaje del motor (lo escribe Dexter, se puede mostrar) o el codigo."""
    try:
        cuerpo = respuesta.json()
    except Exception:
        cuerpo = {}
    return str((cuerpo or {}).get("error") or f"El asistente respondió {respuesta.status_code}.")[:2000]


def _retirar_del_motor(url, tenant, corpus_id):
    import requests

    r = requests.post(
        f"{url.rstrip('/')}/corpus/documentos/{corpus_id}/retirar",
        json={"tenant": tenant},
        timeout=60,
    )
    # 404 = ya no esta: para "que no lo use el asistente" eso es lo mismo.
    if not r.ok and r.status_code != 404:
        raise RuntimeError(_error_de(r))


@shared_task
def ingerir_articulo_en_asistente(solution_id, org_id):
    """Arma el .docx del articulo y lo entrega al corpus, como un documento."""
    import requests

    from common.tasks import set_rls_context

    set_rls_context(org_id)
    sol = Solution.objects.filter(id=solution_id, org_id=org_id).first()
    if sol is None or not debe_estar_en_el_corpus(sol):
        # Lo despublicaron entre el encolado y ahora: no se ingiere nada.
        return

    url, tenant = _motor(org_id)
    if not url or not tenant:
        _guardar(solution_id, estado_ingesta=ERROR, ingesta_detalle=(
            "El asistente no está configurado: falta ASISTENTE_URL en el entorno "
            "del backend, o la organización no tiene empresa en el motor."))
        return

    _guardar(solution_id, estado_ingesta=PROCESANDO)
    version = (sol.version_corpus or 0) + 1
    codigo = codigo_de(sol)
    datos = docx_de_articulo(
        codigo=codigo, version=version, titulo=sol.title, descripcion=sol.description,
        fecha=timezone.localdate().isoformat())
    anterior = sol.corpus_document_id

    try:
        r = requests.post(
            f"{url.rstrip('/')}/corpus/documentos",
            files={"archivo": (f"{codigo}-v{version}.docx", datos)},
            data={
                "tenant": tenant,
                "roles": sol.roles_asistente or "",
                "storage_path": f"solutions/{sol.id}",
                "forzar": "true",
            },
            timeout=900,
        )
        if not r.ok:
            raise RuntimeError(_error_de(r))
        cuerpo = r.json()
        nuevo = str(cuerpo.get("document_id") or "")
        if not nuevo:
            raise RuntimeError("El asistente no devolvió el documento.")

        if cuerpo.get("estado") == "pendiente":
            quien = getattr(sol.updated_by, "email", "") or getattr(sol.created_by, "email", "")
            a = requests.post(
                f"{url.rstrip('/')}/corpus/documentos/{nuevo}/aprobar",
                json={"tenant": tenant,
                      "aprobado_por": f"Base de conocimiento ({quien})" if quien
                      else "Base de conocimiento"},
                timeout=60,
            )
            # 409 = ya no estaba pendiente (otra pasada lo aprobo): es lo pedido.
            if not a.ok and a.status_code != 409:
                raise RuntimeError(_error_de(a))

        if anterior and anterior != nuevo:
            # La version vieja sale DESPUES de que la nueva quedo en uso: nunca
            # hay un momento sin el articulo en el corpus.
            _retirar_del_motor(url, tenant, anterior)

        # ¿Lo despublicaron (o borraron) mientras esto viajaba? Entonces la
        # version recien aprobada tampoco puede quedar en uso.
        ahora = Solution.objects.filter(id=solution_id, org_id=org_id).first()
        if ahora is None or not debe_estar_en_el_corpus(ahora):
            _retirar_del_motor(url, tenant, nuevo)
            _guardar(solution_id, estado_ingesta=RETIRADO, corpus_document_id=None,
                     ingesta_fragmentos=None, ingesta_detalle=None, huella_corpus="")
            return
    except Exception as e:
        # Al log solo el tipo y el id (nada del articulo); a la pantalla, el
        # mensaje que escribio el motor o el codigo.
        logger.warning("Ingesta del articulo %s fallo: %s", solution_id, type(e).__name__)
        detalle = str(e) if isinstance(e, RuntimeError) else (
            "No se pudo hablar con el asistente. Se reintenta al volver a guardar el artículo.")
        _guardar(solution_id, estado_ingesta=ERROR, ingesta_detalle=detalle[:2000])
        return

    notas = []
    if not (cuerpo.get("roles_permitidos") or []):
        notas.append("Sin agentes asignados: el asistente todavía no lo va a citar para "
                     "nadie. Elegí qué agentes pueden usarlo.")
    _guardar(
        solution_id,
        estado_ingesta=OK,
        corpus_document_id=nuevo,
        version_corpus=version,
        ingesta_fragmentos=cuerpo.get("fragmentos"),
        ingesta_detalle="\n".join(notas) or None,
        huella_corpus=huella(sol),
    )


@shared_task
def retirar_articulo_del_asistente(solution_id, org_id, corpus_document_id):
    """Saca el articulo del corpus (pasa a 'obsoleto' en el motor)."""
    from common.tasks import set_rls_context

    set_rls_context(org_id)
    url, tenant = _motor(org_id)
    if not url or not tenant:
        _guardar(solution_id, estado_ingesta=ERROR, ingesta_detalle=(
            "No se pudo retirar del asistente: no está configurado."))
        return
    try:
        _retirar_del_motor(url, tenant, corpus_document_id)
    except Exception as e:
        logger.warning("Retiro del articulo %s fallo: %s", solution_id, type(e).__name__)
        _guardar(solution_id, estado_ingesta=ERROR, ingesta_detalle=(
            "No se pudo retirar del asistente: sigue pudiendo citarlo. "
            "Volvé a despublicarlo para reintentar."))
        return
    # Solo si el articulo sigue existiendo; borrado, no hay fila que marcar.
    _guardar(solution_id, estado_ingesta=RETIRADO, corpus_document_id=None,
             ingesta_fragmentos=None, ingesta_detalle=None, huella_corpus="")
