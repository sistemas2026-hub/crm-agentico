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
tests/test_b4_sincronizaciones.py   40 aserciones, contra PostgreSQL real
  la cola · idempotencia de la clave · elegibles y terminales
  el candado, con dos conexiones reales compitiendo
  los cinco desenlaces, con la regla de Q2 en los dos sentidos
  aislamiento entre empresas (4 aserciones)
  lo que NO sale a la pantalla
  el ejecutor real: adopta en vez de duplicar, no crea a ciegas, resuelve la
    carrera del 400, y un tipo sin ejecutor no queda como 'desconocida'
  el worker: cadencia de 5 min, apagado por defecto, interruptor propio

sincronizacion.test.js              13 aserciones
  desconocida ≠ falló: ni texto, ni tono, ni color
  qué espera a una persona · el panel dice qué falta
```

**Mutaciones:**

| Mutación | Resultado |
|---|---|
| `crear_ticket` incierto vuelve a la cola | 3 rojas |
| se quita el candado de `tomar_sincronizacion` | 2 rojas |

**Una regresión encontrada por una guarda existente:** el worker armaba el
evento del log con una f-string (`f"RECONCILIADOR_HABILITADO={...}"`) y
`test_registro_sin_pii` lo rechazó — el evento tiene que ser texto fijo o no se
puede buscar en el log. Corregido con el mismo patrón que usa el reloj general.

## G7 — sólo queda activar

El mecanismo existe entero: worker ejecutable, cadencia de 300 s, ejecutor real
de `crear_caso` y la cola con su candado. Lo que falta es **encenderlo**:
`RECONCILIADOR_HABILITADO=1` y el servicio desplegado. Eso es acuerdo con
producción, no desarrollo.

El reloj general sigue en ~60 min y **no se tocó**.

## Riesgos abiertos

1. **`crear_ticket` no tiene ejecutor, y no lo va a tener mientras Q2 siga
   rojo.** Un trabajo de ese tipo que llegue a la cola hoy termina en
   `fallida_definitiva` con código `sin_ejecutor:crear_ticket` — visible, no
   silencioso. Es el comportamiento correcto, pero conviene saberlo.
2. **Sólo `crear_caso` se encola**, desde `marcar_escalada`. Los otros tres
   tipos existen en esquema y panel sin productor: encolar `crear_ticket` exige
   decidir antes qué pasa cuando queda `desconocida` en el flujo real.
3. **La búsqueda del caso depende de una herramienta con `busca_caso` en el
   catálogo del tenant, que hoy ningún tenant declara.** Sin ella,
   `buscar_por_nombre` devuelve `None` y todo reintento intentaría crear. No es
   inseguro —el CRM rechaza el nombre repetido con 400 y esa carrera se maneja—
   pero conviene declararla antes de encender el worker.
4. Nada se vio renderizado, como toda la Fase 1.
