# -*- coding: utf-8 -*-
"""
================================================================================
 TEXTOS DEL TRASPASO Y CIERRE POR INACTIVIDAD, EDITABLES  --  12/11/2026
================================================================================

    py -3.13 tests/test_traspaso_editable.py

POR QUE EXISTE
--------------
Hasta el 12/11/2026 'escalamiento.*', 'cierre_inactivas_ia' y
'limites.horas_inactividad_cierra' solo se cambiaban por YAML (CLAUDE.md §3.3;
auditoria del menu, §2 Administrar). Ahora hay GET y dos PUT en
/configuracion/traspaso. Lo que se afirma es el EFECTO:

  - lo que se guarda es lo que el motor le dice al cliente
    (api._mensaje_de_escalada), no solo que la clave cambie;
  - lo invalido no se escribe y la version no se mueve;
  - la version sube SOLO si el documento cambio: corre el _editar() REAL
    contra una base falsa en memoria que responde las tres sentencias que
    _editar ejecuta (select for update, update, insert del historial). Lo
    que se sustituye es el transporte, no la decision.

Sin base, sin red. La decision congelada de CLAUDE.md §12 (un solo texto para
"ya escalada") se protege con un caso propio.
================================================================================
"""

from __future__ import annotations

import contextlib
import copy
import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
os.environ["PERMITIR_CONFIG_SIN_DESPLEGAR"] = "1"   # la guarda de git no es lo que se prueba

from nucleo.canales import api                                      # noqa: E402
from nucleo.config import cargar_config, editor                     # noqa: E402
from nucleo.config.schema import TenantConfig                       # noqa: E402
from nucleo.persistencia import db as persistencia_db               # noqa: E402

fallos: list[str] = []


def comprobar(condicion: bool, que: str) -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}")
    if not condicion:
        fallos.append(que)


def documento() -> dict:
    """El volcado del primer tenants/*.config.yaml. No se nombra ninguno."""
    yamls = [p for p in sorted((RAIZ / "tenants").glob("*.config.yaml"))
             if not p.name.startswith("tenant.config.example")]
    return json.loads(json.dumps(cargar_config(yamls[0]).model_dump(mode="json")))


TENANT = "prueba"


def base_nueva(doc: dict) -> dict:
    return {"config": doc, "version": 7, "historial": []}


base = base_nueva(documento())


class _Cursor:
    def __init__(self):
        self._fila = None

    def execute(self, sql, params=()):
        s = " ".join(sql.split()).lower()
        if s.startswith("select config, config_version"):
            self._fila = {"config": copy.deepcopy(base["config"]),
                          "config_version": base["version"]}
        elif s.startswith("update asistente.tenant_config"):
            base["config"] = json.loads(params[0])
            base["version"] += 1
            self._fila = {"config_version": base["version"]}
        elif s.startswith("insert into asistente.tenant_config_historial"):
            base["historial"].append(params[1])
        else:
            raise AssertionError(f"sentencia inesperada: {s[:60]}")

    def fetchone(self):
        return self._fila


@contextlib.contextmanager
def _sesion_falsa(_tenant):
    # Igual que la real: si algo lanza adentro, no se "confirma" nada. Como
    # la base falsa solo cambia en el update, y el update solo ocurre despues
    # de validar, una excepcion antes deja 'base' intacta.
    yield _Cursor(), "org-1"


reales = (persistencia_db.sesion, api._config_de, api.olvidar_config)
persistencia_db.sesion = _sesion_falsa
api._config_de = lambda _t: TenantConfig(**base["config"])
api.olvidar_config = lambda _t: None


def textos_validos(**cambios) -> dict:
    esc = base["config"]["escalamiento"]
    t = {"tenant": TENANT,
         "mensaje": "Te paso con un asesor de la empresa, ya te escribe.",
         "mensajes_por_motivo": dict(esc.get("mensajes_por_motivo") or {}),
         "mensaje_ya_escalada": "Tu caso ya está con un asesor. Apenas lo revise te escribe.",
         "mensaje_si_falla": "No pude registrar tu caso. Escribime de nuevo en un rato.",
         "frases_de_traspaso": ["un asesor", "te paso con"]}
    t.update(cambios)
    return t


try:
    print()
    print("=" * 78)
    print("  TEXTOS DEL TRASPASO Y CIERRE POR INACTIVIDAD")
    print("=" * 78)

    comprobar({"escalamiento", "cierre_inactivas_ia", "limites"} <= set(editor.SECCIONES_EDITABLES),
              "las tres secciones estan protegidas de una carga del YAML (SECCIONES_EDITABLES)")

    with api.app.test_client() as c:
        print("\n-- lectura --")
        r = c.get(f"/configuracion/traspaso?tenant={TENANT}")
        d = r.get_json() or {}
        comprobar(r.status_code == 200 and set(d) >= {"textos", "motivos", "cierre", "sin_gestion_horas"},
                  f"el GET trae textos, motivos, cierre y el umbral de la Bandeja ({r.status_code})")
        motivos = d.get("motivos") or []
        comprobar(len(motivos) > 0 and motivos == base["config"]["escalamiento"]["activar_si"],
                  "los motivos son los de 'activar_si', en orden")
        comprobar(set(d.get("textos", {})) == set(editor.CLAVES_TEXTOS_TRASPASO),
                  "el GET devuelve exactamente las claves que el PUT exige")

        print("\n-- textos: guardar --")
        motivo_sin_texto = next((m for m in motivos
                                 if m not in (base["config"]["escalamiento"].get("mensajes_por_motivo") or {})),
                                None)
        v0 = base["version"]
        r = c.put("/configuracion/traspaso/textos", json=textos_validos())
        comprobar(r.status_code == 200, f"un juego valido se guarda ({r.status_code}: {(r.get_json() or {}).get('error')})")
        comprobar(base["version"] == v0 + 1, "y la version sube una vez")
        comprobar(len(base["historial"]) == 1, "y queda una copia en el historial")
        cfg = TenantConfig(**base["config"])
        if motivo_sin_texto:
            comprobar(api._mensaje_de_escalada(cfg, motivo_sin_texto)
                      == "Te paso con un asesor de la empresa, ya te escribe.",
                      "EFECTO: un motivo sin texto propio le dice al cliente el general nuevo")
        comprobar(api._mensaje_de_escalada(cfg, "motivo_que_no_existe")
                  == "Te paso con un asesor de la empresa, ya te escribe.",
                  "EFECTO: un motivo desconocido tambien cae al general")

        r = c.put("/configuracion/traspaso/textos", json=textos_validos())
        comprobar(r.status_code == 200 and base["version"] == v0 + 1,
                  "guardar lo mismo otra vez NO sube la version")

        un_motivo = motivos[0]
        por_motivo = {un_motivo: "  Texto propio de este motivo.  "}
        r = c.put("/configuracion/traspaso/textos", json=textos_validos(mensajes_por_motivo=por_motivo))
        cfg = TenantConfig(**base["config"])
        comprobar(r.status_code == 200 and api._mensaje_de_escalada(cfg, un_motivo)
                  == "Texto propio de este motivo.",
                  "EFECTO: el texto de un motivo es lo que recibe ese motivo, recortado")
        r = c.put("/configuracion/traspaso/textos",
                  json=textos_validos(mensajes_por_motivo={un_motivo: "   "}))
        cfg = TenantConfig(**base["config"])
        comprobar(un_motivo not in cfg.escalamiento.mensajes_por_motivo
                  and api._mensaje_de_escalada(cfg, un_motivo) == cfg.escalamiento.mensaje,
                  "vaciar el texto de un motivo lo devuelve al general (no se guarda vacio)")

        r = c.put("/configuracion/traspaso/textos",
                  json=textos_validos(frases_de_traspaso=["Un asesor", "un   asesor", "", "te paso con"]))
        comprobar(TenantConfig(**base["config"]).escalamiento.frases_de_traspaso == ["Un asesor", "te paso con"],
                  "las frases se limpian y no se repiten (mayusculas y espacios no las separan)")

        print("\n-- textos: lo que no se guarda --")
        antes, v_antes = copy.deepcopy(base["config"]), base["version"]
        malos = [
            ("mensaje general vacio", textos_validos(mensaje="   "), "general"),
            ("motivo que no dispara traspasos", textos_validos(mensajes_por_motivo={"inventado": "x"}), "inventado"),
            ("'ya escalada' igual al anuncio (§12)",
             textos_validos(mensaje_ya_escalada=" te paso con UN asesor de la empresa, ya te escribe. "), "anuncio"),
            ("'ya escalada' igual al texto de un motivo",
             textos_validos(mensajes_por_motivo={un_motivo: "Hola, ya te paso."},
                            mensaje_ya_escalada="hola, ya te paso."), "anuncio"),
            ("frase de traspaso demasiado corta", textos_validos(frases_de_traspaso=["un"]), "corta"),
            ("texto de mas de 1000 caracteres", textos_validos(mensaje_si_falla="x" * 1001), "1000"),
            ("frases que no son lista", textos_validos(frases_de_traspaso="un asesor"), "lista"),
        ]
        for que, cuerpo, pista in malos:
            r = c.put("/configuracion/traspaso/textos", json=cuerpo)
            err = (r.get_json() or {}).get("error", "")
            comprobar(r.status_code == 400 and pista in err, f"rechaza: {que} ({r.status_code}, '{err[:70]}')")
        sin_clave = textos_validos()
        sin_clave.pop("frases_de_traspaso")
        r = c.put("/configuracion/traspaso/textos", json=sin_clave)
        comprobar(r.status_code == 400 and "frases_de_traspaso" in (r.get_json() or {}).get("error", ""),
                  "una clave que no vino NO se toma como 'borrala'")
        comprobar(base["config"] == antes and base["version"] == v_antes,
                  "ningun rechazo escribio nada ni movio la version")

        print("\n-- cierre por inactividad --")
        base["config"]["cierre_inactivas_ia"] = {"habilitado": False, "rollout_cutoff": None,
                                                 "backfill_habilitado": False, "backfill_lote": 10}
        base["config"]["sin_gestion_horas"] = None

        def cierre(**k):
            cuerpo = {"tenant": TENANT, "habilitado": True, "horas_inactividad_cierra": 24,
                      "backfill_habilitado": False, "backfill_lote": 10}
            cuerpo.update(k)
            return c.put("/configuracion/traspaso/cierre", json=cuerpo)

        v = base["version"]
        r = cierre()
        d = r.get_json() or {}
        comprobar(r.status_code == 200 and d["cierre"]["habilitado"] is True
                  and d["cierre"]["horas_inactividad_cierra"] == 24, f"encender con 24 h se guarda ({r.status_code})")
        corte = d["cierre"]["rollout_cutoff"]
        comprobar(bool(corte), "al encender sin corte, el corte se fija: sin el no se cerraria NADA")
        cfg = TenantConfig(**base["config"])
        comprobar(cfg.limites.horas_inactividad_cierra == 24 and cfg.cierre_inactivas_ia.habilitado,
                  "EFECTO: lo que lee el barrido (limites + cierre_inactivas_ia) es lo guardado")
        comprobar(base["version"] == v + 1, "la version sube una vez")

        # Un corte de otro dia: si se fijara de nuevo en cada guardado, el
        # segundo de diferencia no alcanzaria para verlo (mutacion medida).
        corte = "2026-01-01T00:00:00Z"
        base["config"]["cierre_inactivas_ia"]["rollout_cutoff"] = corte
        corte = TenantConfig(**base["config"]).cierre_inactivas_ia.rollout_cutoff.isoformat()
        r = cierre(horas_inactividad_cierra=48)
        comprobar(r.status_code == 200 and (r.get_json() or {})["cierre"]["rollout_cutoff"] == corte,
                  "cambiar las horas NO mueve el corte (moverlo convertiria backlog en flujo)")
        r = cierre(habilitado=False)
        comprobar((r.get_json() or {})["cierre"]["rollout_cutoff"] == corte,
                  "apagar tampoco lo borra")
        v = base["version"]
        r = cierre(habilitado=False)
        comprobar(r.status_code == 200 and base["version"] == v, "guardar lo mismo no sube la version")

        antes, v_antes = copy.deepcopy(base["config"]), base["version"]
        base["config"]["sin_gestion_horas"] = 36
        antes["sin_gestion_horas"] = 36
        for que, k, pista in [
            ("encender sin plazo", {"horas_inactividad_cierra": None}, "plazo"),
            ("cerrar antes de que la Bandeja la muestre (espejo de la Bandeja)",
             {"horas_inactividad_cierra": 24}, "36"),
            ("0 horas", {"horas_inactividad_cierra": 0}, "entre"),
            ("mas de 720 horas", {"horas_inactividad_cierra": 721}, "entre"),
            ("lote 0", {"backfill_lote": 0}, "lote"),
            ("'habilitado' como texto", {"habilitado": "si"}, "true o false"),
            ("horas que no son numero", {"horas_inactividad_cierra": "un dia"}, "enteros"),
        ]:
            r = cierre(**k)
            err = (r.get_json() or {}).get("error", "")
            comprobar(r.status_code == 400 and pista in err, f"rechaza: {que} ({r.status_code}, '{err[:70]}')")
        r = c.put("/configuracion/traspaso/cierre", json={"tenant": TENANT, "habilitado": False})
        comprobar(r.status_code == 400, "sin las cuatro claves no se guarda")
        comprobar(base["config"] == antes and base["version"] == v_antes,
                  "ningun rechazo del cierre escribio nada")

        r = cierre(horas_inactividad_cierra=None, habilitado=False)
        comprobar(r.status_code == 200
                  and TenantConfig(**base["config"]).limites.horas_inactividad_cierra is None,
                  "apagado, el plazo se puede quitar (las conversaciones no se cierran por tiempo)")
finally:
    persistencia_db.sesion, api._config_de, api.olvidar_config = reales

print()
if fallos:
    print(f"FALLARON {len(fallos)}:")
    for f in fallos:
        print("  -", f)
    sys.exit(1)
print("Todo en verde.")
