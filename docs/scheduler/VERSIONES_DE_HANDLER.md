# Versiones de handler y despliegue gradual

> **Estado: DISEÑO para P5. No implementado. NO VERIFICADO.**
> Corrige un comportamiento que P2 (`79b1f10`) sí tiene y que no puede llegar a
> activación tal como está.

## El problema, medido

En P2, un ejecutor que recibe un turno cuyo `job_code` no está en su registro
cerrado lo **finaliza como `failed_terminal`** con `JOB_SIN_IMPLEMENTACION`.
Medido en `tests/test_scheduler_multiproceso.py`, sección 6: un proceso nuevo
arranca con el registro vacío y cierra el turno terminal.

Con una sola versión de imagen eso es correcto. **Durante un despliegue gradual
no lo es**: una réplica vieja que recibe un job agregado por la imagen nueva lo
cierra para siempre, y la grilla avanza al slot siguiente. El turno se pierde
aunque haya réplicas nuevas perfectamente capaces de ejecutarlo.

Lo mismo pasa si el handler existe en las dos imágenes pero con **contratos
incompatibles** (la nueva espera inputs que la vieja no entiende).

## Principio

**Un ejecutor sin handler compatible nunca consume el turno ni lo cierra.**
Incompatibilidad no es un fallo del turno: es un problema de flota, y se alerta
como tal.

## Piezas

### 1. Versión mínima en el catálogo

```sql
alter table asistente.job_catalogo
  add column handler_version_minima integer not null default 1
  check (handler_version_minima >= 1);
```

Un entero monótono por `job_code`. Se sube **solo** cuando el contrato del
handler cambia de forma incompatible. Se cambia con una función administrativa
auditada (ver `CORTE_Y_ROLLBACK.md`, P8), nunca con `UPDATE`.

### 2. La versión vive en el código, junto al handler

```python
_PRODUCCION = {
    "importacion_tickets": (barrido_importacion, 3),   # (handler, version)
}
```

La versión no sale de una variable de entorno ni de la base: la declara la
imagen que efectivamente tiene ese código.

### 3. Cada ejecutor anuncia sus capacidades

```sql
create table asistente.job_executor_presencia (
  executor_id    text primary key,          -- host + pid + arranque
  version_imagen text not null,             -- digest de la imagen
  capacidades    jsonb not null,            -- {"importacion_tickets": 3, ...}
  visto_en       timestamptz not null
);
```

`asistente.job_executor_anunciar(p_executor_id, p_version_imagen, p_capacidades)`,
`SECURITY DEFINER`, solo para `job_executor`. Se llama al arrancar y en cada
heartbeat. Una fila con `visto_en` más viejo que el TTL (propuesta: 3 ×
`lease_duracion`) no cuenta.

### 4. Asignación previa compatible

`job_claim` recibe el `executor_id` destino y **solo reclama** si la fila de
presencia de ese ejecutor está viva y `capacidades ->> job_code >=
handler_version_minima`. Si no, devuelve cero filas: no se abre intento, no se
incrementa `attempt_count` ni `fencing_version`. El intento guarda
`asignado_a = executor_id`.

El coordinador elige el destino entre los ejecutores vivos y compatibles; si no
hay ninguno, omite el candidato con motivo **`sin_executor_compatible`** en el
embudo.

### 5. Devolución sin consumir

Defensa en profundidad para la carrera en la que un ejecutor se degrada entre la
asignación y el arranque (reinicio con imagen vieja, registro distinto):

`asistente.job_devolver(p_attempt_id, p_capability, p_motivo)` — solo
`job_executor`:

- cierra el intento con `outcome = 'devuelto'` (nuevo valor);
- **no** cuenta para `max_intentos` (se descuenta de `attempt_count`);
- suelta el lease **sin backoff**: el turno vuelve a ser elegible de inmediato
  para otro ejecutor;
- escribe el evento `HANDLER_INCOMPATIBLE`;
- nunca transiciona el run a terminal.

El ejecutor reemplaza la rama actual `JobSinImplementacion → failed_terminal`
por `JobSinImplementacion → job_devolver`.

Tope contra bucles: si un mismo run acumula N devoluciones seguidas sin ningún
intento real (propuesta: 5), el coordinador deja de asignarlo hasta que aparezca
un ejecutor compatible nuevo, y alerta. **Tampoco** entonces se cierra terminal.

### 6. Alerta

`job_salud` agrega por `job_code`, sin organización:

- `sin_executor_compatible`: jobs habilitados cuya versión mínima no satisface
  ningún ejecutor vivo;
- `devoluciones_ultima_hora`.

`cli/salud_scheduler.py` termina en 1 si el primero es mayor que 0.

## Despliegue gradual con versiones mezcladas

1. La imagen nueva trae el handler v4; el catálogo sigue en v3. Las dos
   generaciones de ejecutores son compatibles: nada cambia.
2. Se despliegan réplicas nuevas junto a las viejas.
3. Cuando la presencia muestra al menos un ejecutor vivo con v4, un operador sube
   `handler_version_minima` a 4 con la función auditada. **La función se niega**
   si ningún ejecutor vivo cumple la versión nueva: nunca queda un job sin nadie
   capaz de ejecutarlo por un cambio de catálogo.
4. Desde ese instante las réplicas viejas dejan de recibir asignaciones de ese
   job. Si alguna recibe uno por carrera, lo devuelve sin consumirlo.
5. Se retiran las réplicas viejas.

Rollback del paso 3: bajar la versión mínima con la misma función auditada,
**antes** de retirar las réplicas nuevas.

## Pruebas exigidas en P5

| escenario | resultado esperado |
|---|---|
| ejecutor viejo + job nuevo | sin claim; `attempt_count` y `fencing_version` intactos; ningún evento terminal |
| ejecutor compatible | claim normal |
| registro vacío | alerta `sin_executor_compatible`; el turno sigue elegible |
| devolución por carrera | `outcome = 'devuelto'`, no cuenta como intento, sin backoff, otro ejecutor lo toma |
| rolling deploy con dos procesos de imagen distinta | ningún turno termina `failed_terminal` por incompatibilidad; todos terminan ejecutados por el compatible |
| subir versión sin ejecutor compatible vivo | la función administrativa lo rechaza |
