# Objetivo · La autonomía se gana con evidencia

> Abierto el 31/10/2026. Estado: **abierto**.
> El **qué** y el **por qué** viven en [PRD.md §2](../../PRD.md) (principio de las cuatro condiciones) y §8.17 (Ola 3). Si difieren, manda el PRD.

## Qué significa terminado

Una acción que hoy aprueba una persona puede pasar a hacerse sola **en una empresa**, solo si cumple las cuatro condiciones. Una persona la promueve viendo la evidencia, y el código la vuelve a «una persona aprueba» sin intervención en cuanto la evidencia se cae.

## Fases

| Fase | Qué | Estado |
|---|---|---|
| A | El código calcula por empresa y acción si es candidata (1 y 2, por su config) y si es elegible (3, con su evidencia), con piso del núcleo. Se muestra en `/capacidad`. **No cambia nada de lo que se ejecuta** | En código (31/10/2026) |
| B | Promover: una persona con rol de administración, viendo la evidencia, la activa; queda escrito quién y cuándo. Vive fuera de `tenant_config`, como el interruptor (falla CERRADO: sin base, nadie es autónomo) | En código (31/10/2026) |
| C | Ejecutar: el motor, en vez de dejar la propuesta pendiente, la ejecuta por `frontera.critica()` con la autonomía como actor, después de sus previas en código. El interruptor y el techo siguen por encima | En código (31/10/2026) |
| D | Degradar sola (condición 4): una verificación no confirmada o una ejecución fallida la devuelve a «una persona aprueba» y lo registra | En código (31/10/2026); falta el recontacto por acción |

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
| 31/10/2026 | **Auditoría de frontera de A-D resuelta.** Sin caminos para ejecutar sin promoción vigente. Altos: la evidencia contaba Bandeja, simulador y la propia autonomía; la degradación dependía de que el cliente volviera a escribir. Medios: bloqueos de la frontera quedaban como fallidas; sin chequeo de canal, control ni escalamiento; promover sin ADMIN del lado del motor; el cliente sin aviso; sin tope en la base. Todo resuelto salvo lo anotado en el PRD (recontacto, reloj de verificaciones, aviso al cliente si vuelve a la cola) | Recontacto por acción | (este commit) |
| 31/10/2026 | **Fases C y D en código.** Misma cadena que una aprobación humana, firmada por la promoción; degradación sola | Auditoría | 852928ff |
| 31/10/2026 | **Fase B en código.** Tabla de solo agregar `asistente.autonomia_ganada` (migración `202610310200`): promover y retirar los escribe `autonomia_operador`; el runtime solo lee y degrada por una función cuyo estado está fijo en el cuerpo, y solo la empresa de su sesión. `vigente()` sin caché y falla cerrado, también ante `SystemExit` (D11). Promover vuelve a medir la evidencia en ese momento. Rutas `/autonomia-ganada/promover` y `/retirar` con el autor de la sesión; botones en `/capacidad` con confirmación obligatoria. Contra Postgres real: permisos de verdad (el runtime no inserta ni edita, no degrada otra empresa) | C, D, auditoría | 0e3d38c9 |
| 31/10/2026 | **Fase A en código.** `nucleo/seguridad/autonomia_ganada.py` (candidata, umbrales con piso, veredicto), `nucleo/persistencia/autonomia_ganada.py` (conteos), `GET /reportes/autonomia-ganada`, sección en `/capacidad`. 9 mutaciones cazadas (una sobrevivía: se agregó el caso que la aísla) | B, C, D | 8d37b33a |
