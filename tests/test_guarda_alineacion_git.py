# -*- coding: utf-8 -*-
"""
================================================================================
 GUARDA DE ALINEACION GIT  --  que 'cargar_config' no escriba con la copia
 local desincronizada del remoto, en NINGUNA de las dos direcciones
================================================================================

Por que existe
--------------
'cli/cargar_config.py' valida el YAML contra el 'schema.py' de ESTA copia
local antes de guardarlo en la base -- no contra el que corre en el motor
desplegado. Si las dos copias difieren, la validacion local no significa nada
para produccion.

Ya existia una guarda para una mitad del problema: '_commits_sin_empujar()'
detecta cuando la copia local esta ADELANTE del remoto (codigo nuevo que el
motor desplegado todavia no tiene). Lo que faltaba era el caso simetrico, y
faltar le costo caro a produccion:

 - Fase #20.1/#20.2 (04-05/09/2026): 'tenant_config' en base tenia dos campos
   ('llm.tarifas', 'limites.mensaje_al_alcanzar_tope') que el schema actual ya
   no reconoce. Se corrigieron quirurgicamente, verificados en la misma
   transaccion antes de comitear (Fase #20.2).
 - Minutos despues, la correccion aparecio deshecha: los dos campos habian
   vuelto, mas uno nuevo ('llm.saldo') (Fase #20.3).
 - El diagnostico de Fase #20.3 encontro la causa estructural: 'cargar()'
   solo comprobaba "¿esta copia esta ADELANTE?" -- nunca "¿esta copia esta
   ATRASADA?". Una copia local vieja, corriendo contra un 'schema.py' que
   todavia reconocia esos campos como validos, los volvio a escribir sin que
   nada la frenara.

Lo que se fija aca (Fase #20.4)
--------------------------------
1. Local y remoto alineados -> no se bloquea nada.
2. Local ADELANTE del remoto -> se bloquea (el caso que YA existia).
3. Local ATRASADO del remoto -> se bloquea (el caso NUEVO de esta fase).
4. Las dos condiciones a la vez -> se bloquea, y el aviso nombra AMBAS, no
   solo la primera que se evalua.
5. Git no puede determinar si la copia esta atrasada (sin remoto, sin git,
   el comando falla) -> se trata como BLOQUEO, nunca como "esta alineado".
   A diferencia de '_commits_sin_empujar()' -- que ante la duda permite,
   porque '_lo_que_pisaria()' la respalda igual -- esta direccion no tiene
   ningun respaldo equivalente: nada mas sabe si un campo sigue siendo valido
   para el schema desplegado.
6. '--forzar' salta LA VERIFICACION COMPLETA, sin siquiera consultar a git.
7. La comprobacion de bajo nivel ('_commits_atrasados') tambien se prueba
   sola: comando exitoso, comando que falla, comando que tarda o no existe,
   y una salida que no es un numero -- las cuatro se tratan igual (None).
8. Estructural: dentro de 'cargar()', la verificacion de alineacion ocurre
   ANTES que '_lo_que_pisaria' y antes de cualquier UPDATE/INSERT.

Se corre sin base y sin red: se sustituyen '_commits_sin_empujar' y
'_commits_atrasados' por dobles, y por separado se sustituye
'subprocess.run' para probar '_commits_atrasados' de forma aislada. Ningun
comando de git real se ejecuta contra este repositorio.

    py -3.13 tests/test_guarda_alineacion_git.py
"""
import inspect
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cli.cargar_config as cc                          # noqa: E402

_COMMITS_SIN_EMPUJAR_ORIGINAL = cc._commits_sin_empujar
_COMMITS_ATRASADOS_ORIGINAL = cc._commits_atrasados

fallos: list[str] = []


def comprobar(condicion: bool, que: str) -> None:
    if condicion:
        print(f"  [OK]   {que}")
    else:
        print(f"  [FALLA] {que}")
        fallos.append(que)


def _mensaje_de(adelante, atras, forzar: bool = False) -> str | None:
    """Corre _verificar_alineacion_git con los dos valores dados ya resueltos
    (sin tocar git de verdad) y devuelve el texto del SystemExit, o None si
    no lo lanzo."""
    cc._commits_sin_empujar = lambda: adelante
    cc._commits_atrasados = lambda: atras
    try:
        cc._verificar_alineacion_git("rapilink", Path("tenants/rapilink.config.yaml"), forzar)
        return None
    except SystemExit as e:
        return str(e)


print("=" * 70)
print(" GUARDA DE cargar_config._verificar_alineacion_git")
print("=" * 70)

# ---------------------------------------------------------------------- 1 --
print("\n[1] Local y remoto alineados -> no se bloquea")
comprobar(_mensaje_de(adelante=0, atras=0) is None,
          "0 adelante y 0 atras deja pasar (no lanza SystemExit)")

# ---------------------------------------------------------------------- 2 --
print("\n[2] Local ADELANTE del remoto -> se bloquea (caso ya existente)")
msg = _mensaje_de(adelante=3, atras=0)
comprobar(msg is not None, "3 commits de adelanto SI bloquea")
comprobar(bool(msg) and "commit(s) locales que todavia no" in msg,
          "el aviso nombra la condicion de ADELANTO")
comprobar(bool(msg) and "commit(s) atras del remoto" not in msg,
          "el aviso NO menciona 'atras' cuando esa condicion no aplica")

# ---------------------------------------------------------------------- 3 --
print("\n[3] Local ATRASADO del remoto -> se bloquea (caso nuevo, Fase #20.4)")
msg = _mensaje_de(adelante=0, atras=5)
comprobar(msg is not None, "5 commits de atraso SI bloquea")
comprobar(bool(msg) and "commit(s) atras del remoto" in msg,
          "el aviso nombra la condicion de ATRASO")
comprobar(bool(msg) and "commit(s) locales que todavia no" not in msg,
          "el aviso NO menciona 'adelanto' cuando esa condicion no aplica")

# ---------------------------------------------------------------------- 4 --
print("\n[4] Las dos condiciones a la vez -> se bloquea y nombra AMBAS")
msg = _mensaje_de(adelante=2, atras=7)
comprobar(msg is not None, "adelanto Y atraso simultaneos SI bloquea")
comprobar(bool(msg) and "commit(s) locales que todavia no" in msg
          and "commit(s) atras del remoto" in msg,
          "el aviso nombra las DOS condiciones, no solo la primera evaluada")

# ---------------------------------------------------------------------- 5 --
print("\n[5] Git no puede determinar el atraso -> se trata como bloqueo")
msg = _mensaje_de(adelante=0, atras=None)
comprobar(msg is not None,
          "None (indeterminado) bloquea aunque 'adelante' de 0 -- fail-closed")
comprobar(bool(msg) and "no se pudo determinar si esta copia" in msg,
          "el aviso distingue 'no se pudo saber' de 'se sabe que esta atrasada'")

msg_ambos_mal = _mensaje_de(adelante=1, atras=None)
comprobar(msg_ambos_mal is not None
          and "commit(s) locales que todavia no" in msg_ambos_mal
          and "no se pudo determinar si esta copia" in msg_ambos_mal,
          "adelanto conocido + atraso indeterminado reporta ambos problemas")

# ---------------------------------------------------------------------- 6 --
print("\n[6] --forzar salta la verificacion completa, sin consultar nada")


def _no_deberia_llamarse():
    raise AssertionError("--forzar debe evitar esta llamada por completo")


cc._commits_sin_empujar = _no_deberia_llamarse
cc._commits_atrasados = _no_deberia_llamarse
try:
    cc._verificar_alineacion_git("rapilink", Path("tenants/rapilink.config.yaml"), True)
    comprobar(True, "forzar=True no lanza SystemExit")
except AssertionError as e:
    comprobar(False, f"forzar=True deberia cortocircuitar antes de llamar a git: {e}")
except SystemExit:
    comprobar(False, "forzar=True NO deberia bloquear nunca")

# ---------------------------------------------------------------------- 7 --
print("\n[7] _commits_atrasados por si sola: exito, fallo, excepcion, basura")

# [6] sustituyo _commits_atrasados por un centinela que revienta si se llama
# -- se restaura la implementacion real antes de probarla directamente.
cc._commits_sin_empujar = _COMMITS_SIN_EMPUJAR_ORIGINAL
cc._commits_atrasados = _COMMITS_ATRASADOS_ORIGINAL


class _ProcesoFalso:
    def __init__(self, returncode: int, stdout: str):
        self.returncode = returncode
        self.stdout = stdout


_original_run = subprocess.run

subprocess.run = lambda *a, **k: _ProcesoFalso(0, "4\n")
comprobar(cc._commits_atrasados() == 4,
          "comando exitoso con salida numerica -> entero correcto")

subprocess.run = lambda *a, **k: _ProcesoFalso(0, "0\n")
comprobar(cc._commits_atrasados() == 0,
          "0 de atraso se distingue de None (alineado de verdad, no un error)")

subprocess.run = lambda *a, **k: _ProcesoFalso(128, "")
comprobar(cc._commits_atrasados() is None,
          "git devuelve error (returncode != 0, ej. sin upstream) -> None")


def _explota(*a, **k):
    raise FileNotFoundError("git no esta instalado")


subprocess.run = _explota
comprobar(cc._commits_atrasados() is None,
          "git no se puede ejecutar (excepcion) -> None, no una excepcion sin atrapar")

subprocess.run = lambda *a, **k: _ProcesoFalso(0, "no-es-un-numero\n")
comprobar(cc._commits_atrasados() is None,
          "salida que no es un entero -> None, no una excepcion sin atrapar")

subprocess.run = _original_run

# ---------------------------------------------------------------------- 8 --
print("\n[8] Estructural: la verificacion ocurre ANTES que _lo_que_pisaria")
codigo_cargar = inspect.getsource(cc.cargar)
pos_alineacion = codigo_cargar.find("_verificar_alineacion_git(")
pos_pisaria = codigo_cargar.find("_lo_que_pisaria(")
comprobar(pos_alineacion != -1 and pos_pisaria != -1,
          "cargar() todavia llama a las dos funciones (no se borro ninguna)")
comprobar(0 <= pos_alineacion < pos_pisaria,
          "_verificar_alineacion_git aparece ANTES que _lo_que_pisaria en el cuerpo de cargar()")
comprobar(codigo_cargar.find("cur.execute(\"\"\"update") > pos_alineacion,
          "el UPDATE a la base aparece DESPUES de la verificacion de alineacion")

print("\n" + "=" * 70)
if fallos:
    print(f" {len(fallos)} FALLA(S):")
    for f in fallos:
        print(f"   - {f}")
    raise SystemExit(1)
print(" Todo en orden: ninguna direccion de desalineacion queda sin bloquear.")
print("=" * 70)
