# B5 — aprobar una acción

```
BASE       d13bcb1
VEREDICTO  implementado, sin aplicar en producción
ENTRADA    G3 cerrado (auditorias/G3-CIERRE.md)
FECHA      20/09/2026
```

## El agujero que cierra

Entre que la IA propone una escritura y que una persona la aprueba pasa tiempo,
y el mundo se mueve: el ticket lo cerró otro técnico, la factura se pagó, el
servicio se dio de baja. Aprobar ejecutaba la propuesta **tal cual**, sin
volver a mirar — escribía sobre un mundo que ya no existía.

## Los cuatro pasos (§9.3)

```
1. reservar    UPDATE condicionado. Transacción corta.
2. revalidar   §3.7. FUERA de transacción.
3. ejecutar    FUERA de transacción.
4. resolver    el desenlace, con su evento (I12).
```

Los dos del medio no están dentro de una transacción a propósito: mantenerla
abierta mientras se espera una API deja sesiones `idle in transaction` detrás
del pooler, y eso ya se midió una vez (X23). El estado `ejecutando` cubre ese
hueco **sin lock** — dice «alguien la tomó» sin que nadie retenga nada.

Las tres condiciones de la reserva viajan **dentro** del UPDATE:

```sql
and estado = 'pendiente'
and (vence_en is null or vence_en > now())
and exists (… conversations … estado = 'abierta')
```

Comprobarlas en una consulta aparte deja una ventana entre la comprobación y
la escritura, y ocho hilos concurrentes la encuentran. Probado con **dos
peticiones HTTP reales compitiendo**: el ejecutor corre una vez, uno recibe 200
y el otro 409.

## La asimetría de la revalidación

Es lo que gobierna `nucleo/relevo/revalidacion.py` entero. **Tres desenlaces,
no dos**:

| | | |
|---|---|---|
| `cumple` | se comprobó y se cumple | ejecuta |
| `no_cumple` | se comprobó y NO se cumple | `vencida` |
| `no_se_pudo` | la API no respondió, dio timeout, falta el campo | **no ejecuta**, vuelve a `pendiente` |

Tratar «no se pudo comprobar» como «se cumple» ejecutaría a ciegas justo cuando
el sistema externo está en problemas — el peor momento posible. Y tratarlo como
«no se cumple» mataría una acción que puede seguir siendo válida. No saber no
es lo mismo que saber que no (X17).

La lectura sale del **mismo catálogo**, no de una URL suelta: así hereda
credenciales, timeouts y las guardas que ya tiene una herramienta declarada.
Una «lectura» que en realidad escribe no corre — correría un efecto antes de
decidir si se corre el efecto. Una revalidación declarada cuya herramienta ya
no está **tampoco se saltea**.

`valor_de_propuesta` cubre el caso de §3.7 para `actualizar_estado_ticket`:
comparar y cambiar. Si otro movió el ticket entre proponer y aprobar, no se
pisa el cambio ajeno.

## El validador, en modo advertencia (Q3)

§3.7 exige `vigencia_minutos` y `revalidar` en toda herramienta aprobable, y el
contrato dice que la carga debe fallar sin ellos. **Esa regla no se puede
encender hoy**: la config vigente de Rapilink no los declara, y escribirla parte
la medición ON vs OFF en curso.

Así que `TenantConfig.advertencias_de_aprobacion()` las reporta en vez de
levantar. El paso a error va en el mismo cambio que active la config nueva.

Lo que **sí** falla cerrado hoy es todo lo que no depende de config: transición
condicionada, conversación abierta, operador autenticado, plazo — y una
revalidación **declarada** que no se puede correr nunca ejecuta.

## Migración

`supabase/202609201800_acciones_b5.sql`. `conversation_id` nullable (sólo por
el legado), `vence_en`, `clave_equivalencia`, el CHECK completo de §3.4 y el
**índice único parcial** sobre `pendiente`/`ejecutando`.

Que el índice sea parcial hace las dos cosas que hacen falta: dos propuestas
equivalentes no pueden estar **vivas** a la vez, y se puede volver a proponer lo
mismo cuando la anterior ya se resolvió.

La deduplicación la sostiene el índice, **no una consulta previa**: comprobar
antes y escribir después deja una ventana.

Ninguna fila se toca. Las 36 de legado siguen `pendiente` con todo en NULL, y
el índice parcial ignora los NULL, así que no colisionan entre ellas.

## La ventana del `conversation_id`

Durante el turno **todavía no existe**: la conversación se crea o se reusa
recién al persistir, en `api.py`. Es el mismo problema que ya tenían
`tool_calls` y los archivos generados, y se resuelve igual — el motor anota la
acción en la sesión y `api.py` la liga cuando el id existe.

**La ventana es segura y no hay que taparla**: mientras la acción no tiene
conversación se la trata como de legado, así que **no se puede aprobar** (X24).
Falla cerrado, y nadie puede aprobar en ese lapso porque el operador todavía no
la vio.

## La pantalla

Panel propio en la conversación. Cuatro finales, cada uno con su texto:

```
ejecutada_ok      se hizo
ejecutada_fallo   NO se hizo, y se sabe
vencida           ya no aplicaba
desconocida       NO SE SABE, y no se reintenta
```

`desconocida` no puede leerse como «falló»: si la pantalla dice que falló,
alguien lo va a rehacer. Misma distinción que el panel de B4, probada igual —
ni el texto, ni el tono.

El botón de aprobar aparece **sólo** donde el backend lo aceptaría. Sin botón de
reintentar. Después de aprobar se **relee** en vez de pintar lo que se
esperaba: el desenlace puede ser `desconocida`, y afirmarlo desde un 200 sería
afirmar un efecto que no se midió.

Quien aprueba sale de la sesión autenticada, nunca del cuerpo (§3.4).

## Tests

```
tests/test_b5_acciones.py          contra PostgreSQL real
  ligada, con plazo y clave · T12 (la equivalente viva no crea otra)
  los tres desenlaces de la revalidación, y comparar-y-cambiar
  los cuatro pasos, medidos por el ejecutor inyectado
  TTL · conversación cerrada · el bloqueo del legado sigue en pie
  DOS aprobaciones concurrentes -> un solo efecto
  unknown != failed · aislamiento entre empresas

acciones.test.js                   18 aserciones
```

**Mutaciones: 16 probadas, 15 rojas.**

| Mutación | Resultado |
|---|---|
| «no se pudo comprobar» pasa a tratarse como «cumple» | ROJO |
| el campo ausente se asume cumplido | ROJO |
| se ejecuta sin revalidar | ROJO |
| la reserva deja de exigir `pendiente` | ROJO |
| la reserva ignora si la conversación está cerrada | ROJO |
| un timeout se trata como fallo definitivo | ROJO |
| la clave de equivalencia deja de mirar los argumentos | ROJO |
| la vista de la conversación vuelve a traer argumentos | ROJO |
| se quita el chequeo previo del plazo | ROJO |
| + 5 sobre la lógica y el cableado de la pantalla | ROJO |
| la reserva ignora el plazo **en el UPDATE** | VERDE |

La superviviente es la **segunda capa** del plazo: quitar la primera sí da
rojo. Es redundancia deliberada — el chequeo previo marca `vencida` con su
evento, y la condición del UPDATE cubre la ventana entre el SELECT y el UPDATE.

**Un bug que encontró el test:** `accion_propuesta_de` no proyectaba
`conversation_id`, así que la guarda del legado bloqueaba acciones que **sí**
tenían conversación. Fallaba cerrado, pero fallaba.

## Riesgos abiertos

1. **La config de Rapilink no declara vigencia ni revalidación**, y no puede
   hacerlo hasta que cierre la medición ON vs OFF (Q3). Hasta entonces las
   acciones nacen **sin plazo** y se aprueban sin revalidar — con las guardas
   que no dependen de config. El mecanismo está entero y probado; lo que falta
   es encenderlo, igual que G7 con el reconciliador.
2. **Las cuatro revalidaciones de §3.7 no están escritas todavía.** El contrato
   las propone [MAPEO] y exige confirmarlas con la skill `wisphub-api` antes de
   escribirlas. Eso es trabajo contra la API real, no contra el repo.
3. **`ejecutando` que queda huérfano** (el proceso muere entre los pasos 2 y 4)
   espera a T20 para pasar a `desconocida`. Hoy T20 no barre acciones: sólo
   sincronizaciones. El índice `acciones_propuestas_a_revisar_idx` ya está para
   eso, pero el barrido no está escrito.
4. Nada se vio renderizado, como toda la Fase 1.
