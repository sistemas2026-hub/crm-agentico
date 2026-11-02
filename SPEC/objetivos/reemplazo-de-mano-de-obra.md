# Objetivo · Que el trabajo no crítico deje de esperar a una persona

> Abierto el 02/11/2026. Estado: **abierto**.
> El **qué** y el **por qué** viven en [PRD.md §1, §2 y §8.18](../../PRD.md): reemplazar la mano de obra humana lo más posible; una persona solo en lo crítico. Si difieren, manda el PRD.
> El dueño del producto delegó las decisiones de este objetivo (02/11/2026): «de aquí adelante te lo dejo a tu decisión».

## Qué significa terminado

Ninguna acción **no crítica** (PRD §2: lo que no mueve dinero, no deja sin servicio de forma que no vuelve sola, no afecta a muchos clientes, no borra ni expone datos y no compromete con terceros) espera a una persona. Lo que antes revisaba esa persona lo revisa el código antes del efecto, y queda comprobado después cuando hay cómo.

## Lo medido que define el orden (02/11/2026, leyendo el código)

```
Herramientas de Rapilink que piden aprobación humana: 15.
  Críticas de verdad (6): registrar_pago, agregar_promesa_pago,
    registrar_promesa_y_reactivar, cambiar_tipo_onu, activar_catv,
    cancelar_solicitud_servicio.                       -> se quedan como están
  No críticas que una PERSONA APRUEBA una por una (4):
    reiniciar_ont      ya tiene en código: síntoma declarado, señal aceptable,
                       ping, sin caída de zona, 1 por conversación, turno propio.
                       Hoy el bot le dice al cliente "un colaborador lo tiene
                       que aprobar".
    crear_ticket, responder_ticket, actualizar_estado_ticket
  No críticas que DISPARA una persona o un servicio (5): no esperan aprobación;
    la marca solo impide que el modelo las llame en conversación. No ahorran
    trabajo al quitarla.                                -> se quedan como están

El reconciliador T20 (cierra en WispHub el ticket de una conversación cerrada)
  NO está en docker-compose.prod.yml, y ninguna de sus escrituras abre permiso
  en la frontera: encendido, también quedaría frenado. Gate G7, sin cerrar.

Sin medir: cuántas propuestas por herramienta aprueban las personas en
  producción, y en qué estado está el interruptor de autonomía. El clasificador
  del modo automático bloquea las lecturas de producción desde esta sesión.
```

## Fases

| Fase | Qué | Estado |
|---|---|---|
| **0** | **Abrir las tres llaves que hoy frenan TODO lo que el sistema hace solo**, y también lo irreversible que aprueba una persona (`frontera.critica` exige la etapa): (a) `AUTONOMIA_2_ACTIVA` llega al motor — no estaba en `docker-compose.prod.yml`, y lo que no se lista no llega; (b) B-7 — aplicar `supabase/operador/cerrar_b7_secreto_jwt.sql` como superusuario y reiniciar pooler y CRM; la rotación del secreto se difiere y va junto con la de las contraseñas filtradas (decidido el 02/11/2026, DESPLIEGUE.md §3); (c) interruptor reactivado, techo y autorización de cada herramienta (`cli/autonomia.py`, `cli/autorizar_herramienta.py`). Sin esto las fases 1-4 no tienen efecto en producción | Código listo (02/11/2026): compose (motor **y** reloj) y el SQL de operador, probado en Postgres de descarte en los cuatro lugares donde puede estar (base, rol, rol en base, todos los roles): queda en 0 y una sesión nueva no lo ve; un rol sin permiso falla sin cambiar nada. **HECHO EN PRODUCCIÓN el 02/11/2026** (medido por el usuario en Dokploy): `veredicto_b7()` → `b7_ok` tras borrar el GUC (0 funciones lo leían); autorizados a las 12:53 Bogotá `registrar_pedido_wifi`, `crear_ticket_caso`, `reportar_comprobante_pago`, `reiniciar_ont` (nivel 2) y `cerrar_ticket_operativo` (nivel 3); techo 3; `AUTONOMIA_2_ACTIVA=1` → `veredicto()` `permitido=True`. Frenadas reales que lo motivaron, en 45 días: pedidos de WiFi 63, cierre del Supervisor 15, tickets de caso 11, comprobantes 6. **Sin autorizar todavía**: el resto de las escrituras externas (sin intentos registrados en 45 días) y las críticas de dinero. **Pendiente de seguridad**: rotar `JWT_SECRET` junto con las contraseñas de la base que quedaron en transcripciones |
| 1 | `reiniciar_ont` sale sola. **Decidido distinto de lo primero que se pensó**: quitarle `irreversible`/`aprobacion_humana` rompía el botón de la Bandeja (la ruta de aprobación las exige) y la sacaba de la cadena que ya revalida previas, confirma el efecto, tiene topes y se degrada sola. Se hizo lo mínimo: un campo nuevo `Herramienta.critica` (True por omisión) y, si la empresa lo declara `false`, la autonomía ganada la promueve **sin evidencia previa** — las garantías en código (efecto verificable, previas) se siguen exigiendo. Rapilink declara `reiniciar_ont: critica: false`, y el texto ya no le hace decir al cliente "un colaborador lo tiene que aprobar" | En código (02/11/2026): `tests/test_autonomia_ganada.py` verde, 2 mutaciones caídas (sin la regla; lo no crítico saltándose las garantías). **En producción falta**: la fase 0, cargar `herramientas[reiniciar_ont]` (`critica`, `descripcion`, `sugerir_cuando_disponible`) con `cli/cargar_claves.py`, y un clic de ADMIN en `/capacidad` → «Darle autonomía» |
| 2 | Los tres de tickets en conversación (`crear_ticket`, `responder_ticket`, `actualizar_estado_ticket`) salen solos, con su validación en código | Pendiente |
| 3 | Las tareas no críticas del Supervisor nacen encendidas en una empresa nueva (la persona puede apagarlas); y la cabecera «SHADOW MODE: no ejecuta» de `operaciones/supervisor.py` dice lo que el Supervisor hace hoy | Pendiente |
| 3b | **Un solo lugar para "qué hace solo cada agente"** (pedido del usuario, 02/11/2026: «eso no debería ir en cada agente... con un agente sí pueda reiniciar y otro no»). La autonomía se decide **por agente** y se controla **en `/agentes`**, junto a las herramientas de cada uno; el Supervisor muestra ahí sus tareas delegables; `/capacidad` queda solo para medir. El dato NO pasa a `tenant_config` (falla abierto): sigue en `asistente.autonomia_ganada`, con el agente como clave (nulo = todos). El último metro compara la promoción por su id y su agente | **En código (02/11/2026), sin desplegar.** Motor: migración `202611021200_autonomia_por_agente.sql` (columna `rol`; la propia manda; degradar baja todo; las funciones de antes siguen para lo general, así el orden migración/push no rompe), `vigente`/`promover`/`retirar` con agente, el último metro con el `rol_solicitante` de la propuesta, y `agentes_que_la_usan` desde `puede_consultar` (NO `roles_permitidos`, que nada consulta). Pantalla: `AutonomiaDeAccion.svelte` en cada acción de cada agente en `/agentes`; `/capacidad` solo mide; la tarjeta del Supervisor NOC dice lo que hace solo, en vivo, y su descripción ya no dice «no ejecuta». **Verificado**: `tests/test_autonomia_ganada.py` (8 mutaciones caídas), `tests/test_autonomia_por_agente_base.py` contra Postgres real (13 comprobaciones; la mutación sin precedencia cae), `test_autonomia_ganada_ejecucion.py`; vitest de agentes (servidor y componente renderizado) y capacidad. **En producción falta**: push, y aplicar la migración por el ledger (`scratchpad/ledger_dbuser.py --aplicar` desde la PC del usuario). Lo promovido hoy para todos sigue valiendo: queda como fila general. **Auditoría de frontera del mismo día** (ningún camino sin la promoción del agente que pidió la acción; 1 alto, 4 medios, 5 bajos): (A1) volver a código anterior con filas por agente haría valer una promoción de un agente para todos — ningún diseño de tabla lo evita; **regla escrita en la migración y en DESPLIEGUE §3: detener el interruptor antes de volver**; (M1) retirar ya no se rechaza por pertenencia; (M2) retirar sin agente baja todos los alcances (`autonomia_ganada_retirar_todo`) y la tarjeta dice cuándo el estado viene de la autorización general; (M3) `rol_solicitante` inmutable por un trigger aparte; (M4) la evidencia de una promoción por agente cuenta SUS propuestas (las verificaciones siguen siendo de toda la herramienta); (B1) degradar toma los mismos candados que promover; (B4) sin propuesta, no sale sola; (B5) rechazos en palabras con 409. **Abierto**: (B2) el orden es migración antes del push; (B3) la guarda de precedencia necesita Postgres y no corre en CI (D1); los candados de B1 no tienen prueba de concurrencia real |
| 4 | El reconciliador corre en producción y sus escrituras pasan por la frontera con su permiso | Pendiente |
| 5 | El Supervisor mira lo que no tiene programado: una revisión abierta diaria que propone lo raro | Pendiente |

## Restricciones

- **NO push** desde la sesión: es deploy, y el clasificador lo bloquea; el comando se le pasa al usuario.
- Quitar la aprobación **nunca** quita la validación en código: frontera, interruptor, techo, idempotencia, auditoría.
- Cada fase que toca una herramienta con efecto pasa por el procedimiento de `auditor-de-frontera`, y la que toca catálogo o prompt, por `cli/evaluar.py`.
- La config de producción se carga con `cli/cargar_claves.py`, solo las claves nombradas y DESPUÉS del push.
