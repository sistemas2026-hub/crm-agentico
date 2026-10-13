# Auditoría · Custodia de materiales (13/10/2026)

Las tres pasadas que la ficha `objetivos/custodia-de-materiales.md` tenía
pendientes desde el 28/09: la adversarial (F14), la de frontera (F12) y la de
PII. Se corrieron como **subagentes de solo lectura** siguiendo el procedimiento
de `.claude/agents/{auditor-independiente,auditor-de-frontera,revisor-de-pii}.md`,
porque esos agentes siguen sin cargarse como tipo en la sesión. Es la misma
pasada independiente, dicha con su forma real.

Sobre el código **en producción** (`725a503`), leído; las pruebas del módulo
contra PostgreSQL real: `pytest campo/` → **925 pasan, 0 fallan** sobre
producción + plantillas.

Dos pasadas independientes llegaron al **mismo** hueco por caminos distintos
(el consumo de una serie que no está en la custodia): una desde el inventario,
otra desde el efecto en el ISP. Cuando coinciden así, el hallazgo no es una
opinión.

## Arreglado, con su prueba (rama `objetivo/plantillas-de-trabajo`)

| # | Hallazgo | Severidad | Arreglo | Prueba |
|---|---|---|---|---|
| A | El teléfono aceptaba los siete tipos del libro: un `ajuste` de +50 a la custodia propia, sin orden ni rol, entraba ACEPTADO; con serie, movía el índice de cualquier aparato a su nombre | ALTA | `MovimientoEntradaSerializer.tipo` acepta solo `consumo` y `devolucion`, que es lo único que la app manda (medido en el código Dart) | `test_custodia_auditoria_13_10::test_a*` |
| B | Un consumo de una serie que el sistema sabe que está en bodega o con otro técnico entraba ACEPTADO (se miraba el saldo por material, no por serie), movía el índice y, con el lazo al ISP encendido, mandaba ese serial a la ficha del cliente — y un reinicio aprobado después apagaría el equipo de otra casa | ALTA | `clasificar()` lo deja en **CONFLICTO** con el motivo de dónde está. Se GUARDA igual: F12 dice que ningún consumo ocurrido se rechaza. Una serie nunca vista sigue entrando | `test_b`, `test_b2`, `test_b3`, `test_b4` |
| C | Una serie instalada (índice en «ninguna ubicación» tras un consumo) se despachaba como libre | MEDIA | `_comprobar_serie_libre` rechaza si el último movimiento es un consumo aceptado; el reuso legítimo es registrar su entrada primero | `test_c`, `test_c2` |
| P1 | El motivo libre de un pedido de material salía sin tapar al canal de avisos de bodega | BAJA-MEDIA | pasa por `operaciones.lectura_de_ticket.tapar` (la misma de los tickets) | `test_pedido_de_material::test_e2b` |
| D1 | La devolución por la app salía de la custodia hacia «ninguna» y la recepción en la web la volvía a restar de la custodia: sin recepción el material desaparecía; con recepción se restaba dos veces y la jornada no cerraba | ALTA | `recibir_devolucion` consume primero lo que el técnico declaró (entra a bodega desde «ninguna») y solo lo no declarado sale de la custodia; las sumas de «devuelto» no cuentan esa firma. Un reintento con referencia devuelve lo registrado en vez de un 500. **Los datos que ya existen en producción NO se corrigen acá** | `test_d1*` |
| D2 | El rol `BODEGA` no se podía asignar | MEDIA | agregado a `ROLES` (migración `common/0044`) y a la pantalla de equipo; no es admin | `test_d2` |
| D3 | El aviso del serial al ISP salía aunque el técnico no estuviera asignado a la orden | ALTA si se enciende | `lazo_isp.intentar_avisar` exige la asignación; el consumo entra igual | `test_d3` |

Verificado contra PostgreSQL real el 13/10/2026:

```
pytest campo/  (rama con los arreglos)          938 pasan, 0 fallan
                                                (925 previos + 13 nuevos)
mutaciones, una por arreglo:
  MUERTA  el telefono acepta todos los tipos    test_a[ajuste]
  MUERTA  no se mira la custodia de la serie    test_b
  MUERTA  instalado cuenta como libre           test_c
  MUERTA  se frena tambien la serie nunca vista por un 500, no por una
                                                afirmacion: la detecta, pero
                                                por el camino menos claro
  MUERTA  el motivo del pedido sin tapar        test_e2b
  -- y en la segunda tanda, la de D1/D2/D3 --
  MUERTA  la recepcion no consume lo declarado  test_d1
  MUERTA  lo declarado recibido cuenta doble    test_d1   (la copia gemela en
                                                cierre_jornada._movido no se
                                                muto aparte)
  MUERTA  el reintento no reconoce lo escrito   test_d1f
  MUERTA  el aviso no mira la asignacion        test_d3
  MUERTA  BODEGA fuera de ROLES                 test_d2
```

## Abierto, con su motivo

| # | Hallazgo | Severidad | Por qué no se arregló hoy |
|---|---|---|---|
| D3b | El lazo `sn_onu` no se reintenta nunca (un FALLO queda así para siempre), reporta un bloqueo de la frontera como «fallo HTTP 502» igual que una caída, y toma el tenant del ENTORNO y no de la empresa del movimiento | MEDIA | La asignación y la custodia de la serie ya se exigen (D3, B), que era el riesgo de escribirle al cliente equivocado. Lo que queda es confiabilidad y multi-empresa: con un solo tenant por instalación no muerde, con dos sí. Conviene resolverlo antes de encender `CAMPO_AVISAR_SN_ONU_AL_ISP` |
| D4 | La reconciliación del índice (F5) solo la llama la vista de una serie; no hay barrido sobre producción, y compara contra el libro, no contra la existencia | MEDIA | Construido y sin llamador: hace falta decidir cada cuánto y qué hacer con lo que encuentre |
| D5 | El cierre de jornada calcula la existencia con otra aritmética (ignora ajustes), y la guarda de «una sola verdad» lo tiene en su lista de permitidos | MEDIA | Unificarlo con `existencia()` cambia lo que ve el técnico al cerrar; necesita su propia prueba de punta a punta |
| D6 | Sin acta, un doble envío del despacho despacha dos veces; con un acta repetida, se traga un despacho distinto | MEDIA | Hace falta decidir la clave del hecho del despacho (hoy es el acta, opcional) |
| D7 | `vencer_reservas` no tiene llamador: una reserva con plazo nunca vence | MEDIA | Agregarla al reloj es una decisión de operación (CLAUDE.md §8) |
| D8 | `series_sin_devolver` cuenta cualquier devolución histórica, no solo las posteriores al último despacho | MEDIA | — |
| D9 | Entradas, devoluciones y conteos aceptan cantidades cero o negativas | BAJA | — |
| P2 | `motivo_tecnico` viaja en el JSON de Reportes aunque no se dibuja | BAJA | — |
| P3 | `/interno/herramienta` devuelve la respuesta cruda de WispHub al CRM sin política de rol; hoy se descarta sin leerla | BAJA, latente | Arreglo barato (`?rol=`) pero toca `nucleo/canales/api.py` |

## Lo que se atacó y aguantó

- **Aislamiento por empresa:** toda búsqueda de ubicación, material, persona,
  orden, proveedor, conteo, reserva y plantilla filtra por `org`.
- **Exposición de datos de cliente:** ninguna respuesta ni pantalla de
  inventario saca un campo de cliente de la orden; solo su número o su UUID.
- **Admin, comandos y tareas:** no escriben inventario. Las escrituras tienen
  seis llamadores, todos vistas con permiso.
- **La frontera del motor:** el lazo pasa por `frontera.autonoma` (interruptor,
  techo, autonomía 2, autorización) y su clave idempotente es estable.
