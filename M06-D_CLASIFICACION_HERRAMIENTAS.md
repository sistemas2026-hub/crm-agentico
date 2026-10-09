# M06-D — Clasificación de autonomía de las 69 herramientas

Fecha: 21/09/2026 · **Es una propuesta para revisión: no se aplicó al runtime.**
Sin cambios en YAML, herramientas, rutas, techo ni autorizaciones. Sin commit,
push, PR ni deploy.

## Resumen

| Nivel | Cantidad | Qué son |
|---|---|---|
| **0 — observar** | **41** | Todas las lecturas salvo `sondear_api` |
| **1 — recomendar** | **3** | Las R1: dejan un pedido o una propuesta para que decida una persona |
| **2 — coordinar** | **7** | Escrituras en el CRM propio con reversibilidad **evidenciada**, sin efecto visible al cliente |
| **3 — ejecutar autorizado** | **14** | 8 con aprobación humana (las 5 R3/R4 y 3 de tickets), 5 escrituras reversibles en el sistema del proveedor, y `cancelar_solicitud_servicio`, que es irreversible |
| **INDETERMINADA** | **4** | Falta un dato decisivo (ver abajo) |

- La fuente de verdad es **`M06-D_MATRIZ_AUTONOMIA.yaml`**, que el runtime no
  lee. La tabla de este informe se generó desde ese archivo.
- La integridad la comprueba **`tests/test_m06d_matriz_autonomia.py`**: 28
  comprobaciones contra el catálogo real y la clasificación de M10-A.
- **La clasificación efectiva no cambió.** Ninguna herramienta declara
  `nivel_autonomia`, así que el runtime sigue exigiendo 0 a las lecturas y 2 a
  las escrituras.

## Criterio

Se aplica en orden, y la primera regla que corresponde decide. Cada nivel 3
cita en su justificación la regla que lo decidió; la prueba falla si alguno no
la cita.

| Regla | Condición | Nivel |
|---|---|---|
| **C1** | Lectura (`solo_lectura=true`) | 0. INDETERMINADA si el catálogo no fija su destino |
| **C2** | Escritura interna que solo deja un pedido o una propuesta para una persona | 1 |
| **C3** | Escritura con `aprobacion_humana` declarada | 3, y **la aprobación se mantiene** (igual que R3/R4) |
| **C4a** | Sin aprobación, en el CRM propio, reversible o inerte **con evidencia**, sin efecto visible al cliente ni recursos comprometidos | 2 |
| **C4b** | Sin aprobación, en el sistema del proveedor o comprometiendo recursos, reversible **con evidencia** | 3 |
| **C4c** | Sin aprobación, con irreversibilidad **evidenciada** | 3, y se recomienda un gate |
| **C4d** | Sin aprobación, sin evidencia de reversibilidad o de visibilidad al cliente | INDETERMINADA |

**Qué cuenta como evidencia:** un campo del catálogo, una línea de código citada
como `archivo:línea` (la prueba verifica que exista) o un hecho ya medido y
documentado. Que M10-A diga que R2 "se deshace con otra operación de registro"
es una afirmación de diseño: **por sí sola no cuenta**. Por eso, de las 16 R2 sin
aprobación, solo 7 llegan a nivel 2.

## Herramientas indeterminadas

| Herramienta | Qué falta para clasificarla |
|---|---|
| `sondear_api` | Una lista cerrada de hosts permitidos, o evidencia de que los destinos son de solo lectura. Hoy el modelo o el ADMIN eligen la URL, y un GET no es inocuo por definición: hay APIs que modifican por GET y la URL puede sacar datos hacia afuera |
| `responder_ticket_operativo` | Si WispHub **notifica al cliente** cuando se agrega una respuesta, y si una respuesta **se puede eliminar**. En el catálogo no hay forma de retirarla, y el flag `do_not_notify_client` solo está documentado en otra instancia, sin verificar aquí |
| `cerrar_ticket_operativo` | Lo mismo sobre la respuesta que deja al cerrar. El cierre en sí es reversible, porque `responder_ticket` reabre |
| `completar_ticket_instalacion` | Si WispHub permite **retirar un adjunto** de un ticket por API. Las fechas se corrigen con otro PATCH, pero el adjunto es la orden, que tiene datos personales |

Las cuatro se resuelven **midiendo contra la API real**, que es algo que este
bloque no puede hacer: lo prohíbe. Hasta entonces, lo seguro es tratarlas como
**no aptas para autonomía**.

## Riesgos encontrados

1. **`cancelar_solicitud_servicio` es irreversible y no tiene aprobación.**
   `CANCELADA` es un estado final (`solicitudes/gestion.py:556`; ninguna
   transición sale de ahí) y, además, **cierra en cascada el ticket en
   WispHub** (`solicitudes/entrega.py:275`). Hoy la protegen la verificación del
   nombre completo y la cadena autónoma, pero no tiene un gate propio. Se
   clasifica 3 por la regla C4c.
2. **`ping_cliente` figura como lectura pero es una sonda activa**: un `POST` que
   dispara un ping al equipo del cliente. No cambia estado, pero es una acción y
   no una lectura pasiva. Queda en 0 y se anota.
3. **Las visitas técnicas comprometen personas.** `agendar_visita_tecnica` y
   `agendar_visita_internet` son reversibles solo **mientras la visita no
   ocurra**; después, el costo del técnico no se deshace. Quedan en 3 y no en 2.
4. **Las R1 tienen efecto externo indirecto.** `registrar_pedido_wifi` y
   `reportar_comprobante_pago` no salen a ningún tercero, pero al completarse
   **escalan**, y la escalada crea caso y ticket por código. Su nivel 1 es
   correcto para la herramienta; la escalada tiene sus propias barreras.
5. **Costo y límites del proveedor en lecturas:** `informe_materiales` (unas 2.700
   llamadas por mes) y `diagnosticar_falla_ont` (unos 10 s por llamada; el
   proveedor prohíbe usarla en polling o en lote). Nivel 0 no significa "sin
   costo".
6. **Datos sensibles en lecturas:** clientes, facturas y equipos conectados. El
   nivel no gobierna qué datos se muestran; eso lo hacen los roles y las listas
   blancas por rol.

## Discrepancias con la clasificación R1–R4

| Herramienta | Clase M10-A | Lo que muestra la evidencia |
|---|---|---|
| `cancelar_solicitud_servicio` | R2 ("se deshace con otra operación") | **Irreversible**, con efecto en cascada en WispHub. Se comporta como de alto impacto |
| `responder_ticket_operativo`, `cerrar_ticket_operativo`, `completar_ticket_instalacion` | R2 | Reversibilidad **no demostrada** (respuestas y adjuntos que no se pueden retirar con el catálogo) |
| `agendar_visita_tecnica`, `agendar_visita_internet` | R2 | Comprometen recursos humanos; reversibles solo dentro de una ventana de tiempo |
| `ping_cliente` | R0 | Sonda activa (POST), no lectura pasiva |
| `sondear_api` | R0 | Destino no fijado: su efecto no está determinado |
| `registrar_pedido_wifi`, `reportar_comprobante_pago` | R1 ("sin tercero") | Cierto para la herramienta, pero su escalada crea registros externos |

**No se cambió ninguna clase.** Son hallazgos para decidir, no correcciones.

## Recomendaciones para el siguiente bloque

1. **Resolver las 4 indeterminadas midiendo**, con autorización expresa y sobre
   el cliente de laboratorio que indiques: notificación y borrado de respuestas
   en WispHub, y adjuntos. Para `sondear_api`, una lista cerrada de hosts o
   dejarla fuera de toda autonomía.
2. **Decidir si `cancelar_solicitud_servicio` lleva gate de aprobación**, como
   las irreversibles. La evidencia apunta a que sí.
3. **Llevar la matriz al runtime en un bloque aparte**, declarando
   `nivel_autonomia` en el catálogo. Advertencia: bajar a 1 las R1 las **relaja**
   (hoy exigen 2 por defecto). Subir a 3 las de C4b las **endurece**. Ese cambio
   de sentido tiene que decidirse herramienta por herramienta, no en bloque.
4. **Mantener las indeterminadas sin nivel declarado** (default 2) hasta tener
   la evidencia, o declararlas con 3 como medida conservadora.
5. Nada de esto habilita autonomía: la etapa sigue apagada, B-7 parcial y no hay
   techo fijado.

## Pruebas de integridad

`tests/test_m06d_matriz_autonomia.py`: **28 de 28**, contra el catálogo real y la
clasificación de M10-A.

- **A, B y C:** 69 filas, ninguna duplicada, ninguna faltante ni sobrante.
- **Coherencia:** las 11 columnas en todas; lectura o escritura y aprobación
  humana coinciden **con el catálogo**; todos los niveles son válidos.
- **D:** la clase de cada una es la de M10-A, y R3/R4 son exactamente las cinco
  críticas.
- **E:** las cinco críticas tienen aprobación en la matriz **y** en el catálogo,
  son irreversibles y quedan en nivel 3.
- **F:** cada nivel 3 cita su regla; las escrituras no son todas del mismo nivel.
- **G:** toda lectura es 0 o INDETERMINADA.
- **H:** ninguna escritura irreversible, ni de reversibilidad no verificada,
  queda en 0, 1 o 2; cada nivel 2 declara en qué se basa su reversibilidad.
- **I:** las 4 indeterminadas dicen qué falta, y solo ellas.
- **Evidencia:** las 11 citas `archivo:línea` apuntan a archivos y líneas que
  existen.
- **No aplicada:** ninguna herramienta declara `nivel_autonomia` y ningún módulo
  del núcleo lee la matriz.

**Desarme de la prueba:** se metieron 10 errores en la matriz, uno por vez, y los
10 fueron detectados. La matriz quedó restaurada byte a byte.

| Error introducido | Detectado por |
|---|---|
| Falta una herramienta | C y A |
| Una duplicada | B y A |
| R4 clasificada como R2 | D |
| Una crítica sin aprobación | coherencia con el catálogo y E |
| Nivel 3 sin la regla que lo decide | F |
| Una lectura sube a 2 | G y H |
| La irreversible puesta en 2 | H |
| Un nivel 2 sin evidencia de reversibilidad | H |
| Una indeterminada sin "falta" | I |
| Una cita de evidencia rota | evidencia |

**Suite del motor (`tests/`, 97 archivos, uno por uno):** 95 de 97 en verde. Las 2 fallas son las preexistentes ya demostradas en M06-A: `test_p2_inerte` (archivos del 17/09 que este bloque no tocó) y `test_reloj` (espera 4 herramientas de importación y hay 5; la quinta ya está en `HEAD`). La regresión de Django no se corrió: este bloque no toca `django-crm/` ni ningún código del motor.

## Confirmaciones

- **Producción no se tocó.** No se ejecutó ninguna herramienta.
- **Ninguna acción sobre clientes:** no se crearon clientes de prueba ni se
  usaron clientes reales.
- **Sin llamadas a WispHub ni a SmartOLT:** la evidencia salió del catálogo y
  del código.
- **Archivos nuevos:** `M06-D_MATRIZ_AUTONOMIA.yaml`,
  `tests/test_m06d_matriz_autonomia.py` y este informe. Ningún archivo existente
  se modificó.

---

## Matriz completa (69 herramientas)

Ordenada por nivel propuesto, y dentro de cada nivel, lecturas primero.
"Barreras existentes": en las escrituras, **cadena autónoma** = kill switch →
techo → etapa → autorización granular → bitácora → permiso → idempotencia →
último metro; **cadena crítica** = lo mismo más la aprobación humana atada con
sello.

| # | Herramienta | Tipo | Clase | Nivel | Aprob. humana | Efecto externo | Reversible | Riesgo principal | Justificación | Barreras existentes | Evidencia |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `cargar_habilidad` | lectura | R0 | **0** | no | no (interno) | no_aplica | bajo | trae los pasos de un procedimiento aprobado | solo habilidades aprobadas por una persona | tipo=interno, solo_lectura=true, carga_habilidad |
| 2 | `confirmar_identidad` | lectura | R0 | **0** | no | no (cambia solo el estado de la SESION) | si | marcar verificada una sesion equivocada | cierra la verificacion pendiente de la conversacion; no llama a ninguna API | requiere verificar_identidad_por_cedula previo | tipo=interno, solo_lectura=true; descripcion ('No llama a ninguna API') |
| 3 | `consultar_casos_bottlecrm` | lectura | R0 | **0** | no | no (GET CRM propio) | no_aplica | bajo | lee casos | rol soporte | solo_lectura=true, GET |
| 4 | `consultar_casos_externos` | lectura | R0 | **0** | no | no (GET CRM propio) | no_aplica | bajo | lectura del importador | rol administracion | solo_lectura=true, GET |
| 5 | `consultar_cliente` | lectura | R0 | **0** | no | no (GET WispHub /api/clientes/) | no_aplica | exposicion de datos personales del cliente | consulta de un cliente por id; no cambia estado en ningun sistema | roles soporte/facturacion/administracion; lista blanca de campos por rol | solo_lectura=true, metodo GET (catalogo) |
| 6 | `consultar_cliente_por_cedula` | lectura | R0 | **0** | no | no (GET WispHub /api/clientes/) | no_aplica | exposicion de datos personales | busqueda por cedula; solo lectura | roles soporte/facturacion; lista blanca por rol | solo_lectura=true, GET |
| 7 | `consultar_dispositivos_conectados` | lectura | R0 | **0** | no | no (GET SmartOLT TR-069) | no_aplica | datos del interior de la casa (equipos conectados) | lista equipos conectados | identidad de sesion | solo_lectura=true, GET get_onu_router_hosts |
| 8 | `consultar_documentacion` | lectura | R0 | **0** | no | no (interno: corpus aprobado) | no_aplica | bajo | busqueda en manuales aprobados | solo documentos en estado vigente (match_chunks) | tipo=interno, solo_lectura=true, consulta_documentacion |
| 9 | `consultar_estabilidad_enlace` | lectura | R0 | **0** | no | no (lecturas a SmartOLT) | no_aplica | bajo | resume caidas de 24 h | identidad de sesion | tipo=interno, solo_lectura=true, resume_estabilidad |
| 10 | `consultar_estado_catv` | lectura | R0 | **0** | no | no (GET SmartOLT) | no_aplica | bajo | estado del puerto de TV | identidad de sesion | solo_lectura=true, GET get_onu_details |
| 11 | `consultar_estado_ont` | lectura | R0 | **0** | no | no (GET SmartOLT) | no_aplica | bajo | estado de la ONU | identidad de sesion | solo_lectura=true, GET get_onu_status |
| 12 | `consultar_factura_detalle` | lectura | R0 | **0** | no | no (GET WispHub) | no_aplica | datos financieros del cliente | detalle de una factura | rol facturacion | solo_lectura=true, GET |
| 13 | `consultar_facturas` | lectura | R0 | **0** | no | no (GET WispHub) | no_aplica | datos financieros del cliente | lee facturas | rol facturacion | solo_lectura=true, GET |
| 14 | `consultar_formas_pago` | lectura | R0 | **0** | no | no (GET WispHub) | no_aplica | bajo | catalogo de formas de pago | rol facturacion; cache | solo_lectura=true, GET, cache=true |
| 15 | `consultar_guia_sintonizacion` | lectura | R0 | **0** | no | no (interno) | no_aplica | bajo | lee guias de TV de la config | roles de soporte | tipo=interno, solo_lectura=true, consulta_guias_tv |
| 16 | `consultar_incidente_red` | lectura | R0 | **0** | no | no (lecturas a SmartOLT, correlacion en codigo) | no_aplica | bajo | correlaciona la ONU con incidentes activos | identidad de sesion | tipo=interno, solo_lectura=true, detecta_incidente |
| 17 | `consultar_mi_servicio` | lectura | R0 | **0** | no | no (GET WispHub) | no_aplica | consultar el servicio de otro cliente (cerrado: el id viene de la sesion) | estado del servicio del cliente autenticado | identidad inyectada desde la sesion (inyectar_sesion); roles de cliente | solo_lectura=true, GET, inyectar_sesion (catalogo) |
| 18 | `consultar_parrilla_canales` | lectura | R0 | **0** | no | no (interno) | no_aplica | bajo | lee la parrilla de la config | rol ventas | tipo=interno, solo_lectura=true, consulta_parrilla |
| 19 | `consultar_plan_detalle` | lectura | R0 | **0** | no | no (GET WispHub) | no_aplica | bajo | precio y velocidad de un plan | rol ventas; cache | solo_lectura=true, GET, cache=true |
| 20 | `consultar_plan_tv` | lectura | R0 | **0** | no | no (GET WispHub plan-internet) | no_aplica | bajo: dato de catalogo | lee la descripcion de un plan | roles; cache | solo_lectura=true, GET, cache=true |
| 21 | `consultar_planes` | lectura | R0 | **0** | no | no (GET WispHub) | no_aplica | bajo | catalogo tecnico de planes | rol ventas; cache | solo_lectura=true, GET, cache=true |
| 22 | `consultar_planes_venta` | lectura | R0 | **0** | no | no (interno) | no_aplica | bajo | cobertura y planes curados, calculados de la config | rol ventas; invocable por servicio (lectura) | tipo=interno, solo_lectura=true, invocable_por_servicio=true |
| 23 | `consultar_senal_ont` | lectura | R0 | **0** | no | no (GET SmartOLT) | no_aplica | bajo | senal optica | identidad de sesion; veredicto calculado en codigo | solo_lectura=true, GET get_onu_signal |
| 24 | `consultar_servicios_ofrecidos` | lectura | R0 | **0** | no | no (interno: config del tenant) | no_aplica | bajo | lee el catalogo comercial | rol ventas | tipo=interno, solo_lectura=true |
| 25 | `consultar_solicitud_por_cedula` | lectura | R0 | **0** | no | no (POST de busqueda al CRM propio) | no_aplica | exposicion de una solicitud ajena (mitigado: nombre enmascarado) | busca una solicitud; el POST es de busqueda, no de escritura | rol ventas; nombre enmascarado en la respuesta | solo_lectura=true; endpoint /api/solicitudes/buscar/; descripcion ('Devuelve el nombre ENMASCARADO') |
| 26 | `consultar_tecnicos` | lectura | R0 | **0** | no | no (GET WispHub /api/staff/) | no_aplica | bajo | lista el personal | rol soporte; cache; invocable por servicio (lectura) | solo_lectura=true, GET, cache=true |
| 27 | `consultar_ticket` | lectura | R0 | **0** | no | no (GET WispHub) | no_aplica | bajo | lee tickets | roles soporte/administracion | solo_lectura=true, GET |
| 28 | `consultar_ticket_por_id` | lectura | R0 | **0** | no | no (GET WispHub) | no_aplica | bajo | lectura del importador | rol administracion; invocable por servicio (lectura) | solo_lectura=true, GET, invocable_por_servicio=true |
| 29 | `consultar_tickets_conocidos` | lectura | R0 | **0** | no | no (GET CRM propio) | no_aplica | bajo | lectura del importador | rol administracion | solo_lectura=true, GET |
| 30 | `consultar_tickets_de_cliente` | lectura | R0 | **0** | no | no (GET WispHub) | no_aplica | bajo | tickets abiertos filtrados por cliente en codigo | roles soporte/administracion | solo_lectura=true, GET |
| 31 | `consultar_velocidad_aprovisionada` | lectura | R0 | **0** | no | no (GET SmartOLT) | no_aplica | bajo | perfil de velocidad configurado | identidad de sesion | solo_lectura=true, GET get_onu_speed_profiles |
| 32 | `contar_clientes` | lectura | R0 | **0** | no | no; puede generar un archivo exportable INTERNO (adjunto a la respuesta) | no_aplica | volumen de llamadas al agrupar; archivo con datos agregados | agregado calculado por codigo; el archivo es para una persona | roles; filtros verificados; tope de grupos | tipo=agregado, solo_lectura=true, exportable=true |
| 33 | `contar_facturas` | lectura | R0 | **0** | no | no; archivo exportable interno | no_aplica | volumen de llamadas | agregado calculado por codigo | roles; filtros verificados | tipo=agregado, solo_lectura=true, exportable=true |
| 34 | `contar_tickets` | lectura | R0 | **0** | no | no; archivo exportable interno | no_aplica | volumen de llamadas | agregado calculado por codigo | roles; filtros verificados | tipo=agregado, solo_lectura=true, exportable=true |
| 35 | `derivar_a_area` | lectura | R0 | **0** | no | no (cambia el ROL que atiende la conversacion) | si | derivar al area equivocada | enrutamiento interno de la conversacion, sin sistema externo | areas_destino declaradas; anti-rebote por conversacion | tipo=interno, solo_lectura=true, deriva_rol=true |
| 36 | `diagnosticar_falla_ont` | lectura | R0 | **0** | no | no (GET SmartOLT get_onu_full_status_info) | no_aplica | costo: ~10 s por llamada; el proveedor prohibe usarla en polling o en lote | diagnostico profundo, solo lectura | identidad de sesion | solo_lectura=true, GET; skill smartolt-api ('~10s de latencia, no usar en polling/bulk') |
| 37 | `informe_materiales` | lectura | R0 | **0** | no | no | no_aplica | costo: ~2.700 llamadas por mes; es proceso por lotes | lee y agrega respuestas de tickets | rol administracion | tipo=batch, solo_lectura=true; descripcion ('Coste ~2.700 llamadas por mes') |
| 38 | `listar_tags_crm` | lectura | R0 | **0** | no | no (GET CRM propio) | no_aplica | bajo | lista etiquetas | rol administracion | solo_lectura=true, GET |
| 39 | `listar_tickets_recientes` | lectura | R0 | **0** | no | no (GET WispHub) | no_aplica | bajo | lectura del importador | rol administracion; invocable por servicio (lectura) | solo_lectura=true, GET, invocable_por_servicio=true |
| 40 | `ping_cliente` | lectura | R0 | **0** | no | sonda ACTIVA: POST que dispara un ping al equipo del cliente via WispHub; no cambia estado | no_aplica | carga sobre el equipo del cliente si se repite; es una accion, no una lectura pasiva | observa conectividad; no modifica configuracion ni registros | identidad de sesion; roles de cliente; asincrona | solo_lectura=true pero metodo POST /api/clientes/{id_servicio}/ping/ (catalogo); verificado en vivo agosto 2026 (descripcion) |
| 41 | `verificar_identidad_por_cedula` | lectura | R0 | **0** | no | no (GET WispHub) | no_aplica | enumeracion de cedulas (mitigado: no devuelve datos, solo el nombre a confirmar) | primer paso de verificacion | roles de cliente; respuesta reducida | solo_lectura=true, GET, verifica_identidad |
| 42 | `proponer_herramienta` | escritura | R1 | **1** | no | no: deja un borrador interno | si | una herramienta mal declarada (mitigado: queda pendiente hasta que un ADMIN la apruebe) | genera una propuesta para decision humana (C2) | rol configuracion_guiada; aprobacion de un ADMIN en la pantalla | tipo=interno, propone_herramienta; descripcion ('NO la activa -- queda pendiente hasta que un ADMIN humano la apruebe') |
| 43 | `registrar_pedido_wifi` | escritura | R1 | **1** | no | indirecto: al completarse ESCALA, y la escalada crea caso y ticket por codigo | si | un pedido de cambio de WiFi mal tomado | no aplica el cambio: deja el pedido para que lo aplique una persona (C2) | cadena autonoma (pasa por la frontera); valida el pedido; escalar_al_completar | tipo=interno, valida_pedido_wifi, escalar_al_completar=pedido_para_ejecutar; descripcion ('NO aplica el cambio: lo aplica una persona') |
| 44 | `reportar_comprobante_pago` | escritura | R1 | **1** | no | indirecto: escala a cartera (caso y ticket por codigo) | si | reporte de pago falso (mitigado: no registra nada, lo valida una persona) | junta lo que dijo el cliente para que una persona lo valide (C2) | cadena autonoma; identidad de sesion; escalar_al_completar | tipo=interno, reporta_comprobante_pago, escalar_al_completar=comprobante_para_validar; YAML ('NO registra nada en WispHub, NO reconecta') |
| 45 | `cerrar_caso_crm` | escritura | R2 | **2** | no | si, CRM propio (PATCH del estado del caso) | si (evidenciado: politica de reapertura y cambio de estado por el mismo endpoint) | cerrar un caso vivo | CRM propio, reversible, sin notificacion al cliente desde el CRM (C4a) | cadena autonoma; la ejecuta el codigo (operativo.cerrar_caso_crm) | cases/models.py:757-781 (ReopenPolicy); PATCH /api/cases/{id_caso}/ |
| 46 | `crear_caso_soporte` | escritura | R2 | **2** | no | si, CRM propio (crea un caso); correo al usuario ASIGNADO (personal interno) | si (evidenciado: el caso se cierra con cerrar_caso_crm y se reabre por estado) | casos duplicados; carga de trabajo para el equipo | coordinacion interna en el CRM propio, reversible, no notifica al cliente (C4a) | cadena autonoma | cases/views.py:395,535 (send_email_to_assigned_user: al asignado, no al cliente); existe cerrar_caso_crm |
| 47 | `crear_tag_crm` | escritura | R2 | **2** | no | si, CRM propio (crea una etiqueta) | si (evidenciado: DELETE y restore en el CRM) | bajo: etiquetas duplicadas | CRM propio, reversible con evidencia, sin efecto visible al cliente (C4a). Es ademas el piloto elegido para Autonomia 2 | cadena autonoma | django-crm/backend/common/urls.py:151-152 (tags/<pk>/ con delete, tags/<pk>/restore/); common/views/tags_views.py:366 |
| 48 | `importar_caso_externo` | escritura | R2 | **2** | no | si, CRM propio (crea un caso espejo de un ticket) | si (idempotente: get_or_create; el caso se cierra) | casos espejo duplicados (mitigado: idempotente) | sincronizacion hacia el CRM propio, idempotente (C4a) | cadena autonoma; lista de estados iniciales permitidos | cases/importacion_views.py:83-180 (ImportarCaseView, 'status' inicial validado, 201/200 segun creado) |
| 49 | `reconciliar_caso_externo` | escritura | R2 | **2** | no | si, CRM propio (solo campos espejo del proveedor) | si (re-derivable desde el proveedor; nunca toca Case.status ni assigned_to) | datos espejo desactualizados | escribe solo una lista blanca de campos espejo (C4a) | cadena autonoma; lista blanca de campos; assert de que no mueve el estado | cases/importacion_views.py:58-61 (campos permitidos), :387-453 (assert caso.status == estado_previo) |
| 50 | `registrar_solicitud_servicio` | escritura | R2 | **2** | no | si, CRM propio (solicitud NUEVA + link de formulario) | inerte (evidenciado): una NUEVA no tiene efecto hasta que el prospecto envia el formulario | solicitudes NUEVA acumuladas | no compromete recursos; el efecto real lo dispara el prospecto al enviar el formulario (C4a, efecto inerte) | cadena autonoma; identidad de sesion | solicitudes/models.py:128 ('NUEVA: el link se genero, todavia no la enviaron') y :136-139 ('si el cliente nunca lleno el formulario no hay expediente') |
| 51 | `sincronizar_respuestas_externas` | escritura | R2 | **2** | no | si, CRM propio (hilo de respuestas espejo) | si (upsert por huella: repetir no duplica) | bajo | espejo idempotente hacia el CRM propio (C4a) | cadena autonoma | cases/importacion_views.py:474-528 (RespuestasExternasView, upsert por huella) |
| 52 | `activar_catv` | escritura | R3 | **3** | **SÍ** | si, SmartOLT (enciende la TV en el equipo) | no verificado como reversible por el sistema (M10-A la clasifica R3) | dar un servicio no contratado | R3: aprobacion humana obligatoria y atada (C3) | cadena critica; previas (plan con TV, CATV Disabled) re-medidas; limite 1 | irreversible=true, aprobacion_humana=true, exige_previas |
| 53 | `actualizar_estado_ticket` | escritura | R2 | **3** | **SÍ** | si, WispHub (PUT del estado) | si (el mismo PUT) | cerrar o abrir un ticket por error | declara aprobacion humana: se mantiene (C3) | aprobacion humana (cola); M06-B: no sale con permiso autonomo | aprobacion_humana=true |
| 54 | `agendar_visita_internet` | escritura | R2 | **3** | no | si, WispHub (ticket de visita) | si, mientras la visita no ocurra | enviar un tecnico sin necesidad | igual que agendar_visita_tecnica (C4b); la dispara el codigo, no el modelo | cadena autonoma; la ejecuta nucleo/seguimiento/agendamiento.py | POST WispHub /api/tickets/; descripcion ('la ejecuta el codigo cuando el caso no_internet llega a una rama que requiere visita') |
| 55 | `agendar_visita_tecnica` | escritura | R2 | **3** | no | si, WispHub (crea un ticket de visita: compromete a un tecnico) | si, mientras la visita no ocurra (el ticket se cierra); el costo del tecnico no se revierte despues | enviar un tecnico sin necesidad | sistema del proveedor y compromete recursos; reversible por cierre del ticket (C4b) | cadena autonoma; rol soporte; el colaborador confirma antes (descripcion) | POST WispHub /api/tickets/; descripcion ('se ejecuta de inmediato, SIN ningun paso de confirmacion humana'); existen herramientas de cierre de ticket |
| 56 | `agregar_promesa_pago` | escritura | R4 | **3** | **SÍ** | si, WispHub (promesa de pago; puede reactivar el servicio) | no_verificado | dinero / reactivacion | R4: aprobacion humana obligatoria y atada (C3) | cadena critica con sello | irreversible=true, aprobacion_humana=true; M06-C |
| 57 | `cambiar_tipo_onu` | escritura | R3 | **3** | **SÍ** | si, SmartOLT (cambia el tipo registrado de la ONU) | no verificado (M10-A la clasifica R3) | dejar el equipo mal clasificado | R3: aprobacion humana obligatoria y atada (C3) | cadena critica; previa (CATV Not supported) re-medida; limite 1; turno propio | irreversible=true, aprobacion_humana=true, exige_previas |
| 58 | `cancelar_solicitud_servicio` | escritura | R2 | **3** | no | si, CRM propio Y, en cascada, WispHub (cierra el ticket de instalacion) | NO (evidenciado): CANCELADA es un estado final, ninguna transicion sale de el | cancelar la instalacion de otra persona o por error (mitigado: exige el nombre completo) | irreversible con evidencia y con efecto en cascada en el proveedor: no puede quedar en un nivel permisivo (C4c). Se recomienda gate de aprobacion | cadena autonoma; exige consultar_solicitud_por_cedula y el nombre completo; solo solicitudes ENVIADA | solicitudes/gestion.py:556 (s.estado = CANCELADA; ninguna otra linea sale de CANCELADA); solicitudes/entrega.py:275-278 ('cancelar solo en el CRM deja el ticket vivo en WispHub') |
| 59 | `crear_ticket` | escritura | R2 | **3** | **SÍ** | si, WispHub (crea un ticket) | si (se cierra con actualizar_estado_ticket) | tickets erroneos en el sistema del proveedor | declara aprobacion humana: se mantiene y no puede ir por la puerta autonoma (C3) | aprobacion humana (cola); M06-B: no sale con permiso autonomo | aprobacion_humana=true (catalogo); frontera.exigir, APROBACION_HUMANA_REQUERIDA |
| 60 | `crear_ticket_caso` | escritura | R2 | **3** | no | si, WispHub (crea un ticket al escalar) | si (el ticket se cierra) | tickets duplicados en el sistema del proveedor | escribe en el sistema del proveedor, reversible por cierre (C4b) | cadena autonoma; la ejecuta el codigo al escalar | POST WispHub /api/tickets/; descripcion ('la ejecuta el codigo cuando una conversacion se escala') |
| 61 | `crear_ticket_instalacion` | escritura | R2 | **3** | no | si, WispHub (ticket de instalacion) | si (evidenciado: cancelar la solicitud cierra el ticket con cerrar_ticket_operativo) | instalacion agendada por error | sistema del proveedor, reversible (C4b); la dispara el formulario del prospecto | cadena autonoma; invocable por servicio (backend) | POST WispHub /api/tickets/, invocable_por_servicio=true; solicitudes/entrega.py:272-290 (cerrar_ticket_wisphub) |
| 62 | `reasignar_ticket_instalacion` | escritura | R2 | **3** | no | si, WispHub (PUT: cambia a quien esta asignado el ticket) | si (el mismo PUT lo reasigna de vuelta) | asignar la instalacion al equipo equivocado | sistema del proveedor, reversible con la misma operacion (C4b); la dispara una persona desde la plataforma | cadena autonoma; invocable por servicio | PUT WispHub /api/tickets/{id_ticket}/, invocable_por_servicio=true; descripcion ('la llama el backend cuando una persona confirma la factibilidad') |
| 63 | `registrar_pago` | escritura | R4 | **3** | **SÍ** | si, WispHub (registra el pago; con accion=1 reactiva el servicio) | no (revertir un pago es una operacion contable) | dinero | R4: aprobacion humana obligatoria y atada (C3) | cadena critica con sello | irreversible=true, aprobacion_humana=true; M06-A |
| 64 | `reiniciar_ont` | escritura | R3 | **3** | **SÍ** | si, SmartOLT (reinicia el equipo en casa del cliente) | no (un reinicio no se deshace; el cliente queda sin servicio 1-2 min) | corte de servicio; reiniciar el equipo equivocado | R3: aprobacion humana OBLIGATORIA y atada; el nivel no la reemplaza (C3) | cadena critica; previas re-medidas al aprobar; verificacion posterior; limite 1; turno propio | irreversible=true, aprobacion_humana=true, exige_previas, verificacion (catalogo); M06-A |
| 65 | `responder_ticket` | escritura | R2 | **3** | **SÍ** | si, WispHub (respuesta, puede reabrir) | no_verificado | respuesta publicada que no se retira | declara aprobacion humana: se mantiene (C3) | aprobacion humana (cola); M06-B: no sale con permiso autonomo | aprobacion_humana=true |
| 66 | `sondear_api` | lectura | R0 | **INDETERMINADA** | no | desconocido: GET contra una URL externa que elige el modelo o el ADMIN | no_verificado | un GET no es inocuo por definicion (hay APIs que mutan por GET); la URL puede sacar datos hacia afuera | el catalogo NO fija el destino, asi que su efecto depende de a donde apunte — **Falta:** lista cerrada de hosts permitidos, o evidencia de que los destinos sondeados son de solo lectura | rol configuracion_guiada; bloqueo de redes privadas; devuelve solo un resumen | tipo=interno, solo_lectura=true, sondea_api; descripcion ('Hace un GET ... contra una URL externa que describis vos') |
| 67 | `cerrar_ticket_operativo` | escritura | R2 | **INDETERMINADA** | no | si, WispHub (respuesta + cierre del ticket) | parcial: el cierre se revierte (responder_ticket puede reabrir); la respuesta agregada no se verifico | cerrar un ticket vivo; nota permanente posiblemente visible al cliente | misma falta de evidencia que responder_ticket_operativo sobre la respuesta que deja — **Falta:** si la respuesta de cierre se notifica al cliente y si puede eliminarse | cadena autonoma; invocable por servicio (la usa la cascada de cancelacion) | POST WispHub /api/tickets/{id_ticket}/respuesta/, invocable_por_servicio=true; responder_ticket: 'con la opcion de reabrirlo' |
| 68 | `completar_ticket_instalacion` | escritura | R2 | **INDETERMINADA** | no | si, WispHub (PATCH de fechas + adjunta la orden) | parcial: las fechas se corrigen con otro PATCH; retirar el adjunto no se verifico | adjuntar la orden de otra persona (datos personales en el archivo) | no hay evidencia de que un adjunto se pueda retirar — **Falta:** si WispHub permite eliminar un adjunto de ticket por API | cadena autonoma; invocable por servicio | PATCH WispHub /api/tickets/{id_ticket}/, multipart con argumentos_archivo; descripcion ('le adjunta la orden') |
| 69 | `responder_ticket_operativo` | escritura | R2 | **INDETERMINADA** | no | si, WispHub (agrega una respuesta al ticket y lo deja En Progreso) | no_verificado | una respuesta publicada no se puede retirar con ninguna herramienta; puede ser visible o notificada al cliente | no hay evidencia de si WispHub permite borrar una respuesta ni de si notifica al cliente — **Falta:** si WispHub notifica al cliente al agregar una respuesta, y si una respuesta puede eliminarse | cadena autonoma; la ejecuta el codigo al responder una persona desde la pantalla | POST WispHub /api/tickets/{id_ticket}/respuesta/; ninguna herramienta del catalogo borra respuestas; skill wisphub-api: 'do_not_notify_client' solo documentado en otra instancia, no verificado aqui |
