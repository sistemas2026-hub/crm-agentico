# Objetivo · Dexter Campo — versión candidata

> Abierto el 23/09/2026. Estado: **abierto**.
> Primera ficha del sistema. Lo que encontró al estrenarse está en "Qué reveló
> esta ficha", al final — no se borra: es lo que hay que arreglar del sistema.

## Qué significa terminado

La aplicación de técnicos tiene un artefacto instalable que una empresa puede
usar mañana, y lo que se le promete está medido, no supuesto.

**Se parte en dos, porque son dos cosas distintas y solo una se puede
automatizar:**

| | Qué | Quién puede cerrarlo |
|---|---|---|
| **A** | La suite verde en la rama correcta, el APK de release compilado, y el contrato commiteado y al día | Una sesión con `/goal` |
| **B** | Las cinco verificaciones de campo del contrato §5 | **Una persona con un teléfono.** Ninguna IA |

`/goal` cierra **A**. **B** es una lista de control que firma una persona.
Escribir un objetivo que prometa cerrar las dos sería exactamente el error que
este repositorio llama *afirmar sobre el mecanismo en vez del efecto*.

## Criterios de aceptación

### Parte A — verificable por comando

| # | Evidencia | Cómo se comprueba |
|---|---|---|
| A1 | El trabajo corre sobre la rama que tiene Campo | `git ls-files apps/tecnicos-mobile/test/ \| wc -l` → **101**, no 6. Salida pegada |
| A2 | La suite pasa entera | `flutter test` en `apps/tecnicos-mobile/` → exit 0 y el conteo pegado (referencia del contrato: **529**) |
| A3 | Pasa en las **dos** compilaciones | la suite verde con la bandera de demostración apagada **y** encendida. Una guarda que solo corre apagada no prueba nada |
| A4 | El APK de release existe | `flutter build apk --release` → exit 0, ruta y tamaño del artefacto pegados |
| A5 | El contrato está en el repositorio y al día | `CAMPO_RELEASE_CONTRACT.md` commiteado; sus cifras coinciden con lo que A2 midió recién, o se corrigen |
| A6 | Nada se coló | `git diff --cached --name-only` solo muestra rutas bajo `apps/tecnicos-mobile/` |

### Parte B — no se cierra con un comando

Del contrato §5. Cada una necesita un teléfono, una cuenta real, o tiempo.

- [ ] Instalar el APK limpio en un teléfono. *(Ya hubo dos fallas que solo
      aparecen en el artefacto final: un comentario XML con `--` que rompía
      `mergeReleaseResources`, y config declarada en el repo que producción no
      tenía.)*
- [ ] Entrar con una cuenta real y bajar una jornada de verdad.
- [ ] Recorrer el día completo en el teléfono, sin red parte del tiempo.
- [ ] Reinstalar sobre una versión anterior, para ejercitar las migraciones de
      la base local con datos ya guardados.
- [ ] Medir arranque y scroll con una jornada de veinte órdenes.

## Restricciones

Las tres permanentes del repositorio:

- **NO push** — push a `fix/integracion-wisphub` es deploy a producción.
- **NO escribir `tenant_config`** — parte la medición de razonamiento ON/OFF.
- **NO correr los 56 casos dorados** — son del motor, no de Campo.

Las propias de este objetivo:

- **NO agregar funcionalidad.** Una candidata se estabiliza, no se amplía.
- **NO cambiar arquitectura.** Los seis invariantes del contrato §3 se respetan;
  el más caro ya apareció **cinco veces**: el esquema del formulario se lee en
  un solo lugar (`campo_del_formulario.dart`).
- **NO tocar `nucleo/`, `django-crm/` ni `tenants/`.** Este objetivo es la app.
- **NO integrar `feat/campo-diseno-stitch` a otra rama** sin decisión explícita:
  es una decisión de entrega, no un paso del objetivo.

## Qué NO hacer

- **No construir lo que el contrato §2 declara ausente** — telemetría óptica,
  vehículo, academia, turno y cuadrilla, escáner, mapa. Son **51** datos
  pendientes, inventariados, y su ausencia es deliberada: *un destino que lleva
  a "en construcción" es una promesa que no se cumple.*
- **No normalizar el esquema de evidencias.** Es deuda anotada del contrato §6,
  real, y no es de esta entrega.
- **No prometer la Parte B como hecha** porque la A esté verde.

## Agentes involucrados

| Agente | Para qué | Estado |
|---|---|---|
| `auditor-independiente` | La pasada adversarial antes de entregar. Es el único agnóstico del stack: sus cinco huecos (mecanismo que nunca corre, prueba que afirma existencia, repo que declara lo que el artefacto no tiene, condición de éxito ruidosa, garantía sobre algo inestable) aplican igual a Flutter | pendiente |
| `arquitecto-dexter` | Solo su pregunta 1 y 3 (¿ya existe? ¿dónde vive?). Su contenido está escrito para el motor | parcial |
| `guardia-de-release` | Su **espíritu** aplica —¿estamos listos para salir?— pero su checklist es ledger, `tenant_config` y variables del motor. No sirve tal cual | **no aplica sin reescribir** |
| `verificador-de-api` · `revisor-de-pii` · `auditor-de-frontera` · `corredor-de-evaluacion` · `guardia-de-config` | **Se saltean.** Ninguno toca este trabajo: no hay API externa nueva, ni listas blancas del motor, ni frontera de autorización, ni casos dorados, ni config de tenant | se saltean |

## Bloqueos

**B1 · El código no está bajo tus pies, y es una decisión, no una tarea.**
Medido el 23/09/2026: 6 archivos de prueba en `integrar-centro-mando` contra
101 en `feat/campo-diseno-stitch`. Hay que elegir:

| Camino | Implica |
|---|---|
| Worktree aparte sobre `feat/campo-diseno-stitch` | Cero riesgo para el Centro de Mando. Dos árboles que mantener |
| Integrar Campo a `integrar-centro-mando` primero | Un solo árbol. Mezcla dos trabajos que hoy avanzan por separado |

Sin resolver esto, A1 no se puede cumplir y el objetivo no arranca.

**B2 · Los archivos sueltos no tienen dueño declarado.** `e2e_002/003/004`,
`test/apoyo/` y `docs/CAMPO_RELEASE_CONTRACT.md` están sin commitear en esta
rama, que no es la de Campo. Hay que decidir si son arrastre de la otra rama o
trabajo nuevo que va a alguna parte. **No se tocan hasta que eso se decida.**

**B3 · La Parte B necesita un teléfono y una cuenta real.** Y "entrar con una
cuenta real" toca producción. Eso lo hace una persona, y conviene decidir
quién y cuándo antes de dar la candidata por lista.

## Bitácora

| Fecha | Qué avanzó | Qué falta | Commit |
|---|---|---|---|
| 23/09/2026 | Ficha abierta. Medido dónde vive Campo (B1) y qué falta del contrato §5 | Resolver B1 para poder arrancar | — |

---

## Qué reveló esta ficha sobre el propio sistema

Se estrenó y encontró tres cosas. Se dejan escritas acá porque son trabajo
pendiente del sistema de trabajo, no de Campo:

1. **Los agentes no estaban cargados en la sesión.** El comando `/objetivo`
   manda invocar al `orquestador` y no existía como tipo de agente: de los
   nueve, la sesión solo había registrado `verificador-de-api`. Están
   commiteados y en disco. Su plan se aplicó a mano.
2. **Seis de los nueve agentes no sirven para un trabajo de Flutter.** Están
   escritos para el motor. Ya estaba anotado como hueco conocido en CLAUDE.md
   §11.1 (`especialista-mobile`, sin crear); este objetivo lo confirma con un
   caso real, que era la condición para crearlo.
3. **Un objetivo puede tener una mitad que ninguna IA cierra.** La plantilla no
   preveía eso y empujaba a escribir todo como comando + salida. La partición
   A/B de arriba es la respuesta; conviene subirla a `PLANTILLA.md`.
