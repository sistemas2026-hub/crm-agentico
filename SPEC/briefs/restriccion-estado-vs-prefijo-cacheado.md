# Restricción de implementación · el estado dinámico no toca el prefijo cacheado

> Escrito el 25/09/2026, **antes** de la ficha y a propósito. La ficha del cambio
> espera dos mediciones (abajo); esta restricción no, porque el riesgo que cubre
> es que alguien implemente la solución obvia sin conocer el dato que la
> desaconseja.
>
> No cierra la arquitectura. Acota **una** decisión.

## El defecto que motiva todo esto

Medido el 25/09/2026, con su guarda en
[tests/test_system_identidad_no_queda_obsoleto.py](../../tests/test_system_identidad_no_queda_obsoleto.py)
(en ROJO DECLARADO, defecto abierto):

Los mensajes `system` que el motor arma dentro de `if not historial`
([nucleo/modelo/motor.py:3144](../../nucleo/modelo/motor.py)) se escriben **una
vez, en el primer turno**, y nada los invalida cuando el estado que describen
cambia. Una conversación que arranca sin verificar y se verifica después arrastra
para siempre *"Este cliente TODAVIA NO esta verificado: no sabes quien es, no
tienes su cuenta ubicada y no conoces su servicio"* — con `sesion.verificado`
ya en `True`.

**Un `system` no es memoria: es una instrucción vigente.** Si afirma un estado
que puede cambiar, en algún momento se vuelve una mentira activa, y el modelo no
tiene con qué saber cuál de los dos mundos es el de hoy.

## La solución obvia, y por qué es media solución

La lectura natural del defecto lleva a:

> *"El estado cambia, entonces regeneremos el `system` en cada turno con el
> estado actual."*

Es correcta en el diagnóstico y peligrosa en el lugar. El `system` es el
**primer** mensaje del payload, y el caché de entrada del proveedor es **de
prefijo**: cualquier cambio arriba invalida todo lo que viene después.

### La restricción

```
El estado dinámico NO modifica el prefijo estable del prompt.

La vista del contexto se construye preservando:
  - instrucciones estables ARRIBA      (cacheables: identidad, rol, políticas)
  - estado operativo dinámico ABAJO    (zona variable, recalculado por turno)

No mover estado al prefijo sin medir el impacto de caché.
```

Y el corolario que arregla el defecto sin pagar el costo: **el mensaje del turno
1 deja de afirmar estado.** El estado viaja en la cola, que es la parte que
cambia de todos modos — y de paso es donde tiene más peso de atención.

## El número, que es lo que hace defendible la restricción

Está medido en el repo y nadie lo va a cruzar con este problema por su cuenta
— [nucleo/modelo/cliente.py](../../nucleo/modelo/cliente.py), sobre
`tokens_entrada_cache`:

```
un token de entrada cacheado sale ~30 veces mas barato que uno nuevo
   ($0.014 contra $0.44 por millon, DeepSeek)

medido sobre 30 dias reales de Rapilink:
   141.8 millones de tokens  ->  $7.48       ($0.053 por millon)
   la misma carga sin cache  ->  $30 a $60   (estimado)
```

Se cita el número no para cerrar el diseño sino porque sin él la restricción
suena a preferencia. **Ninguna guarda del proyecto mira el costo**: un cambio que
multiplique la factura por 4 a 8 pasa el CI entero en verde.

## Lo que esta restricción NO decide

- **Cómo se invalida** un `system` vencido: `pop` como el precedente que ya
  existe ([api.py:1754](../../nucleo/canales/api.py) lo hace para
  `INSTRUCCION_REENCAUZAR`), o no escribirlo nunca arriba. Las dos respetan la
  restricción.
- **Qué forma tiene** el bloque de estado.
- **Si hace falta un contrato por inyección** (`tipo: permanente | temporal`,
  `vence: cuando cambia X`). Probablemente sí, y es de la ficha.

## Precedente: el principio ya está en el proyecto, aplicado a otra cosa

*Cada parte del sistema ve la vista adecuada a su responsabilidad* no es nuevo
acá: es lo que hacen las **listas blancas por rol**, que deciden qué campos del
cliente llegan al modelo según el área que atiende, sobre datos que siguen
completos abajo.

```
datos del cliente        -> vista según responsabilidad   ✅ resuelto
contexto conversacional  -> vista según responsabilidad   ← esto
```

Mismo principio, y más delicado en el segundo caso: el lenguaje natural arrastra
más que un campo ausente. **La regla que se conserva es la misma: no se arregla
eliminando información.** La identidad de agosto queda, el historial queda, la
auditoría queda. Lo que cambia es qué vista recibe cada componente.

## Lo que falta antes de la ficha

```
1  A/B/C contra el modelo, N>=5           C:\tmp\abc_router_con_modelo.py
     Hoy está probado que la contradicción EXISTE; falta cuánto mueve la
     decisión. Sin eso no hay causalidad. Mide sobre la traza, no la redacción,
     y repite porque el modelo es probabilístico -- el proyecto ya pagó esa
     lección dos veces con el ping (1 de 3, 2 de 3 y 3 de 3 con el mismo equipo
     sano).
2  la segunda medición pendiente del hilo de investigación
     (`puede_consultar` declarado contra capacidad real)
```

Con esos dos, la ficha. Sin ellos, esta restricción sola.
