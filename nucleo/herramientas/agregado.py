# -*- coding: utf-8 -*-
"""
================================================================================
 EJECUTOR DE HERRAMIENTAS TIPO 'agregado'  --  el modelo compone, esto calcula
================================================================================

Implementa PRD 12.5: ningun numero que lea el asesor lo calculo el modelo.
Puerto generico del motor de agregacion que ya funcionaba en
soporte_wisphub.py (AGREGACIONES/consultar_agregado), ahora dirigido
enteramente por 'Herramienta' (nucleo/config/schema.py) en vez de un
diccionario Python hardcodeado por WispHub.

Alcance de esta version (ver plan)
-----------------------------------
- Agrupar solo funciona con filtros tipo 'enum' (los que declaran
  'valores'): son los unicos con una lista CERRADA de valores para recorrer
  con una llamada por valor. Pedir agrupar por un filtro tipo 'id' o 'texto'
  se rechaza con un motivo explicito -- no hay catalogo para enumerar sus
  valores todavia.
- Las advertencias de negocio especificas de un proveedor (ej. "facturas
  pendientes no es lo mismo que clientes morosos") NO se portaron: son
  conocimiento de negocio, no le corresponden a nucleo/. Solo se genera la
  advertencia generica de campos de texto libre y la de periodo por defecto.
================================================================================
"""

from __future__ import annotations

import re
from datetime import date, timedelta

import requests

from nucleo.herramientas.http import ErrorHerramientaHttp, headers_de, url_de

TIMEOUT_SEGUNDOS = 30
_FECHA_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ErrorAgregado(Exception):
    """Consulta agregada invalida o rechazada por la API."""


def _contar(herramienta, params: dict, tenant: str | None = None) -> int:
    """
    Una llamada, cero filas: se pide limit=1 y se lee 'count' del paginado.
    Contar 8.700 registros cuesta lo mismo que contar 3 -- el modelo nunca
    ve una fila.
    """
    p = dict(params)
    p["limit"] = 1
    r = requests.get(url_de(herramienta), headers=headers_de(herramienta, tenant),
                     params=p, timeout=TIMEOUT_SEGUNDOS)
    if r.status_code == 400:
        # La API suele explicar bien sus rechazos (rango de fechas muy
        # amplio, formato invalido) -- se propaga ese motivo en vez de uno
        # generico, para que el modelo pueda corregir la consulta.
        try:
            motivo = r.json().get("error") or r.text[:120]
        except ValueError:
            motivo = r.text[:120]
        raise ErrorAgregado(f"La API rechazo la consulta: {motivo}")
    r.raise_for_status()
    payload = r.json()
    if isinstance(payload, dict) and "count" in payload:
        return payload["count"]
    if isinstance(payload, list):
        return len(payload)
    raise ErrorAgregado("La API no devolvio un conteo reconocible.")


def _traducir_filtros(herramienta, argumentos_modelo: dict):
    """Solo los filtros DECLARADOS pasan (fail-closed) -- mismo principio que
    ya usa nucleo/modelo/motor.py para herramientas tipo 'http'."""
    params: dict = {}
    usados: dict = {}   # clave interna -> (FiltroVerificado, valor elegido)
    for clave, filtro in herramienta.filtros_verificados.items():
        valor = argumentos_modelo.get(clave)
        if valor is None:
            continue
        if filtro.tipo == "enum" and filtro.valores:
            if valor not in filtro.valores:
                continue
            params[filtro.param] = filtro.valores[valor]
        elif filtro.tipo == "id":
            if not str(valor).isdigit():
                continue
            params[filtro.param] = int(valor)
        else:
            params[filtro.param] = valor
        usados[clave] = (filtro, valor)
    return params, usados


def _parsear_periodo(texto: str, periodo_cfg) -> tuple[str, str]:
    """'AAAA-MM' o 'AAAA-MM-DD a AAAA-MM-DD' -> (desde, hasta) ISO."""
    texto = texto.strip()
    desde = hasta = None
    for sep in (" a ", "..", " hasta "):
        if sep in texto:
            desde, hasta = (t.strip() for t in texto.split(sep, 1))
            break
    if desde is None:
        if not re.match(r"^\d{4}-\d{2}$", texto):
            raise ErrorAgregado(f"Periodo '{texto}' no reconocido. Usa 'AAAA-MM' "
                                f"o 'AAAA-MM-DD a AAAA-MM-DD'.")
        anio, mes = (int(x) for x in texto.split("-"))
        desde = f"{anio:04d}-{mes:02d}-01"
        primero_mes_sig = date(anio + (mes == 12), (mes % 12) + 1, 1)
        hasta = (primero_mes_sig - timedelta(days=1)).isoformat()

    if not (_FECHA_ISO.match(desde) and _FECHA_ISO.match(hasta)):
        raise ErrorAgregado(f"Periodo '{texto}' no tiene formato de fecha valido.")
    d0, d1 = date.fromisoformat(desde), date.fromisoformat(hasta)
    if d1 < d0:
        raise ErrorAgregado("La fecha de 'hasta' es anterior a la de 'desde'.")
    if (d1 - d0).days > periodo_cfg.max_meses * 31:
        raise ErrorAgregado(f"El rango pedido supera el maximo permitido "
                            f"({periodo_cfg.max_meses} meses).")
    return desde, hasta


def _describir(herramienta, usados: dict, periodo_texto: str | None) -> str:
    """Redacta EN CODIGO como se interpreto la pregunta (PRD 12.5 regla 4) --
    a partir de los filtros que de verdad se enviaron, nunca de lo que el
    modelo dijo que quiso decir."""
    partes = [f"{clave} '{valor}'" for clave, (_, valor) in usados.items()]
    texto = (herramienta.etiqueta or herramienta.entidad or herramienta.nombre).capitalize()
    texto += (" con " + ", ".join(partes)) if partes else " (sin filtros)"

    if periodo_texto:
        campo = herramienta.periodo.por_defecto if herramienta.periodo else ""
        texto += f", por fecha de {campo} entre {periodo_texto}"
    elif herramienta.periodo:
        texto += f", {herramienta.periodo.nota_defecto}"
    return texto + "."


def ejecutar(herramienta, argumentos_modelo: dict, tenant: str | None = None) -> dict:
    argumentos_modelo = argumentos_modelo or {}

    try:
        base_params, usados = _traducir_filtros(herramienta, argumentos_modelo)

        periodo_texto = None
        if herramienta.periodo:
            crudo = argumentos_modelo.get("periodo")
            if crudo:
                desde, hasta = _parsear_periodo(str(crudo), herramienta.periodo)
                campo = herramienta.periodo.campos[herramienta.periodo.por_defecto]
                s0, s1 = herramienta.periodo.sufijos
                base_params[campo + s0] = desde
                base_params[campo + s1] = hasta
                periodo_texto = f"{desde} y {hasta}"

        avisos = []
        if not periodo_texto and herramienta.periodo:
            avisos.append(herramienta.periodo.advertencia_defecto)
        if any(f.tipo == "texto" for f, _ in usados.values()):
            avisos.append("Los filtros de texto libre admiten variantes de "
                          "escritura; un valor distinto pero equivalente "
                          "puede no coincidir.")

        interpretacion = _describir(herramienta, usados, periodo_texto)
        agrupar_por = argumentos_modelo.get("agrupar_por")

        if not agrupar_por:
            total = _contar(herramienta, base_params, tenant)
            salida = {"total": total, "interpretacion": interpretacion}
            if avisos:
                salida["advertencia"] = " ".join(avisos)
            return salida

        if agrupar_por not in herramienta.agrupar_por:
            return {"error": f"'{herramienta.nombre}' no puede agrupar por "
                             f"'{agrupar_por}'."}
        filtro_grupo = herramienta.filtros_verificados.get(agrupar_por)
        if not filtro_grupo or filtro_grupo.tipo != "enum" or not filtro_grupo.valores:
            return {"error": f"Agrupar por '{agrupar_por}' todavia no esta "
                             f"soportado: no hay un catalogo cerrado de sus "
                             f"valores para recorrer."}

        valores = list(filtro_grupo.valores.items())
        if len(valores) > herramienta.tope_grupos:
            return {"error": f"Agrupar por '{agrupar_por}' daria {len(valores)} "
                             f"grupos y el tope es {herramienta.tope_grupos}."}

        desglose = {}
        for etiqueta, valor_api in valores:
            params = dict(base_params)
            params[filtro_grupo.param] = valor_api
            desglose[etiqueta] = _contar(herramienta, params, tenant)

        salida = {
            "total": sum(desglose.values()),
            "desglose": desglose,
            "interpretacion": f"{interpretacion[:-1]}, desglosado por {agrupar_por}.",
        }
        if avisos:
            salida["advertencia"] = " ".join(avisos)
        return salida

    except (ErrorAgregado, ErrorHerramientaHttp) as e:
        return {"error": str(e)}
