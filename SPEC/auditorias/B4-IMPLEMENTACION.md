# B4 — la cola de efectos externos

```
BASE       e2e26cf
VEREDICTO  implementado, sin commitear
ENTRADA    gate Q2 ROJO (auditorias/B4-Q2-WISPHUB.md) + las dos decisiones
           cerradas: panel propio y T20 con cadencia propia de 5 min
```

## El agujero que cierra

`escalar()` crea el caso en el CRM y, si falla, el `except` lo manda al log y
**la intención se pierde**. La conversación queda escalada, visible en la
bandeja, y sin caso — y nadie se entera hasta que alguien lo busca a mano.

Ahora la intención se encola **en la misma transacción** que la marca de
escalada (`marcar_escalada`, `db.py`), así que no existe un estado donde la
conversación quedó escalada y el efecto se perdió.

## Las dos velocidades, que gobiernan todo el diseño

```
crear_caso     incierto → vuelve a la cola. El nombre del caso lleva el
               conversation_id y es único por organización: se puede preguntar
               «¿ya existe?» y adoptarlo.
crear_ticket   incierto → 'desconocida', TERMINAL. La API de WispHub no permite
               preguntarlo (gate Q2). Espera a una persona.
```

Esa regla vive en un solo lugar —`reconciliador._desenlace()`— y es lo único
que decide si algo se reintenta. La constante que la expresa dice por qué:

```python
#: Lo que NO se reintenta cuando el resultado quedó incierto. La razón no es el
#: tipo de efecto sino la API: sin forma de preguntar si ya se hizo, reintentar
#: es apostar.
SIN_REINTENTO_SI_INCIERTO = frozenset({"crear_ticket", "cerrar_ticket"})
```

**Un `transitorio` de `crear_ticket` sí se reintenta**: transitorio significa
que no llegó a salir. Lo que no se reintenta es lo que *pudo* haber salido.

## Migración

`supabase/202609201000_sincronizaciones_externas.sql`, aplicada limpia sobre una
base construida desde cero (49 archivos en el ledger, todos `aplicada`).

Además de lo que §3.6 pide, dos checks que no estaban en el contrato y que salen
de cómo se consume la tabla:

```sql
sincronizaciones_pendiente_con_hora    un 'pendiente' sin proximo_intento_en
                                       sería invisible para T20: quedaría en la
                                       cola sin que nadie lo tome nunca
sincronizaciones_terminal_con_causa    'fallida_definitiva' y 'desconocida'
                                       exigen ultimo_error_clase, o el operador
                                       ve un pendiente de revisión sin motivo
```

Tres índices parciales: los elegibles (lo que T20 consulta cada 5 min), los de
una conversación (el panel) y los que esperan revisión. El primero no crece con
el histórico: lo terminado sale del índice solo.

## T20

`nucleo/relevo/reconciliador.py`. Cadencia propia de 5 minutos, **sin tocar el
reloj general** (~60 min): bajarlo movería todas las tareas periódicas del motor.
Un ciclo sin trabajo elegible es una consulta a un índice parcial y nada más.

El candado está en `tomar_sincronizacion`: el `and estado = 'pendiente'` del
UPDATE. Sin él, dos reconciliadores crearían dos casos para la misma
conversación. Probado con dos conexiones reales compitiendo.

`procesar_una` no conoce ni al CRM ni a WispHub: recibe un `ejecutar` inyectado.
Lo que decide es **qué hacer con el desenlace**, no cómo se produce — y así la
regla de Q2 se puede probar sin red.

**Una excepción del ejecutor se trata como `incierto`, no como fallo**: el
pedido pudo haber viajado antes de que se cortara.

## Sincronización externa (el panel)

Panel propio en la columna de contexto, arriba del todo. **No va en Activity**:
Activity es historia —qué pasó— y esto es estado actual —qué falta—. Un
pendiente de revisión enterrado entre movimientos del relevo se lee como algo
que ya ocurrió y se cerró.

**Sin botón de reintentar.** Lo que está `desconocida` no se reintenta porque
nadie puede saber si ya se hizo; un botón invitaría al gesto exacto que Q2
prohíbe, y dos visitas técnicas al mismo cliente no se deshacen.

Lo ya hecho no se lista: el panel dice qué **falta**. Si no falta nada, no hay
panel — y eso es información, no un hueco.

`datos_intencion` **no viaja a la pantalla**: lo que necesita es qué faltó y si
alguien tiene que mirarlo, no los parámetros con los que se iba a hacer.
Probado con un campo `secreto_interno` dentro de la intención.

## Tests

```
tests/test_b4_sincronizaciones.py   26 aserciones, contra PostgreSQL real
  la cola · idempotencia de la clave · elegibles y terminales
  el candado, con dos conexiones reales compitiendo
  los cinco desenlaces, con la regla de Q2 en los dos sentidos
  aislamiento entre empresas (4 aserciones)
  lo que NO sale a la pantalla

sincronizacion.test.js              13 aserciones
  desconocida ≠ falló: ni texto, ni tono, ni color
  qué espera a una persona · el panel dice qué falta
```

**Mutaciones:**

| Mutación | Resultado |
|---|---|
| `crear_ticket` incierto vuelve a la cola | 3 rojas |
| se quita el candado de `tomar_sincronizacion` | 2 rojas |

## G7 — queda como gate de despliegue

La implementación está completa en código: `CADENCIA_SEGUNDOS = 300` y el
reconciliador listo para ser llamado. **La activación real de esa cadencia en
producción no se tocó.** El reloj general sigue en ~60 min y ese cambio es
acuerdo con producción, no de desarrollo.

## Riesgos abiertos

1. **T20 no está enganchado a ningún reloj todavía.** `correr()` existe y está
   probado, pero nada lo llama periódicamente. Es deliberado —G7— pero conviene
   decirlo: hoy la cola se llena y no se vacía sola.
2. **El ejecutor real no está escrito.** `procesar_una` recibe `ejecutar`
   inyectado y los tests usan uno de prueba. Conectarlo al CRM es trabajo
   pequeño y con idempotencia demostrada; conectarlo a WispHub **no se hace**
   mientras Q2 siga rojo.
3. **Sólo `crear_caso` se encola hoy**, desde `marcar_escalada`. Los otros tres
   tipos existen en el esquema y en el panel, sin productor. Encolar
   `crear_ticket` exige decidir antes qué pasa cuando queda `desconocida` en el
   flujo real, que es una decisión de operación.
4. Nada se vio renderizado, como toda la Fase 1.
