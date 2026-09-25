# M06-C — Aislamiento de la autorización y aprobación R4 completa

Fecha: 21/09/2026 · Rama local: `fix/integracion-wisphub` · **Sin commit, push,
PR ni deploy. Sin migraciones aplicadas en ningún entorno persistente.**

## Resumen

- **Parte A.** `autorizacion_herramienta` y `ejecucion_autonoma` ahora tienen
  RLS **forzada** por organización, con el patrón exacto del interruptor y del
  techo. Se probó contra Postgres real: lectura y escritura entre empresas,
  runtime legítimo, operador legítimo, identidad sin permisos y qué ve una
  identidad con BYPASSRLS.
- **Parte B.** `agregar_promesa_pago` pasa a la puerta crítica. Al hacerlo
  apareció un límite del mecanismo de M06-A frente a tus reglas 4 y 5: **el
  origen y el tenant solo se exigían "no vacíos", no se comparaban**. Se cerró
  con un **sello de aprobación**, que vale para las cinco acciones R3/R4.

---

## 1. Archivos modificados

| Archivo | Cambio |
|---|---|
| `supabase/202609212000_m06c_aislamiento_y_sello.sql` | **Nueva, sin aplicar.** RLS de las dos tablas, columna `sello_aprobacion`, trigger extendido, comprobaciones |
| `nucleo/seguridad/aprobacion.py` | `sello_de()`; `Aprobacion` lleva organización y sello; el veredicto exige el sello y lo recalcula (`APROBACION_SIN_SELLO`, `APROBACION_ALTERADA`) |
| `nucleo/persistencia/db.py` | `aprobar_accion_propuesta` bloquea la fila, calcula el sello y lo escribe en el mismo UPDATE que aprueba (compare-and-set) |
| `tenants/rapilink.config.yaml` | `agregar_promesa_pago`: `irreversible: true` (solo la semilla) |
| `tests/test_m06c_promesa_y_aislamiento.py` | **Nuevo**: 37 comprobaciones sin base |
| `tests/test_m06c_postgres.py` | **Nuevo**: 34 comprobaciones contra Postgres descartable |
| `tests/test_m06a_gate_critico.py` | La fila de prueba se **sella** como la sellaría la aprobación, antes de aplicar las alteraciones; R4 incluye la promesa; "22 escrituras no irreversibles" (eran 23) |
| `tests/test_m06a_frontera_autorizacion.py` | La decisión pasa a ser todo R3 y R4 (5), tomada de la clasificación de M10-A y no de una lista a mano |
| `tests/test_m06b_techo_autonomia.py` | El control "lo que declara aprobación no sale autónomo" se prueba con una copia en memoria del piloto que declara aprobación, porque la promesa ya es irreversible |
| `PRD.md`, este informe | Documentación |

No se tocaron frontera, kill switch, techo, niveles, clasificación R1–R4, WispHub,
SmartOLT, Case ni OT, y no se crearon herramientas.

## 2. Cambios de RLS

Quién usa cada tabla, medido en el código:

| Tabla | Escribe | Lee | Django | Acceso legítimo entre empresas |
|---|---|---|---|---|
| `autorizacion_herramienta` | **nadie en código**; solo `autonomia_operador` tiene INSERT | el gate (`persistencia.autorizacion_herramienta`), como `app_backend` | no la toca | ninguno |
| `ejecucion_autonoma` | la bitácora de la frontera (`registrar_ejecucion_autonoma`), como `app_backend` | nadie en código; `app_backend` y el operador tienen SELECT | no la toca | ninguno |

Qué cambió:

- **ENABLE + FORCE RLS** en las dos, igual que `interruptor_autonomia` y
  `nivel_autonomia`.
- **Una política por rol y por comando**, siempre contra `asistente.org_actual()`.
- **No se agregó ningún permiso**: las políticas acotan lo que los GRANTs ya
  daban.
- La migración **comprueba al final** tres cosas: que las dos tablas tengan RLS
  forzada, que el runtime no tenga escritura sobre las autorizaciones, y que el
  runtime no pueda reescribir ni borrar la bitácora. Si alguna falla, la
  migración falla.

## 3. Política de acceso por tenant

| Rol | `autorizacion_herramienta` | `ejecucion_autonoma` |
|---|---|---|
| `app_backend` (runtime) | **leer** solo su empresa | **leer** y **agregar** solo en su empresa; nunca modificar ni borrar |
| `autonomia_operador` | leer y agregar solo en su empresa (autorizar y revocar) | **leer** solo su empresa |
| cualquier otro rol | sin acceso | sin acceso |

Sin empresa activa (`app.current_tenant` vacío), el runtime ve **0 filas**.

**BYPASSRLS (punto F):**

- El usuario con el que **conecta** el motor lo tiene. Así resuelve el tenant
  antes de bajar de rol (`persistencia/db.py::_organizacion`).
- `service_role` también lo tiene: es el vector de B-7.
- Ninguno de los dos es el rol que lee o escribe. El motor hace
  `SET ROLE app_backend`, que no lo tiene, y ahí la RLS aplica.
- Se midió en Postgres: el usuario que conecta ve las dos empresas;
  `app_backend` (`bypassrls=false`) no.
- La existencia de BYPASSRLS en otra identidad no justifica dejar las tablas
  sin política: es exactamente lo que vuelve necesaria la política.

## 4. El vínculo de aprobación de `agregar_promesa_pago`

**Qué pasó:**

- Queda marcada `irreversible`.
- Su propuesta guarda la **huella canónica** de los argumentos (factura, fecha
  límite, acción) y el **origen** (el mensaje que la pidió).
- Aprobarla persiste estado, aprobador, momento y **sello**, **antes** del
  efecto.
- Ejecutarla pasa por la cadena completa: tenant → kill switch → techo → etapa →
  autorización granular → aprobación atada → auditoría → permiso → idempotencia
  → último metro.

**El sello.** Se calcula así:

```
sello = SHA-256 canónico de { tenant, organization_id, herramienta, origen, huella, aprobador }
```

Se escribe al aprobar, con la fila bloqueada. Al ejecutar se recalcula con el
**tenant que está ejecutando** y la **herramienta que se va a ejecutar**, más lo
que la fila dice en ese momento. Si cambió cualquiera de esos datos, no
coincide. Después de aprobar, el trigger impide reescribirlo, incluso como
administrador.

| Regla | Cómo se cumple | Código |
|---|---|---|
| 1. No sirve para `registrar_pago` | herramienta distinta, y además el sello | `APROBACION_DE_OTRA_HERRAMIENTA` / `ALTERADA` |
| 2. No sirve para otra promesa | huella de argumentos | `APROBACION_DE_OTROS_ARGUMENTOS` |
| 3. Argumentos cambiados después de aprobar | huella; si también se acomoda la huella, el sello | `OTROS_ARGUMENTOS` / `ALTERADA` |
| 4. Cambia el tenant | el sello incluye tenant y organización | `ALTERADA` / `APROBACION_DE_OTRO_TENANT` |
| 5. Cambia el origen | el sello incluye el origen (antes solo "no vacío") | `ALTERADA` |
| 6. No se ejecuta dos veces | compare-and-set al aprobar (la segunda aprobación encuentra 0 filas) | — |
| 7. Replay | idempotencia sobre `accion_aprobada:<id>` | 1 sola escritura |
| 8. La aprobación existe antes del efecto | se persiste antes de ejecutar; la frontera la lee de la fila | — |
| 9. Sin aprobación, cero efecto | la puerta crítica y el último metro | `APROBACION_NO_VIGENTE` / `AUSENTE` |
| 10. Con aprobación, sigue por las demás barreras | kill switch, techo, etapa y autorización granular siguen mandando | pruebas 13–15 |

**Alcance del sello.** Se aplica a las **cinco** irreversibles, no solo a la
promesa, porque el hueco de origen y tenant era del mecanismo. Es un control
**agregado**: los códigos de bloqueo de M06-A no cambian y su batería pasa
entera (110 comprobaciones).

## 5. Migraciones

`supabase/202609212000_m06c_aislamiento_y_sello.sql` es **nueva, está revisada y
se probó en Postgres descartable. No se aplicó en ningún entorno persistente.**

- No tiene `RunPython` ni `RunSQL`: es SQL del motor. No hay migraciones de Django.
- Es aditiva: RLS, políticas, una columna nullable y el trigger reemplazado.
- Es idempotente: aplicada dos veces, no falla.
- Su orden de despliegue es: `202609191430` (Autonomía 2) → `202609211800` (M06-A) →
  `202609211900` (M06-B) → `202609212000` (M06-C). Ninguna consta como aplicada.

Sin ella, el código falla cerrado: sin la columna, la aprobación no se escribe; y
una fila sin sello da `APROBACION_SIN_SELLO`.

## 6 y 7. Pruebas ejecutadas y resultado

**`tests/test_m06c_promesa_y_aislamiento.py`** (código real, red y base
simuladas): **37 de 37.**

- Puntos 6–15.
- El sello por su cuenta: sin sello, otro aprobador, sello falso.
- Los bypass de M06-A/B aplicados a la promesa: `_ejecutar_tool`, ejecutor
  directo, ruta de servicio, `humana()`, `autonoma()` y el ejecutor de
  aprobaciones común. Todos quedan bloqueados, y el control positivo por la
  puerta crítica **sí** sale.
- La conversación propone la promesa atada, con 0 llamadas.
- La parte estática de la migración.

**`tests/test_m06c_postgres.py`** (código real contra una base **creada y
borrada** en el contenedor local `pg-b7`; se niega a correr contra otro host):
**34 de 34.**

| # | Resultado |
|---|---|
| 1 | Lectura entre empresas bloqueada en las dos tablas: A ve 1 fila, 0 de B; sin empresa activa, 0 |
| 2 | Escritura entre empresas bloqueada: el runtime no escribe la bitácora de B y el operador de A no autoriza en B. El runtime no reescribe ni borra la bitácora, y las filas quedan intactas |
| 3 | El runtime legítimo funciona con el código real: lee la autorización de su empresa, escribe su bitácora, y la autorización de punta a punta da `autorizada` |
| 4 | El operador legítimo funciona: revoca en su empresa, el gate lo ve al instante (`REVOCADA`) y lee solo su bitácora |
| 5 | Una identidad sin permisos no lee ninguna de las dos; el runtime no puede autorizarse |
| F | BYPASSRLS medido (sección 3) |
| Sello | Escrito por la base igual al calculado; vale para esa promesa y no para `registrar_pago`; una segunda aprobación da 0 filas; reescribir origen, sello, aprobador o argumentos se rechaza **incluso como administrador** (`CheckViolation`); una propuesta pendiente no puede traer sello; A no ve la propuesta desde B |

**Desarme:** cada control se rompió a propósito y la prueba lo detectó. Los
archivos se restauraron idénticos (sha256).

| Control desarmado | Fallas | Qué se vio |
|---|---|---|
| Comparar el sello | 7 | Las alteraciones de origen, tenant, organización y la fila de un pago re-etiquetada **se ejecutan** |
| Exigir que haya sello | 1 | Una fila sin sello queda frenada igual (`ALTERADA`): defensa en profundidad, pero el código cambia y la prueba lo nota |
| Promesa `irreversible` | 22 | Vuelve el camino de antes: aprobación no atada |
| Origen dentro del sello | 1 | Cambiar el origen **pasa** |
| RLS de `ejecucion_autonoma` (contra Postgres) | 6 | A **lee y escribe** la bitácora de B |

En el desarme de la RLS, una etiqueta tenía texto fijo ("ninguna de B") que
mentía en rojo. Se corrigió para mostrar el conteo medido.

## 8. Regresión completa

**Suite relacionada** (seguridad y frontera, M06-A, M06-B, M10-A, escalada):
todas en verde. En particular:

- `test_m06a_gate_critico`: **110** (antes 97; ahora incluye la promesa en cada
  sección).
- `test_m06a_frontera_autorizacion`: **73**.
- `test_m06b_techo_autonomia`: **94**.
- `test_m06b_techo_postgres`: **20**, contra Postgres, después de M06-C.
- `test_m10a_gobierno_frontera`: **23**.
- `test_escalada_forzada`: **120**.

**Motor (`tests/`, 96 archivos, uno por uno con su exit code): 94 de 96 en
verde.** Las dos pruebas de Postgres aparecen en verde en esa cuenta porque en el
host se **omiten**, y lo dicen; sus resultados reales son los de arriba (34 y
20), corridas en contenedor. Las 2 fallas son las preexistentes de la sección 9.

**Django (backend completo, base descartable `pg-b7`):**
`2 failed, 4585 passed, 43 skipped` en 22:03. Es idéntico a M05-B, M06-A y M06-B:
**0 fallos nuevos**. M06-C no toca Django.

## 9. Fallas preexistentes

Son las mismas cuatro de los bloques anteriores, todas demostradas:

- **Motor:**
  - `test_p2_inerte`: señala archivos del 17/09, sin versionar, que este bloque
    no tocó.
  - `test_reloj`: espera 4 herramientas de importación y hay 5; la quinta ya
    está en `HEAD` (601a001).
- **Django:**
  - `test_docs_environment_variables`: falla igual contra `origin @ 73bb30c`.
  - `test_portal_rls`: corre como `admin`, que tiene `BYPASSRLS`.

## 10. Producción no fue tocada

- Sin deploy, push, commit ni PR.
- El cambio de config está solo en la semilla YAML.
- Las pruebas con base corrieron contra `pg-b7`, local, en bases creadas y
  borradas por la propia prueba. Los roles que crearon (`autonomia_operador`,
  `m06c_intruso`) también se borraron.
- El `.env` real quedó tapado por uno vacío en cada corrida en contenedor.

## 11. Acciones sobre clientes

Ninguna. Los datos son inventados: factura `999001`, dominio `.invalid`.

## 12. WispHub y SmartOLT

No hubo llamadas reales. El módulo `requests` del ejecutor estaba reemplazado por
uno que solo anota, y la credencial por `clave-de-prueba`. No se corrieron los
casos dorados.

---

## Lo que queda abierto (no es de este bloque)

- **La cola de aprobación sigue sin pantalla** en este repo. Ahora la promesa
  también va a esa cola.
- Con la cadena completa, **ninguna de las cinco acciones R3/R4** puede
  ejecutarse hasta que se enciendan la etapa, se cierre B-7, haya autorización
  granular y un techo ≥ 2. Es lo pedido, y ahora incluye la promesa: facturación
  deja de registrar promesas desde el asistente hasta que se cumplan esas
  condiciones.
- Las cuatro migraciones del motor (Autonomía 2, M06-A, M06-B y M06-C) y las de
  Django de M04/M05 siguen sin aplicar.
