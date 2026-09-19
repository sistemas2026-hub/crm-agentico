# DEXTER — ESTADO ACTUAL

Autoridad del estado. Quien empieza una sesión lee ESTO, no el historial.
Si contradice a una conversación, gana este archivo.

**Un gate no está cerrado hasta que este archivo lo refleje.** Y se poda cuando
se actualiza: una sección que quedó vieja no es inocua — la siguiente sesión la
lee como verdad. La historia detallada vive en `auditorias/`, no acá.

Última actualización: 19/09/2026, al cerrar la Fase 1.

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
139f8ca  cierre de 1.6
f61fd4d  1.7 Customer
929b86e  cierre de 1.7
4541423  1.8 Network
d5cc765  cierre de 1.8
b7bc9ea  1.9 cierre visual
```

## WORKTREE

Queda **un solo** archivo modificado sin commitear:

```
SPEC/CONTRATO_RELEVO_IA_HUMANO.md   arrastre ajeno sobre G9, sin destino propio
```

No restaurarlo ni borrarlo. Y mientras siga ahí, **stage por rutas explícitas
siempre, también para documentación**: prohibidos `git add .`, `git add -A`,
`commit -a` y **`git add SPEC/`**.

Ese último se coló en el cierre de 1.8 y metió el arrastre en el commit
documental. Un directorio entero es el mismo gesto que un `add .`: basta con que
alguien deje un archivo ajeno adentro. Verificar siempre con
`git diff --cached --name-only` antes de commitear.

## CERRADO

```
Fase 0 (componentización)     ✅
D29 · D30                     ✅
G9 recibo punta a punta       ✅ verde en producción 16/09/2026
Fase 1.1–1.4B (visual)        ✅
FASE 1.4C  backend + UI de T6 ✅
FASE 1.5   Case + Tools       ✅
FASE 1.6   Activity           ✅  el relevo se lee por primera vez
FASE 1.7   Customer           ✅  lo que sabe del cliente, y lo que no
FASE 1.8   Network            ✅  qué se le hizo al equipo, sin botones
FASE 1.9   cierre visual      ✅  utilidades de panel unificadas
FASE 1     Bandeja rediseñada ✅  COMPLETA
```

## ABIERTO al cerrar la Fase 1

```
G6 sobre messages poblada   🔒 gate de DESPLIEGUE. La migración aplica limpia
                               desde cero y el ledger la anota sola, pero no se
                               midió sobre una tabla con datos. No bloquea
                               desarrollo; sí bloquea cualquier push.
QA visual multi-viewport    🔴 NO EJECUTABLE con los medios disponibles, y no
                               por falta de intento: el dev server levanta pero
                               hooks.server.js:373 redirige a /login antes de
                               montar el layout, así que ni el estado de error
                               dentro de .mesa.bandeja se dibuja. Entrar exige
                               un JWT del backend de producción; una ruta de
                               prueba con datos falsos está prohibida.
                               NINGÚN píxel de 1.4C a 1.9 se vio renderizado.
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
Branding   pantalla de ajustes, FUERA de la Fase 1
```

No es la Bandeja: es «Settings · Appearance & Branding», con subida de archivo,
almacenamiento de assets y alcance por organización. Hoy existe `Marca.logo_url`
en el esquema del tenant **sin ningún consumidor**, y nada más. Necesita su
propio scope.

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
ficha del cliente     Dexter guarda identidad + equipo y nada más (RNF-01);
                      no se consulta el ISP en vivo desde la Bandeja
acciones sobre el     no se ejecutan desde la Bandeja: reiniciar corta el
equipo                servicio y pasa por la cola con confirmación (PRD §7.4)
ACCION_CONFIRMADA     el equipo hizo lo pedido ≠ el cliente tiene internet
NO_VERIFICABLE        «no se pudo medir» ≠ «se midió y el efecto no está»
el ping               no es veredicto: medido, un equipo sano da 1/3, 2/3 y 3/3
bloqueo               ≠ error: el código frenando la acción es la protección
                      funcionando, y no ensucia la tasa de error
```
