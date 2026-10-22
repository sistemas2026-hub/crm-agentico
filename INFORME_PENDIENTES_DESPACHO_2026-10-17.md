# Pendientes del paso a Despacho — qué hay y qué pasaría con cada regla

Medido el 16/10/2026 a las 20:40 (Bogotá) con `informe_de_pendientes` sobre
Rapilink: **64 propuestas pendientes de lectura de ticket**. Pasan hoy: **0**.
Las reglas vigentes son las de la ficha `SPEC/objetivos/supervisor-pasa-a-despacho.md`.

## En una línea

De 64, **36 son casos que ya están cerrados**: no hay nada que despachar. De
los 27 abiertos, **3 pasarían si LOS pasara** y **5 si alcanzara con confianza
media**. Los otros 19 no pasan con ninguna regla, y **6 de ellos están sin
clasificar aunque su hipótesis es clara**.

## 1 · Los 36 cerrados: nada que despachar, pero ocupan la bandeja

- Tickets de hace 1 a 3 días, cerrados hace 0 a 3 días. **Inferido:** el flujo
  normal del ISP los resolvió antes de que una persona decidiera la propuesta.
- Lo que decían sus hipótesis: 10 cortes o fallas de fibra en NAP o planta,
  7 sin energía en el domicilio, 6 desajustes de configuración en la OLT, y el
  resto varios (equipo sin registrar, intermitencia, instalación).
- **La lección para las reglas:** el ISP cierra las fallas de fibra en 1 a 3
  días por su cuenta. El paso automático solo agrega algo si mueve el ticket
  **en la hora de su lectura**. Con "LOS va a una persona", los 3 LOS de abajo
  llevan 1 y 2 días esperando.
- **Qué hacer:** retirarlas, como se hizo con las de otras áreas. No cambia
  ninguna regla; deja la bandeja con lo real.

## 2 · Los 3 caídos por LOS: pasarían con la regla 1 del 14/10

| Ticket | Edad | Hipótesis del Supervisor | Medición |
|---|---|---|---|
| 95218 | 2 d | corte o falla en la fibra (NAP o tramo), servicio 2109 | caído, pérdida de señal óptica |
| 95486 | 1 d | corte o falla en el tramo de fibra, servicio 791… | caído, pérdida de señal óptica |
| 95530 | 1 d | corte o falla de fibra en la planta (NAP o acometida) | caído, pérdida de señal óptica |

Los tres con confianza alta, los tres con el caso abierto. El riesgo que
motivó la decisión del 16/10 sigue: un equipo desenchufado se ve igual desde
la OLT. La mitigación es que el despachador llame antes de mandar a alguien.

**Recomendación: que pasen.** Es volver a la regla 1 tal como se decidió el
14/10, con la medición real en vez de la lectura.

## 3 · Los 5 con el equipo en línea y en rango: siguen a una persona

| Ticket | Señal | Hipótesis | Lectura |
|---|---|---|---|
| 95251 | -20.81 dBm | en línea, buena señal, configuración no coincide con el perfil | desajuste en la OLT: tarea del NOC, no visita |
| 95318 | -21.8 dBm | discrepancia de configuración en la OLT (mismatch) | igual |
| 95394 | -22.92 dBm | degradación de la señal óptica | la medición lo contradice |
| 95523 | -20.0 dBm | corte o falla de fibra en la planta | ahora está en línea: pudo resolverse |
| 95531 | -25.0 dBm | sin falla de red activa | justo en el borde del rango |

**Recomendación: se sostiene la decisión del 16/10.** Dos son tareas de
configuración en la OLT, que no se resuelven con una visita. El de -25.0 dBm
está en el límite exacto: con -25.1 pasaría solo.

## 4 · Los 6 frenados por la confianza: obras de red y un trabajo pedido

| Ticket | Grupo | Confianza | Hipótesis |
|---|---|---|---|
| 94668 | obra de red | media | intervención o relevamiento sobre la CTO |
| 60409 | obra de red | media | deterioro de planta en una caja, enfrentadores en mal estado |
| 86528 | obra de red | media | intervención de planta sobre la caja NAM |
| 90441 | obra de red | media | **sin hipótesis** |
| 77986 | trabajo pedido | media | reactivación de un servicio dado de baja |
| 95395 | trabajo pedido | **sin confianza** | instalación de TDT financiada, aceptada por el cliente |

Con "media" pasan 5. Cuatro tienen una hipótesis clara de obra o de trabajo;
90441 no tiene hipótesis y es el dudoso. 95395 no trae confianza del grupo: el
Supervisor no la escribió, y con cualquier regla se queda.

**Recomendación: aceptar confianza media para obra de red y trabajo pedido.**
Si se quiere más cuidado, exigir además que haya hipótesis: eso deja afuera
solo al 90441.

## 5 · Los 6 que siempre van a una persona: correcto

94562 y 94056 (bloqueo o filtrado de dominios: ninguna herramienta de red lo
mide), 94481, 57820, 91906 y 95275 (órdenes internas o tickets que no son de
un abonado ni de la red). Ninguna regla debería moverlos.

## 6 · Los 6 sin grupo: el Supervisor no clasificó, y tres son obras evidentes

| Ticket | Hipótesis |
|---|---|
| 71357 | falla de niveles ópticos en planta externa: el segundo splitter de la… |
| 84000 | degradación del segundo splitter de la CTO 11-43 Villa María |
| 90491 | falla o degradación en planta externa (ramal/CTO) que afecta a ~28… |
| 94010 | el servicio 5574 figura sin equipo registrado en el proveedor |
| 56768 | la instalación nueva del servicio 5574 no se ejecutó |
| 71874 | sin hipótesis |

Los tres primeros son obras de red con todas las letras, y uno afecta a
unos 28 clientes. El modelo dejó el grupo vacío igual. **Esto no se arregla
con una regla:** es la clasificación, y hoy la relectura de los sin grupo no
los está destrabando. Es otra tarea: revisar la ayuda del campo `grupo` que
se le da al modelo, y medirlo con los casos dorados antes de desplegar.

## 7 · Los 2 que esperan un dato

- 65210: el equipo volvió como caído, sin causa ni señal. Se mide de nuevo
  mañana; si repite, es un equipo registrado que SmartOLT no sabe leer.
- 95227: la última lectura del ticket en WispHub falló. La hipótesis dice
  corte de fibra. Se destraba solo cuando el importador vuelva a leerlo.

## Qué decidir

| Decisión | Pasarían hoy | Recomendación |
|---|---|---|
| LOS pasa solo | +3 | Sí |
| Confianza media alcanza para obra de red y trabajo pedido | +5 | Sí; 90441 es el dudoso |
| Retirar las propuestas de casos cerrados | 0, pero la bandeja baja de 64 a 28 | Sí |
| Los 6 sin grupo | 0 | No es una regla: tarea aparte sobre la clasificación |

Con las dos primeras, hoy pasarían 8 de los 27 abiertos. Las otras 19 se
quedan por motivos que una persona confirmaría: equipo sano, nada que medir,
sin clasificar, o esperando un dato.

**Lo que esta medición no dice:** cuántos de los 3 LOS son equipos
desenchufados. Eso se sabe después, con lo que encuentre el despachador. Vale
la pena anotarlo caso por caso durante las primeras semanas: es el número que
confirma o corrige la regla.

## Lo que se decidió con esto (16/10, noche)

Regla nueva, Fase 4: **se queda con una persona solo la falla que la medición
contradice** (equipo en línea con la señal en rango) y la que se apagó por
falta de luz. Todo lo demás pasa: LOS, lo que no se pudo medir, y los trabajos
pedidos y obras de red sin exigir confianza. Siguen con una persona los que
nada mide, las órdenes internas, y los que el Supervisor no clasificó.

Con esta regla, de los 27 abiertos pasan 10 y quedan 17.

Y lo que trababa a los sin grupo no era la clasificación: el modelo pedía
herramientas en sus tres vueltas y nunca llegaba a contestar. Se le pide un
cierre sin herramientas, y esas lecturas rotas ya no gastan sus reintentos.
