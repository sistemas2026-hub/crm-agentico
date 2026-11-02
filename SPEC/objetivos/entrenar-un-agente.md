# Entrenar un agente desde la plataforma

**Estado:** etapa 1 construida · **Abierto:** 02/11/2026

## Qué pidió el usuario

> *"quiero que en agentes se pueda crear el agente yo mismo y entrenarlo"*

Crear ya funcionaba. Entrenar, no — y la palabra necesitaba definirse.

## Qué significa «entrenar» acá, y qué no

**No es fine-tuning.** `PRD.md:121` lo pone fuera de alcance y el proveedor no
lo ofrece para imágenes ni texto en este plan. Entrenar es: corregir con
procedimientos, y medir si la corrección sirvió.

## El hallazgo que ordenó el trabajo

**El carril de entrenar ya existía y es `/habilidades`, no `/manual`.**

| | `ejemplos_validados` (/manual) | `asistente.habilidades` |
|---|---|---|
| Por rol | **no** | sí, `roles_permitidos`, fail-closed |
| Entra al prompt | **no** | sí, índice en cada turno |
| Aprobada por una persona | n/a | sí, nace `propuesta` |

Medido: el único lector de `ejemplos_validados` es la consulta que pinta
`/manual`; **cero llamadores en `nucleo/modelo/`**. Marcar un ejemplo no
cambia una palabra del prompt de nadie. Y aprobar una revisión del Supervisor
solo mueve `estado`: el `aporte_sugerido` que redactó muere en la fila.

Por eso la corrección **no** creó un «ejemplo malo». Habría sido una segunda
marca sin efecto, al lado de una que ya existe y tampoco lo tiene.

## Las tres piezas, y por qué esas

Cierran un ciclo: *se equivocó → lo corrijo → sé si mejoró*.

1. **Probarlo.** El proxy del simulador fijaba `rol: 'cliente_final'`. El
   motor siempre aceptó `rol` en `POST /chat`; era el proxy el que lo tapaba,
   así que un agente recién creado no se podía probar desde ninguna pantalla.
2. **Corregirlo.** Botón «✎ Corregir» en la burbuja, al lado de «☆ Buen
   ejemplo», que escribe una habilidad **para el rol de esa conversación**.
   Reusa `POST /habilidades` tal como está.
3. **Saber si mejoró.** `GET /habilidades/huecos` ya calcula por rol; la
   tarjeta de `/agentes` lo muestra. Antes ahí solo había la tasa de escalada
   de **toda la empresa** (`db.tasa_escalamiento` dice en su docstring que
   «no filtra por rol»): al lado de un agente decía algo que no era de él.

## Decisiones tomadas

| # | Decisión | Por qué |
|---|---|---|
| 1 | **Corregir escribe una habilidad, no un ejemplo** | Un ejemplo no llega al agente; una habilidad sí, y está por rol |
| 2 | **Nace `propuesta`, nunca se aprueba sola** | Mismo contrato que el resto de `/habilidades`: que lo haya escrito una persona mirando una respuesta mala no lo pone a operar |
| 3 | **Cambiar de agente sube el número de prueba** | La sesión del motor ES el `identificador_sesion`. Una conversación abierta restaura su `rol_efectivo` y **pisa** el rol que manda la pantalla (`api.py:875`): sin número nuevo, el selector habría mostrado un agente y hablado con otro — el resultado falso más caro en la herramienta que existe para probar |
| 4 | **La lógica pura vive en `$lib/components/manual/entrenar.js`** | El harness de vitest no compila `.svelte` ni resuelve `$env/dynamic/private`. Dentro del componente habría quedado sin guarda |
| 5 | **Reusar `/habilidades/huecos`, no escribir un segundo SQL** | Dos definiciones de la misma métrica divergen en el primer cambio |

## Lo que sigue abierto

- **Sin datos no se muestra nada.** Un agente que nadie usó no tiene huecos, y
  «0 huecos» habría dicho que anda bien cuando lo que pasa es que no hay datos.
- **No hay «respuesta esperada».** Escribir *la respuesta que debía dar* es un
  **caso dorado**, no un procedimiento: afirma sobre el turno y se puede
  re-correr. Eso es etapa 3 y necesita tabla propia.
- **Correr los 97 casos dorados desde la pantalla**: no entra todavía.
  `cli/evaluar.py` tarda ~23 min, llama APIs reales, cuesta plata, y CLAUDE.md
  §6 ya mide que **no pasa por `atender_turno`**.
- **Editar una habilidad vigente** creando `version+1`: las columnas existen,
  falta el `PUT`. Hoy el ciclo es crear nueva y retirar la vieja.
- **Retirar un documento del corpus** es la única ruta del motor sin interfaz.

## Bitácora

| Fecha | Qué | Evidencia | Hash |
|---|---|---|---|
| 02/11/2026 | **Etapa 1.** Selector de agente en el simulador (y número nuevo al cambiarlo); «✎ Corregir» en la burbuja, en Conversaciones y en el simulador, que escribe una habilidad para el rol de esa conversación; huecos por rol en la tarjeta de `/agentes` | `entrenar.test.js` **19 verdes** y **4 mutaciones muertas** (el número no cambia, el código sin sufijo, la señal de «se le enseñó y escaló igual» indistinguible, el rol vuelve a quedar fijo). `svelte-check`: **0 errores**. `vitest` completo: 70 archivos / 10 pruebas rojas **idéntico al baseline sin mis cambios** (93 verdes contra 92: los 19 nuevos) | este commit |
