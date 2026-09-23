---
description: Cierra un bloque de trabajo — pasada adversarial, guardas, y actualiza la autoridad del estado
argument-hint: (opcional) qué bloque u objetivo se está cerrando
---

# Cerrar un bloque

Bloque a cerrar: **$ARGUMENTS**

Cerrar no es "terminé de escribir". Es: **la evidencia existe, alguien que no lo construyó lo miró, y el estado del proyecto lo refleja.** Los tres, o no está cerrado.

## Paso 1 · Las guardas

Corré `/verificar` sobre el diff completo del bloque. Si algo queda en rojo, **el bloque no se cierra**: se reporta y se para acá.

Si el bloque tiene una ficha en `SPEC/objetivos/`, sus criterios de aceptación mandan sobre esta lista: son comando + salida esperada, y hay que satisfacerlos uno por uno, pegando la salida real.

## Paso 2 · La pasada que no heredó tus supuestos

Invocá al agente `auditor-independiente` sobre el diff del bloque.

Su valor es no haber construido esto. **No descartes un hallazgo porque sabés por qué escribiste ese código** — saber por qué lo escribiste es justamente lo que te impide ver qué escribiste.

Con cada hallazgo, una de dos, nunca una tercera:

- **Se resuelve**, y se vuelve a verificar.
- **Se anota** en `SPEC/auditorias/` con su motivo y su estado. Un hallazgo que sobrevive a la sesión se escribe; uno que no, se resuelve en el momento.

Si el bloque es chico y acotado, esta pasada se puede saltear — **diciéndolo**, con el motivo. Lo peligroso no es saltarse un paso.

## Paso 3 · Actualizar la autoridad del estado

`SPEC/DEXTER_ESTADO_ACTUAL.md`. Y dos reglas del propio archivo:

> **Un gate no está cerrado hasta que este archivo lo refleje.**
>
> **Se poda cuando se actualiza:** una sección que quedó vieja no es inocua — la siguiente sesión la lee como verdad.

O sea: agregá lo que se cerró **y borrá lo que dejó de ser cierto**. Si el bloque tenía ficha en `SPEC/objetivos/`, marcala cerrada, podala a su resultado, y anotá la última línea de su bitácora.

## Paso 4 · El commit

- **Stage por rutas explícitas.** Prohibidos `git add .`, `git add -A`, `commit -a` y `git add SPEC/` — un directorio entero es el mismo gesto que un `add .`.
- Verificá con `git diff --cached --name-only` **antes** de commitear, y mostrá esa lista.
- Mensaje en español que dice **el efecto**, no el mecanismo.
- **No pushees.** Push a `fix/integracion-wisphub` es deploy a producción, y eso lo decide una persona, con la palabra dicha antes.

## Paso 5 · Entregar

```
BLOQUE      <qué se cerró>
EVIDENCIA   <guarda> → verde   (salida pegada arriba)
AUDITORÍA   <hallazgos: resueltos / anotados en SPEC/auditorias/ / ninguno>
ESTADO      <qué se agregó y qué se podó de DEXTER_ESTADO_ACTUAL.md>
COMMIT      <hash> — sin push
QUEDÓ FUERA <lo que no se hizo, y por qué>
```

El último bloque no es opcional. Reducir el alcance es decisión del usuario, no tuya: lo que quedó afuera se dice, no se omite.
