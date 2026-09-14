# Scheduler persistente — arquitectura efectiva

> Describe lo que **implementa** el candidato `79b1f10`, no el diseño previo.
> Donde el diseño previo decía otra cosa, se dice aquí explícitamente.
> Cada afirmación lleva la prueba que la mide.

## Corrección respecto del diseño anterior

El diseño previo decía que **solo el coordinador** podía hacer heartbeat y
finalizar. La implementación reparte distinto, y es la que vale:

| rol de acceso | puede ejecutar | no puede |
|---|---|---|
| `scheduler_coordinator` | `jobs_vencidos`, `job_claim` | `job_contexto`, `job_heartbeat`, `job_finalize`, `job_salud` |
| `job_executor` | `job_contexto`, `job_heartbeat`, `job_finalize` | `job_claim`, `jobs_vencidos`, `job_salud` |
| `monitor_ro` | `job_salud` | todo lo demás |
| `app_backend` | ninguna función `job_*` | — |
| PUBLIC | ninguna | — |

Medido: `tests/test_matriz_de_roles.py` (conectando como superusuario +
`SET ROLE`) y `tests/test_roles_de_conexion.py` (conectando **como cada
login**, con contraseña).

Por qué así y no como decía el diseño: quien sabe si el trabajo sigue vivo es
quien lo está haciendo. Si el heartbeat dependiera del coordinador, la muerte del
coordinador mataría leases de trabajos sanos; y si el coordinador finalizara,
tendría que recibir el resultado del ejecutor por algún canal, que es una
segunda copia del desenlace que puede divergir.

## Quién hace qué

```
coordinador                          PostgreSQL                      ejecutor
-----------                          ----------                      --------
jobs_vencidos() ──────────────────►  lee job_schedule_state
job_claim(job, org, slot) ────────►  congela config, abre intento,
                                     genera capability, guarda hash
            ◄──── run_id + capability (en claro, UNA vez)
entrega (run_id, capability) ─────────────────────────────────────►
                                                job_contexto(run_id, cap) ◄──
                                     relee turno, recalcula hashes,
                                     fija app.current_tenant ────────────►
                                                                    trabaja
                                                job_heartbeat(att, cap) ◄── cada lease/3
                                                job_finalize(att, cap, …) ◄──
                                     cierra intento, evento, backoff
                                     o avanza la grilla
```

## Escenarios de falla

### Muere el coordinador, el ejecutor sigue vivo

- **Con procesos separados** (lo que P5 exige, ver hallazgo abajo): no pasa
  nada con el turno en curso. El ejecutor tiene su capability, late por su
  propia conexión y finaliza él mismo. El coordinador no participa en ninguna de
  esas tres llamadas — no tiene ni el permiso.
- **En el modo en-proceso de hoy** (`coordinador.un_tick` llama a
  `ejecutor.ejecutar` en el mismo proceso): coordinador y ejecutor son el mismo
  proceso, así que mueren juntos y aplica el caso siguiente.

### Muere el ejecutor

1. Nadie late. El intento queda abierto (`outcome is null`).
2. `lease_until` vence. Hasta entonces `jobs_vencidos` **no** devuelve el turno.
3. Vencido, lo devuelve con `motivo = 'lease_vencido'`.
4. Un coordinador —cualquiera— lo reclama: cierra el intento viejo como
   `lease_lost`, abre el siguiente con `fencing_version` mayor y capability nueva.
5. El turno conserva `run_id`, `idempotency_key`, `config_version`,
   `config_hash`, `inputs` e `inputs_hash`.

Medido con un proceso matado con `kill` —no un hilo, no un `return`—:
`tests/test_scheduler_multiproceso.py`, secciones 2 y 3.

### Se pierde la conexión del heartbeat

- `_Latido` atrapa el error, **no** marca el lease como perdido y reintenta en
  la vuelta siguiente (cada `lease_duracion / 3`). Un corte breve no abandona
  trabajo válido.
- Si el corte dura más que el lease, el siguiente heartbeat exitoso devuelve
  `NULL` —`job_heartbeat` no renueva un lease vencido— y el ejecutor marca
  `lease_perdido`.
- El hilo del trabajo **no se mata**: matarlo a mitad de un POST deja el efecto
  hecho y el registro sin escribir. Su `job_finalize` devolverá `NULL`.
- Consecuencia: el trabajo puede quedar hecho dos veces. El contrato es
  **at-least-once**.

### Recuperación del lease

Solo por vencimiento. No hay "robar" un lease vivo ni forzarlo: `job_claim`
re-verifica `lease_until` **dentro** del `for update skip locked`.

### Vuelve el proceso muerto

Su capability ya no sirve para nada: `job_finalize`, `job_heartbeat` y
`job_contexto` devuelven `NULL` / cero filas, porque su intento está cerrado y
el fencing avanzó. Medido: multiproceso, sección 4; y el fencing aislado del
cierre del intento en `test_scheduler_funciones.py`.

## Quién conserva la capability

- El valor en claro existe **solo en memoria** del proceso que recibió el
  resultado de `job_claim`, y del ejecutor al que se entrega.
- En la base queda únicamente `sha256`. **Ninguna función vuelve a emitir una
  capability existente.**
- Si el proceso que la tiene muere, la capability se pierde con él. **No se
  recupera**: se recupera el *turno*, por vencimiento del lease, con una
  capability nueva.
- No aparece en logs, métricas, eventos ni en el `repr` del `Turno`
  (`test_p2_compuertas.py`, bloque B).

## Quién registra el resultado

El **ejecutor**, con `job_finalize`, bajo `job_executor`. El coordinador no
puede — no tiene `EXECUTE`. Si `job_finalize` no llega (red, caída), el intento
queda abierto con lease y se rescata como en "muere el ejecutor".

El desenlace registrado puede no ser el reportado: un `failed_retryable` en el
último intento se registra `failed_terminal`, para que haya un solo evento
terminal por intento.

---

## HALLAZGO para P5: el modo en-proceso necesita dos membresías

`coordinador.un_tick` reclama con `puerta.sesion(COORDINADOR)` y, en el mismo
proceso y con el mismo DSN (`conexion.dsn()`), llama a `ejecutor.ejecutar`, que
abre `puerta.sesion(EJECUTOR)`.

Con un login de **una sola membresía** —la condición que P5 exige— eso no
funciona. Medido (`test_roles_de_conexion.py`, sección 5) conectando como
`scheduler_login`:

- el claim funciona;
- la fase de ejecución falla con `InsufficientPrivilege` al asumir
  `job_executor`;
- el turno queda reclamado con lease vivo y **se atrasa un lease entero** hasta
  que otro lo rescate.

Lo que P5 tiene que hacer, sin tocar el candidato:

1. **Dos procesos**, cada uno con su login: el coordinador reclama; el ejecutor
   recibe `(run_id, capability)` y ejecuta.
2. **Entrega por pipe**: el coordinador lanza el proceso ejecutor y le escribe
   `run_id` y capability por **stdin**. Nunca por argv (visible en `ps`), ni
   variable de entorno (visible en `/proc`), ni archivo, ni cola persistente, ni
   log. La prueba multiproceso usa un archivo temporal para la entrega: **es solo
   de prueba** y no es el canal de producción.
3. **DSN por rol** en `puerta.sesion`, en vez de un `conexion.dsn()` común.
4. **Guard de superusuario** en `puerta.sesion`: rehusar arrancar si
   `session_user` tiene `rolsuper` o `rolbypassrls`. Hoy no existe. Medido por
   qué importa: conectado como `motor`, después de `set role
   scheduler_coordinator` basta `reset role` para leer `asistente.job_run`
   directamente.

## Usuarios de conexión

Declarados en `supabase/roles/conexiones_scheduler.sql`, fuera de la cadena de
migraciones:

| login | única membresía | opciones |
|---|---|---|
| `scheduler_login` | `scheduler_coordinator` | `SET TRUE`, `INHERIT FALSE`, `ADMIN FALSE` |
| `executor_login` | `job_executor` | ídem |
| `monitor_login` | `monitor_ro` | ídem |

Todos `LOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE
NOREPLICATION`, **sin contraseña en el archivo**. El archivo converge: reaplicado,
revoca cualquier membresía ajena. Medido en `test_roles_de_conexion.py`.
