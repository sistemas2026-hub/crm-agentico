# PRE-ACTIVACIÓN DE AUTONOMÍA 2 · CIERRE OPERATIVO DE B-7

Fecha: 2026-09-19 · **PASS**

Nada se activó. Producción intacta, sin commit, sin `git stash`, sin tocar
trabajo ajeno.

---

# BLOQUE A — VALIDACIÓN FINAL DEL PILOTO `crear_tag_crm`

`tests/test_autonomia2_preactivacion.py` — **todo en verde**.

**Cómo se mide:** se sustituye `requests` **dentro** de
`nucleo/herramientas/http.py`, no el ejecutor. Así corre el código real —
frontera incluida— y lo único que no ocurre es el viaje por la red. Si el
contador sube, **la llamada habría salido**. Sustituir el ejecutor saltearía
justo el control que hay que probar.

| # | Punto | Medido |
|---|---|---|
| 1 | kill switch | `detenido` → **0 llamadas**, con el motivo del interruptor. Desarme: `activo` + todo en regla → **1** |
| 2 | nivel de autonomía | sin fila (=0), techo 0 y techo 1 → **0**. Desarme: techo 2 → **1** |
| 3 | autorización específica | sin fila de `crear_tag_crm` → **0**. Con fila → la autorización manda |
| 4 | idempotencia | segundo pedido con la misma clave → **0** |
| 5 | `decision != "ejecutar"` | `'ejecutar '`, `'EJECUTAR'`, `'devolver'`, `''`, `None`, `0`, `True` → **0** cada uno. Desarme: `'ejecutar'` exacto → **1** |
| 6 | no autorizada con nivel suficiente | `cerrar_caso_crm` con techo **4** → **0**; en la misma corrida la autorizada → **1** |
| 7 | la autorización no eleva el techo | autorización nivel 4 + techo 1 → bloquea, efectivo **1** (el techo), 0 llamadas |
| 8 | sin ruta que saltee `frontera.py` | ver abajo |
| 9 | sin endpoint de ejecución directa | ver abajo |
| 10 | registro de la ejecución | 1 fila `permitida` por ejecución real |
| 11 | bloqueada ≠ fallida | 1 fila `bloqueada`, `resultado='no_ejecutada'` (**no** `fallida`), con el código de la compuerta |
| 12 | repetida sin segundo efecto | 3 pedidos, misma clave → **1** llamada |

## Punto 8 — una sola frontera, verificada por los dos lados

**Estática.** El único módulo de `nucleo/` que nombra `crear_tag_crm` y llama al
ejecutor es `nucleo/seguimiento/escalamiento.py` (crea la etiqueta del caso
cuando `listar_tags_crm` no la encuentra). El control **no está en él**: está en
el ejecutor (`http.py` → `frontera.exigir`), que es por donde pasa todo.

**Dinámica.** `escalamiento.py` no abre permiso de frontera — medido: **cero**
referencias. Y llamar al ejecutor sin permiso:

```
ejecutor_http.ejecutar(crear_tag_crm, ...)  sin permiso  ->  0 llamadas,
                                                code ACCION_EXTERNA_SIN_AUTORIZAR
lo mismo con tenant vacio                                ->  0 llamadas
```

Es decir: esa ruta **no saltea la frontera, queda bloqueada por ella**. Falla
cerrado.

`frontera.py` sigue teniendo **exactamente dos puertas**: `autonoma` y `humana`
(verificado por AST, no por texto).

## Punto 9 — y un hallazgo medido

`crear_tag_crm` **no es invocable por servicio**, y la ruta
`/interno/herramienta/<nombre>` rechaza lo que no esté declarado — la
comprobación está escrita en `api.py`.

`[HALLAZGO]` **La comprobación `invocable_por_servicio` vive en la RUTA, no
donde ocurre el efecto.** Medido:

```
motor.ejecutar_para_servicio(config, crear_tag_crm, ...)  ->  1 llamada
   (herramienta NO invocable, llamada directamente, con todo lo demas en verde)
```

Es el mismo patrón que `frontera.py` existe para corregir: un control puesto en
el llamador lo saltea el llamador siguiente.

**No es un fail-open**, y esto también se midió:

```
por esa MISMA via, sin autorizacion granular   ->  0 llamadas
por esa MISMA via, una R3 (reiniciar_ont) con techo 4  ->  0 llamadas
```

La frontera la gobierna igual. Lo que `invocable_por_servicio` acota es **qué
puede disparar un servicio del despliegue**, no qué puede ejecutarse solo — y
eso segundo ya lo decide la autorización granular.

`[DECISIÓN PENDIENTE]` **No lo corregí.** Mover la comprobación dentro de
`ejecutar_para_servicio` cambia el comportamiento de la ruta `/interno`, que
este bloque no autoriza a tocar, y no es el mismo perímetro: `frontera.py`
gobierna el *efecto externo*; `invocable_por_servicio` gobierna *quién puede
pedirlo*. Queda propuesto para el bloque de cierre, en una línea:

```python
# al principio de motor.ejecutar_para_servicio()
if not herramienta.invocable_por_servicio:
    raise ValueError(f"'{herramienta.nombre}' no es invocable por un servicio")
```

## Puntos 10 y 11 — y lo que la bitácora **no** registra

Lo que sí:

```
ejecucion real  -> 1 fila decision='permitida', resultado NO 'fallida'
bloqueada       -> 1 fila decision='bloqueada', resultado='no_ejecutada',
                   codigo = la compuerta que freno
```

El punto 11 se cumple: **una operación bloqueada no se registra como fallida**.

`[HALLAZGO]` Lo que **no** registra, medido y no supuesto:

```
[MEDIDO] resultado de la ejecucion en la fila: AUSENTE
[MEDIDO] clave de idempotencia en la fila:     AUSENTE
```

La bitácora guarda la **decisión de autorización**, no el **desenlace**. El
desenlace sí queda —en `asistente.operaciones_externas`, con `exitosa`/`fallida`
y su respuesta— pero **el puente entre las dos tablas no se escribe**:
`frontera._bitacora()` no pasa `clave_idempotencia`, aunque la columna existe y
`registrar_ejecucion_autonoma()` la acepta.

Consecuencia honesta: hoy la bitácora contesta *«¿qué autorizó el sistema?»*
pero **no** *«¿cómo terminó?»* sin un cruce manual. El punto 10, leído al pie de
la letra («el resultado de ejecución queda registrado»), **se cumple a medias**.

`[DECISIÓN PENDIENTE]` No lo corregí: el efecto ocurre *después* de que la
frontera cede el control, así que cerrarlo bien exige decidir quién escribe la
segunda fila y cuándo. Es trabajo de diseño, no una línea, y este bloque es de
validación.

---

# BLOQUE B — `limites`: **METADATA**

**Conclusión explícita: `limites` NO participa en ninguna decisión de
ejecución.**

Medido, no supuesto:

| Qué | Resultado |
|---|---|
| ¿se lee de la fila? | **sí** — `autorizacion.py:175` |
| ¿viaja en el veredicto? | **sí** — campo `Veredicto.limites` |
| ¿alguien lo evalúa? | **no** — ninguna comparación, ningún `if`, en todo `nucleo/` |
| `LIMITE_DE_AUTORIZACION_EXCEDIDO` | **definido y jamás devuelto** |

> Las coincidencias de `.limites` en `api.py` son `config.limites` — los topes de
> conversación del tenant. **Otra cosa**, sin relación con la autorización.

**Prueba de efecto** (`tests/test_autonomia2_preactivacion.py`, sección B): con
`limites = {"por_dia": 0, "maximo": 0, "prohibido": True}` —imposibles a
propósito— el veredicto **sigue siendo permitido** y la ejecución **sale igual**.

Se mantienen **como metadata**, según lo indicado. No se implementó ningún
sistema de límites. Dos cosas para que el código no aparente lo que no hace:

- `Veredicto.limites` y `LIMITE_EXCEDIDO` quedan marcados en el código como
  metadata y reservado-sin-usar.
- La prueba **falla** si alguien empieza a evaluarlos — así la reclasificación
  será obligatoria y no un olvido.

---

# BLOQUE C — B-7, CONFIRMADO SIN ESCRIBIR

Conexión de **solo lectura efectiva**: `SHOW transaction_read_only = on`
verificado antes de consultar.

| Dato | Estado |
|---|---|
| `DBHOST` | `crm.rapilinksas.co` |
| `DBPORT` | `5433` (session mode) · puerto real detrás del pooler: `5432` |
| `DBNAME` | `postgres` |
| `DBUSER` | rol base **`postgres`** + sufijo de pooler (36 caracteres) |
| `DBPASSWORD` | **presente** (valor no leído ni impreso) |
| `session_user` / `current_user` | **`postgres`** / `postgres` |

```
crm_migrator   super=F bypassrls=F createdb=F createrole=F login=T
crm_owner      super=F bypassrls=F createdb=F createrole=F login=F
crm_user       super=F bypassrls=F createdb=F createrole=F login=T
motor_user     super=F bypassrls=T createdb=F createrole=F login=T
postgres       super=F bypassrls=T createdb=T createrole=T login=T

crm_migrator es miembro de crm_owner : True
ALTER ROLE crm_migrator -> role=crm_owner
```

`crm_user`, privilegios vigentes:

```
tablas     SELECT 135/135   INSERT 135/135
tablas     TRUNCATE 0   REFERENCES 0   TRIGGER 0    <- los cuatro REVOKE, aplicados
secuencias USAGE 51/51   UPDATE 0/51
CREATE sobre schema public : True                    <- ver Bloque D
dueño de tablas de public  : 0
```

## `app.settings.jwt_secret`: **EXISTE**

- Alcance: **todos los roles**, base `postgres`. Mecanismo: `ALTER DATABASE … SET`.
- Valor **no impreso**. Solo se declara su existencia y longitud (32 caracteres).
- **Legible por `crm_user`: True.**

## El camino indirecto: **SIGUE ABIERTO**

```
token del .env (SUPABASE_SERVICE_ROLE_KEY): alg=HS256  role=service_role  iss=supabase
el GUC verifica su firma              : SI
service_role bypassrls                : True
authenticator -> SET ROLE service_role: True
```

Es decir: quien lea ese GUC puede firmar un `service_role` con `BYPASSRLS`. **El
privilegio que B-7 retira se recupera por esa vía.** No se modificó nada.

Producción: las tres tablas de Autonomía 2 **ausentes**; kill switch
**`detenido`**.

---

# BLOQUE D — `CREATE` sobre `public`: **NO NECESARIO**

| # | Pregunta | Respuesta medida |
|---|---|---|
| 1 | ¿el runtime lo necesita? | **NO.** En el entorno aislado `crm_user` tiene `CREATE=false` y el runtime funciona |
| 2 | ¿las 18/18 dependieron de CREATE? | **NO.** Re-ejecutado hoy: **18/18 OK** con `CREATE en public = false` durante la corrida |
| 3 | ¿hay objetos en `public` creados por el runtime? | **NO.** Objetos cuyo dueño es `crm_user`: **0** |
| 4 | `CREATE` sobre `public` vs `pg_temp` | **Son privilegios distintos**, y ninguno se usa |

Inventario de `public` en producción, por dueño:

```
135 tablas       -> crm_owner
 51 secuencias   -> crm_owner
135 tipos        -> crm_owner
149 funciones    -> supabase_admin
  0 objetos      -> crm_user
```

Sobre el punto 4, con precisión: una tabla temporal vive en `pg_temp_N`, **no en
`public`**, y solo requiere `TEMPORARY` sobre la base — que `crm_user` tiene
(`True`) y que **no se toca**. Revocar `CREATE` sobre `public` no afecta a las
temporales. Además: **cero** `CREATE TABLE/INDEX/VIEW/TEMP` en código de runtime,
ni en `django-crm/backend` fuera de `migrations/`, ni en `nucleo/`.

De dónde sale el privilegio:

```
ACL de public: ... | crm_user=UC/pg_database_owner | crm_owner=UC/pg_database_owner
                              ^^ C = CREATE, concesión explícita
```

## Veredicto: **NO NECESARIO — PENDIENTE DE REVOCACIÓN**

No se ejecutó el `REVOKE`, como indica el bloque. Queda para el cierre de B-7:

```sql
REVOKE CREATE ON SCHEMA public FROM crm_user;
```

`[NOTA]` `crm_migrator` también tiene `CREATE` sobre `public`, y ese **sí lo
necesita**: es la identidad que crea tablas al migrar. No entra en la propuesta.

---

# BLOQUE E — CHECKLIST DE ROTACIÓN (DOKPLOY)

Para el administrador. **No se automatiza desde el repositorio, no se escriben
secretos en ningún archivo, no se imprime ningún valor.**

**Proyecto: `automatizacion-rp-supabase-dgimpk`** — no `crm-agentico-*`.

Contexto medido que hace falta antes de empezar: los servicios de ese stack
conectados a la base son **PostgREST 14.12** (rol `authenticator`), **Realtime**
(`supabase_admin`), **Storage** (`supabase_storage_admin`) y **Supavisor**.

| # | Paso | Cómo se sabe que salió bien |
|---|---|---|
| 1 | **Rotar `JWT_SECRET`.** Generar ≥40 caracteres con el gestor de secretos. Nunca a mano en un archivo | el valor nuevo queda solo en Dokploy |
| 2 | **Regenerar `ANON_KEY`** — JWT firmado con el secreto nuevo, claims `role: anon`, `iss: supabase` | decodificar y ver `role=anon` |
| 3 | **Regenerar `SERVICE_ROLE_KEY`** — ídem con `role: service_role` | ídem |
| 4 | **Aplicar los tres valores** en los servicios que los llevan: `kong`, `auth` (GoTrue), `rest` (PostgREST), `realtime`, `storage`, y `studio` si existe | los tres presentes en cada servicio |
| 5 | **Redeploy / recreate.** Dokploy aplica las variables **al recrear el contenedor, no al guardar el formulario** (`DESPLIEGUE.md` lo advierte dos veces) | contenedores con fecha de creación nueva |
| 6 | **Verificar que el secreto anterior ya no valida** | avisarme: lo compruebo por firma HS256, sin usar ningún token contra ningún servicio y sin imprimir valores |
| 7 | **Verificar que el servicio sigue operativo** | los cuatro servicios reconectan a la base; `pg_stat_activity` vuelve a mostrarlos |

Después, y solo entonces, dos pasos que sí puedo ejecutar yo con autorización:

```sql
-- retirar la copia del secreto que nadie usa dentro de la base
ALTER DATABASE postgres RESET app.settings.jwt_secret;
ALTER DATABASE postgres RESET app.settings.jwt_exp;
```

> Medido: **ninguna función SQL de esta base lee ese GUC** y `pgjwt` no está
> instalada. **Límite honesto:** eso prueba que ninguna función *de la base* lo
> usa; **no** prueba que ningún servicio externo lo lea por SQL. El paso 4 de
> esta checklist —revisar la configuración del stack en Dokploy— es lo único que
> puede cerrar esa duda.

## Impacto, para decidir la ventana antes de ejecutar

| Se invalida | Alcance |
|---|---|
| `SERVICE_ROLE_KEY` y `ANON_KEY` actuales | quien los tenga guardados; el Studio de Supabase |
| Sesiones de GoTrue | si hay usuarios autenticados por Supabase Auth |
| Conexiones de Realtime con JWT | se reconectan con el token nuevo |
| **Sesiones y tokens del CRM (Django)** | **NO se afectan** — usan `SECRET_KEY`, otro secreto |
| **Motor ↔ base y CRM ↔ base** | **NO se afectan** — psycopg directo, sin JWT |

`SUPABASE_SERVICE_ROLE_KEY` está en el `.env` y **ningún archivo de código de
este repositorio lo lee** (grep completo). El impacto real recae en el stack de
Supabase, no en la plataforma.

---

# ACTIVACIÓN AUTONOMÍA 2 — CHECKLIST

## PRECONDICIONES TÉCNICAS

| | Qué | Estado hoy |
|---|---|---|
| ☐ | Migración `supabase/202609191430_autonomia2_autorizacion.sql` aplicada a producción | **NO aplicada** — las tres tablas ausentes |
| ☑ | El piloto pasa los 12 puntos del Bloque A | **sí**, todo en verde |
| ☑ | Runtime `crm_user` 18/18 en entorno aislado | **sí**, re-ejecutado hoy |
| ☑ | Fail-closed en `idempotencia.ejecutar` | **sí** (corrección cerrada) |
| ☑ | El SQL probado contra PostgreSQL real | **sí**, en el aislado |
| ☐ | Fila de `nivel_autonomia` (techo) para la empresa | **no existe** |
| ☐ | Fila de `autorizacion_herramienta` para `crear_tag_crm` | **no existe** |

## PRECONDICIONES DE SEGURIDAD

| | Qué | Estado hoy |
|---|---|---|
| ☐ | **`JWT_SECRET` rotado y verificado** (Bloque E) | **NO** — el GUC existe y verifica la firma del `SERVICE_ROLE_KEY` |
| ☐ | GUC `app.settings.jwt_secret` retirado | **NO** — existe, legible por `crm_user` |
| ☐ | Camino indirecto `service_role` cerrado | **NO** — `service_role` tiene `BYPASSRLS` y `authenticator` puede `SET ROLE` |
| ☐ | `DBUSER` = `crm_user` | **NO** — `session_user` medido: `postgres` |
| ☐ | `REVOKE CREATE ON SCHEMA public FROM crm_user` | **NO** — pendiente (Bloque D: no necesario) |
| ☑ | Los cuatro REVOKE aplicados | **sí** — TRUNCATE/REFERENCES/TRIGGER 0, secuencias UPDATE 0 |
| ☑ | `crm_user` sin SUPERUSER/BYPASSRLS/CREATEDB/CREATEROLE | **sí** |
| ☑ | R3 y R4 fuera del piloto | **sí**, medido con techo 4 |
| ☑ | `limites` clasificado como metadata | **sí**, con guarda |

## PRECONDICIONES OPERATIVAS

| | Qué | Estado hoy |
|---|---|---|
| ☐ | Ventana de cambio definida | **no definida** — es decisión suya, no la invento |
| ☐ | Vigencia de la autorización del piloto (`vigente_hasta`) decidida | **no decidida** |
| ☐ | Quién autoriza (el `autorizado_por` que va en la fila) | **no definido** |
| ☐ | Kill switch levantado | **`detenido`** |
| ☐ | `AUTONOMIA_2_ACTIVA` encendida | **apagada** (ausente del `.env`) |
| ☑ | Rollback definido: revocar, bajar el techo, apagar la variable o el kill switch | **sí**, ninguno requiere desplegar |

## ACCIÓN HUMANA OBLIGATORIA

Lo que **no puedo hacer yo** y bloquea todo lo demás:

1. **Rotar `JWT_SECRET` en Dokploy** (Bloque E, pasos 1–5). No tengo acceso:
   sin variables `DOKPLOY_*`, sin CLI, sin `~/.dokploy`, sin token.
2. **Autorizar** el cambio de `DBUSER` y la ventana.
3. **Decidir** la vigencia y el responsable de la autorización del piloto.
4. **Levantar el kill switch** y **encender `AUTONOMIA_2_ACTIVA`**, en ese orden
   y solo al final.

## Lo que sigue siendo cierto hoy, dicho sin rodeos

- **B-7 NO está cerrado** mientras el secreto no se rote y se verifique.
- **`DBUSER` sigue en `postgres`** hasta ejecutar el cambio autorizado.
- **El kill switch sigue `detenido`.**
- **`AUTONOMIA_2_ACTIVA` sigue apagada.**
- **`crear_tag_crm` no se ejecuta todavía.**
- **Las migraciones de Autonomía 2 no se aplican todavía en producción.**
- **No se inserta ninguna autorización productiva todavía.**

Y una consecuencia de diseño que conviene tener presente: aunque se encienda
`AUTONOMIA_2_ACTIVA`, **el motor sigue contestando `B7_REQUERIDO`** mientras el
GUC exista. El prerequisito se mide contra la base; no es una bandera que se
pueda dar por buena.

---

# REGRESIÓN

- **Núcleo: 87 de 89** archivos. Los 2 que fallan son previos y ajenos
  (`test_p2_inerte`, guarda del scheduler; `test_reloj`, barridos sin datos de
  conexión). Ninguno menciona Autonomía 2 ni importa los módulos tocados.
- **CRM (Django)**: sin cambios desde la corrida completa anterior
  (**4383 pasan / 10 fallan**, todas de entorno SQLite o deriva previa).
  `django-crm/backend` no importa nada de `nucleo/`.

# PRODUCCIÓN

```
asistente.nivel_autonomia            existe=False
asistente.autorizacion_herramienta   existe=False
asistente.ejecucion_autonoma         existe=False
kill switch: Rapilink | detenido     (sin cambios)
tablas en public: 135 · roles: 41 · django_migrations: 192
DBUSER efectivo: postgres
```

Todo lo que se consultó fue con `transaction_read_only = on` verificado en el
servidor. Ninguna escritura.

---

# CRITERIO DE SALIDA: **PASS**

| Criterio | Resultado |
|---|---|
| no hay nuevo fail-open | **cumple** — los dos hallazgos se midieron y ninguno ejecuta algo no autorizado |
| `crear_tag_crm` tiene una única frontera verificable | **cumple** — dos puertas en `frontera.py`, control en el ejecutor, la ruta alternativa queda bloqueada |
| `limites` clasificado como metadata | **cumple**, con guarda que obliga a reclasificar |
| estado de B-7 confirmado sin modificar producción | **cumple** |
| `CREATE` clasificado | **cumple** — **NO NECESARIO**, pendiente de revocación |
| checklist exacta de Dokploy | **cumple** |
| criterios objetivos de activación | **cumple** |

## Los dos hallazgos, juntos, para que no se pierdan

1. **`invocable_por_servicio` se comprueba en la ruta, no en la función.** No es
   un fail-open (la frontera gobierna igual, medido con y sin autorización), pero
   es un control en el llamador. Corrección propuesta de una línea; **no
   aplicada**, porque toca la ruta `/interno`, fuera de este bloque.
2. **La bitácora no guarda el desenlace ni la clave de idempotencia.** Registra
   qué se autorizó, no cómo terminó. El desenlace existe en
   `operaciones_externas`, pero **el puente entre las dos tablas no se escribe**.
   El punto 10 se cumple a medias, y lo digo así en vez de darlo por bueno.

---

**No se hizo commit. No se tocó producción. No se levantó el kill switch. No se
cambió `DBUSER`. No se aplicaron migraciones productivas. No se ejecutó
`crear_tag_crm`. No se usó `git stash`.**
