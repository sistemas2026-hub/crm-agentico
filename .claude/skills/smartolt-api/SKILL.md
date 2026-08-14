# API de SmartOLT — lo que ya se verificó en vivo

SmartOLT administra las ONUs autorizadas en la OLT de fibra. Se integra para
convertir el diagnóstico ciego actual (`ping_cliente` vía WispHub) en uno
concluyente: distinguir equipo sin energía, sin señal óptica, señal débil, o
equipo sano (la falla está en otro lado).

**Misma regla que con WispHub: la documentación es una hipótesis.** Todo lo de
abajo se verificó contra la instancia real de Rapilink el 14/08/2026, no se
tomó de la página de developers (que además es JS-rendered, igual que WispHub
— el HTML crudo no trae nada).

## Auth

Header **`X-Token: <api_key>`** — no `Authorization`, no prefijo `Bearer`.
Confirmado: `Authorization: Bearer ...` no se probó porque `X-Token` funcionó
al primer intento contra `/api/system/get_olts`.

`nucleo/herramientas/http.py::headers_de()` fija hoy el nombre del header en
`Authorization` — hace falta el campo `auth_header` configurable (ver plan).

## Límite de tasa — confirmado por cabecera, no por la doc de terceros

**1.000 llamadas/hora**, no 15 — la cifra de 15/hora que circulaba por
búsqueda web era de un caso de uso masivo específico, no el límite de cuenta.
Cada respuesta trae `X-RateLimit-Limit: 1000` y `X-RateLimit-Remaining`, así
que se puede monitorear en vivo sin adivinar.

Con el uso real del asistente (una consulta puntual por conversación de
soporte), 1.000/hora es holgadísimo. La preocupación de caché del plan
original (pensada para 15/hora) ya no aplica al camino conversacional.

## El sobre de respuesta

`{"response_code": "success", "status": true, ...}` en éxito;
`{"status": false, "error": "...", "error_code": ...}` en error, con
**HTTP distinto de 200** (probado: 400 para parámetro inválido). A diferencia
del `arp_ping` de WispHub, no encontré todavía un caso de error disfrazado de
200 — pero solo se probó el camino de "serial inválido", no todos los errores
posibles. No dar por cerrado el riesgo.

Cada endpoint envuelve el dato en su propia clave de primer nivel
(`onu_details`, `onus`, `onu_status`, `onu_signal`) — igual que BottleCRM,
cada endpoint tiene su propio sobre, no asumir un patrón común entre ellos.

## Endpoints verificados (agosto 2026)

| Endpoint | Método | Verificado | Nota |
|---|---|---|---|
| `/api/system/get_olts` | GET | Sí, 14/08/2026 | Sin parámetros. 2 OLTs en Rapilink, ambas Huawei. **No usar como heartbeat** — el proveedor lo pide explícito en la doc que pegó el usuario |
| `/api/onu/get_onu_details/{sn}` | GET | Sí, 14/08/2026 | Detalle completo — ver tabla de campos abajo |
| `/api/onu/get_onu_status/{sn}` | GET | Sí, 14/08/2026 | Minimal: solo `onu_status`, `last_status_change`. Sin PII |
| `/api/onu/get_onu_signal/{sn}` | GET | Sí, 14/08/2026 | Solo señal — el más liviano para un cliente final, sin PII |
| `/api/onu/get_all_onus_details` | GET | Sí, con cautela | Masivo. Ver "Filtros" abajo — **no usar en el camino conversacional** |
| `/api/onu/reboot/{onu_id}` | POST | **NO ejecutado, pero documentado por el proveedor** (el usuario pego el contrato oficial) | `{"status": true, "response": "Device reboot command sent"}`. Sincrono en el sentido de "el comando se mando", NO en el de "la ONU ya reinicio" -- son cosas distintas. 400 si: falta el id, no existe la ONU, o la OLT no pudo procesar el comando. Sin body, sin confirmacion adicional |
| `/api/system/get_outage_pons/{olt_id}` | GET | Sí, 14/08/2026 | **Resuelve la regla del splitter (G-GO-11) sin reconstruirla a mano** -- ver seccion propia abajo |
| `/api/system/get_odbs/{zona_id opcional}` | GET | Documentado, no llamado | Metadata de cada ODB (splitter fisico): id, nombre, lat/long, zona. Coordenadas de la CAJA, no del cliente -- mucho menos sensible |
| `/api/onu/get_onu_full_status_info/{sn}` | GET | Sí, 14/08/2026 | **El mas completo. Reemplaza a `get_onu_details`+`get_onu_signal` para el diagnostico real** -- ver seccion propia abajo. ~10s de latencia, el proveedor pide no usarlo en polling/bulk |
| `/api/onu/get_onus_by_pon_port/...` | GET | Probado, **no existe** | 405 "Unknown method" |
| `/api/onu/get_onus_by_olt_board_port/...` | GET | Probado, **no existe** | 405 "Unknown method" |

## El identificador — el hallazgo más importante del sondeo

**`sn_onu` de WispHub funciona DIRECTO como identificador de SmartOLT.** No
hace falta traducir a un `onu_id` interno — es el mismo valor
(`unique_external_id` / `sn` en la respuesta de SmartOLT). Verificado con
`HWTCAF721761` (Carlos Eliecer Diaz Lazo, id_servicio 6580 en WispHub):
`get_onu_details` lo aceptó y devolvió exactamente ese cliente.

**Método del valor imposible aplicado al identificador** (no a un filtro,
al identificador mismo — es la variante que corresponde cuando lo que hay que
verificar es "¿me deja pedir la ONU de cualquiera?"):

```
serial real (HWTCAF721761)      -> HTTP 200, datos del cliente correcto
serial imposible (ZZZZ00000000) -> HTTP 400 "Invalid parameters"
```

**Sirve** — el endpoint valida el identificador, no lo ignora. Esto simplifica
el diseño: no hace falta la cadena de captura `sn_onu → onu_id` que el plan
dejaba como contingencia principal.

⚠️ **Cobertura de la llave: 68%, no 100%.** Ver el hallazgo en
`.claude/skills/wisphub-api/SKILL.md` — 1.299 de 4.163 clientes activos no
tienen `sn_onu` en WispHub. Para ese tercio, cualquier herramienta de SmartOLT
no tiene con qué consultar.

## Link directo a la ONU en el panel de SmartOLT — util para `soporte`, no para el asistente

Documentado por el proveedor junto a `get_onu_details` (agosto 2026, no
verificado en un navegador todavia -- es UI, no API, "el metodo del valor
imposible" no aplica igual):

```
https://{subdominio}.smartolt.com/onu/details/{onu_external_id}
```

Con `sn_onu` (=`onu_external_id`) se arma sin llamar a la API. Sirve para un
"ver en SmartOLT" en la pantalla de un colaborador (ficha del cliente, o el
detalle de un ticket) -- un atajo a la vista completa del proveedor cuando
el catalogo del asistente no cubre lo que hace falta (ej. cambiar
`configuration_method`, ver el historial completo). NO es para `cliente_final`
(requiere login de SmartOLT, y es panorama interno de red) ni para que el
asistente lo devuelva en una conversacion -- es un link de interfaz, no un
dato de una herramienta.

## Campos de `get_onu_details` — con qué cuidado

Registro real completo, filtrado a lo relevante (60+ campos totales, no
todos abajo):

| Campo | Valor de ejemplo | Peligro |
|---|---|---|
| `name` | `"CARLOS ELIECER DIAZ LAZO"` | 🔴 **Nombre completo del cliente, en el registro de la ONU.** Mismo riesgo que WispHub — nunca a `cliente_final`, y pensarlo dos veces incluso para `soporte` |
| `address` | `""` (vacío en este caso; el campo existe) | 🔴 Dirección — no confirmado con un caso poblado, pero el campo existe |
| `latitude` / `longitude` | `None` en este caso | 🔴 GPS — mismo campo que `coordenadas` de WispHub, mismo criterio RNF-01 |
| `password` / `username` | `None` en este caso | 🔴 Credenciales — el campo existe aunque vacío acá |
| `contact` | `""` | 🟡 Probable teléfono/contacto |
| `zone_name` | `"CANDELARIA 2"` | 🟡 Topología de red, no personal |
| `odb_name` | `""` | 🟢 Nombre de la caja/splitter — útil para diagnóstico, no personal |
| `olt_id`, `olt_name`, `board`, `port`, `onu` | `3`, `"OLT-RAPILINKSAS_X7"`, `4`, `14`, `17` | 🟡 Topología — necesaria para `soporte`, no para `cliente_final` |
| `status` | `"Online"` / `"Offline"` | 🟢 Necesario para el diagnóstico |
| `signal` | `"Very good"` | 🟢 **SmartOLT ya clasifica la señal en texto** — no hace falta que el modelo interprete el dBm, se puede mostrar directo |
| `signal_1310` | `-23.98` (dBm) | 🟡 Ver nota de wavelength abajo |
| `signal_1490` | `-21.74` (dBm) | 🟡 Ver nota de wavelength abajo |
| `distance` | `"4289"` (metros, inferido) | 🟢 Sin riesgo |
| `last_status_change` | timestamp | 🟢 Sirve para distinguir corte reciente de intermitencia vieja |
| `authorization_date` | timestamp | 🟢 Sin riesgo |

**`get_onu_signal/{sn}` es el candidato natural para `cliente_final`**: devuelve
`onu_signal` (clasificación en texto), `onu_signal_1310`, `onu_signal_1490` —
nada de nombre, dirección, ni topología. Más limpio que filtrar
`get_onu_details` después.

## La IP del cliente: dos campos que MIDEN COSAS DISTINTAS, no confundirlos

Hallazgo corregido el 14/08/2026 -- la primera version de esta seccion
concluia "SmartOLT no trae la IP, salvo 1 ONU de prueba en modo OMCI" y
estaba **mal**, por confundir dos campos con nombre parecido:

| Campo | Endpoint | Lo que se midio | Conclusion |
|---|---|---|---|
| `wan_mode` / `ip_address` | `get_onu_details`, `get_all_onus_details` | **4.966 ONUs, TODA la OLT `olt_id=3`**: 4.953 en `"Setup via ONU webpage"`, 12 en blanco, 1 en `"Static"` -- CERO en OMCI, `ip_address` siempre `None` | Este campo especifico esta vacio para practicamente cualquier ONU real. Sigue siendo cierto, pero **no es la pregunta que importa** |
| `ONU details.Management mode` | `get_onu_full_status_info` | **Muestra de 10 ONUs reales (no de prueba)**: las 10 en `"OMCI"`. `ONU WAN Interfaces.IPv4 address` poblado en 8 de esas 10 | Este es el campo que de verdad decide si la IP esta visible -- y para la gran mayoria de clientes reales, SI lo esta |

**La leccion, no solo el dato**: dos campos con nombres parecidos
(`wan_mode` vs `Management mode`) en dos endpoints distintos del MISMO
proveedor pueden medir cosas completamente distintas. Medir uno y sacar una
conclusion sobre el otro sin verificar es exactamente el error que esta
skill entera existe para evitar -- y aca se cometio una vez, hay que
tenerlo presente.

**Para consultar la IP de un cliente real, dos fuentes validas**:
- **WispHub** (`GET /api/clientes/?id_servicio=N`, campo `ip`) -- rapido,
  siempre disponible, confirmado que coincide exacto con SmartOLT cuando
  se cruzaron (`172.16.26.143` en ambos para id_servicio 6580 / `HWTCAF721761`).
- **SmartOLT** (`get_onu_full_status_info/{sn}` -> `full_status_json["ONU
  WAN Interfaces"]["IPv4 address"]`) -- mismo dato, pero paga el costo de
  ~10s de latencia de ese endpoint. Sin motivo para preferirlo sobre
  WispHub solo para la IP; tiene sentido si de todas formas se esta
  llamando a ese endpoint por el diagnostico de causa de caida (ver abajo).

## `get_onu_full_status_info` -- estructura completa verificada (14/08/2026)

`full_status_json` tiene 7 secciones, cada una un dict de un nivel (con
espacios en las claves, no rompe la notacion con punto de
`nucleo/seguridad/listas_blancas.py` -- `"ONU details.Last down cause"`
funciona tal cual):

- `Optical status`: `Rx optical power(dBm)`, `Tx optical power(dBm)`,
  `Temperature(C)`, `OLT Rx ONT optical power(dBm)`, `CATV Rx optical power(dBm)`.
- `ONU CATV port`: `Port State`.
- `ONU details`: `Control flag`, `Run state`, `Match state`,
  `ONT distance(m)`, `SN`, `Management mode`, `Description` (nombre del
  cliente -- PII, mismo criterio que `name` en `get_onu_details`),
  **`Last down cause`** (ver el mapeo dying-gasp/LOSi-LOBi mas arriba en
  esta skill), `Last up time`, `Last down time`, `ONT online duration`,
  mas config de linea (perfil, FEC, QoS) que es topologia de red, no dato
  de diagnostico.
- `History`: LISTA (no dict) de hasta 10 eventos `{Auth at, Offline at,
  Cause}` -- no accesible con la notacion con punto de un nivel, solo
  `Last down cause` (el mas reciente) es directamente utilizable hoy.
- `ONU WAN Interfaces`: `IPv4 address`, `Subnet mask`, `Default gateway`,
  `Manage VLAN`, `MAC address`, mas un artefacto de serializacion (`"2":
  {"[]": "0"}`) que hay que ignorar, no es un campo real.
- `ONU LAN Interfaces status`: por puerto, `Link state` (up/down) -- sirve
  para saber si hay un cable conectado al puerto LAN, mas alla del estado
  optico.
- `MACs on OLT from this ONU`: direcciones MAC vistas en el puerto -- topologia,
  no diagnostico de cliente.

El identificador se pasa SIN guion (`CDTC505AEAFF`, no `CDTC-505AEA-FF`) --
mismo formato de 12 caracteres que documenta la skill `wisphub-api`.

## ⚠️ 1310 vs 1490 — inferido por convención GPON, NO verificado empíricamente

Downstream (OLT→ONU) es 1490nm, upstream (ONU→OLT) es 1310nm por estándar
GPON. La señal que le interesa a G-GO-04 ("ONT del cliente: −8 a −25 dBm") es
la que **recibe la ONT**, o sea la de bajada: **`signal_1490`**.

Con el único caso sano medido (`signal_1490=-21.74`, `signal_1490=-21.8` en
la segunda lectura — fluctúa entre llamadas, normal), el valor cae dentro del
rango aceptable, consistente con `signal: "Very good"`. Pero **no se cruzó
contra un caso de señal mala real** para confirmar el umbral exacto. Antes de
fijar `signal_1490` como LA métrica en el catálogo, vale confirmarlo con
alguien técnico de Rapilink o con un caso real de señal débil.

## Offline SÍ distingue el motivo — pero no en el endpoint que se probó primero

`get_onu_status`/`get_onu_details` (los livianos) solo dan `"Offline"`, un
único estado sin causa -- eso SÍ se confirmó y sigue siendo cierto para esos
dos endpoints puntuales. **Pero `get_onu_full_status_info` sí trae la causa**,
en `ONU details.Last down cause` y en el `History` completo (10 eventos, cada
uno con su `Cause`). Valores reales vistos en la instancia de Rapilink:

| `Last down cause` | Qué significa | Mapeo a G-GO-04 |
|---|---|---|
| `dying-gasp` | La ONU avisó que se quedó sin energía justo antes de apagarse (mecanismo estándar GPON) | Corte de luz en la casa del cliente -- LED POWER apagado |
| `ONT LOSi/LOBi alarm` | Loss Of Signal / Loss Of Burst -- perdió la señal óptica | Fibra cortada o falla en la NAP -- LED LOS rojo |
| `ONT LOFi alarm` | Loss Of Frame -- perdió sincronía, también óptico | Mismo grupo que LOS: falla óptica |
| `"ONU is currently online"` | No es una causa de caída, es el estado del evento más reciente cuando está en línea | — |

Con esto, **el asistente sí puede distinguir corte de luz de falla de fibra
sin preguntarle nada al cliente** -- corrige lo que se había anotado antes en
esta misma skill. El costo es la latencia: `get_onu_full_status_info` tarda
~10s (medido: 9.9s), swich el proveedor lo autoriza explícitamente para
"investigating a real-time issue reported by a user" -- que es exactamente
este caso -- pero prohíbe usarlo en polling o en bulk.

`full_status_json` (la forma estructurada, no el texto plano de
`full_status_info`) es limpia y anidada por sección
(`"Optical status"`, `"ONU details"`, `"History"`, ...) -- se parsea con
claves de diccionario, sin regex.

## El endpoint masivo — confirma el mismo patrón de filtro ignorado que WispHub

`get_all_onus_details` **sí filtra por `olt_id`** (verificado: sin filtro
5.328 ONUs, con `olt_id=3` solo 804, y las 804 tienen `olt_id: '3'` — filtro
real). **`pon_port` se IGNORA en silencio**: con `pon_port=14` la respuesta
trae puertos del 0 al 15 mezclados, no solo el 14.

Mismo método que ya cazó el `arp_ping` de WispHub — probar con un valor real
y contar cuántos de la respuesta lo cumplen, no confiar en que el nombre del
parámetro implica que funciona.

**Consecuencia**: la regla del splitter (G-GO-11 — "si varias ONUs del mismo
puerto están caídas, es la troncal") **no se puede resolver con una llamada
filtrada**. Hace falta traer las ONUs de la OLT completa (cientos) y filtrar
por `board`+`port` en Python. Eso descarta hacerlo en vivo por conversación —
804 filas es pesado para un turno de chat, y llamar al masivo por cada
mensaje de "no tengo internet" violaría la guía del proveedor de cachear y no
repetir. Si se quiere esta regla, es un trabajo periódico con caché
(`Herramienta.cache_segundos` del plan), no una herramienta conversacional.

## `reboot` ejecutado en vivo (14/08/2026) — contrato confirmado, y el tiempo de recuperación medido

Probado contra la ONU de prueba (`CDTC505AE4AB`, descripción "PRUEBA", la
misma del modo OMCI), con autorización explícita del usuario y en un
equipo que no es de un cliente real:

```
POST /api/onu/reboot/CDTC505AE4AB
-> HTTP 200, 0.56s: {"status": true, "response": "Device reboot command sent"}
```

Contrato confirmado tal cual lo documentaba el proveedor: responde rápido
porque solo confirma que el comando se mandó, no que la ONU ya reinició.

### Dos "tiempos de recuperación" distintos — no confundirlos

Se midieron los DOS, en reinicios separados, y dan numeros muy distintos
porque miden cosas distintas:

| Que se midio | Como | Resultado |
|---|---|---|
| `onu_status` de SmartOLT vuelve a `"Online"` | `last_status_change` tras el reinicio | **~5 min 53 s** |
| El equipo responde ping real (via WispHub, `arp_ping=false`) | Ping cada 5s hasta 3 de 3 exitosos, con timestamps propios | **~73 s** |

La diferencia es real, no ruido de medicion: `onu_status`/`last_status_change`
refleja cuando la OLT termina el re-registro GPON completo (sincronizacion
optica, reaplicar el perfil de servicio) -- un proceso mas lento y mas
completo. El **ping responde mucho antes**, en cuanto el equipo tiene
conectividad IP basica, que es lo que de verdad le importa al cliente
("¿ya tengo internet?").

**Para el texto que le promete algo al cliente, usar el numero del ping
(~1-2 minutos), no el de `onu_status` (~6 minutos)** -- prometer 6 minutos
cuando en la practica vuelve a andar en 1 hace que el asistente parezca
mas lento e inseguro de lo que es en realidad. Sigue siendo un solo dato
por metodo, no una distribucion -- sirve de referencia de orden de
magnitud, no de garantia exacta.

Señal despues del reinicio: `-19.95 / -21.37 dBm`, `"Very good"` --
practicamente identica a antes (`-19.95 / -21.49 dBm`), el equipo volvio
sano en ambos reinicios probados.

**Hallazgo de infraestructura, no de la integracion**: la ficha de
WispHub de esta ONU de prueba (id_servicio 6555, "PRUEBA TEMPORAL", estado
GRATIS -- no aparece en busquedas por `estado=activo`) tenia
`interfaz_lan='ether2'` cargado, un valor que **no correspondia a esta
ONU** y hacia fallar CUALQUIER ping (con o sin `arp_ping`) con
`"input does not match any value of interface"`. El panel web de SmartOLT/
WispHub, dejando el campo "Interface" en blanco, si pingeaba bien -- la
diferencia es que la interfaz vacia SI se omite, una interfaz con un
valor incorrecto NO se ignora aunque el valor este mal. Se corrigio
vaciando `interfaz_lan` en esa ficha puntual. **Implicacion para produccion**:
un cliente real con un `interfaz_lan` incorrecto (no vacio, sino con un
valor que no le corresponde) rompe `ping_cliente` de la misma forma, y el
sintoma seria identico a "el equipo no responde" -- vale la pena tenerlo
presente si alguna vez un ping falla de forma sospechosamente consistente
para UN cliente puntual.

## No verificado todavía (fuera del alcance del sondeo de hoy)

- Si hay dirección/contacto poblados en algún registro real (el que se leyó
  los traía vacíos) — para terminar de calibrar qué tan sensible es el campo.
- `get_running_config` y los endpoints de escritura del script de terceros
  (`update_onu_speed_profiles`, `update_main_vlan`, `move`) — no hicen falta
  para este alcance, no se sondearon.
