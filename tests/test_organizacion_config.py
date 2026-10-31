# -*- coding: utf-8 -*-
"""
================================================================================
 LA ORGANIZACION DE LA EMPRESA ES CONFIGURACION  --  P1.1
================================================================================

Por que existe
--------------
La oficina virtual dibujaba SEIS departamentos y los seis estaban escritos en
el frontend. Se midio el 30/10/2026 de donde salian: de agrupar el campo 'area'
de los roles configurados. O sea que la pantalla no mostraba la organizacion de
la empresa -- mostraba los GRUPOS DE SUS AGENTES.

Tres consecuencias lo prueban, y las tres se comprueban aqui:

  * un departamento sin ningun agente NO EXISTIA. Recursos Humanos y Auditoria
    son departamentos reales de un proveedor de internet y no hay un agente que
    los represente.
  * dos etiquetas de rol que son UN departamento salian como dos salas.
  * la siguiente empresa necesitaba una sesion de codigo.

Que afirma esta prueba, y que NO
---------------------------------
Afirma el EFECTO de las validaciones: que cada invariante RECHAZA. Una prueba
que dijera "el modelo tiene un campo 'organizacion'" no probaria nada -- es
exactamente la forma de prueba que CLAUDE.md 6 llama "una prueba que dice que
algo existe no prueba que funcione", y que el 09/09/2026 sobrevivio intacta a
una inversion completa de la conducta.

Y afirma que el FIXTURE DEL FRONTEND sigue siendo lo que el motor sirve. Esa
comprobacion existe por la leccion de E1: su prueba COPIABA la consulta en vez
de importar el modulo, asi que la funcion podia no funcionar con la prueba en
verde. El fixture de la pantalla es una copia por necesidad --vitest no puede
importar Python-- y entonces hace falta algo que la mantenga honesta.

Como se corre
-------------
No necesita base ni red.

    py -3.13 tests/test_organizacion_config.py
"""
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from pydantic import ValidationError                                 # noqa: E402

from nucleo.config.organizacion import (ORGANIZACION_POR_DEFECTO,    # noqa: E402
                                        PLANTILLAS_DE_SALA,
                                        organizacion_de)
from nucleo.config.schema import (Departamento, EspacioDeTrabajo,    # noqa: E402
                                  Ocupacion, Organizacion, Piso,
                                  cargar_config)

FIXTURE = (RAIZ / "django-crm" / "frontend" / "src" / "lib" / "centro-mando" /
           "__fixtures__" / "organizacion-por-defecto.json")
FIXTURE_PLANTILLAS = (RAIZ / "django-crm" / "frontend" / "src" / "lib" /
                      "centro-mando" / "__fixtures__" / "plantillas-del-motor.json")

fallos: list[str] = []


def comprobar(ok: bool, que: str) -> None:
    print(f"  [{'OK' if ok else 'FALLA'}]  {que}")
    if not ok:
        fallos.append(que)


def rechaza(que: str, construir) -> None:
    """Afirma que una configuracion invalida NO se puede construir."""
    try:
        construir()
    except ValidationError:
        comprobar(True, f"RECHAZA: {que}")
        return
    except ValueError:
        comprobar(True, f"RECHAZA: {que}")
        return
    comprobar(False, f"RECHAZA: {que}  <-- la acepto")


def _depto(**kw):
    base = dict(id="x", rotulo="X", piso=1, plantilla="tecnica")
    base.update(kw)
    return Departamento(**base)


# =============================================================================
#  1. LA ESTRUCTURA POR DEFECTO ES LA APROBADA
# =============================================================================
def estructura_por_defecto() -> None:
    print("\n[1] la estructura por defecto del producto")
    O = ORGANIZACION_POR_DEFECTO

    comprobar(len(O.departamentos) == 8,
              f"son ocho departamentos (son {len(O.departamentos)})")
    comprobar([d.rotulo for d in O.departamentos] == [
        "NOC y Redes", "Operaciones de Campo", "Atención al Cliente",
        "Comercial y Marketing", "Finanzas y Cartera", "Administración",
        "Recursos Humanos", "Auditoría y Cumplimiento"],
        "y son los ocho aprobados, en orden")

    comprobar([p.nivel for p in O.pisos] == [3, 2, 1], "tres pisos declarados")
    reparto = {}
    for sala in [*O.departamentos, *O.espacios]:
        reparto[sala.piso] = reparto.get(sala.piso, 0) + 1
    comprobar(reparto == {3: 3, 2: 3, 1: 5},
              f"el reparto es 3/3/5 (es {reparto})")

    comprobar([e.id for e in O.espacios] == ["direccion", "sala_reuniones", "recepcion"],
              "los tres espacios complementarios estan")
    #  UN ESPACIO NO ES UN DEPARTAMENTO. La decision de producto lo dice con
    #  estas palabras: "no deben convertirse automaticamente en agentes
    #  ejecutables".
    comprobar(all(not getattr(e, "areas", []) for e in O.espacios),
              "y ninguno reclama un area")
    comprobar(not hasattr(O.espacios[0], "ocupaciones"),
              "ni puede declarar quien lo ocupa")

    #  DEPARTAMENTOS SIN NINGUN AGENTE. Es el caso que la estructura deducida
    #  de los agentes no podia representar.
    vacios = [d.id for d in O.departamentos if not [o for o in d.ocupaciones if o.agente]]
    comprobar(set(vacios) == {"campo", "recursos_humanos", "auditoria"},
              f"tres departamentos existen SIN agente ({vacios})")

    sentados = [o.agente for d in O.departamentos for o in d.ocupaciones if o.agente]
    comprobar(len(sentados) == 6, f"se sientan seis agentes (son {len(sentados)})")
    capacidades = [c for d in O.departamentos for c in d.capacidades]
    comprobar(sorted(capacidades) == ["administracion", "facturacion", "soporte"],
              "y las tres capacidades se declaran como tales, sin escritorio")

    #  DOS ETIQUETAS DE ROL, UN DEPARTAMENTO.
    at = next(d for d in O.departamentos if d.id == "atencion_cliente")
    comprobar("Soporte Técnico" in at.areas and "Atención al Cliente" in at.areas,
              "'Soporte Tecnico' y 'Atencion al Cliente' caen en el MISMO departamento")


# =============================================================================
#  2. EL MOTOR NO CONOCE A NINGUNA EMPRESA
# =============================================================================
def sin_empresas() -> None:
    print("\n[2] nada de la estructura por defecto nombra a una empresa")
    texto = json.dumps(ORGANIZACION_POR_DEFECTO.model_dump(mode="json"),
                       ensure_ascii=False).lower()
    #  Los slugs que existen hoy. La guarda grande es
    #  tests/test_nucleo_sin_tenants.py; esto es la comprobacion local, al lado
    #  del dato.
    for prohibida in ["rapilink", "wisphub", "smartolt", "bottlecrm"]:
        comprobar(prohibida not in texto, f"no aparece '{prohibida}'")
    #  Y la mutacion: el mismo control SI encuentra la palabra cuando esta.
    comprobar("rapilink" in json.dumps({"x": "rapilink"}).lower(),
              "y el control encontraria la palabra si estuviera")


# =============================================================================
#  3. CADA INVARIANTE RECHAZA  (el efecto, no la presencia)
# =============================================================================
def invariantes() -> None:
    print("\n[3] las validaciones rechazan lo que haria mentir a la pantalla")

    rechaza("dos salas con el mismo id",
            lambda: Organizacion(departamentos=[_depto(id="a"), _depto(id="a")]))

    rechaza("un espacio con el id de un departamento",
            lambda: Organizacion(
                departamentos=[_depto(id="a")],
                espacios=[EspacioDeTrabajo(id="a", rotulo="A", piso=1,
                                           plantilla="reuniones")]))

    rechaza("una sala en un piso que no esta declarado",
            lambda: Organizacion(pisos=[Piso(nivel=1)],
                                 departamentos=[_depto(id="a", piso=7)]))

    rechaza("dos pisos con el mismo nivel",
            lambda: Organizacion(pisos=[Piso(nivel=1), Piso(nivel=1)],
                                 departamentos=[_depto(id="a")]))

    rechaza("un area reclamada por DOS departamentos",
            lambda: Organizacion(departamentos=[
                _depto(id="a", areas=["Atención al Cliente"]),
                _depto(id="b", areas=["atencion al cliente"])]))

    rechaza("el mismo agente sentado en dos departamentos",
            lambda: Organizacion(departamentos=[
                _depto(id="a", ocupaciones=[Ocupacion(puesto="principal", agente="z")]),
                _depto(id="b", ocupaciones=[Ocupacion(puesto="p1", agente="z")])]))

    rechaza("el mismo agente sentado dos veces en la misma sala",
            lambda: _depto(ocupaciones=[Ocupacion(puesto="principal", agente="z"),
                                        Ocupacion(puesto="principal", agente="w")]))

    rechaza("un agente que es capacidad Y ocupa un puesto",
            lambda: Organizacion(departamentos=[
                _depto(id="a", capacidades=["z"],
                       ocupaciones=[Ocupacion(puesto="principal", agente="z")])]))

    rechaza("un id con mayusculas o espacios",
            lambda: _depto(id="NOC y Redes"))

    rechaza("un acento que no es #rrggbb",
            lambda: _depto(acento="rojo"))

    rechaza("una sala sin plantilla",
            lambda: Departamento(id="a", rotulo="A", piso=1, plantilla=""))

    rechaza("un campo que nadie declaro (extra='forbid')",
            lambda: _depto(subdepartamentos=["x"]))

    print("\n[3b] y lo VALIDO se acepta")
    try:
        #  Un area escrita de dos formas en el MISMO departamento es legitima:
        #  es justo el puente entre los dos vocabularios.
        Organizacion(departamentos=[_depto(id="a", areas=["Atención al Cliente",
                                                          "atencion_cliente"])])
        comprobar(True, "dos escrituras del mismo area en el MISMO departamento")
    except Exception as e:                                           # noqa: BLE001
        comprobar(False, f"rechazo algo valido: {type(e).__name__}: {e}")

    try:
        #  Una organizacion de una sola planta no tiene por que declararla.
        Organizacion(departamentos=[_depto(id="a")])
        comprobar(True, "una organizacion sin pisos declarados")
    except Exception as e:                                           # noqa: BLE001
        comprobar(False, f"rechazo algo valido: {type(e).__name__}: {e}")

    try:
        #  Un puesto declarado y SIN agente: la silla existe y esta libre.
        _depto(ocupaciones=[Ocupacion(puesto="p1", nombre="Cobranza")])
        comprobar(True, "un puesto renombrado y vacio")
    except Exception as e:                                           # noqa: BLE001
        comprobar(False, f"rechazo algo valido: {type(e).__name__}: {e}")


# =============================================================================
#  4. CANTIDADES VARIABLES: ESTO ES UN PRODUCTO, NO UNA PANTALLA
# =============================================================================
def cantidades_variables() -> None:
    print("\n[4] empresas de otros tamanios")

    chica = Organizacion(
        pisos=[Piso(nivel=1, rotulo="Planta")],
        departamentos=[_depto(id=f"d{i}", piso=1, areas=[f"a{i}"]) for i in range(4)])
    comprobar(len(chica.departamentos) == 4 and len(chica.pisos) == 1,
              "cuatro departamentos en una sola planta")

    grande = Organizacion(
        pisos=[Piso(nivel=n) for n in range(1, 6)],
        departamentos=[_depto(id=f"d{i}", piso=(i % 5) + 1, areas=[f"a{i}"])
                       for i in range(15)])
    comprobar(len(grande.departamentos) == 15 and len(grande.pisos) == 5,
              "quince departamentos en cinco niveles")

    alta = Organizacion(pisos=[Piso(nivel=n) for n in range(1, 13)],
                        departamentos=[_depto(id="a", piso=12)])
    comprobar(len(alta.pisos) == 12, "doce pisos: nada esta acotado a tres")

    #  Una organizacion vacia es "no declarada", y lo dice.
    comprobar(Organizacion().declarada() is False,
              "una organizacion vacia NO se declara declarada")
    comprobar(chica.declarada() is True, "una con departamentos si")


# =============================================================================
#  5. LA PROCEDENCIA, Y QUE UNA CONFIG YA CARGADA SIGUE CARGANDO
# =============================================================================
def procedencia() -> None:
    print("\n[5] de donde salio la estructura, y compatibilidad")

    yamls = sorted((RAIZ / "tenants").glob("*.config.yaml"))
    reales = [y for y in yamls if "example" not in y.name]
    if not reales:
        comprobar(False, "no hay ningun YAML de tenant para comprobar")
        return

    #  Una config REAL del repositorio, que NO declara organizacion. Es la
    #  comprobacion de compatibilidad: agregar el campo no puede volver
    #  incargable lo que ya estaba.
    config = cargar_config(reales[0])
    comprobar(True, f"'{reales[0].name}' sigue cargando con el campo nuevo")

    doc = organizacion_de(config)
    if config.organizacion.declarada():
        comprobar(doc["origen"] == "declarada",
                  "el YAML ya declara organizacion -> origen 'declarada'")
    else:
        comprobar(doc["origen"] == "por_defecto",
                  "no la declara -> origen 'por_defecto', y se dice")
        comprobar(len(doc["departamentos"]) == 8,
                  "y se sirve la estructura generica del producto")

    #  Y con una organizacion declarada, se sirve ESA y no la de por defecto.
    config.organizacion = Organizacion(
        pisos=[Piso(nivel=1)],
        departamentos=[_depto(id="unico", rotulo="Único", areas=["Operaciones"])])
    doc2 = organizacion_de(config)
    comprobar(doc2["origen"] == "declarada", "declarada -> origen 'declarada'")
    comprobar(len(doc2["departamentos"]) == 1,
              "y gana la de la empresa, no la del producto")
    comprobar(doc2["departamentos"][0]["id"] == "unico", "con su propio contenido")


# =============================================================================
#  6. EL FIXTURE DE LA PANTALLA NO SE QUEDA VIEJO
# =============================================================================
def fixture_al_dia() -> None:
    print("\n[6] el fixture del frontend es lo que el motor sirve")
    #  POR QUE ESTA COMPROBACION. vitest no puede importar Python, asi que la
    #  prueba de la pantalla usa una copia del documento. Copiar es exactamente
    #  lo que dejo a E1 sin probar: su prueba copiaba la consulta en vez de
    #  importar el modulo, y la funcion no funcionaba con la prueba en verde.
    #  Si el fixture se queda viejo, la pantalla pasaria sus pruebas contra una
    #  estructura que el motor ya no sirve.
    if not FIXTURE.exists():
        comprobar(False, f"falta el fixture: {FIXTURE}")
        return
    guardado = json.loads(FIXTURE.read_text(encoding="utf-8"))
    esperado = {"origen": "por_defecto",
                **ORGANIZACION_POR_DEFECTO.model_dump(mode="json")}
    igual = guardado == esperado
    comprobar(igual, "el fixture coincide byte a byte con lo que sirve el motor")
    if not igual:
        print("        Para regenerarlo:")
        print("        py -3.13 cli/exportar_organizacion.py")

    #  EL CATALOGO DE SALAS, que es el otro lado del mismo riesgo. El motor
    #  sirve los NOMBRES y el frontend tiene la GEOMETRIA: son dos listas en
    #  dos lenguajes, y separadas el formulario ofrece una sala que la oficina
    #  dibuja como «Sala sin plantilla». Degrada visible, pero es un defecto.
    if not FIXTURE_PLANTILLAS.exists():
        comprobar(False, f"falta el fixture del catalogo: {FIXTURE_PLANTILLAS}")
        return
    catalogo = json.loads(FIXTURE_PLANTILLAS.read_text(encoding="utf-8"))
    comprobar(catalogo == PLANTILLAS_DE_SALA,
              "el fixture del catalogo de salas es el que sirve el motor")

    #  Y el catalogo mismo. Un nombre repetido haria que dos salas distintas se
    #  guardaran con el mismo identificador en la configuracion de la empresa.
    nombres = [p["nombre"] for p in PLANTILLAS_DE_SALA]
    comprobar(len(set(nombres)) == len(nombres),
              "ningun nombre de plantilla se repite")
    comprobar(all(re.fullmatch(r"[a-z][a-z0-9_]*", n) for n in nombres),
              "todo nombre de plantilla es un id valido para el esquema")
    comprobar(all(p["puestos"] >= 1 for p in PLANTILLAS_DE_SALA),
              "ninguna plantilla ofrece cero puestos")

    #  EL NOMBRE DE UNA VARIANTE PROMETE UN NUMERO. Si prometiera 10 y trajera
    #  7, la empresa elegiria su sala por un numero que no es el que recibe, y
    #  el sintoma seria un escritorio de menos que nadie sabria explicar.
    variantes = [p for p in PLANTILLAS_DE_SALA if re.search(r"_\d+$", p["nombre"])]
    comprobar(len(variantes) > 0,
              f"el catalogo ofrece tamanos ({len(variantes)} variantes)")
    comprobar(all(int(p["nombre"].rsplit("_", 1)[1]) == p["puestos"]
                  for p in variantes),
              "el nombre de cada variante dice cuantos puestos tiene")


def main() -> int:
    estructura_por_defecto()
    sin_empresas()
    invariantes()
    cantidades_variables()
    procedencia()
    fixture_al_dia()

    print("\n" + "=" * 70)
    if fallos:
        print(f"[FALLA] {len(fallos)} comprobacion(es):")
        for f in fallos:
            print(f"   - {f}")
        return 1
    print("[OK] la organizacion es configuracion, y sus invariantes rechazan.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
