# Objetivo · La autonomía se gana con evidencia

> Abierto el 31/10/2026. Estado: **abierto**.
> El **qué** y el **por qué** viven en [PRD.md §2](../../PRD.md) (principio de las cuatro condiciones) y §8.17 (Ola 3). Si difieren, manda el PRD.

## Qué significa terminado

Una acción que hoy aprueba una persona puede pasar a hacerse sola **en una empresa**, solo si cumple las cuatro condiciones. Una persona la promueve viendo la evidencia, y el código la vuelve a «una persona aprueba» sin intervención en cuanto la evidencia se cae.

## Fases

| Fase | Qué | Estado |
|---|---|---|
| A | El código calcula por empresa y acción si es candidata (1 y 2, por su config) y si es elegible (3, con su evidencia), con piso del núcleo. Se muestra en `/capacidad`. **No cambia nada de lo que se ejecuta** | En código (31/10/2026) |
| B | Promover: una persona con rol de administración, viendo la evidencia, la activa; queda escrito quién y cuándo. Vive fuera de `tenant_config`, como el interruptor (falla CERRADO: sin base, nadie es autónomo) | Pendiente |
| C | Ejecutar: el motor, en vez de dejar la propuesta pendiente, la ejecuta por `frontera.critica()` con la autonomía como actor, después de sus previas en código. El interruptor y el techo siguen por encima | Pendiente |
| D | Degradar sola (condición 4): una verificación no confirmada o una ejecución fallida la devuelve a «una persona aprueba» y lo registra | Pendiente |

## Lo medido que define el diseño (31/10/2026)

```
Con la config de Rapilink, de las 15 acciones que piden aprobación humana:
  candidata:        reiniciar_ont (mide last_status_change, exige previas)
  no candidatas:    registrar_pago, cancelar, tickets, promesas, CATV, cambio de tipo:
                    13 sin efecto verificable en código ni previas; 2 sin efecto verificable.
Revisada = una persona decidió (aprobada, ejecutada ok/fallo/incierta, rechazada).
Vencida y cancelada NO cuentan: nadie la miró.
```

## Criterios de aceptación

| # | Evidencia | Cómo se comprueba |
|---|---|---|
| A1 | Candidata por propiedades, no por nombre; piso que ninguna empresa baja; elegible exige las tres a la vez | `py -3.13 tests/test_autonomia_ganada.py` |
| A2 | La evidencia se cuenta exacta contra Postgres real | `py -3.13 tests/test_autonomia_ganada_base.py` (con DBHOST… de la base efímera) |
| A3 | La pantalla recibe la respuesta entera con los mismos nombres, y el tablero sobrevive si falla | vitest `capacidad-servidor.test.js` |

## Restricciones

- **NO push** — es deploy. **NO** escribir `tenant_config` fuera de la base efímera.
- Fases B a D tocan la frontera: `auditor-de-frontera` antes de commitear cada una.

## Bitácora

| Fecha | Qué avanzó | Qué falta | Commit |
|---|---|---|---|
| 31/10/2026 | **Fase A en código.** `nucleo/seguridad/autonomia_ganada.py` (candidata, umbrales con piso, veredicto), `nucleo/persistencia/autonomia_ganada.py` (conteos), `GET /reportes/autonomia-ganada`, sección en `/capacidad`. 9 mutaciones cazadas (una sobrevivía: se agregó el caso que la aísla) | B, C, D | (este commit) |
