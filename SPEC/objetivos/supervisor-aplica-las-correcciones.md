# Objetivo · El Supervisor aplica las correcciones del usuario a su diagnóstico

> Abierto el 18/10/2026. Estado (19/10/2026): **tandas 1, 3 y 4 desplegadas**
> (`5bbf9fb8`); **tanda 2, partes 1 y 2 (nivel de la OLT y corte de red)
> desplegadas** (`179610c4`, 18:08) **con su lista blanca cargada** (config
> v178); la parte 3 (banda de la ONU) espera que el usuario corrija el
> registro en SmartOLT.

## Qué significa terminado

Las 9 reglas que salieron de las correcciones del usuario
(`SPEC/objetivos/correcciones-al-diagnostico.md`, casos 1 a 4) deciden en el
paso a Despacho, la lectura del ticket y la medición; los pendientes mal
diagnosticados se vuelven a leer con ellas; y antes de encenderlas el usuario
ve, en sombra, qué casos pasarían y por qué.

## Decisiones

| Fecha | Decisión | Por qué |
|---|---|---|
| 18/10 | **Tolerancia del doble diagnóstico: 1 dB** | Propuesta del asistente y "sí arranca" del usuario. El ejemplo del usuario: 0.00 y 0.19 dB de diferencia. **Quedó como constante del código y no como configuración** (19/10): solo informa, no decide nada, y es una equivalencia de medición, no un dato que varíe por empresa. Si un día decide, pasa a configuración |
| 18/10 | **Plan "alto" para una C-Data de una banda: desde 100 Mb**, como configuración | Ídem. El caso 1 era un plan de 100. **Va con la tanda 2** (la banda de cada tipo de ONU), que está bloqueada |
| 18/10 | **El límite de la guía es -25 dBm** (el del motor, `SENAL_MINIMA_DBM`) | Confirmado por el usuario |
| 18/10 | **El historial de 24 h se arma con las mediciones del propio Supervisor** | `verificador-de-api`: SmartOLT no da historial numérico de la señal, solo una imagen (medido el 13/10). Leer la imagen pide visión, un tercero nuevo (CLAUDE.md §5) |
| 18/10 | **El modelo de la ONU informa, no decide** | `verificador-de-api`: 355 equipos registrados `CDATA` son físicamente iguales a los `CDATA-CATV` (medido el 18/08). La banda de cada tipo es dato de la empresa (configuración) |
| 18/10 | **Las reglas que hacen pasar más casos van detrás de su propia tarea delegada, primero en sombra** | Lo que se le dijo al usuario: "antes de encenderlas te muestro cuáles pasarían y por qué". Mismo patrón que el paso a Despacho |
| 19/10 | **La tarea es `pasar_a_despacho_con_las_correcciones`, propia y de nivel 3** | Encenderla no enciende el paso de rebote: hacen falta las dos y el nivel. Sin ella, cada propuesta que se queda y pasaría con las correcciones lo dice en su motivo ("Con las correcciones del usuario pasaría: …"), el log cuenta por cuál, y `informe_de_pendientes` tiene la columna "con correcciones" |
| 19/10 | **Re-medir lo que frena una falla (en rango, o caída sin energía) como máximo dos veces, a 8 h una de otra** | Con la original son tres puntos en un día: cubren la noche y el día, que es lo que hace falta para ver la oscilación del caso 2. La primera versión re-medía cada 3 h mientras la propuesta viviera, y `auditor-independiente` señaló que eso es polling de `get_onu_full_status_info`, que SmartOLT autoriza para investigar un reclamo y prohíbe en polling (skill smartolt-api). Cuenta también la re-medición que no pudo medir (`test_e2`) |
| 19/10 | **La re-medición nunca reemplaza a la medición**: va al historial, y la que decide se elige al decidir (`la_medicion_vigente`): con la tarea, la más reciente; sin ella, la de siempre | Sin esto, re-medir ya habría hecho pasar casos por la Fase 4 antes de que el usuario viera la sombra. La primera versión la hacía reemplazar con la tarea delegada, y `auditor-de-frontera` midió el costo: quitada la tarea, la pieza nueva seguía decidiendo (`test_g`) |
| 19/10 | **Una re-medición que no midió no entra a la serie ni borra la medición** | Sin esto, dos vueltas con el proveedor caído convertían una falla con la señal en rango en "no se pudo medir en dos vueltas", que pasa. Encontrado al diseñar, con su prueba (`test_h`) |
| 19/10 | **Una relectura no saca a una falla frenada de la regla de la medición sin la tarea** | `auditor-de-frontera`: la relectura por versión vuelve a leer justo esas fallas, y si el modelo cambiaba el grupo a trabajo pedido u obra, el caso pasaba por la Fase 4 en la misma vuelta, sin la tarea y sin sombra. Ahora es una corrección más (`relectura`): decide solo con la tarea y se cuenta en sombra (`test_y`) |
| 19/10 | **Las tres líneas nuevas de las instrucciones del modelo van solo con la tarea**; las dos claves nuevas se piden siempre | Ídem: le cambian al modelo la forma de leer y pueden mover el grupo de un ticket nuevo. Las claves sí van siempre, porque la sombra las necesita, y su ayuda dice que no cambian el grupo (`test_t3`) |
| 19/10 | **La acción autorizada cuenta solo si el ticket lo escribió una cuenta con nombre de la empresa** (`humano_verificado`) | `auditor-de-frontera`: un ticket que creó Dexter desde WhatsApp, o que llegó por la cuenta compartida, puede traer "se autoriza" escrito por el propio cliente. **Contrapartida**: si la empresa crea tickets con la cuenta compartida, esos quedan afuera; la sombra lo va a mostrar (`test_b3`) |
| 19/10 | **Delegar la tarea de las correcciones avisa si falta la del paso** | `auditor-de-frontera`: contestaba "ya puede actuar" sin el paso delegado (`test_t2`) |
| 19/10 | **El descarte de un valor inventado cita solo una palabra suelta** | `revisor-de-pii`: si el modelo contesta una clave con una frase, esa frase podía traer el nombre o la dirección del cliente hasta la salida de `informe_de_pendientes`. Una frase se anota por su largo (`test_p`) |
| 19/10 | **La corrección 1 cambia la tabla de fábrica**: trabajo pedido → correctivo, y una fila nueva `instalacion_nueva` → instalación | Corrige la decisión del 17/10 ("trabajo pedido → instalación") con el caso 1 del usuario. **Si la empresa ya guardó su tabla en Cuadrillas, manda la suya**: hay que cambiar ahí "Trabajo pedido" a correctivo |
| 19/10 | **Cliente nuevo = el ticket cuelga del cliente de instalaciones del ISP** (`id_servicio_instalaciones`) | El discriminador medido (220 de 220) que ya usan la pantalla de Despacho y el clasificador. Por el texto solo, no: "instalación" aparece también en un punto de TV |
| 19/10 | **Una instalación nueva no tiene barrio** | Su ficha es la del cliente ficticio, y todas caerían en el mismo barrio. Se guarda sin barrio y se cuenta aparte (`instalaciones_sin_barrio`). Hipótesis a confirmar: los 14 casos de "OFICINA" del 18/10 son eso |
| 19/10 | **La medición después del arreglo informa, no decide** | Decisión del asistente: queda en la propuesta (si la señal quedó en rango o no), sin reabrir el caso ni tocar la orden. Volverla una alerta es otro paso |
| 19/10 | **…con tres intentos como máximo, lo nunca intentado primero, y sin medir un cambio de equipo** | `auditor-independiente`: lo que no se podía medir se pedía cada hora durante dos días (polling), y cinco de esas ocupaban todas las plazas de la vuelta. Si la lectura trae una acción autorizada (cambio de equipo o de router), lo más probable es que el ISP siga con el serial viejo (`test_c2`, `test_c3`, `test_c4`) |
| 19/10 | **Las instalaciones nuevas sin barrio se suman a las zonas de las cuadrillas de instalación** | `auditor-independiente`, ALTA: sin barrio no entraban en ninguna zona y, con el trabajo pedido de clientes existentes como correctivo, ningún caso pedía instalación. La cuadrilla de instalación salía de correctivo y sus órdenes quedaban sin cuadrilla en el reparto. No se sabe en qué zona caerá cada una, pero sí que la hará una cuadrilla de esa labor (`test_u2`) |
| 19/10 | **Al delegar la tarea, se relee una vez más con las instrucciones de las correcciones** lo que se leyó en sombra | `auditor-independiente`: desplegado en sombra, las fallas frenadas se releían con las claves nuevas pero sin las instrucciones, y al delegar ya no se volvían a leer. Cada lectura guarda con qué instrucciones se hizo (`test_r3`) |
| 19/10 | **La relectura filtra antes de cortar** en las 60 pendientes | `auditor-independiente`: el tope cortaba las 60 más viejas y después filtraba; con más pendientes, las de atrás no se releían nunca. Limitación anterior a este bloque (`test_r4`) |
| 19/10 | **"Sí" y "SI" cuentan como "si" en las dos claves nuevas; en el grupo, no** | `auditor-independiente`: un "Sí" se descartaba y la lectura, ya en versión 2, no se repetía. En el grupo se deja exacto a propósito: aceptar "Obra_de_red" cambiaría lo que pasa por la Fase 4 (`test_p`) |
| 19/10 | **Tanda 2 · el nivel que recibe la OLT entra al doble diagnóstico** (`senal_olt_dbm`) | Ya venía en la misma respuesta de SmartOLT y se descartaba. Solo informa. Llega cuando la lista blanca de `supervisor_noc` en `tenant_config` lo declare: se carga después del deploy, con `editor._editar` |
| 19/10 | **Tanda 2 · el corte de red: cada caso pasa marcado con su puerto** | Decidido por el usuario entre tres opciones: «cada caso marcado con la misma marca de puerto; el despachador arma una sola orden». Las otras dos eran una propuesta por puerto (hoy no llega a Despacho, y la orden apuntaría a la caja) o retener y avisar |
| 19/10 | **Tanda 2 · es corte de red desde 2 ONU del mismo puerto, y solo cuenta LOS** | Decidido por el usuario. 2 es el umbral que ya usa el resto del sistema para una falla agrupada; un «Power fail» es la luz de la casa, no la fibra |
| 19/10 | **Tanda 2 · la banda de la ONU sale del tipo registrado en SmartOLT, después de que el usuario corrija los 355 mal registrados** | Decidido por el usuario. Hasta entonces la parte 3 espera |
| 19/10 | **Tanda 2 · los vecinos del puerto se cuentan en el motor, solo para una caída por LOS**, con `get_all_onus_details` filtrado y `fields=status,last_status_change,sn` | Verificado en vivo ese día (script del verificador, corrido por el usuario): los filtros por olt/placa/puerto y `status=los` funcionan, y `fields` devuelve solo lo pedido. Sin `fields`, cada fila trae nombre, dirección y contacto del cliente. El serial solo sirve para encontrar la fila propia y no sale del motor. "A la vez" es la ventana de 20 minutos de `incidentes.py`, contra la caída del mismo equipo en la misma lista (mismo reloj). Cuesta dos llamadas más, solo en una caída por LOS; el cupo medido ese día es de 500 por hora |
| 19/10 | **El umbral del corte de red es por empresa**: `ConfiguracionDeReparto.onus_para_corte_de_red`, 2 de fábrica, editable en Cuadrillas | CLAUDE.md §3.3: decide cómo se marca un caso, y en otro ISP puede ser otro número |
| 19/10 | **La marca del corte de red va siempre, sin la tarea de las correcciones** | No cambia si el caso pasa: una caída por LOS ya pasaba por la Fase 4. Cambia el motivo que ve el despachador ("CORTE DE RED: N equipos del puerto P… una sola orden") y que la demanda de la jornada cuente el corte una vez, como obra de red. Se enciende de hecho cuando se carga la lista blanca en `tenant_config` |
| 19/10 | **"-23.01 / -23.38 dBm" se leen los dos niveles** | `auditor-independiente`: así escribe el ISP el de la ONU y el de la OLT, y se perdía el primero (`test_l`) |
| 19/10 | **La relectura por versión solo toca lo que la lectura nueva puede mover** (falla con una medición que frena, lectura de versión 1), con una lectura extra de tope | Releer todo gastaría el tope de la vuelta en tickets que la lectura nueva no cambia |
| 19/10 | **Una respuesta rota del modelo no pisa una lectura buena; en un ticket que nunca se leyó, se anota igual** | El 95531 (producción, ese día) quedó "sin grupo" porque una relectura rota pisó su lectura. Y `auditor-independiente`: no anotarla nunca dejaba al ticket nunca leído en la cola para siempre. Con lectura buena se deja el rastro y vale la anterior (`test_r5`); sin ella se anota con el grupo vacío y corta el tope absoluto, 6 pedidas al modelo (`test_r6`) |
| 19/10 | **El corte de red se cuenta una vez por PUERTO, no por zona, y el que ya tiene su orden no pide otra obra** | `auditor-independiente`: un puerto que alimenta dos zonas contaba dos obras, y el corte cuya orden ya armó el despachador (lo que pide la marca) contaba otra con los casos que quedaban. Los cortes con orden se juntan antes de recorrer la cola, así no depende del orden (`test_u4`, `test_u5`) |
| 19/10 | **La marca del corte llega a la ficha de Despacho aunque el caso lo haya aceptado una persona** (`lectura.corte_de_red`) | `auditor-independiente`: viajaba solo en "por qué pasó solo", vacío si aceptó una persona, y el despachador armaba una orden por cliente mientras la jornada contaba un solo trabajo. Si ya está en el motivo, no se repite (`test_h`, `test_h2`) |
| 19/10 | **Con exactamente dos niveles en el ticket se comparan por posición: el primero con la ONU, el segundo con la OLT**. Con tres o más, cada nivel medido toma el reportado más cercano libre | `auditor-independiente`: por cercanía, ONU -29.5 y OLT -28.3 contra "-28.24 / -29.59" se cruzaban y daban "coincide" dos veces. Con tres o más el texto no dice cuál es el par (`test_m4`) |
| 19/10 | **Los vecinos: 5 s por consulta, hasta 3 páginas, el serial también en hexadecimal, y un conteo en cero dice por qué en el log** | `auditor-independiente`: el CRM le da 25 s a todo el diagnóstico y `get_onu_full_status_info` ya usa ~10; 68 equipos de Rapilink solo responden con el serial en hexadecimal; un puerto puede venir en más de una página |
| 19/10 | **El conteo de vecinos corre en los cinco llamadores de `diagnosticar_servicio`, no solo en el Supervisor** — costo aceptado | Solo ante una caída por LOS: dos a cuatro llamadas más, 5 s cada una, contra un cupo de 500 por hora. Hacerlo opcional por llamador exigiría un campo de configuración nuevo, y hoy el número no lo pide |

## Tandas

| Tanda | Reglas | Qué necesita | Estado (19/10) |
|---|---|---|---|
| 1 | Labor del trabajo pedido según cliente nuevo o existente; acción ya autorizada = trabajo pedido sin objetar; energía descartada por el ticket = falla de fibra; doble diagnóstico con el nivel del ticket; la medición en rango de una falla se repite y se guarda su historial | Nada nuevo: código del Supervisor y la lectura | **Desplegada** (`5bbf9fb8`) |
| 2 | Parte 1: el nivel que recibe la OLT en el doble diagnóstico. Parte 2: ONU del mismo puerto en LOS = un solo trabajo de red. Parte 3: la banda de cada tipo de ONU | Partes 1 y 2: el motor (`diagnosticar_servicio`) y, después del deploy, la lista blanca de `supervisor_noc` en `tenant_config`. Parte 3: el registro corregido en SmartOLT | **Partes 1 y 2 desplegadas** (`179610c4`) **y su lista blanca cargada** (v178). **Parte 3 espera** (ver Bloqueos) |
| 3 | Volver a medir cuando el técnico reporta el arreglo | El cierre de la orden en campo | **Desplegada** (`5bbf9fb8`, `verificacion_de_arreglos`) |
| 4 | Volver a leer los pendientes con las instrucciones nuevas, con tope por vuelta | La versión de las instrucciones en cada lectura | **Desplegada** (`5bbf9fb8`, `VERSION_DE_LA_LECTURA = 2`) |

## Criterios de aceptación

| # | Evidencia | Cómo se comprueba |
|---|---|---|
| 1 | Cada regla de la tanda 1 con su prueba en Postgres real, con el rol de pruebas y con uno que el RLS ata | Salida pegada |
| 2 | Mutaciones: cada regla tiene una que la invierte y muere | Salida pegada |
| 3 | La sombra: sin la tarea delegada, el log dice cuántos pasarían con las reglas nuevas y por qué, sin pasar ninguno | Prueba de ciclo |
| 4 | Regresión de `campo` y `operaciones` con los mismos rojos previos de origin | Salida pegada |
| 5 | `auditor-de-frontera`, `revisor-de-pii` y `auditor-independiente` corrieron y lo que encontraron está resuelto o anotado | Informe |

## Restricciones

- **NO push** sin el "haz el push" del usuario: push es deploy a producción.
- **NO escribir `tenant_config`** ni cargar config a producción.
- Stage por rutas explícitas. No amend.
- **No leer `.env`** ni usar credenciales de producción desde la sesión.

## Bloqueos

- ~~**Tanda 2, partes 1 y 2, después del deploy**: la lista blanca~~ —
  **cargada el 19/10/2026** por el usuario, con `editor._editar` en el
  contenedor del motor: config v178. `diferencias_config.py`: 0 en la
  dirección peligrosa. Humo con `--base`: 9/10, cae solo el caso aceptado
  como línea base ("una venta a un prospecto no verifica identidad").
- **Tanda 2, una llamada de confirmación**: que `fields=status,
  last_status_change,sn` devuelva el serial (sin él, la caída propia no se
  ubica y el corte no se marca nunca, con aviso en el log). Script de una
  sola llamada GET, que corre el usuario: `scratchpad/scripts/verificar_fields_sn.py`.
- **Tanda 2, la banda de cada tipo de ONU**: 355 equipos registrados `CDATA`
  son físicamente iguales a los `CDATA-CATV`. El usuario corrige el registro en
  SmartOLT (19/10); después el Supervisor usa el tipo registrado, con el plan
  "alto" (100 Mb) como configuración.
- **Tanda 2, el corte del puerto**: construido (casos marcados, desde 2,
  solo LOS). Los filtros por OLT, placa, puerto y `status=los` se verificaron
  en vivo el 19/10 con el script del verificador, corrido por el usuario.

## Riesgos que quedan, dichos

- **La tabla de labores puede no cambiar en producción**: el formulario de
  Cuadrillas manda la tabla entera con cualquier guardado del reparto, así
  que si alguien guardó ese formulario después del 17/10 quedó persistido
  "trabajo pedido → instalación" y pisa la de fábrica. Se corrige a mano en
  Cuadrillas → "De qué labor es cada caso".
- **El cliente nuevo se reconoce solo si `WISPHUB_ID_SERVICIO_INSTALACIONES`
  está en `tenant_config`** (el YAML dice 3545). Si la base no lo tiene, no se
  detecta ninguna instalación nueva y no hay error. Se mira con
  `py -3.13 cli/diferencias_config.py rapilink`.
- **La acción autorizada depende de quién escribió el ticket**: si la empresa
  crea tickets con la cuenta compartida, esos quedan afuera de la corrección
  1. La sombra lo va a mostrar.
- **Una sola lectura por debajo de -25 dBm confirma una intermitencia**: es
  el mismo umbral que ya usa la Fase 4 para pasar una señal fuera de rango.
- **Las instrucciones nuevas no se midieron contra el modelo real**: no hay
  set dorado de la lectura del Supervisor (`cli/evaluar.py` mide el motor, no
  este camino). La sombra es la medición.
- **Dos lecturas sueltas de la ONU en el mismo ticket se leen como el par
  ONU / OLT**: con exactamente dos niveles se compara por posición. El doble
  diagnóstico informa y no decide.
- **Si el proveedor deja de devolver el serial con `fields`, el corte no se
  marca nunca**: no hay error, solo la línea del log "las filas del puerto no
  traen el serial".

## Bitácora

| Fecha | Qué avanzó | Qué falta | Commit |
|---|---|---|---|
| 18/10/2026 | Ficha abierta. Informe de `verificador-de-api` sobre SmartOLT | Todo | — |
| 19/10/2026 | Auditoría independiente: re-mediciones y verificación acotadas (no son polling), las instalaciones sin barrio para las cuadrillas de instalación, relectura al delegar, filtrar antes de cortar, "Sí" con tilde, "-a / -b dBm". Ver "Riesgos que quedan" | Push (lo decide el usuario) | `5bbf9fb8`, desplegado |
| 19/10/2026 | Auditorías de frontera y de PII: la re-medición nunca reemplaza, la relectura que mueve el grupo es una corrección más, las instrucciones nuevas y la acción autorizada atadas a la tarea y al autor, el aviso al delegar, el descarte sin frases | Auditoría independiente | `5bbf9fb8`, desplegado |
| 19/10/2026 | Tandas 1, 3 y 4 construidas: las claves nuevas de la lectura y su versión, las tres reglas detrás de la tarea nueva con su sombra, la re-medición cada 3 h con historial, el doble diagnóstico, la labor por cliente nuevo o existente, la medición después del arreglo y la columna del informe. Pruebas en Postgres con los dos roles, mutaciones, regresión, ruff, svelte-check y build | Tanda 2. Que el usuario mire la sombra antes de delegar la tarea | `5bbf9fb8`, desplegado |
| 19/10/2026 | Sombra observada en producción: el 95394 pasaría por la re-medición (-22.92 de noche, -26.38 de día). Una respuesta rota dejó al 95531 "sin grupo": ya no la pisa, y el informe muestra la re-medición y la versión de cada lectura | Delegar la tarea (lo decide el usuario) | `4f559af2` (rebaseado; era `0d328eb4`) |
| 19/10/2026 | Tanda 2, partes 1 y 2: el nivel de la OLT en el doble diagnóstico; el corte de red marcado con su puerto, umbral por empresa en Cuadrillas, contado una vez en la jornada y visible en la ficha de Despacho. Auditorías de frontera, PII e independiente, con lo que encontraron resuelto. Pruebas del motor, 734 del backend en Postgres, 71 de vitest, mutaciones (motor 8 de 8, backend 16 de 16), ruff y svelte-check sin hallazgos nuevos, build | Push (lo decide el usuario); cargar la lista blanca; la llamada de confirmación del serial; parte 3 | `8bedc9dd`, `a47b96ef`, `180c138f`, `179610c4` (los hashes que quedaron en origin después de rebasar) |
| 19/10/2026 | Tanda 2 desplegada a las 18:08 (el sello del frontend cambió después del push), con los mismos 22 rojos previos en la regresión de `campo`, `operaciones` y `cases`. Lista blanca cargada (v178), `diferencias_config` limpio y humo `--base` 9/10 | La llamada de confirmación del serial; parte 3 | `179610c4` |
