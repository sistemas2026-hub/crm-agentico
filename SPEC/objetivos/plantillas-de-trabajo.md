# Objetivo · Las plantillas de trabajo se crean y se ajustan desde la plataforma

> Abierto el 13/10/2026. Estado: **construido en la rama
> `objetivo/plantillas-de-trabajo`** (worktree `C:/tmp/dexter-plantillas`),
> **sin desplegar**. Lo que falta para cerrarlo está al final.

## De dónde sale

De probar la app con un técnico real. Al despachar un caso, la pantalla
preguntaba *«con qué plantilla va»* sin decir qué es una plantilla, y al
buscar dónde se crean apareció que **no había ningún lugar**: solo el admin de
Django, escribiendo el esquema en JSON a mano, o un comando semilla. Cada
empresa trabaja distinto, así que eso dejaba a cada ISP esperando una sesión de
código para algo que es suyo (CLAUDE.md §3.3).

## La pregunta que se respondió primero: ¿hace falta?

**La plantilla sí.** Es lo que vuelve verificable una visita: sin ella, cerrar
una orden es un técnico escribiendo «listo». Con ella el cierre exige lo que la
plantilla pide (`verificar_checklist_completo`), y su labor decide qué
cuadrilla la recibe (`campo/reparto.py`).

**Un editor libre de JSON, no.** Y el motivo que se dio primero estaba mal, y
se corrigió al medir:

- **Se dijo:** lo valioso son los campos que el sistema interpreta (potencia,
  serial), y eso es motor.
- **Se midió (13/10/2026):** el backend **no interpreta ningún id concreto** del
  esquema. `serial_ont` y `potencia_rx` no significan nada fuera de la
  plantilla. El serial que vuelve al ISP sale del **inventario**
  (`lazo_isp.py`), y la señal sale del **contexto** de la orden
  (`telemetria.py`). El esquema es casi todo formulario.
- **El riesgo real es el contrato con la app.** Varias cosas que el validador
  acepta, la app y el backend las entienden distinto, y en todas la orden queda
  **cerrada en el teléfono y trabada en el servidor**:

| Se declara | La app | El backend |
|---|---|---|
| booleano obligatorio | sin tocar lo da por completo | `CAMPO_FALTANTE` |
| `min`/`max` en texto | compara el número | compara el largo |
| `entero` | teclado de texto, no valida | `int()` lo rechaza |
| `regex` | lo ignora | lo aplica |
| `fecha` / `foto` / `documento` como campo | texto libre | otro tipo |
| evidencia `firma` | guarda `firma_receptor` y `firma_observaciones`, que nadie declara | rechaza el PATCH entero (400) y la cola no lo reintenta distinto |

Por eso el editor ofrece una **lista cerrada** de lo que los dos lados hacen
igual: texto, número con rango, selección, verificación (seleccion «Hecho / No
aplica», no booleano) y fotos. Ampliarla es cambiar `campo/plantillas.py` y
nada más, el día que la app se alinee.

## Qué tipos de trabajo: medido

`5.298` tickets de WispHub (14/08–13/10/2026), contados por asunto **sin imprimir
los que están fuera del catálogo del proveedor** (traen nombre y barrio del
cliente). La mayoría es administrativo y de cartera; los que generan visita:

```
correctivo de fibra   ~690   sin internet 454 (muchos se resuelven remoto),
                             intermitente 76, visita reiterativa 93, lento 25,
                             fibra partida 13, cable bajo/colgado 17 ...
retiro de equipos     ~380   recoleccion 315, retiro de servicio 58 ...
instalacion           ~220   24 por asunto + ~200 colgadas del cliente 3545
television             ~76   problemas de TV 56, punto adicional 12, TDT 8
traslado               ~76   cambio de domicilio
cambio de equipo       ~30   cambio de router 22, reubicacion de ONU 8
otros                        asuntos sueltos (camara wifi, cableado ...)
```

**Las dos plantillas semilla que existían —instalación y correctivo— no cubrían
el segundo trabajo más frecuente en una casa: retirar equipos.** El catálogo
base quedó en siete. Los números son de una empresa: **ordenan** el catálogo, no
lo recortan.

## Qué se construyó

```
campo/plantillas.py             catalogo base · componer() · leer_definicion()
                                · crear() · publicar()
campo/plantillas_views.py       GET/POST /campo/plantillas/
                                GET/PATCH /campo/plantillas/<id>/
                                POST /campo/plantillas/<id>/publicar/
/supervisor-noc/plantillas      lista, editor, vista previa, catalogo
/supervisor-noc/despacho        el selector dice que es una plantilla
```

Decisiones que costaron pensarlas:

- **Cada cambio publica una versión nueva**, y las órdenes ya creadas conservan
  la suya (la FK es `PROTECT`). La pantalla dice cuántas órdenes abiertas NO
  cambian, para que nadie crea que su cambio ya llegó a la calle.
- **Publicar lo mismo no crea otra versión** (se compara el `schema_hash`).
- **Los ids sobreviven a un cambio de título**: los datos que la app guarda van
  por id, y renombrar «Potencia» no puede dejar huérfano lo anotado ayer.
- **Una plantilla armada a mano con algo de la tabla no se abre en el editor**,
  y publicar encima da 409: adaptarla en silencio cambiaría lo que pide sin que
  nadie lo decida. Se sigue pudiendo usar.
- **Sin migración.** El catálogo vive en código (es de la plataforma, como el
  validador) y lo adoptado es un `WorkType` normal de la empresa.

## Verificado

Todo contra **PostgreSQL real** (contenedor efímero en la red del laboratorio,
base propia `test_icm_plantillas`), el 13/10/2026:

```
pytest test_plantillas_editables + despacho_pantalla + cuadrillas
       + circuito_completo + contrato_del_esquema + plantilla_no_se_publica_rota
                                                   -> 78 pasan, 0 fallan
vitest src/routes/(app)/supervisor-noc/plantillas  -> 10 pasan
svelte-check                                       -> 0 errores en lo tocado
                                                      (los demas, preexistentes)
```

**Siete mutaciones, las siete muertas** (una sobrevivió a la primera tanda y
originó `test_d2`):

```
MUERTA  el checklist viaja como booleano          test_a[correctivo_fibra]
MUERTA  publicar siempre crea version             test_d
MUERTA  los ids salen siempre del titulo          test_e
MUERTA  sin la guarda NO_EDITABLE                 test_f
MUERTA  la v2 se sella sin hash                   test_d2   <- sobrevivia
MUERTA  un texto con min/max se deja editar       test_f2
MUERTA  crear sin exigir rol de gestion           test_h
```

Y una lección de la suite del frontend, anotada en la propia prueba:
`beforeEach(() => mock.mockReset())` **devuelve** el mock, y vitest 4 toma una
función devuelta por `beforeEach` como limpieza y la llama al final. Las
pruebas de error quedaban en rojo con todas sus afirmaciones pasadas. Costó
cinco hipótesis falsas.

## Lo que queda afuera, dicho

1. **Los seis desacuerdos app ↔ backend de la tabla no se arreglaron.** El
   editor los esquiva; las plantillas armadas a mano siguen expuestas. El de la
   **firma** puede estar vivo hoy si alguna plantilla de producción la declara:
   **no se pudo medir desde acá**. Es un objetivo propio, de la app.
2. **El seguimiento por momento** (`esquema.seguimiento`) no se edita: una
   plantilla que lo tenga queda «no editable», con ese motivo.
3. **No se probó en la pantalla real** ni con la app en un teléfono.
4. **No hay `auditor-independiente`** sobre este bloque todavía.
