# B-7 — COMMIT DE LA SEPARACIÓN DE MIGRACIONES

Fecha: 2026-09-19

```
COMMIT    40d10b38634a6fb000bf90c3b9441e54d895ee2c   CREADO
PUSH      RECHAZADO (non-fast-forward)               NO COMPLETADO
VERIFICACION DEL COMMIT                              PASS
```

**No se hizo Redeploy ni Rebuild. No se ejecutó ninguna migración de producción.
No se modificaron permisos, RLS, ownership ni credenciales. No se usó `--force`.
No se usó `git stash`. No se tocó ningún archivo de otro colaborador.**

---

## 1. El commit

```
hash    40d10b38634a6fb000bf90c3b9441e54d895ee2c
corto   40d10b3
rama    fix/integracion-wisphub
autor   sistemas2026-hub <sistemasautomatizacion5@gmail.com>
fecha   2026-09-19 18:14:07 -0500
asunto  fix(b7): separar migraciones del runtime
```

Contenido, leído del objeto del commit y no del disco:

```
A  django-crm/backend/common/credenciales.py                                 333 +
A  django-crm/backend/common/management/commands/verificar_credenciales.py    66 +
M  django-crm/docker/backend/entrypoint.sh                                    39 +-
M  docker-compose.prod.yml                                                    11 +
                                                    4 files, +447 −2
```

Exactamente los cuatro archivos aprobados. Ni uno más.

---

## 2. Lo verificado antes del commit

### Contenido del *staged*: 4 archivos, +447 −2 — coincide con el diff aprobado

```
.env / archivo de entorno    -> ninguno
migracion                    -> ninguno
archivo de pruebas           -> ninguno
clave suelta b8_*.txt        -> ninguno
archivo de secretos          -> ninguno
```

**Las cinco reglas se probaron contra un cebo** (`backend/.env`,
`common/migrations/0041_x.py`, `tests/test_x.py`, `b8_crm_user_clave.txt`,
`secrets.json`): las cinco lo detectan. Un cero sin esa prueba no significa nada.

### Secretos en el contenido, con cinco detectores

```
clave/secreto asignado a literal : 0
cadena tipo JWT                  : 0
verificador SCRAM-SHA-256        : 0
URI con credencial embebida      : 0
UUID de pooler                   : 1   <- ver abajo
```

Los cinco detectores disparan contra su cebo.

### `[ACLARACIÓN]` El UUID del pooler, la única coincidencia

En el comentario de `rol_base()` aparece
`'postgres.05b5a4b4-…-f3ed8f8ac0a1'`, explicando por qué hay que recortar el
sufijo. Antes de decidir, lo medí:

| Comprobación | Resultado |
|---|---|
| ¿Está ya en archivos versionados? | **Sí** — `DESPLIEGUE.md` en `HEAD` |
| ¿Está ya publicado en `origin`? | **Sí** — `origin/…:DESPLIEGUE.md` |
| ¿Commits previos que lo introdujeron? | **3** (`574db45`, `6ba5f0b`, `154f52b`) |
| ¿Autentica algo por sí solo? | **No** — es el sufijo de tenant que exige Supavisor, parte del *usuario*, nunca de la contraseña |

No es un secreto y no es algo que este commit introduzca: ya estaba publicado
desde antes. Lo dejo tal cual porque cambiarlo alteraría el diff que aprobaste.
Si prefieres que diga `'postgres.<sufijo del pooler>'`, es una línea y se
enmienda.

### `[FALSA ALARMA]` CRLF — mi primer instrumento medía mal

`git add` avisó de conversión LF→CRLF, y en este proyecto eso ya rompió un
`entrypoint.sh` dentro de un contenedor Linux (`$'\r': command not found`). Mi
primera comprobación dio «CRLF en los 4 archivos» — pero contradecía a `od -c`,
que mostraba `\n` limpio en el shebang.

El instrumento estaba mal (`grep -c $'\r'` hacía match en todas las líneas).
Medido en bytes, con controles de LF y de CRLF de verdad:

```
entrypoint.sh              CR=0  LF=96    control CRLF -> CR=2  OK
credenciales.py            CR=0  LF=333   control LF   -> CR=0  OK
verificar_credenciales.py  CR=0  LF=66
docker-compose.prod.yml    CR=0  LF=462
```

El blob que se commiteó tiene **LF limpio**. `.gitattributes` ya trae
`*.sh text eol=lf` justo por esta lección.

---

## 3. El push: **RECHAZADO**

```
! [rejected]  fix/integracion-wisphub -> fix/integracion-wisphub (non-fast-forward)
error: failed to push some refs
```

**El remoto no cambió.** El push se intentó sin `--force`, así que un rechazo no
escribe nada.

### La causa

La copia local estaba, antes de mi commit, **23 commits por detrás de `origin` y
0 por delante**:

```
local  108935f  2026-09-15   (antes del commit)
origin 601d8be  2026-09-17
```

Los 23 son de **`marioth727`** — logs que filtraban teléfonos y wamids, el
apagado ordenado de `motor`, el manifiesto de PG17, permisos de `public`. Nada
mío.

### Lo que sí está limpio

Mis 4 archivos **no chocan** con ese trabajo. Simulado con `git merge-tree`, que
no modifica nada:

```
merge LIMPIO: sin conflictos
```

El colaborador tocó `docker-compose.prod.yml` en dos commits, pero en
`motor` (línea 329+) y `motor-reloj` (404+); lo mío está en `backend` (111–124).
No se solapan. `entrypoint.sh`, `credenciales.py` y `verificar_credenciales.py`
no los tocó nadie.

### Por qué me detengo aquí y no hago `git pull`

Integrar esos 23 commits no estaba en lo autorizado, y además **el `pull`
abortaría**: 11 archivos que cambian en `origin` están modificados sin commitear
en esta copia.

```
DESPLIEGUE.md                      nucleo/reloj.py
cli/cargar_config.py               nucleo/seguimiento/importacion_io.py
nucleo/canales/api.py              nucleo/seguimiento/operativo.py
nucleo/herramientas/http.py        tests/test_reloj.py
nucleo/modelo/motor.py
nucleo/persistencia/db.py
nucleo/programador/coordinador.py
```

`git pull` respondería *«Your local changes would be overwritten by merge»*. La
salida habitual sería `git stash`, que está prohibido en este proyecto —y con
razón: ya dañó un archivo ajeno una vez. Ese trabajo en curso no es de este
bloque y no es mío para decidir.

### Tres caminos, ninguno ejecutado

| | Qué haría | Riesgo |
|---|---|---|
| **A. Rama propia** *(el más limpio)* | Crear `b7-separar-migraciones` desde `origin/fix/integracion-wisphub`, llevar ahí el commit y publicarla | No toca `fix/integracion-wisphub`, no toca el árbol, no toca los 23 commits. Queda como rama aparte para fusionar cuando quieras |
| **B. Integrar primero** | Commitear o resolver los 11 archivos en conflicto, `git pull`, luego push | Obliga a decidir sobre trabajo en curso que no es de este bloque |
| **C. Esperar** | Dejar el commit local hasta que el árbol esté ordenado | Nada se publica todavía |

El commit es local y reversible con `git reset --soft HEAD~1`, que devolvería los
4 archivos al estado de antes sin perder una línea.

---

## 4. Verificación final

| # | Comprobación | Resultado |
|---|---|---|
| 1 | `git status` limpio | **NO** — 171 entradas de trabajo previo, ajeno a este bloque. Ver abajo |
| 2 | HEAD en el nuevo commit | **SÍ** — `40d10b3`, y la rama apunta ahí |
| 3 | Los 4 archivos incluidos | **SÍ** — 4 de 4, leídos del objeto del commit |
| 4 | Sin secretos en el commit | **SÍ** — 0 en los cuatro detectores |
| 5 | Sin migraciones nuevas | **SÍ** — 0 archivos en `migrations/`; 0 pendientes de aplicar |

### Sobre el punto 1, con precisión

El árbol **no está limpio y no puede estarlo**: tenía 171 entradas sin commitear
*antes* de que empezara este bloque (Autonomía 2, M03, campo, operaciones…).
Ninguna es mía de este trabajo.

Lo que sí quedó limpio:

```
preparado para commit (staged) : 0 archivos
los 4 archivos del bloque      : ninguno pendiente -> quedaron dentro del commit
```

Decir «`git status` limpio» habría sido falso.

### Estado de producción

Sin cambios. No se conectó para escribir, no se desplegó, no se migró.

```
migraciones que 'migrate' aplicaria: 0
```

---

## CONCLUSIÓN

| | |
|---|---|
| **Commit** | `40d10b38634a6fb000bf90c3b9441e54d895ee2c` — **hecho y verificado** |
| **Push** | **NO COMPLETADO** — rechazado por estar 23 commits detrás |
| **Verificación del commit** | **PASS** — 5 de 5 |

El cambio está commiteado y es correcto. **No está publicado**, así que Dokploy
sigue sin poder verlo: la separación runtime/migraciones continúa **sin efecto en
producción**, y **B-7 sigue siendo PARCIAL**.

Necesito que elijas entre A, B o C para publicarlo. No hice Redeploy ni Rebuild.
