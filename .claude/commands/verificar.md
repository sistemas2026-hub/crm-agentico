---
description: Corre las guardas que el cambio actual exige, según la tabla de disparadores de CLAUDE.md §6
argument-hint: (opcional) qué acotar, si no querés verificar todo el diff
---

# Verificar este cambio

Lo que tocaste decide qué corre — **no el criterio del momento**. Este comando aplica la tabla de disparadores de `CLAUDE.md` §6 sobre el diff actual.

Acotación pedida por el usuario, si la hay: **$ARGUMENTS**

## Paso 1 · Ver qué se tocó

```
git status --short
git diff --stat
git diff --cached --name-only
```

Si no hay nada modificado ni en el stage, decilo y terminá: no hay nada que verificar.

## Paso 2 · Elegir las guardas por lo que tocó

| Si el diff toca… | Corré | Tarda |
|---|---|---|
| cualquier cosa bajo `nucleo/` | `py -3.13 tests/test_nucleo_sin_tenants.py` | segundos |
| `nucleo/observabilidad/`, `nucleo/canales/` | `py -3.13 tests/test_registro_sin_pii.py` | segundos |
| `nucleo/config/editor.py`, el editor de agentes | `py -3.13 tests/test_editor_config.py` | segundos |
| `nucleo/modelo/` | `py -3.13 tests/test_timeouts_modelo.py` | segundos |
| prompts de rol, catálogo, modelo | `py -3.13 cli/evaluar.py rapilink --humo` | ~3 min |
| `tenants/*.config.yaml`, o se aplicó config | `py -3.13 cli/diferencias_config.py rapilink` **y** `py -3.13 cli/evaluar.py rapilink --humo --base` | seg. + 3 min |
| `supabase/*.sql` | `py -3.13 cli/migrar_asistente.py --estado` | segundos |
| `nucleo/seguridad/` | las de arriba que apliquen, **más** los agentes `auditor-de-frontera` y `revisor-de-pii` | |

Además, si el archivo tocado tiene una guarda propia con su mismo nombre en `tests/`, correla: este repo suele nombrarlas así.

**`--base` no es opcional después de aplicar config.** Sin él el corredor lee el YAML, que es justo el lado donde el dato sí estaba.

**No corras los 56 casos dorados** salvo que el usuario lo pida: tardan ~23 minutos y cuestan tokens reales contra el modelo de producción. Para eso están los 8 de humo.

## Paso 3 · Correrlas y pegar la salida

Una por una. **Pegá la salida real, no la resumas.** Si una falla, mostrá el error completo y no sigas como si nada.

Reglas del método, que acá son la mitad del valor:

- **Nunca declares que un test pasó si no lo ejecutaste.**
- Si no pudiste correr algo —falta una credencial, hace falta la base real, `py` no está— decilo explícitamente. "No verificado" es una respuesta válida; un verde inventado no.
- Afirmá sobre el **efecto**, no sobre la presencia del mecanismo.

## Paso 4 · Informe

```
TOCÓ        <las zonas del diff>
CORRIÓ      <guarda>  → verde / ROJO
            <guarda>  → verde / ROJO
NO CORRIÓ   <guarda>  → <por qué: tarda 23 min y no se pidió / falta la base / …>
AGENTES     <los que este cambio exige y todavía no corrieron>
```

Si algo quedó en rojo, eso va primero y no se entierra debajo de los verdes.
