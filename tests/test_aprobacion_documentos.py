# -*- coding: utf-8 -*-
"""
================================================================================
 GUARDA DE APROBACION DE DOCUMENTOS  --  lo pendiente NO se recupera
================================================================================

Por que existe
--------------
Hasta agosto de 2026, un documento subido desde /manual quedaba VIGENTE al
instante: se vectorizaba y el asistente podia recuperarlo en la siguiente
consulta de un cliente sin que nadie lo hubiera leido.

El riesgo no es teorico y esta medido en este mismo proyecto. La unica guia
de diagnostico del corpus, G-GO-04, tiene 7 de sus 8 fragmentos escritos
para un tecnico en campo: entrar al domicilio con Power Meter, revisar
conectores SC, reemplazar el cable de acometida, revisar tensores. Asignada
por error a un rol de cara al cliente, eso son instrucciones peligrosas
entregadas a alguien sin herramientas ni instruccion, y sin que salte
ningun error.

Lo que se fija aca
------------------
1. Un documento en 'pendiente' NO lo devuelve match_chunks, aunque su
   similitud sea altisima y aunque tenga el rol asignado. La garantia vive
   en SQL (la funcion filtra por estado='vigente'), no en el frontend ni en
   un prompt -- PRD 7.4, el codigo es la garantia.
2. Aprobarlo lo vuelve recuperable, y deja registrado quien y cuando.
3. Aprobar dos veces no hace nada la segunda: la funcion solo actua sobre
   'pendiente'. Sin eso, aprobar un documento retirado lo resucitaria en
   silencio.

Usa un documento de prueba propio, con codigo reservado, y lo borra al
terminar -- no toca el corpus real.

Uso
---
    py -3.13 tests/test_aprobacion_documentos.py
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv                     # noqa: E402
load_dotenv(RAIZ / ".env", override=True)          # noqa: E402

from nucleo.config import fuente                   # noqa: E402
from nucleo.ingesta import corpus as ingesta       # noqa: E402
from nucleo.persistencia.db import sesion          # noqa: E402
from nucleo.recuperacion.busqueda import recuperar_candidatos  # noqa: E402

TENANT = "rapilink"
CODIGO = "ZZ-TEST-APROBACION"
# Texto muy especifico, para que la consigna de prueba lo traiga primero si
# de verdad estuviera disponible. Si con esto no aparece, no aparece por
# nada.
CONTENIDO = ("El procedimiento de prueba de aprobacion documental establece "
             "que el conector de calibracion violeta debe verificarse antes "
             "de cualquier medicion del equipo de prueba.")
CONSULTA = "conector de calibracion violeta del equipo de prueba"

fallos: list[str] = []


def comprobar(condicion: bool, que: str) -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}")
    if not condicion:
        fallos.append(que)


class _FragmentoFalso:
    """Lo minimo que ingerir() necesita, sin pasar por un .docx real."""
    def __init__(self, orden, contenido):
        self.orden = orden
        self.contenido = contenido
        self.metadata = {"seccion": "1.1"}

    def contextualizar(self, doc):
        return self.contenido


class _DocFalso:
    codigo = CODIGO
    titulo = "Documento de prueba de aprobacion"
    version = "01"
    defectos: list = []
    fragmentos = [_FragmentoFalso(1, CONTENIDO)]


def _limpiar(cur, org):
    cur.execute(
        """delete from asistente.document_chunks
            where document_id in (select id from asistente.documents
                                   where organization_id=%s and codigo=%s)""",
        (org, CODIGO))
    cur.execute("delete from asistente.documents where organization_id=%s and codigo=%s",
                (org, CODIGO))


def _rol_de_prueba(config) -> str:
    """Un rol cualquiera del tenant: lo que se prueba es el estado, no el rol."""
    return sorted(config.roles)[0]


print("=" * 70)
print(" APROBACION DE DOCUMENTOS  --  lo pendiente no llega al asistente")
print("=" * 70)

config = fuente.cargar(TENANT, raiz=RAIZ)
rol = _rol_de_prueba(config)
print(f"\nrol de prueba: {rol}\n")

try:
    # --- se sube como PENDIENTE -------------------------------------------
    with sesion(TENANT) as (cur, org):
        _limpiar(cur, org)
        r = ingesta.ingerir(
            cur, org, _DocFalso(), "hash-de-prueba-1",
            modelo_embeddings=config.rag.modelo_embeddings,
            roles_permitidos=[rol], estado="pendiente",
            original=b"bytes-falsos-del-docx", nombre_archivo="prueba.docx",
            mime="application/vnd.openxmlformats-officedocument."
                 "wordprocessingml.document")
        doc_id = r["document_id"]

    comprobar(r["estado"] == "pendiente", "se carga en estado 'pendiente'")
    comprobar(r["fragmentos"] == 1, "se vectoriza igual (1 fragmento)")

    candidatos = recuperar_candidatos(config, TENANT, rol, CONSULTA)
    codigos = [c.codigo for c in candidatos]
    comprobar(CODIGO not in codigos,
              f"PENDIENTE: no lo recupera match_chunks (trajo {codigos[:2] or 'nada'})")

    # --- se aprueba --------------------------------------------------------
    with sesion(TENANT) as (cur, org):
        ok = ingesta.aprobar(cur, org, doc_id, None)
    comprobar(ok, "aprobar() actua sobre un documento pendiente")

    candidatos = recuperar_candidatos(config, TENANT, rol, CONSULTA)
    codigos = [c.codigo for c in candidatos]
    comprobar(CODIGO in codigos, "aprobado: ahora SI lo recupera")

    with sesion(TENANT) as (cur, org):
        cur.execute("""select estado, aprobado_en from asistente.documents
                        where organization_id=%s and codigo=%s""", (org, CODIGO))
        fila = cur.fetchone()
    comprobar(fila["estado"] == "vigente", "queda en 'vigente'")
    comprobar(fila["aprobado_en"] is not None, "registra CUANDO se aprobo")

    # --- aprobar de nuevo no hace nada -------------------------------------
    with sesion(TENANT) as (cur, org):
        otra_vez = ingesta.aprobar(cur, org, doc_id, None)
    comprobar(not otra_vez,
              "aprobar dos veces no hace nada la segunda (solo actua sobre pendiente)")

    # --- el original queda guardado ----------------------------------------
    #  Sin esto, "Fulano aprobo este documento" no se puede verificar
    #  despues: los fragmentos son una representacion derivada y no permiten
    #  reconstruir el archivo con sus tablas de firma ni su formato.
    with sesion(TENANT) as (cur, org):
        cur.execute("""select original_content, nombre_archivo, hash
                         from asistente.documents
                        where organization_id=%s and codigo=%s""", (org, CODIGO))
        fila = cur.fetchone()
    comprobar(fila["original_content"] == b"bytes-falsos-del-docx",
              "guarda el archivo original tal cual se subio")
    comprobar(fila["nombre_archivo"] == "prueba.docx", "guarda el nombre del archivo")

    # --- resubir el MISMO archivo no invalida la aprobacion ----------------
    #  Bug real, encontrado probando esto en produccion (22/08/2026): una
    #  resubida identica (con 'forzar', para re-vectorizar tras un cambio de
    #  pipeline) devolvia el documento a 'pendiente' y lo dejaba FUERA DE
    #  SERVICIO hasta que alguien lo re-aprobara. La aprobacion es sobre los
    #  bytes: si los bytes no cambiaron, no hay nada nuevo que aprobar.
    with sesion(TENANT) as (cur, org):
        r2 = ingesta.ingerir(
            cur, org, _DocFalso(), "hash-de-prueba-1",   # mismo hash
            modelo_embeddings=config.rag.modelo_embeddings,
            roles_permitidos=[rol], estado="pendiente", forzar=True,
            original=b"bytes-falsos-del-docx")
    comprobar(r2["estado"] == "vigente",
              "resubir el MISMO archivo no lo devuelve a pendiente")

    candidatos = recuperar_candidatos(config, TENANT, rol, CONSULTA)
    comprobar(CODIGO in [c.codigo for c in candidatos],
              "y sigue disponible para el asistente, sin quedar fuera de servicio")

    # --- una version APROBADA no se puede pisar ----------------------------
    #  Es lo que hace verificable la aprobacion: si los bytes se pueden
    #  cambiar bajo el mismo codigo y version, "que aprobo esa persona" deja
    #  de tener respuesta.
    hubo_rechazo = False
    try:
        with sesion(TENANT) as (cur, org):
            ingesta.ingerir(
                cur, org, _DocFalso(), "hash-DISTINTO",
                modelo_embeddings=config.rag.modelo_embeddings,
                roles_permitidos=[rol], estado="pendiente",
                original=b"otros-bytes")
    except ingesta.VersionAprobadaInmutable:
        hubo_rechazo = True
    comprobar(hubo_rechazo,
              "una version ya aprobada NO se puede reemplazar con otro contenido")

    with sesion(TENANT) as (cur, org):
        cur.execute("""select original_content from asistente.documents
                        where organization_id=%s and codigo=%s""", (org, CODIGO))
        comprobar(cur.fetchone()["original_content"] == b"bytes-falsos-del-docx",
                  "y el original aprobado sigue intacto tras el intento")

    # --- un retirado no se resucita aprobandolo ----------------------------
    with sesion(TENANT) as (cur, org):
        ingesta.retirar(cur, org, doc_id)
        revivido = ingesta.aprobar(cur, org, doc_id, None)
        cur.execute("""select estado from asistente.documents
                        where organization_id=%s and codigo=%s""", (org, CODIGO))
        estado_final = cur.fetchone()["estado"]
    comprobar(not revivido and estado_final == "obsoleto",
              "aprobar NO resucita un documento retirado")

finally:
    try:
        with sesion(TENANT) as (cur, org):
            _limpiar(cur, org)
        print("\n  (documento de prueba borrado)")
    except Exception as e:
        print(f"\n  [aviso] no se pudo limpiar el documento de prueba: {e}")

print("\n" + "=" * 70)
if fallos:
    print(f" {len(fallos)} FALLA(S):")
    for f in fallos:
        print(f"   - {f}")
    raise SystemExit(1)
print(" Un documento sin aprobar no llega al asistente.")
print("=" * 70)
