# -*- coding: utf-8 -*-
"""
Lo que el técnico llenó en el formulario del trabajo, para leerlo en la oficina.

POR QUÉ EXISTE (18/10/2026)
---------------------------
El formulario del trabajo (`orden.datos`) y las fotos del checklist se
guardaban, y ninguna pantalla de la web los mostraba: la ficha de la orden
contaba «Evidencias: 4» y nada más. Los reportes de inicio, avance y cierre sí
se veían, porque la bitácora ya los leía con su esquema.

Acá se hace la misma lectura para el formulario: cada campo con su título, en
el orden de la plantilla, y el «Otro» junto con su texto. La pantalla no
interpreta el esquema; dibuja estas filas. Si cada una leyera la plantilla a
su manera, el día que difieran nadie sabría cuál es la respuesta del técnico.

Las fotos que cuelgan de un reporte NO van acá: ya se ven dentro de ese
reporte, en la bitácora, y repetirlas haría pensar que son otras.
"""

from __future__ import annotations

from campo.services.validador import OTRO, SUFIJO_OTRO, campos_con_otro


def _vacio(valor) -> bool:
    if valor is None:
        return True
    if isinstance(valor, str):
        return not valor.strip()
    if isinstance(valor, (list, dict)):
        return not valor
    return False


def _obligatorio(definicion: dict) -> bool:
    return bool(definicion.get("obligatorio")
                or (definicion.get("reglas") or {}).get("required"))


def formulario_del_trabajo(orden) -> dict:
    """Los campos y las fotos del checklist, en el orden de la plantilla."""
    esquema = orden.tipo_trabajo_version.esquema or {}
    definiciones = [c for c in esquema.get("campos") or []
                    if isinstance(c, dict) and c.get("id")]
    datos = dict(orden.datos or {})

    #  «Otro» y su texto se leen juntos, igual que en la bitácora.
    for c in campos_con_otro(definiciones):
        texto = datos.pop(c["id"] + SUFIJO_OTRO, None)
        if datos.get(c["id"]) == OTRO and texto:
            datos[c["id"]] = f"{OTRO}: {texto}"

    campos = []
    for c in definiciones:
        valor = datos.pop(c["id"], None)
        campos.append({
            "id": c["id"],
            "titulo": c.get("titulo") or c["id"],
            "tipo": c.get("tipo"),
            "valor": valor,
            "obligatorio": _obligatorio(c),
            "sin_responder": _vacio(valor),
        })
    #  Un valor guardado con una plantilla anterior se muestra igual: lo que
    #  el técnico escribió no desaparece porque la plantilla cambió.
    for cid, valor in datos.items():
        if cid.endswith(SUFIJO_OTRO) or _vacio(valor):
            continue
        campos.append({
            "id": cid, "titulo": cid, "tipo": None, "valor": valor,
            "obligatorio": False, "sin_responder": False,
            "fuera_de_la_plantilla": True,
        })

    return {"campos": campos, "fotos": _fotos_del_checklist(orden, esquema)}


def _fotos_del_checklist(orden, esquema) -> list[dict]:
    """Un renglón por foto que pide la plantilla, con las que llegaron."""
    requisitos = [e for e in esquema.get("evidencias") or []
                  if isinstance(e, dict) and e.get("id")]
    por_requisito: dict[str, list] = {}
    for ev in (orden.evidencias.filter(evento__isnull=True)
               .order_by("-vuelta", "created_at")):
        por_requisito.setdefault(ev.requisito_id or "", []).append({
            "id": str(ev.id),
            "vuelta": ev.vuelta,
            "capturada_en_cliente": (ev.capturada_en_cliente.isoformat()
                                     if ev.capturada_en_cliente else None),
            #  Que exista la fila no es que la foto esté en el servidor: quien
            #  dibuja necesita la diferencia para no mostrar un hueco roto.
            "disponible": ev.estado_archivo in ("recibido", "verificado"),
        })

    filas = []
    for r in requisitos:
        fotos = por_requisito.pop(r["id"], [])
        filas.append({
            "requisito_id": r["id"],
            "titulo": r.get("titulo") or r["id"],
            "obligatorio": bool(r.get("obligatorio")),
            "fotos": fotos,
            "sin_foto": not any(f["disponible"] for f in fotos),
        })
    #  Fotos de un requisito que la plantilla de hoy ya no pide.
    for rid, fotos in por_requisito.items():
        filas.append({
            "requisito_id": rid, "titulo": rid or "Foto sin requisito",
            "obligatorio": False, "fotos": fotos,
            "sin_foto": not any(f["disponible"] for f in fotos),
            "fuera_de_la_plantilla": True,
        })
    return filas
