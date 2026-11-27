"""
EL CONTRATO DEL PROVEEDOR: PREPARARLO, PEDIR EL ENLACE DE FIRMA, SABER SI SE
FIRMO  --  26/11/2026.

El usuario decidio que el cliente firme SOLO el contrato del proveedor (no uno
de Dexter), que la instalacion se cree al confirmar el contrato y que la cedula
y el recibo queden en los archivos del cliente en el proveedor. La API del
primer proveedor no tiene nada de eso: vive en su panel web, y lo maneja
`nucleo/herramientas/web.py`. Este modulo decide CUANDO y CON QUE se usa.

TRES OPERACIONES
----------------
* `preparar`: guarda el contrato de la instalacion, tal como viene de la
  plantilla del proveedor y sin firma, con los documentos. ESCRIBE: sale por la
  puerta HUMANA de quien confirmo el contrato, una vez por pedido (clave fija
  `origen|herramienta`), y solo si la instalacion existe con ese numero y es de
  ESE contrato -- de esa fila sale tambien el usuario del cliente.
* `enlace`: el enlace para que el cliente firme. Entra al portal del cliente
  SIN clave: no se guarda ni se registra en ningun lado, y quien lo pide lo
  entrega directo al telefono del tecnico.
* `firmado`: si el contrato ya tiene la firma. Si/no, nunca la firma.

«NO SE» NO ES «FALLO». Si el formulario salio y algo fallo sin que el panel
dijera por que, nadie sabe si quedo guardado: vuelve `no_se_sabe`, y quien
llama no lo reintenta solo. `fallo` es solo cuando el panel DIJO que no (sus
avisos vienen tapados) o cuando nada llego a salir.

Las herramientas se encuentran POR SU MARCA, nunca por su nombre (CLAUDE.md
3.1).
"""
from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass, field

from nucleo.observabilidad.registro import registrar

PREPARADO = "preparado"
SUBIDO = "subido"                     # las fotos quedaron en los archivos del cliente
NO_ENCONTRADA = "no_encontrada"       # no hay una instalacion de este contrato
SIN_USUARIO = "sin_usuario"           # la instalacion no trae el usuario del cliente
SIN_HERRAMIENTA = "sin_herramienta"
DATOS_INVALIDOS = "datos_invalidos"
BLOQUEADO = "bloqueado"               # el sistema decidio no escribir
FALLO = "fallo"                       # el panel dijo que no, o nada salio
NO_SE_SABE = "no_se_sabe"             # salio y no se sabe si quedo
NO_SE_PUDO_COMPROBAR = "no_se_pudo_comprobar"
EN_CURSO = "en_curso"                 # el mismo pedido esta corriendo
LISTO = "listo"                       # enlace o firma leidos

#: Cuantos documentos por contrato. La cedula por los dos lados y el recibo
#: son tres; el tope deja lugar y frena un envio desbordado.
MAX_ARCHIVOS = 10


@dataclass
class ResultadoContrato:
    estado: str
    motivo: str = ""
    referencia: str = ""
    contrato_id: str = ""
    usuario: str = ""
    #: Lo que el panel escribio al rechazar, tapado (ver web._avisos).
    avisos: list[str] = field(default_factory=list)
    #: El pedido llego al registro de operaciones: pudo haber salido.
    emitido: bool = False
    #: Solo `enlace`. NO se registra: entra al portal del cliente sin clave.
    enlace: str = ""
    #: Solo `firmado`.
    firmado: bool | None = None

    def como_dict(self) -> dict:
        d = {"estado": self.estado, "motivo": self.motivo, "referencia": self.referencia,
             "contrato_id": self.contrato_id, "usuario": self.usuario,
             "avisos": list(self.avisos), "emitido": self.emitido}
        if self.enlace:
            d["enlace"] = self.enlace
        if self.firmado is not None:
            d["firmado"] = self.firmado
        return d


def _herramientas(config) -> dict:
    hs = list(config.herramientas or [])
    return {
        "preparar": next((h for h in hs if getattr(h, "prepara_contrato_del_proveedor", False)),
                         None),
        "enlace": next((h for h in hs if getattr(h, "da_enlace_de_firma", False)), None),
        "firma": next((h for h in hs if getattr(h, "lee_firma_del_contrato", False)), None),
        "fotos": next((h for h in hs if getattr(h, "sube_documentos_del_cliente", False)), None),
    }


def _archivos(archivos) -> tuple[list[dict] | None, str]:
    """Los documentos tal como viajan al panel, o (None, por que no). Cada uno
    `{"nombre", "tipo", "base64", "titulo"}`; el contenido se valida aca para
    no gastar un pedido en uno roto."""
    if archivos in (None, []):
        return [], ""
    if not isinstance(archivos, list) or len(archivos) > MAX_ARCHIVOS:
        return None, f"los documentos son una lista de hasta {MAX_ARCHIVOS}"
    salida = []
    for i, a in enumerate(archivos, 1):
        if not isinstance(a, dict) or not isinstance(a.get("base64"), str):
            return None, f"el documento {i} no trae contenido"
        try:
            base64.b64decode(a["base64"], validate=True)
        except Exception:                                    # noqa: BLE001
            return None, f"el documento {i} no es base64 valido"
        salida.append({"nombre": str(a.get("nombre") or f"documento-{i}")[:120],
                       "tipo": str(a.get("tipo") or "application/octet-stream")[:80],
                       "titulo": str(a.get("titulo") or "")[:120],
                       "base64": a["base64"]})
    return salida, ""


def _huella_de(archivos: list[dict]) -> list[dict]:
    """Lo que entra a la huella del pedido: nombre, titulo y un resumen del
    contenido -- no el contenido entero."""
    return [{"nombre": a["nombre"], "titulo": a["titulo"],
             "sha256": hashlib.sha256(a["base64"].encode("ascii")).hexdigest()}
            for a in archivos]


def _instalacion(config, tenant: str, d: dict, numero: str):
    """La fila de la instalacion de ESTE contrato y la herramienta que la leyo,
    o (None, None). Levanta `_NoSePudoLeer` si una lectura falla."""
    from nucleo.seguimiento import alta_de_cliente as alta

    h = alta._herramientas(config)
    comun = h["buscar"].parametros_de_busqueda_por_ip if h["buscar"] else None
    for herr in h["buscar_instalaciones"]:
        pb = herr.parametros_de_busqueda_por_ip
        for fila in alta._filas_de(herr, comun, config, tenant, d["ip"]):
            if (alta._el_numero(fila.get((comun or pb).campo_id)) == numero
                    and alta._es_el_nuestro(fila, comun or pb, d)):
                return fila, pb
    return None, None


def preparar(config, tenant: str, *, actor: str, origen: str, datos, id_servicio,
             archivos=None) -> ResultadoContrato:
    """Guarda el contrato de la instalacion de ESTE contrato. Ver el encabezado."""
    from nucleo.herramientas import http as ejecutor_http
    from nucleo.herramientas import web
    from nucleo.seguimiento import alta_de_cliente as alta
    from nucleo.seguridad import frontera, idempotencia, interruptor

    def _fin(estado, motivo="", **kw) -> ResultadoContrato:
        return ResultadoContrato(estado, motivo, referencia=origen, **kw)

    h = _herramientas(config)
    ha = alta._herramientas(config)
    if h["preparar"] is None or not ha["buscar_instalaciones"] or ha["crear"] is None:
        return _fin(SIN_HERRAMIENTA, "la empresa no declara como se prepara el contrato "
                                     "del proveedor")
    numero = alta._el_numero(id_servicio)
    if not numero:
        return _fin(DATOS_INVALIDOS, "falta el numero de servicio de la instalacion")
    d, por_que = alta.leer_datos(datos, ha["crear"].parametros_de_alta)
    if d is None:
        return _fin(DATOS_INVALIDOS, por_que)
    docs, por_que = _archivos(archivos)
    if docs is None:
        return _fin(DATOS_INVALIDOS, por_que)

    #  1. LA INSTALACION TIENE QUE ESTAR, CON ESE NUMERO Y DE ESTE CONTRATO.
    try:
        fila, pb = _instalacion(config, tenant, d, numero)
    except alta._NoSePudoLeer as e:
        return _fin(NO_SE_PUDO_COMPROBAR, f"no se pudo leer el proveedor ({e})")
    if fila is None:
        return _fin(NO_ENCONTRADA, "no hay en el proveedor una instalacion de este "
                                   "contrato con ese numero")
    usuario = str(fila.get(pb.campo_usuario) or "").strip() if pb.campo_usuario else ""
    if not usuario:
        return _fin(SIN_USUARIO, "la instalacion no trae el usuario del cliente: sin el "
                                 "no hay enlace de firma")

    #  2. EL INTERRUPTOR, sin cache y pegado a la escritura.
    try:
        veredicto = interruptor.veredicto(tenant)
    except Exception as e:                                   # noqa: BLE001
        registrar("contrato_proveedor", "no se pudo leer el interruptor: NO se escribe", error=e)
        return _fin(BLOQUEADO, "no se pudo comprobar el interruptor")
    if not veredicto.permitido:
        interruptor.anotar_bloqueo(tenant, actor=actor, recurso="contrato_del_proveedor",
                                   motivo=f"{veredicto.estado}: {veredicto.motivo}")
        return _fin(BLOQUEADO, "el interruptor de la empresa esta detenido")

    #  3. UNA VEZ, POR LA PUERTA HUMANA.
    herr = h["preparar"]
    huella = {"id_servicio": int(numero), "archivos": _huella_de(docs)}

    def _hacer():
        leido = web.ejecutar(herr, {"id_servicio": int(numero), "archivos": docs}, tenant,
                             config.variables_tenant)
        return {"contrato_id": str(leido.get("contrato_id") or "")}

    try:
        with frontera.humana(tenant, herr.nombre, actor=actor, evidencia=origen, origen=origen):
            res = idempotencia.ejecutar(tenant, herr.nombre, huella, origen, _hacer,
                                        clave=f"{origen}|{herr.nombre}")
    except ejecutor_http.ErrorHerramientaHttp as e:
        registrar("contrato_proveedor", "el ejecutor no dejo salir el contrato", error=e)
        return _fin(BLOQUEADO, "el contrato no salio: el ejecutor lo freno antes de llegar "
                               "al proveedor", usuario=usuario)
    except frontera.AccionExternaNoAutorizada as e:
        registrar("contrato_proveedor", "la frontera no autorizo el contrato", error=e)
        return _fin(BLOQUEADO, "la frontera no autorizo el contrato", usuario=usuario)
    except web.ErrorWeb as e:
        if e.envio and not e.avisos:
            return _fin(NO_SE_SABE, f"el formulario salio y no se sabe si quedo ({e.etapa})",
                        usuario=usuario, emitido=True)
        return _fin(FALLO, f"el panel no guardo el contrato ({e.etapa}: {e.motivo})",
                    usuario=usuario, avisos=e.avisos, emitido=True)
    except Exception as e:                                   # noqa: BLE001
        registrar("contrato_proveedor", "el contrato volvio con un error inesperado", error=e)
        return _fin(NO_SE_SABE, "no se sabe si el contrato quedo guardado", usuario=usuario,
                    emitido=True)
    if res.decision == "en_curso":
        return _fin(EN_CURSO, "ese pedido ya esta corriendo", usuario=usuario, emitido=True)
    if not res.ejecutada and res.decision != "repetida":
        return _fin(BLOQUEADO, "el registro de operaciones no dejo salir este pedido "
                               f"({res.decision})", usuario=usuario, emitido=True)
    contrato_id = str((res.respuesta or {}).get("contrato_id") or "")
    if not contrato_id:
        return _fin(NO_SE_SABE, "el panel guardo y no devolvio el numero del contrato",
                    usuario=usuario, emitido=True)
    registrar("contrato_proveedor", "contrato del proveedor preparado")
    return _fin(PREPARADO, contrato_id=contrato_id, usuario=usuario, emitido=True)


def enlace(config, tenant: str, *, usuario: str, id_servicio) -> ResultadoContrato:
    """El enlace de firma. NO se registra: ver el encabezado."""
    from nucleo.herramientas import web
    from nucleo.seguimiento import alta_de_cliente as alta

    herr = _herramientas(config)["enlace"]
    if herr is None:
        return ResultadoContrato(SIN_HERRAMIENTA, "la empresa no declara el enlace de firma")
    numero = alta._el_numero(id_servicio)
    usuario = str(usuario or "").strip()
    if not numero or not usuario or len(usuario) > 200:
        return ResultadoContrato(DATOS_INVALIDOS, "faltan el usuario o el numero de servicio")
    try:
        leido = web.ejecutar(herr, {"usuario": usuario, "id_servicio": int(numero)}, tenant,
                             config.variables_tenant)
    except web.ErrorWeb as e:
        return ResultadoContrato(NO_SE_PUDO_COMPROBAR, f"el panel no dio el enlace ({e.etapa})")
    except Exception as e:                                   # noqa: BLE001
        registrar("contrato_proveedor", "pedir el enlace fallo", error=e)
        return ResultadoContrato(NO_SE_PUDO_COMPROBAR, "no se pudo pedir el enlace")
    valor = str(leido.get("enlace") or "")
    if not valor.startswith(("http://", "https://")):
        return ResultadoContrato(NO_SE_PUDO_COMPROBAR, "el panel no devolvio un enlace")
    return ResultadoContrato(LISTO, enlace=valor)


def firmado(config, tenant: str, *, contrato_id) -> ResultadoContrato:
    """Si el contrato ya tiene la firma del cliente. SOLO LEE."""
    from nucleo.herramientas import web
    from nucleo.seguimiento import alta_de_cliente as alta

    herr = _herramientas(config)["firma"]
    if herr is None:
        return ResultadoContrato(SIN_HERRAMIENTA, "la empresa no declara como leer la firma")
    numero = alta._el_numero(contrato_id)
    if not numero:
        return ResultadoContrato(DATOS_INVALIDOS, "falta el numero del contrato")
    try:
        leido = web.ejecutar(herr, {"contrato_id": numero}, tenant, config.variables_tenant)
    except web.ErrorWeb as e:
        return ResultadoContrato(NO_SE_PUDO_COMPROBAR, f"el panel no dejo leer ({e.etapa})")
    except Exception as e:                                   # noqa: BLE001
        registrar("contrato_proveedor", "leer la firma fallo", error=e)
        return ResultadoContrato(NO_SE_PUDO_COMPROBAR, "no se pudo leer la firma")
    return ResultadoContrato(LISTO, contrato_id=numero, firmado=bool(leido.get("firmado")))


# =============================================================================
#  LAS FOTOS DEL TRABAJO, A LOS ARCHIVOS DEL CLIENTE  --  26/11/2026
# =============================================================================
#  Decision del usuario: al «Finalizar trabajo» las fotos de la instalacion
#  (fachada, caja, ONU, potencia...) van a los archivos del cliente en el
#  proveedor, por su formulario PROPIO de varios documentos -- no reenviando el
#  contrato ya firmado. ESCRIBE: puerta humana de quien finalizo, una vez por
#  pedido, y solo si la instalacion es de ESTE contrato Y el usuario de la
#  ruta es el de esa instalacion: ese usuario decide en los archivos de QUIEN
#  quedan las fotos.
MAX_FOTOS = 12


def subir_fotos(config, tenant: str, *, actor: str, origen: str, datos, id_servicio,
                usuario: str, archivos) -> ResultadoContrato:
    """Sube las fotos del trabajo a los archivos del cliente. Ver arriba."""
    from nucleo.herramientas import http as ejecutor_http
    from nucleo.herramientas import web
    from nucleo.seguimiento import alta_de_cliente as alta
    from nucleo.seguridad import frontera, idempotencia, interruptor

    def _fin(estado, motivo="", **kw) -> ResultadoContrato:
        return ResultadoContrato(estado, motivo, referencia=origen, **kw)

    herr = _herramientas(config)["fotos"]
    ha = alta._herramientas(config)
    if herr is None or not ha["buscar_instalaciones"] or ha["crear"] is None:
        return _fin(SIN_HERRAMIENTA, "la empresa no declara como se suben las fotos")
    numero = alta._el_numero(id_servicio)
    usuario = str(usuario or "").strip()
    if not numero or not usuario or len(usuario) > 200:
        return _fin(DATOS_INVALIDOS, "faltan el numero de servicio o el usuario del cliente")
    d, por_que = alta.leer_datos(datos, ha["crear"].parametros_de_alta)
    if d is None:
        return _fin(DATOS_INVALIDOS, por_que)
    if not isinstance(archivos, list) or not archivos:
        return _fin(DATOS_INVALIDOS, "no hay fotos que subir")
    if len(archivos) > MAX_FOTOS:
        return _fin(DATOS_INVALIDOS, f"son mas de {MAX_FOTOS} fotos")
    fotos, por_que = _archivos(archivos)
    if fotos is None:
        return _fin(DATOS_INVALIDOS, por_que)

    #  1. LA INSTALACION DE ESTE CONTRATO, y el usuario de la ruta es el suyo.
    try:
        fila, pb = _instalacion(config, tenant, d, numero)
    except alta._NoSePudoLeer as e:
        return _fin(NO_SE_PUDO_COMPROBAR, f"no se pudo leer el proveedor ({e})")
    if fila is None:
        return _fin(NO_ENCONTRADA, "no hay en el proveedor una instalacion de este contrato "
                                   "con ese numero")
    suyo = str(fila.get(pb.campo_usuario) or "").strip() if pb.campo_usuario else ""
    if not suyo or suyo != usuario:
        return _fin(NO_ENCONTRADA, "el usuario no es el de la instalacion de este contrato")

    #  2. EL INTERRUPTOR, sin cache y pegado a la escritura.
    try:
        veredicto = interruptor.veredicto(tenant)
    except Exception as e:                                   # noqa: BLE001
        registrar("fotos_al_proveedor", "no se pudo leer el interruptor: NO se escribe", error=e)
        return _fin(BLOQUEADO, "no se pudo comprobar el interruptor")
    if not veredicto.permitido:
        interruptor.anotar_bloqueo(tenant, actor=actor, recurso="fotos_al_proveedor",
                                   motivo=f"{veredicto.estado}: {veredicto.motivo}")
        return _fin(BLOQUEADO, "el interruptor de la empresa esta detenido")

    #  3. UNA VEZ, POR LA PUERTA HUMANA.
    huella = {"usuario": usuario, "archivos": _huella_de(fotos)}

    def _hacer():
        web.ejecutar(herr, {"usuario": usuario, "archivos": fotos}, tenant,
                     config.variables_tenant)
        return {"subidas": len(fotos)}

    try:
        with frontera.humana(tenant, herr.nombre, actor=actor, evidencia=origen, origen=origen):
            res = idempotencia.ejecutar(tenant, herr.nombre, huella, origen, _hacer,
                                        clave=f"{origen}|{herr.nombre}")
    except ejecutor_http.ErrorHerramientaHttp as e:
        registrar("fotos_al_proveedor", "el ejecutor no dejo salir las fotos", error=e)
        return _fin(BLOQUEADO, "las fotos no salieron: el ejecutor las freno antes de llegar "
                               "al proveedor")
    except frontera.AccionExternaNoAutorizada as e:
        registrar("fotos_al_proveedor", "la frontera no autorizo las fotos", error=e)
        return _fin(BLOQUEADO, "la frontera no autorizo las fotos")
    except web.ErrorWeb as e:
        if e.envio and not e.avisos:
            return _fin(NO_SE_SABE, f"el formulario salio y no se sabe si quedo ({e.etapa})",
                        emitido=True)
        return _fin(FALLO, f"el panel no guardo las fotos ({e.etapa}: {e.motivo})",
                    avisos=e.avisos, emitido=True)
    except Exception as e:                                   # noqa: BLE001
        registrar("fotos_al_proveedor", "las fotos volvieron con un error inesperado", error=e)
        return _fin(NO_SE_SABE, "no se sabe si las fotos quedaron", emitido=True)
    if res.decision == "en_curso":
        return _fin(EN_CURSO, "ese pedido ya esta corriendo", emitido=True)
    if not res.ejecutada and res.decision != "repetida":
        return _fin(BLOQUEADO, f"el registro de operaciones no dejo salir este pedido "
                               f"({res.decision})", emitido=True)
    registrar("fotos_al_proveedor", "fotos del trabajo subidas al cliente")
    return _fin(SUBIDO, emitido=True)
