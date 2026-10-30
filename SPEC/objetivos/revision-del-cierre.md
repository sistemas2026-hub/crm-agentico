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

El Supervisor revisa e **indica**; **una persona confirma**. *Reabierta el 30/10 por el usuario («¿de qué manera hacemos para que el supervisor cierre solo?»): el Supervisor puede cerrar solo si se le **delega la tarea**, con el nivel 3 y el interruptor, y el ticket pasa por la puerta autónoma del motor. Ver la bitácora.*

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
| 30/10/2026 | **La auditoría de frontera lo encontró roto, y se arregló antes de desplegar.** Lo que se había dicho («con las 3 llaves abiertas cierra solo») era FALSO: la herramienta de cierre declara `aprobacion_humana` (M06-E, `tenants/rapilink.config.yaml:3762`) y la frontera rechaza todo permiso autónomo sobre ella; las pruebas no lo veían porque sustituían el ejecutor, donde vive ese control. Y peor: el rechazo quemaba el intento (`OPERACION_FALLIDA_PREVIA`). **Arreglado:** (H1) la quinta compuerta se pregunta antes de reclamar la clave, y una sección de la prueba usa el catálogo y el ejecutor REALES; (H2) la ruta humana rechaza actores del sistema (`techo.ACTORES_DEL_SISTEMA`) y el CRM no la pide sin persona; (H3) las dos puertas comparten la clave `orden_validada:<orden>|<herramienta>` — una sola publicación aunque cierren las dos, medido — y lo que no se sabe se dice `ESTADO_INCIERTO`; (H5) la casilla `supervisor_cierra_solo` (y su migración `0046`, nunca desplegada) se quitó: el cierre es una **tarea delegada** desde el chat (`aprobar_y_cerrar_lo_que_dio_por_bueno`) con el **nivel 3** y el **interruptor**, y una **fase del ciclo horario** después de la medición, como las otras tareas de acción; (H4) no cierra solo una orden ya devuelta, y si el ticket quedó cerrado y la orden cambió en el medio deja una alerta; (H6) una orden de falla cuya medición todavía no llegó es «Revisalo», y sin saber cuáles esperan no cierra ninguna. **Sigue abierto, y es decisión del usuario:** levantar `aprobacion_humana` exige medir antes si el ISP le avisa al cliente al cerrar (verificador-de-api) y cerrar `/interno/herramienta` y la cascada de cancelación sin `Idempotency-Key`, que esa marca hoy también protege | Mutaciones de los arreglos; regresión; deploy | este commit |
| 30/10/2026 | **Segunda auditoría de frontera.** Cerrados y medidos con sondas sobre el catálogo y el ejecutor reales: la doble publicación (5 escenarios, siempre 1 POST), el intento quemado (H1) y el interruptor (H5). Arreglados en esta ronda: (H6) «necesita medición» ya no depende de la ventana de 48 h de la medición, y la fase usa la hora real y no la del arranque del ciclo; si no se puede saber qué espera medición, la tarjeta dice «Revisalo»; (H4) la alerta de divergencia se ve en el log, en rojo; (H3) un timeout después de mandar es `ESTADO_INCIERTO` y la tarjeta no dice «no lo dejó» cuando no se sabe; (H2) el chequeo de actores agarra `supervisor_noc`, `Supervisor-NOC`, «Dexter», y deja pasar a «Supervisora Ana»; la prueba del orden de las fases ahora CORRE el ciclo. Mutaciones 7/7. **Queda abierto a propósito, y es condición para levantar `aprobacion_humana`** (hoy no puede pasar: la quinta compuerta frena antes de llegar al ISP): (1) un rechazo DEFINITIVO del ISP al Supervisor deja la clave compartida en `fallida` y traba la validación humana de esa orden — hay que permitir el reintento humano ante un 4xx (CLAUDE.md §12); (2) cada intento frenado por la quinta compuerta deja una fila «autorizada» sin desenlace en la bitácora de la frontera; (3) la ruta humana sigue creyéndole el `actor` a quien tenga el token (límite documentado de `puerta`); (4) otros caminos cierran el mismo ticket con otras claves (`operativo.cerrar_todo`, la cascada de cancelación); (5) el interruptor se lee una vez por fase; (6) `MOTOR_TENANT` único (D5) | Medir si el ISP avisa al cliente (verificador-de-api); decidir la marca; resolver (1)-(4) antes de levantarla | este commit |
