# -*- coding: utf-8 -*-
"""
================================================================================
 GUARDA DEL CORPUS COMO HERRAMIENTA  --  una fuente no entra sin ser elegida
================================================================================

Que cambio, y por que
---------------------
El corpus se inyectaba en el historial ANTES de la primera llamada al modelo.
El modelo nunca decidia si lo queria: ya lo tenia puesto cuando llegaba a
decidir. No es que el corpus le ganara a las herramientas en una eleccion --
llegaba antes de que la eleccion existiera.

Lo que eso producia, medido el 03/09/2026 sobre el set etiquetado. Estos son
los cuatro fragmentos de MAYOR similitud entre los que NO debian entrar:

    0.488  "cuanto cuesta el plan mas caro"     -> lo responde una herramienta
    0.411  "cual es el saldo de la cedula X"    -> lo responde una herramienta
    0.367  "cuantos clientes activos tenemos"   -> lo responde una herramienta
    0.394  "a que hora abre la oficina"         -> no esta en el corpus

Y no se arregla con el umbral: la respuesta legitima mas baja (0.343) queda
POR DEBAJO del ruido mas alto (0.488). Verificado barriendo de 0.25 a 0.60.
Las distribuciones se solapan; no hay numero que las separe.

Lo que se fija aca
------------------
1. UN ROL CON LA HERRAMIENTA NO PRECARGA. Si precargara ademas de ofrecerla,
   el cambio no serviria de nada: el corpus seguiria entrando sin ser elegido
   y ademas costaria una llamada extra.

2. UN ROL SIN LA HERRAMIENTA SIGUE IGUAL QUE SIEMPRE. La condicion existe
   para migrar rol por rol y poder volver atras sin tocar codigo. Si esto se
   rompe, el cambio deja de ser reversible.

3. SIN RESULTADOS NO SE IMPROVISA. Cuando el corpus no cubre algo, la
   instruccion que vuelve prohibe explicitamente completar el procedimiento.
   Es el mismo criterio que ya rige en cargar_habilidad, y nace del mismo
   riesgo: un modelo que pide documentacion y recibe silencio tiende a
   inventar los pasos.

4. LO RECUPERADO SE PRESENTA COMO "LO MAS PARECIDO", NO COMO LA RESPUESTA.
   Superar el umbral es parecido semantico, no respaldo. Quien redacta tiene
   que poder abstenerse igual.

5. UN ROL DE CARA AL CLIENTE NO VE LA PROCEDENCIA. El codigo del documento
   interno es panorama de la empresa, no algo que un cliente deba leer --
   mismo criterio que ya aplicaba la precarga.

6. UN FALLO DE BUSQUEDA NO INVENTA UN CORPUS VACIO. Si la base o los
   embeddings fallan, hay que decirlo: tratar "no pude mirar" como "no hay
   nada" es la misma trampa que ya costo tiempo con TR-069.

Corre SIN BASE DE DATOS y sin red.
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nucleo.modelo import motor                                    # noqa: E402
from nucleo.recuperacion import busqueda                           # noqa: E402
from nucleo.recuperacion.busqueda import Fragmento                 # noqa: E402

fallos: list[str] = []


def afirmar(condicion: bool, que: str) -> None:
    print(f"  {'OK  ' if condicion else 'FALLA'}  {que}")
    if not condicion:
        fallos.append(que)


class RolFalso:
    def __init__(self, orientado_a="colaborador"):
        self.orientado_a = orientado_a


class ConfigFalsa:
    class identidad:
        slug = "tenant_de_prueba"

    def __init__(self, orientado_a="colaborador"):
        self.roles = {"rol_x": RolFalso(orientado_a)}


FRAGMENTO = Fragmento(codigo="G-GO-04", titulo="Guia de fallas",
                      version="01", contenido="Paso 1: revisar la ONT.",
                      similitud=0.71)


print("\n== 3-5. que devuelve, y como lo presenta ==")

busqueda_original = motor.recuperar

motor.recuperar = lambda *a, **k: ([FRAGMENTO], 0.71)
salida = motor._ejecutar_consulta_documentacion(
    ConfigFalsa(), "rol_x", {"pregunta": "como diagnostico una falla"})
afirmar(salida.get("encontrado") is True and salida["fragmentos"][0]["contenido"],
        "con resultados devuelve los fragmentos")
afirmar("mas parecido" in salida.get("instruccion_interna", "").lower(),
        "presenta lo recuperado como lo mas parecido, no como la respuesta")
afirmar("documento" in salida["fragmentos"][0],
        "un rol colaborador SI ve la procedencia del documento")

salida_cliente = motor._ejecutar_consulta_documentacion(
    ConfigFalsa("cliente_final"), "rol_x", {"pregunta": "que hago"})
afirmar("documento" not in salida_cliente["fragmentos"][0]
        and "titulo" not in salida_cliente["fragmentos"][0],
        "un rol de cara al cliente NO ve el codigo interno del documento")

motor.recuperar = lambda *a, **k: ([], 0.12)
motor.registrar_sin_resultados = lambda *a, **k: None
vacio = motor._ejecutar_consulta_documentacion(
    ConfigFalsa(), "rol_x", {"pregunta": "algo que no esta"})
afirmar(vacio.get("encontrado") is False,
        "sin resultados lo dice explicitamente")
afirmar("no improvises" in vacio.get("instruccion_interna", "").lower(),
        "sin resultados prohibe improvisar el procedimiento")


print("\n== 6. un fallo de busqueda no se confunde con corpus vacio ==")


def _revienta(*a, **k):
    raise RuntimeError("base caida")


motor.recuperar = _revienta
roto = motor._ejecutar_consulta_documentacion(
    ConfigFalsa(), "rol_x", {"pregunta": "cualquier cosa"})
afirmar(roto.get("error") == "BUSQUEDA_NO_DISPONIBLE",
        "un fallo devuelve error, no 'encontrado: false'")
afirmar(roto.get("encontrado") is None,
        "no dice que no encontro nada cuando no pudo mirar")

sin_pregunta = motor._ejecutar_consulta_documentacion(ConfigFalsa(), "rol_x", {})
afirmar(sin_pregunta.get("error") == "FALTA_PREGUNTA",
        "sin pregunta devuelve error propio, no busca a ciegas")

motor.recuperar = busqueda_original


print("\n== 1-2. la precarga se apaga sola, y solo donde corresponde ==")
fuente = Path("nucleo/modelo/motor.py").read_text(encoding="utf-8")
afirmar('if any(getattr(h, "consulta_documentacion", False) for h in herramientas):'
        in fuente,
        "la precarga se saltea cuando el rol declara la herramienta")
afirmar("elif not _corpus_es_herramienta:" in fuente,
        "el registro de 'sin resultados' no corre si no se busco nada")

# El default del campo es lo que hace reversible el cambio: un tenant que no
# lo declara sigue funcionando exactamente igual que antes.
esquema = Path("nucleo/config/schema.py").read_text(encoding="utf-8")
afirmar("consulta_documentacion: bool = False" in esquema,
        "el default es False: un rol que no la declara precarga como siempre")


print("\n== y en la config real de rapilink ==")
import yaml                                                        # noqa: E402
cfg = yaml.safe_load(Path("tenants/rapilink.config.yaml").read_text(encoding="utf-8"))
herr = {h["nombre"]: h for h in cfg["herramientas"]}
doc = herr.get("consultar_documentacion")
afirmar(doc is not None and doc.get("consulta_documentacion") is True,
        "la herramienta esta declarada")
afirmar(doc and doc.get("solo_lectura") is True,
        "es de solo lectura")
afirmar(doc and "NO la uses" in doc.get("descripcion", ""),
        "la descripcion dice cuando NO usarla, no solo que hace")

# Un rol que puede recuperar corpus y no tiene la herramienta seguiria
# precargando -- estado valido, pero conviene saber cual es cual.
con_doc = [n for n, r in (cfg.get("roles") or {}).items()
           if "consultar_documentacion" in (r.get("puede_consultar") or [])]
afirmar(len(con_doc) >= 6,
        f"los roles que la declaran son {len(con_doc)}: {', '.join(sorted(con_doc))}")


print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es):")
    for f in fallos:
        print(f"  - {f}")
    raise SystemExit(1)
print("[OK] El corpus entra solo cuando el modelo lo pide, y el cambio es reversible.")
