# Objetivo · El Supervisor revisa el cierre del técnico y una persona lo confirma

> Abierto el 30/10/2026. Estado: **abierto**.

## Qué significa terminado

Cuando el técnico manda el cierre de una orden, el Supervisor la revisa sin que nadie se lo pida y dice en Programación **«se puede cerrar»** o **«no se cierra»**, con el porqué. Una persona lo confirma con un toque:

- **Aprobar y cerrar:** valida la orden, cierra el ticket del ISP y la saca de la bandeja.
- **Devolver al técnico:** con los motivos ya escritos. Al técnico le llega el push que ya existe.

## De dónde sale

El usuario, 30/10/2026: «ya al momento que el técnico envía el reporte final el supervisor debe revisar si quedó bien y indicar si lo cierra o no y por qué».

Lo que se midió antes de empezar:

- **Aprobar y devolver ya existían en el servidor, pero ninguna pantalla los llamaba.** Son `ValidarTrabajoView` y `CerrarTrabajoView`. Ese mismo día la OT #3 quedó «Terminó» y no tenía cómo avanzar.
- **Aprobar cierra el ticket del ISP.** Lo hace `cierre_en_isp.cerrar_ticket_al_validar`, que entra al motor **por la puerta humana**.

## Decisiones (30/10/2026; las recomendadas, por la regla del usuario «escoge la más recomendable»)

**1 · Quién decide**

El Supervisor revisa e **indica**; **una persona confirma**.

Que el Supervisor apruebe solo haría que una IA cierre tickets del ISP por la puerta humana del motor, y eso CLAUDE.md §4 lo prohíbe: «crecer en alcance, no en autonomía». Automatizarlo exige pasar por la frontera, con el interruptor y el techo, y una medición de cuánto acierta la revisión.

**2 · Cómo revisa**

En código, sin modelo (CLAUDE.md §4, «el modelo compone, el código calcula»). Cada punto se responde con sí, no o no se sabe:

- el checklist completo;
- que exista el reporte de cierre de esta vuelta;
- si el técnico afirmó que el servicio quedó funcionando;
- la medición después del arreglo, en las fallas de servicio;
- el material: si registró consumo o si confirmó que no usó.

**3 · El veredicto**

- **No se cierra:** algún punto dice «no».
- **Revisar:** algún punto dice «no se sabe».
- **Se puede cerrar:** todo dice «sí».

Los motivos son los textos de los puntos.

**4 · Cuándo**

Se calcula al leer, no se guarda. Mismo criterio que `salud_seguimiento`: un veredicto guardado miente cuando llega la medición una hora después.

**5 · Devolver**

Usa `requerir_correccion`, que exige nombrar qué evidencia se rehace. La pantalla sugiere las que el checklist marca y deja elegir; la observación lleva los motivos del Supervisor.

## Criterios de aceptación

```
pytest campo/tests/test_revision_del_cierre.py       → verde contra Postgres
mutaciones: el «no» no bloquea, el «no se sabe» se da por bueno, aprobar
  sin persona, otra empresa                          → todas mueren
pytest campo operaciones business_hours              → los 94 de la base, ninguno nuevo
vitest + svelte-check (152 = base) + vite build
```

## Restricciones

- No push sin «haz el push». No tocar `nucleo/` ni `tenant_config`.
- El Supervisor no aprueba, no cierra y no devuelve solo: solo indica.

## Bitácora

| Fecha | Qué | Evidencia | Hash |
|---|---|---|---|
| 30/10/2026 | **Construida.** `campo/revision_del_cierre.py`: cinco puntos en código (checklist, reporte de esta vuelta, servicio afirmado, medición después del arreglo, material) y el veredicto; Programación lo trae en cada orden terminada sin validar (`dia_publicado`, con la vuelta para la clave). En la tarjeta (`RevisionDelCierre.svelte`): el veredicto, qué hizo el técnico, cada punto, «Aprobar y cerrar» (validar y después cerrar, `Idempotency-Key` con orden y vuelta) y «Devolver al técnico» con las fotos sugeridas marcadas y el porqué ya escrito. Medido: 8 pruebas contra Postgres; mutaciones del servidor 6/7 muertas — sobrevive la que quita el filtro `org=` de la medición, porque RLS ya esconde la fila ajena y la prueba no puede ver el filtro solo (queda como segunda defensa para los roles que saltan RLS, CLAUDE.md §5); web: 31 pruebas, mutaciones 6/6; `svelte-check` 152 = base; `vite build` OK. Una prueba de otra empresa fallaba por RLS al crearse y eso dejaba en «muere» a todas las mutaciones: se arregló y se volvieron a correr | Regresión completa; deploy; aprobar y devolver una orden real | este commit |
| 30/10/2026 | **El Supervisor cierra solo, detrás de las compuertas.** El usuario: «¿de qué manera hacemos para que el supervisor cierre solo?». Se reabre la decisión 1, por él, sin saltar la frontera. **Motor:** `cierre_por_validacion.cerrar_ticket_por_el_supervisor` y la ruta `/interno/orden/<id>/cerrar-ticket-supervisor`, por `frontera.autonoma()` (interruptor, techo, Autonomía 2 con B-7, autorización de la herramienta), con clave propia y sin `actor` del que llama. **Servidor:** `campo/cierre_por_el_supervisor.py`, cada 10 min y solo si la empresa lo encendió (`ConfiguracionDeSeguimiento.supervisor_cierra_solo`, migración `0046`, apagado por omisión, editable en Programación): lo que la revisión marca «Se puede cerrar» → primero el ticket afuera, y solo si quedó cerrado, aprobar y cerrar adentro; si el motor se niega, queda para una persona y la tarjeta dice qué compuerta (un intento por hora). **En producción hoy no cierra nada:** `AUTONOMIA_2_ACTIVA` apagada, B-7 abierto (el GUC del secreto JWT) y 0 autorizaciones; con el interruptor encendido, cada intento queda anotado como «lo quiso cerrar y no pudo»: es la medición de lo que haría. Medido: motor 8 secciones (puerta autónoma, cada compuerta frena y dice cuál, la humana no se abre); servidor 9 pruebas contra Postgres; web 26; mutaciones 14/14 (la de la casilla sobrevivió hasta agregar el caso desmarcado); `svelte-check` 152 = base; `vite build` OK; `test_nucleo_sin_tenants` OK. **No probado en vivo:** el cierre de un ticket real (dexter-local corre con `SIN_EFECTOS_EXTERNOS=1` a propósito) | Abrir las 3 compuertas en producción; encender el interruptor; cerrar un ticket de Mario Sabanagrande | este commit |
