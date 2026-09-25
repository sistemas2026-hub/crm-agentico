---
description: El arranque de toda sesión — lee el estado real, los objetivos abiertos y el terreno, y pregunta qué se trabaja
---

# Arranque de sesión

Antes de tocar nada. Tu salida es un **informe corto de situación** y una pregunta, no trabajo.

## Paso 1 · Leer, del disco, en este orden

La jerarquía de autoridad de `CLAUDE.md` §1. De arriba hacia abajo, y gana el de más arriba:

1. `CLAUDE.md`
2. `SPEC/DEXTER_CONTRATOS_GLOBALES.md` — invariantes congelados
3. `SPEC/DEXTER_ESTADO_ACTUAL.md` — **la autoridad del estado.** Gana sobre cualquier conversación, resumen o recuerdo
4. `SPEC/objetivos/*.md` — los que estén en estado **abierto**

`PRD.md` y `ARQUITECTURA.md` se leen cuando el trabajo los toque, no en el arranque: son largos y el arranque tiene que ser barato.

## Paso 2 · Medir git, no recordarlo

```
git fetch origin
git branch --show-current
git status --short
git log --oneline -5
git log -5 --oneline -- PRD.md ARQUITECTURA.md SPEC/DEXTER_ESTADO_ACTUAL.md
```

El último importa: **commits que no reconocés en esos archivos son cambios de otro colaborador**, y hay que revisarlos antes de tocar nada relacionado.

Si el árbol tiene trabajo sin commitear, nombralo. Alguien lo dejó ahí a propósito y no se limpia sin preguntar.

## Paso 3 · Comprobar que las puertas están puestas

```
git config core.hooksPath
```

Tiene que devolver `.githooks`. Si devuelve vacío, el `pre-commit` **no corre** — y un hook que no corre es la falla que CLAUDE.md §6 llama *código construido no es código que corre*. Decilo, con el comando para arreglarlo:

```
git config core.hooksPath .githooks
```

## Paso 4 · Informe

Corto. Esto se lee de un vistazo, no se estudia:

```
RAMA        <rama> · <N> commits sin pushear · <limpio | N archivos sin commitear>
ESTADO      <lo que dice DEXTER_ESTADO_ACTUAL: qué está cerrado, qué sigue>
OBJETIVOS   <fichas abiertas, una línea cada una: título + qué falta>
NOVEDADES   <commits de otro colaborador en los documentos de autoridad, o "ninguna">
PUERTAS     <hooks activos | NO activos, con el comando>
```

Si algo de lo que leíste **se contradice** con otra cosa —un objetivo que dice una cosa y el estado otra, un documento que se declara autoridad fuera de la jerarquía de §1— eso va arriba de todo. Es el hallazgo más valioso de un arranque y el más fácil de pasar por alto.

## Paso 5 · Preguntar

Terminá preguntando qué se va a trabajar, y ofrecé lo que se deduce del estado: un objetivo abierto que quedó a mitad, una deuda de §13, un gate que falta cerrar. Dos o tres opciones concretas, no un catálogo.

**No empieces a trabajar en este turno**, ni siquiera si la respuesta parece obvia.
