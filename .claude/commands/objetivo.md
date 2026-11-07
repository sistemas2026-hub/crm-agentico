---
description: Encuadra un objetivo grande, escribe su ficha versionada y emite la condición /goal lista para pegar
argument-hint: <qué se quiere lograr, en una frase>
---

# Encuadrar un objetivo

El usuario quiere lograr esto: **$ARGUMENTS**

**No empieces a construir.** Tu trabajo en este comando es encuadrar: dejar escrito qué significa "terminado", y entregar la condición que después va a empujar el trabajo. Nada de código en este turno.

## Paso 1 · Entender el terreno

Leé, del disco, lo que corresponda:

- `CLAUDE.md` §11.2 (qué es un cambio relevante) y §6 (qué guardas exige)
- `SPEC/DEXTER_ESTADO_ACTUAL.md` — dónde estamos hoy; gana sobre cualquier recuerdo
- `SPEC/objetivos/` — si ya hay una ficha abierta para esto, **no crees una segunda**: retomá esa

Después invocá al agente `orquestador` con el pedido. Te devuelve qué agentes participan, cuáles se saltean y por qué, y —lo más importante— **los bloqueos antes de empezar**: una decisión pendiente, una credencial que falta, una aprobación de un tercero. Si hay un bloqueo de ese tipo, decilo antes que nada: puede que el objetivo no se pueda ni arrancar.

## Paso 2 · Preguntar solo lo que no podés deducir

Si algo es ambiguo y cambia materialmente el trabajo, preguntá **ahora**, no a mitad de camino. Lo típico que falta:

- ¿Qué evidencia concreta lo da por cerrado?
- ¿Hay una fecha, una demo, o algo que dependa de esto?
- ¿Qué queda explícitamente fuera?

Lo que se pueda deducir del repo, deducilo. No preguntes lo que podés leer.

## Paso 3 · Escribir la ficha

En `SPEC/objetivos/<slug>.md`, siguiendo `SPEC/objetivos/PLANTILLA.md`. El slug en minúsculas con guiones.

**La sección que decide si esto sirve o no es "Criterios de aceptación".** No se escribe en prosa: se escribe como **comando + salida esperada**, porque de ahí sale literalmente la condición del `/goal` y porque el evaluador solo puede juzgar lo que aparezca en la conversación.

```
Mal:   la herramienta funciona
Mal:   mejorar la seguridad del flujo
Bien:  py -3.13 cli/evaluar.py rapilink --humo --base   → 8/8, salida pegada
Bien:  py -3.13 cli/diferencias_config.py rapilink      → exit 0
Bien:  git diff --name-only no muestra ningún archivo fuera de nucleo/relevo/
```

Si un criterio no se puede expresar así, no es un criterio: es un deseo. Decilo y buscá con el usuario cuál sería la evidencia.

## Paso 4 · Emitir la condición `/goal`

Al final de tu respuesta, en un bloque de código, la condición **lista para copiar y pegar**. Se arma con: los criterios de aceptación + las restricciones + un tope de turnos.

Las restricciones de este repositorio van **siempre**, sin que el usuario tenga que acordarse — con `/goal` en auto mode los turnos corren sin que nadie mire:

```
NO push (push a fix/integracion-wisphub es DEPLOY A PRODUCCIÓN).
NO escribir tenant_config (parte la medición de razonamiento ON/OFF).
NO cargar config ni migrar contra producción.
NO correr los 56 casos dorados; usar --humo (~3 min).
Stage por rutas explícitas: nunca git add . ni git add -A.
```

Sumá las específicas del objetivo (qué archivos no se tocan, qué decisión no se reabre), y cerrá con un tope: `Parar después de N turnos y reportar qué falta.`

Caben 4.000 caracteres, así que entra el contrato entero. Mejor explícito que corto.

Formato de la entrega:

```
/goal <estado final medible>.
Condición: <criterio 1, con su comando y la salida pegada>; <criterio 2>; ...
Restricciones: <las de arriba> <las propias del objetivo>.
Parar después de N turnos y reportar qué falta.
```

## Paso 5 · Avisar lo que hace falta antes de largarlo

Dos cosas, en una línea cada una:

- Si `git config core.hooksPath` no devuelve `.githooks`, la puerta del `pre-commit` **no corre**. Con `/goal` en auto mode eso significa turnos autónomos sin ninguna red. Decilo.
- `/goal` no cambia el modo de permisos: sin auto mode va a preguntar igual en cada herramienta no permitida.

## Qué NO hace este comando

- No escribe código.
- No ejecuta el `/goal` (el usuario lo pega cuando decide arrancar).
- No decide por el usuario: si el objetivo depende de una decisión de producto todavía abierta, la ficha la nombra como bloqueo y el objetivo no arranca.
