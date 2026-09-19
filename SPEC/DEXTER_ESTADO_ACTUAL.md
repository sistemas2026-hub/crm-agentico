# DEXTER — ESTADO ACTUAL

Autoridad del estado. Quien empieza una sesión lee ESTO, no el historial.
Si contradice a una conversación, gana este archivo.

**Un gate no está cerrado hasta que este archivo lo refleje.** Y se poda cuando
se actualiza: una sección que quedó vieja no es inocua — la siguiente sesión la
lee como verdad. La historia detallada vive en `auditorias/`, no acá.

Última actualización: 19/09/2026, al cerrar la Fase 1.6.

---

## BASE CANÓNICA

```
rama       feature/bandeja-relevo
worktree   C:\tmp\dexter-bandeja
```

Nada pusheado. Sobre `d0d6be9`:

```
04d835e  backend T6, medido contra PostgreSQL 16.14
df7eb7c  checkpoint + esta memoria operativa
d033e58  UI de T6
fa6b91a  cierre de 1.4C + corrección de la lista de warnings
5f30f74  1.5 Case + Tools
178d749  cierre de 1.5
4d73ea8  1.6 Activity
```

## WORKTREE

Queda **un solo** archivo modificado sin commitear:

```
SPEC/CONTRATO_RELEVO_IA_HUMANO.md   arrastre ajeno sobre G9, sin destino propio
```

No restaurarlo ni borrarlo, y **nunca** `git add .` / `-A` / `commit -a` mientras
siga ahí.

## CERRADO

```
Fase 0 (componentización)     ✅
D29 · D30                     ✅
G9 recibo punta a punta       ✅ verde en producción 16/09/2026
Fase 1.1–1.4B (visual)        ✅
FASE 1.4C  backend + UI de T6 ✅
FASE 1.5   Case + Tools       ✅
FASE 1.6   Activity           ✅  el relevo se lee por primera vez
```

## ABIERTO — nada de esto bloquea 1.7

```
G6 sobre messages poblada   🔒 gate de DESPLIEGUE. La migración aplica limpia
                               desde cero y el ledger la anota sola, pero no se
                               midió sobre una tabla con datos. No bloquea
                               desarrollo; sí bloquea cualquier push.
smoke visual integral       ⏭ nada de 1.4C, 1.5 ni 1.6 se vio renderizado, en
                               ningún viewport. Hay auditoría estática de CSS.
D28                         ⏭ abierto para B4. La pantalla lo MUESTRA (1.5): el
                               dueño del CRM es informativo, el de Dexter manda.
                               No se reconcilian — no comparten identidad de
                               usuario, y por eso se comparan nombres.
hot path ③a/③c              ⏭ idempotencia del outbound automático del canal,
                               retirado y preservado en
                               auditorias/1.4C-hotpath-diferido.md
T7 endpoint                 ⏭ «devolver sin responder»: capacidad distinta, NO
                               el recovery de T6
semánticos ember/clay/      ⏭ resueltos en context/ (1.5); los consumidores de
rust/moss                      otras pantallas, en la fase de cada una
```

## SIGUIENTE GATE

```
Fase 1.7   Customer
```

Entrada: `SPEC/FASE_1_CHECKPOINT.md`.

## CONTRATOS CONGELADOS DE ESTA RAMA

No se reauditan sin evidencia nueva.

```
T6 · control = ia     sólo con wamid + estado_entrega='enviado' durables
T6 · sin optimismo    el control cambia sólo con devuelto_al_asistente === true
rechazado             ≠ incierto / sin_id / aceptado_sin_registro
unknown               conserva el control humano y NO ofrece reintentar
clave idempotente     una por intento; viaja con la burbuja junto a la intención
T7                    no es el recovery de T6
D28                   dueño del ticket CRM ≠ dueño durable de Dexter;
                      nombres iguales NO prueban identidad
bloqueo               ≠ error: el código frenando la acción es la protección
                      funcionando, y no ensucia la tasa de error
```
