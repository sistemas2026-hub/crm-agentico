# -*- coding: utf-8 -*-
"""
================================================================================
 GUARDA DE ALINEACION GIT  --  que ninguna de las DOS puertas que escriben
 tenant_config lo haga con la copia local desincronizada del remoto, en
 NINGUNA direccion
================================================================================

Por que existe, y por que cambio de lugar (Fase #20.6.4)
----------------------------------------------------------
Hay dos escritores de 'asistente.tenant_config': 'cli/cargar_config.py::cargar()'
(el camino del YAML) y 'nucleo/config/editor.py::_editar()' (el camino de la
interfaz). Los dos validan contra ESTA copia local antes de guardar -- no
contra el codigo REALMENTE desplegado -- y eso ya causo produccion rota dos
veces el mismo dia (04/09/2026): una vez por cada puerta.

La Fase #20.4 agrego la deteccion de la direccion que faltaba (copia
ATRASADA) en 'cli/cargar_config.py'. Ese mismo dia, en paralelo y sin saberlo,
otro colaborador movio la deteccion de la direccion que ya existia (copia
ADELANTADA) a 'nucleo/config/editor.py', para que las dos puertas compartieran
una sola implementacion -- y de paso dejo un bug real: 'cargar_config.py'
llamaba a 'editor.commits_sin_empujar()' sin tener importado el nombre
'editor', un NameError reproducido empiricamente en la Fase #20.6.3.

La Fase #20.6.4 integra las dos cosas: TODA la deteccion (las dos direcciones)
vive ahora en 'nucleo/config/editor.py', como una funcion de puros datos
(‘problemas_de_alineacion_git()’, sin excepcion propia), porque una puerta
corre como CLI (SystemExit tiene sentido) y la otra corre DENTRO del proceso
servido (SystemExit lo tumbaria entero) -- cada puerta arma su propia
excepcion con la misma lista de problemas.

Lo que se fija aca
-------------------
1. 'problemas_de_alineacion_git()': local=remoto -> lista vacia.
2. local ADELANTADO -> lista con el problema, nombra la condicion.
3. local ATRASADO -> lista con el problema, nombra la condicion.
4. las dos a la vez -> lista con AMBOS problemas.
5. estado indeterminado (atras=None) -> se trata como bloqueo, no como 0.
6. 'commits_atrasados()' por si sola: exito, fallo, excepcion, salida invalida.
7. '_editar()' bloquea (ErrorEdicion) cuando hay problemas, SIN llegar a abrir
   una sesion de base -- y permite (llega a intentar abrir sesion) cuando no
   los hay.
8. 'cargar()' bloquea (SystemExit) cuando hay problemas, y permite (corre
   hasta el final) cuando no los hay -- con la conexion y el cursor
   sustituidos, nunca una base real.
9. El escape de cada puerta sigue siendo el suyo: '--forzar' en cargar_config,
   'PERMITIR_CONFIG_SIN_DESPLEGAR' en el editor -- ninguno se unifico, y los
   dos siguen evitando la comprobacion por completo.
10. Regresion del NameError: 'cli.cargar_config' importa 'editor' de verdad
    (si no, este archivo entero no se podria ni importar), y el cuerpo de
    'cargar()' ya no menciona ningun nombre borrado de la version anterior.

Se corre sin base y sin red: se sustituyen 'editor.commits_sin_empujar' /
'editor.commits_atrasados' por dobles, y por separado 'subprocess.run' y
'_conectar'/'sesion' para las pruebas de las dos puertas. Ningun comando de
git real se ejecuta contra este repositorio, y no se escribe nada.

    py -3.13 tests/test_guarda_alineacion_git.py
"""
import inspect
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import nucleo.config.editor as editor                    # noqa: E402
import cli.cargar_config as cc                            # noqa: E402
from nucleo.config.editor import ErrorEdicion             # noqa: E402

_COMMITS_SIN_EMPUJAR_ORIGINAL = editor.commits_sin_empujar
_COMMITS_ATRASADOS_ORIGINAL = editor.commits_atrasados

fallos: list[str] = []


def comprobar(condicion: bool, que: str) -> None:
    if condicion:
        print(f"  [OK]   {que}")
    else:
        print(f"  [FALLA] {que}")
        fallos.append(que)


def _con(adelante, atras):
    """Sustituye las dos funciones de bajo nivel por valores fijos, para
    ejercitar solo la logica de combinacion de problemas_de_alineacion_git()."""
    editor.commits_sin_empujar = lambda: adelante
    editor.commits_atrasados = lambda: atras


print("=" * 70)
print(" GUARDA DE editor.problemas_de_alineacion_git (Fase #20.6.4)")
print("=" * 70)

# ---------------------------------------------------------------------- 1 --
print("\n[1] Local y remoto alineados -> lista vacia")
_con(0, 0)
comprobar(editor.problemas_de_alineacion_git() == [],
          "0 adelante y 0 atras -> sin problemas")

# ---------------------------------------------------------------------- 2 --
print("\n[2] Local ADELANTADO -> reporta la condicion")
_con(3, 0)
problemas = editor.problemas_de_alineacion_git()
comprobar(len(problemas) == 1, "3 commits de adelanto -> exactamente 1 problema")
comprobar(bool(problemas) and "commit(s) locales que todavia no" in problemas[0],
          "el problema nombra la condicion de ADELANTO")

# ---------------------------------------------------------------------- 3 --
print("\n[3] Local ATRASADO -> reporta la condicion (Fase #20.4/#20.6.4)")
_con(0, 5)
problemas = editor.problemas_de_alineacion_git()
comprobar(len(problemas) == 1, "5 commits de atraso -> exactamente 1 problema")
comprobar(bool(problemas) and "commit(s) atras del remoto" in problemas[0],
          "el problema nombra la condicion de ATRASO")

# ---------------------------------------------------------------------- 4 --
print("\n[4] Las dos condiciones a la vez -> reporta AMBAS")
_con(2, 7)
problemas = editor.problemas_de_alineacion_git()
comprobar(len(problemas) == 2, "adelanto Y atraso simultaneos -> 2 problemas")
texto = " ".join(problemas)
comprobar("commit(s) locales que todavia no" in texto and "commit(s) atras del remoto" in texto,
          "se nombran las DOS condiciones, no solo la primera evaluada")

# ---------------------------------------------------------------------- 5 --
print("\n[5] Estado indeterminado -> se trata como bloqueo, no como 0")
_con(0, None)
problemas = editor.problemas_de_alineacion_git()
comprobar(len(problemas) == 1,
          "None (indeterminado) reporta problema aunque 'adelante' de 0 -- fail-closed")
comprobar(bool(problemas) and "no se pudo determinar si esta copia" in problemas[0],
          "el problema distingue 'no se pudo saber' de 'se sabe que esta atrasada'")

_con(1, None)
problemas = editor.problemas_de_alineacion_git()
comprobar(len(problemas) == 2,
          "adelanto conocido + atraso indeterminado -> reporta ambos")

editor.commits_sin_empujar = _COMMITS_SIN_EMPUJAR_ORIGINAL
editor.commits_atrasados = _COMMITS_ATRASADOS_ORIGINAL

# ---------------------------------------------------------------------- 6 --
print("\n[6] editor.commits_atrasados por si sola: exito, fallo, excepcion, basura")


class _ProcesoFalso:
    def __init__(self, returncode: int, stdout: str):
        self.returncode = returncode
        self.stdout = stdout


_original_run = subprocess.run

subprocess.run = lambda *a, **k: _ProcesoFalso(0, "4\n")
comprobar(editor.commits_atrasados() == 4,
          "comando exitoso con salida numerica -> entero correcto")

subprocess.run = lambda *a, **k: _ProcesoFalso(0, "0\n")
comprobar(editor.commits_atrasados() == 0,
          "0 de atraso se distingue de None (alineado de verdad, no un error)")

subprocess.run = lambda *a, **k: _ProcesoFalso(128, "")
comprobar(editor.commits_atrasados() is None,
          "git devuelve error (returncode != 0, ej. sin upstream) -> None")


def _explota(*a, **k):
    raise FileNotFoundError("git no esta instalado")


subprocess.run = _explota
comprobar(editor.commits_atrasados() is None,
          "git no se puede ejecutar (excepcion) -> None, no una excepcion sin atrapar")

subprocess.run = lambda *a, **k: _ProcesoFalso(0, "no-es-un-numero\n")
comprobar(editor.commits_atrasados() is None,
          "salida que no es un entero -> None, no una excepcion sin atrapar")

subprocess.run = _original_run

# ============================================================================
print("\n" + "=" * 70)
print(" PUERTA 1: nucleo.config.editor._editar()")
print("=" * 70)


class _SesionAlcanzada(Exception):
    """Senal de que _editar() paso el guardia y trato de abrir una sesion de
    base -- nunca se llega a abrir una base real, la excepcion se lanza antes."""


def _sesion_falsa_marcadora(tenant):
    raise _SesionAlcanzada()


import nucleo.persistencia.db as db_mod                   # noqa: E402
_SESION_ORIGINAL = db_mod.sesion

print("\n[7a] Con problemas -> ErrorEdicion, SIN llegar a abrir sesion")
db_mod.sesion = _sesion_falsa_marcadora
_con(3, 0)
try:
    editor._editar("tenant_de_prueba", lambda doc: None)
    comprobar(False, "_editar() deberia haber lanzado ErrorEdicion")
except ErrorEdicion as e:
    comprobar("commit(s) locales que todavia no" in str(e),
              "_editar() bloquea local ADELANTADO con ErrorEdicion, mensaje correcto")
except _SesionAlcanzada:
    comprobar(False, "_editar() NO deberia haber intentado abrir una sesion")

_con(0, 5)
try:
    editor._editar("tenant_de_prueba", lambda doc: None)
    comprobar(False, "_editar() deberia haber lanzado ErrorEdicion")
except ErrorEdicion as e:
    comprobar("commit(s) atras del remoto" in str(e),
              "_editar() bloquea local ATRASADO con ErrorEdicion, mensaje correcto")
except _SesionAlcanzada:
    comprobar(False, "_editar() NO deberia haber intentado abrir una sesion")

print("\n[7b] Alineado -> NO bloquea, SI llega a intentar abrir sesion")
_con(0, 0)
try:
    editor._editar("tenant_de_prueba", lambda doc: None)
    comprobar(False, "no deberia llegar aca: la sesion falsa siempre revienta")
except _SesionAlcanzada:
    comprobar(True, "alineado: _editar() paso el guardia y llego a abrir sesion")
except ErrorEdicion:
    comprobar(False, "_editar() bloqueo estando alineado -- no deberia")

print("\n[7c] PERMITIR_CONFIG_SIN_DESPLEGAR salta el guardia, incluso desalineado")
import os                                                  # noqa: E402
_con(9, 9)
os.environ["PERMITIR_CONFIG_SIN_DESPLEGAR"] = "1"
try:
    editor._editar("tenant_de_prueba", lambda doc: None)
    comprobar(False, "no deberia llegar aca: la sesion falsa siempre revienta")
except _SesionAlcanzada:
    comprobar(True, "con el escape activo, _editar() ignora el desalineamiento")
except ErrorEdicion:
    comprobar(False, "el escape PERMITIR_CONFIG_SIN_DESPLEGAR no funciono")
finally:
    del os.environ["PERMITIR_CONFIG_SIN_DESPLEGAR"]

db_mod.sesion = _SESION_ORIGINAL
editor.commits_sin_empujar = _COMMITS_SIN_EMPUJAR_ORIGINAL
editor.commits_atrasados = _COMMITS_ATRASADOS_ORIGINAL

# ============================================================================
print("\n" + "=" * 70)
print(" PUERTA 2: cli.cargar_config.cargar()")
print("=" * 70)


class _CursorFalso:
    """Responde UNA fila por cada .execute()+.fetchone(), en el orden en que
    cargar() las pide: primero _organizacion() (un id cualquiera, 'ya
    vinculado'), despues la config 'actual' (None -- asi ni la comparacion de
    'sin cambios' ni _lo_que_pisaria disparan, y se llega limpio al guardia)."""

    def __init__(self):
        self._respuestas = [("org-de-prueba-000",), None]
        self.llamadas: list[str] = []

    def execute(self, sql, params=None):
        self.llamadas.append(sql)

    def fetchone(self):
        return self._respuestas.pop(0) if self._respuestas else None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _ConexionFalsa:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def commit(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


_CONECTAR_ORIGINAL = cc._conectar
RUTA_YAML_REAL = Path("tenants/rapilink.config.yaml")

print("\n[8a] Con problemas -> SystemExit, y la unica escritura intentada es")
print("     ninguna (el guardia corta antes del UPDATE/INSERT)")
cc._conectar = lambda: _ConexionFalsa(_CursorFalso())
_con(4, 0)
try:
    cc.cargar(RUTA_YAML_REAL)
    comprobar(False, "cargar() deberia haber lanzado SystemExit")
except SystemExit as e:
    comprobar("commit(s) locales que todavia no" in str(e),
              "cargar() bloquea local ADELANTADO con SystemExit, mensaje correcto")

_con(0, 6)
try:
    cc.cargar(RUTA_YAML_REAL)
    comprobar(False, "cargar() deberia haber lanzado SystemExit")
except SystemExit as e:
    comprobar("commit(s) atras del remoto" in str(e),
              "cargar() bloquea local ATRASADO con SystemExit, mensaje correcto")

print("\n[8b] Alineado -> NO bloquea, corre hasta el final (INSERT simulado)")
_con(0, 0)
cursor_final = _CursorFalso()
cc._conectar = lambda: _ConexionFalsa(cursor_final)
try:
    cc.cargar(RUTA_YAML_REAL)
    comprobar(True, "alineado: cargar() no lanzo SystemExit, corrio completo")
except SystemExit as e:
    comprobar(False, f"cargar() bloqueo estando alineado -- no deberia: {e}")
comprobar(any("insert into asistente.tenant_config" in sql for sql in cursor_final.llamadas),
          "llego a intentar el INSERT -- confirma que paso el guardia, no que lo saco")

print("\n[8c] --forzar salta el guardia, incluso desalineado")
_con(9, 9)
cc._conectar = lambda: _ConexionFalsa(_CursorFalso())
try:
    cc.cargar(RUTA_YAML_REAL, forzar=True)
    comprobar(True, "--forzar ignora el desalineamiento, no lanza SystemExit")
except SystemExit as e:
    comprobar(False, f"--forzar deberia haber saltado el guardia: {e}")

cc._conectar = _CONECTAR_ORIGINAL
editor.commits_sin_empujar = _COMMITS_SIN_EMPUJAR_ORIGINAL
editor.commits_atrasados = _COMMITS_ATRASADOS_ORIGINAL

# ============================================================================
print("\n" + "=" * 70)
print(" REGRESION DEL NameError (Fase #20.6.3/#20.6.4)")
print("=" * 70)

print("\n[9] cli.cargar_config importa 'editor' de verdad (no solo una constante)")
comprobar(hasattr(cc, "editor"), "'editor' es un nombre real en el modulo (si no, "
          "este archivo entero no se habria podido importar)")
comprobar(hasattr(cc.editor, "problemas_de_alineacion_git"),
          "el modulo importado expone problemas_de_alineacion_git")

print("\n[10] El cuerpo de cargar() ya no referencia nombres borrados")
codigo_cargar = inspect.getsource(cc.cargar)
comprobar("_verificar_alineacion_git" not in codigo_cargar,
          "no queda ninguna referencia a la funcion vieja (ya no existe)")
comprobar("editor.commits_sin_empujar()" not in codigo_cargar,
          "no llama a editor.commits_sin_empujar() suelta (esa era la linea del NameError)")
comprobar("editor.problemas_de_alineacion_git()" in codigo_cargar,
          "llama a la funcion centralizada nueva")
pos_guardia = codigo_cargar.find("editor.problemas_de_alineacion_git(")
pos_pisaria = codigo_cargar.find("_lo_que_pisaria(")
pos_update = codigo_cargar.find('cur.execute("""update')
comprobar(pos_guardia != -1 and pos_pisaria != -1 and pos_update != -1
          and pos_guardia < pos_pisaria < pos_update,
          "el guardia sigue ANTES que _lo_que_pisaria y ANTES del UPDATE")

# ============================================================================
print("\n" + "=" * 70)
print(" SECCIONES_EDITABLES cubre 'llm' y 'limites' (Fase #20.6.6)")
print("=" * 70)
# Incidente aparte del NameError, mismo dia (05/09/2026): una carga del YAML
# borro 'llm.tarifas' y 'llm.saldo' de produccion sin ningun aviso, porque
# esas dos secciones no estaban en la lista que protege _lo_que_pisaria(). No
# es el guardia de alineacion Git -- es la OTRA guarda (perdidas de contenido,
# tests/test_guarda_cargar_config.py) -- pero se fija aca porque se reconcilio
# en el mismo commit y esta fase lo pide explicitamente.

print("\n[11] 'llm' y 'limites' ahora estan en SECCIONES_EDITABLES")
comprobar("llm" in editor.SECCIONES_EDITABLES, "'llm' esta protegida")
comprobar("limites" in editor.SECCIONES_EDITABLES, "'limites' esta protegida")

print("\n[12] El incidente real de hoy: la perdida ahora SI se reporta")
base_con_tarifa_real = {
    "roles": {},
    "llm": {"tarifas": {"deepseek:deepseek-v4-flash": {"entrada": 0.44, "salida": 1.32}},
           "saldo": {"url": "https://api.deepseek.com/user/balance"}},
}
yaml_sin_tarifa = {"roles": {}, "llm": {}}
perdidas = cc._lo_que_pisaria(base_con_tarifa_real, yaml_sin_tarifa)
comprobar(any("llm" in p for p in perdidas),
          "una carga que borraria la tarifa y el saldo reales -- exactamente "
          "lo que paso hoy -- ahora se detecta y se reportaria ANTES de escribir")

# ============================================================================
print("\n" + "=" * 70)
if fallos:
    print(f" {len(fallos)} FALLA(S):")
    for f in fallos:
        print(f"   - {f}")
    raise SystemExit(1)
print(" Todo en orden: las dos puertas comparten una guarda, sin NameError,")
print(" y 'llm'/'limites' ya no se pierden en silencio.")
print("=" * 70)
