# Gate Q2 — ¿se puede reintentar `crear_ticket` en WispHub?

```
BASE       01a4471
VEREDICTO  Q2 ROJO — crear_ticket NO es reintentable automáticamente
ALCANCE    auditoría. Sin código, sin migración, sin tocar producción.
FECHA      20/09/2026
```

El contrato (§3.6) condiciona el reintento de `crear_ticket` a demostrar **una
de tres cosas, en orden**. Las tres se examinaron. Ninguna se sostiene.

## Vía 1 — ¿acepta una clave de idempotencia o referencia externa?

**NO.** Verificado contra la especificación oficial, descargada hoy de
`wisphub.net/static/yaml/api/Tickets/paths/list_tickets.yaml`.

`POST /api/tickets/` declara **14 campos**:

```
requeridos  servicio · asunto · asuntos_default · tecnico · descripcion
            estado · prioridad · departamento · departamentos_default
opcionales  archivo_ticket · email_tecnico · fecha_inicio · fecha_final
            origen_reporte
```

**Ninguno es una clave de idempotencia ni una referencia externa.** No hay
`referencia`, `external_id`, `idempotency_key`, `uuid` ni equivalente.

## Vía 2 — ¿se puede buscar un ticket por esa referencia?

**Imposible por construcción**: sin referencia no hay nada que buscar.

Y aunque la hubiera, `GET /api/tickets/` documenta **cinco** parámetros y ninguno
sirve para localizar un ticket concreto:

```
estado · fecha_creacion · mis_tickets · limit · offset
```

## Vía 3 — ¿se puede localizar por el `conversation_id` embebido en el asunto?

**No, y por cuatro razones independientes.** Basta una para descartarla; hay
cuatro.

**(a) El asunto no es texto libre.** Sale de un catálogo cerrado de ~140 valores
(`Internet Lento`, `No Tiene Internet`, `Antena Desalineada`…), y el campo
`asuntos_default` es requerido con la condición «es necesario que sea igual al
**asunto**». La skill ya lo había documentado por otra vía:
`/api/tickets/asuntos-tickets/` trae ese catálogo, y `"Instalacion Nueva"` e
`"Instatalacion Nueva"` (con el typo) conviven como **valores distintos del
catálogo**, lo que confirma que es una lista y no una cadena libre.
*Documental: falta confirmar en vivo que la API rechace un asunto ajeno al
catálogo.*

**(b) WispHub reescribe el asunto.** [VERIFICADO, skill] Se guarda como
`"Asunto - Cliente"`. Lo que se manda no es lo que queda.

**(c) No hay con qué buscarlo.** No existe filtro de texto documentado, y el
filtro por cliente en tickets está **medido como ignorado** — 8 nombres
probados. [VERIFICADO, skill]

**(d) Y aunque existiera el filtro, el histórico no está.** [VERIFICADO, skill]

```
tickets sin filtro de fecha   2.635
tickets sólo de julio         2.637   ← un subconjunto mayor que el conjunto
tickets sólo de junio         3.341
```

Sin rango de fecha la API aplica un recorte propio, y el rango tiene **tope de 2
meses**. El reconciliador reintenta con espera creciente: un ticket creado antes
de esa ventana no se podría encontrar ni paginando.

## Lo que NO se pudo hacer, y por qué no cambia el veredicto

**No se ejecutó ninguna llamada contra la API real.** La credencial sale de
`secretos.obtener(tenant, auth_ref)` — vive en el `.env` (que no se lee) o en
`asistente.tenant_config` de producción (a la que no se conecta). No hay vía
legítima de obtenerla desde acá.

Lo que faltaría probar en vivo es si existe un `asunto__contains` no
documentado, por el precedente de `telefono__contains` en clientes, que la
skill sí verificó.

**Pero ese hallazgo no cambiaría el resultado.** Aunque `asunto__contains`
funcionara, siguen en pie (a) el catálogo cerrado, (b) la reescritura del asunto
y (d) el recorte del histórico. La vía 3 necesita las cuatro condiciones a la
vez; sobra con que falle una.

Por eso **Q2 se puede cerrar en ROJO sin tocar producción**. Si en algún momento
hay un entorno de pruebas de WispHub, vale confirmar (a) y probar (c) — no para
reabrir el veredicto, sino para cerrarlo con medición en vez de con documentación.

## Q2: ROJO

Consecuencia, que el contrato ya deja escrita y ahora queda activada:

> «Sin ninguna: un fallo con resultado incierto queda `desconocida` y **no se
> crea otro**. Es preferible un ticket pendiente de revisión a dos visitas
> técnicas duplicadas.»

Para B4 eso significa, concretamente:

```
crear_ticket fallo TRANSITORIO ANTES de enviar    se puede reintentar
crear_ticket fallo con resultado INCIERTO         → 'desconocida', NO se reintenta
                                                     visible en la conversación,
                                                     para revisión humana
crear_caso   (CRM)                                 SÍ reintentable: el nombre del
                                                   caso incluye el conversation_id
                                                   y es único por organización;
                                                   un repetido da 400 y se adopta
                                                   el existente [VERIFICADO, §3.6]
```

Es decir: **el reconciliador de B4 nace con dos velocidades**. El caso del CRM se
reconcilia solo; el ticket de WispHub no, y su cola necesita un estado terminal
que espere a una persona.

## Lo que esto le exige a B4 cuando se autorice

1. `sincronizaciones_externas` necesita `desconocida` como estado de primera
   clase, no como variante de `fallida_definitiva`. Ya está en el esquema de
   §3.6; queda confirmado que **se va a usar de verdad**, no como caso teórico.
2. Hace falta una **superficie en la conversación** para esos pendientes: el
   contrato dice «visible en la conversación, nunca silenciosa», y hoy no hay
   dónde mostrarlo. La Bandeja ya tiene el patrón — `NetworkPanel` muestra
   veredictos de acciones sin ejecutarlas.
3. El reintento automático de `crear_ticket` **no se implementa**. Escribirlo
   «por si acaso» es exactamente lo que produce dos visitas al mismo cliente.
