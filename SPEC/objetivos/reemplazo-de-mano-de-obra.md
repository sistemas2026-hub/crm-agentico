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
| **0** | **Abrir las tres llaves que hoy frenan TODO lo que el sistema hace solo**, y también lo irreversible que aprueba una persona (`frontera.critica` exige la etapa): (a) `AUTONOMIA_2_ACTIVA` llega al motor — no estaba en `docker-compose.prod.yml`, y lo que no se lista no llega; (b) B-7 cerrado — migración `202611021000_cerrar_b7_secreto_jwt.sql`; (c) interruptor reactivado, techo y autorización de cada herramienta (`cli/autonomia.py`, `cli/autorizar_herramienta.py`). Sin esto las fases 1-4 no tienen efecto en producción | Código listo (02/11/2026): compose y migración, probada en Postgres de descarte (superusuario borra y una sesión nueva no lo ve; un rol sin permiso falla sin cambiar nada). **Lo de producción lo corre el usuario** |
| 1 | `reiniciar_ont` sale sola. **Decidido distinto de lo primero que se pensó**: quitarle `irreversible`/`aprobacion_humana` rompía el botón de la Bandeja (la ruta de aprobación las exige) y la sacaba de la cadena que ya revalida previas, confirma el efecto, tiene topes y se degrada sola. Se hizo lo mínimo: un campo nuevo `Herramienta.critica` (True por omisión) y, si la empresa lo declara `false`, la autonomía ganada la promueve **sin evidencia previa** — las garantías en código (efecto verificable, previas) se siguen exigiendo. Rapilink declara `reiniciar_ont: critica: false`, y el texto ya no le hace decir al cliente "un colaborador lo tiene que aprobar" | En código (02/11/2026): `tests/test_autonomia_ganada.py` verde, 2 mutaciones caídas (sin la regla; lo no crítico saltándose las garantías). **En producción falta**: la fase 0, cargar `herramientas[reiniciar_ont]` (`critica`, `descripcion`, `sugerir_cuando_disponible`) con `cli/cargar_claves.py`, y un clic de ADMIN en `/capacidad` → «Darle autonomía» |
| 2 | Los tres de tickets en conversación (`crear_ticket`, `responder_ticket`, `actualizar_estado_ticket`) salen solos, con su validación en código | Pendiente |
| 3 | Las tareas no críticas del Supervisor nacen encendidas en una empresa nueva (la persona puede apagarlas); y la cabecera «SHADOW MODE: no ejecuta» de `operaciones/supervisor.py` dice lo que el Supervisor hace hoy | Pendiente |
| 4 | El reconciliador corre en producción y sus escrituras pasan por la frontera con su permiso | Pendiente |
| 5 | El Supervisor mira lo que no tiene programado: una revisión abierta diaria que propone lo raro | Pendiente |

## Restricciones

- **NO push** desde la sesión: es deploy, y el clasificador lo bloquea; el comando se le pasa al usuario.
- Quitar la aprobación **nunca** quita la validación en código: frontera, interruptor, techo, idempotencia, auditoría.
- Cada fase que toca una herramienta con efecto pasa por el procedimiento de `auditor-de-frontera`, y la que toca catálogo o prompt, por `cli/evaluar.py`.
- La config de producción se carga con `cli/cargar_claves.py`, solo las claves nombradas y DESPUÉS del push.
