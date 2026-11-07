# Agente de campo para el técnico instalando

**Estado:** encuadrado, **no se construyó nada** · **Anotado:** 02/11/2026

> **Por qué queda anotado y no se arrancó.** El usuario: *«dejalo anotado para
> después, que están haciendo un cambio que da otro punto de vista»*. Hay
> trabajo en curso de otra sesión que puede mover los supuestos de abajo.
> **Antes de retomar esto, releer lo que haya cambiado**, en especial la
> autonomía por agente y lo que se decida sobre acciones críticas.

## Qué pidió el usuario

> *«se crearía para que ayude al técnico al momento de realizar una
> instalación, a llenar los formularios y adjuntar los documentos, autorizar
> el equipo en SmartOLT y demás funciones que uno le indique. Este agente lo
> supervisa el agente Supervisor IA. El técnico empieza y gestiona la
> instalación desde la app — aún no está habilitado instalación.»*

Y confirmó después: **la misma app y el mismo técnico** hacen soporte,
instalación y cualquier otro trabajo. Una instalación es **un tipo de trabajo
más**, no un flujo aparte.

## El hallazgo que ordena todo

**Lo que falta no es un agente.** Falta (a) autorizar la ONU en SmartOLT, que
no existe ni como herramienta ni como endpoint verificado, y (b) el alta del
cliente en WispHub, verificada en la skill pero sin herramienta y sin un solo
llamador. El agente es la última capa; hoy no tendría nada que ofrecer.

## Lo que ya existe, y no hay que volver a construir

| Pieza | Estado |
|---|---|
| Labor `instalacion` + plantillas de partida `instalacion_fibra` y `traslado_servicio` | ✅ de fábrica. `instalacion_fibra`: 120 min, 5 campos (serial ONU, metros de fibra, potencia en roseta −28/−8 dBm, WiFi probada, cliente informado), 4 evidencias, 2 obligatorias |
| El ciclo completo de la orden, el checklist que bloquea el cierre, la cola offline de evidencias | ✅ y **no distinguen labor** |
| El clasificador que separa instalación de correctivo | ✅ por el cliente de instalaciones del ISP; 220 de 220 acertados (08/10/2026) |
| La IA mirando las fotos contra las instrucciones de la plantilla | ✅ desplegado el 31/10–01/11/2026 |
| El serial del equipo volviendo al ISP solo | ✅ `lazo_isp.py` |
| La revisión del cierre por el Supervisor | ✅ |
| El canal de aviso al técnico | ✅ salvo el proveedor de push |

**«No está habilitado instalación» no es código: es configuración.** Cuatro
cosas, todas desde pantallas: adoptar la plantilla y **publicar** su versión;
declararle **asuntos** (con dos plantillas de la misma labor y sin asuntos, el
caso **no se despacha**); una cuadrilla con labor habitual `instalacion`; y
`hora_de_corte` (sin eso el Supervisor no crea órdenes solo). **Medirlo es una
lectura, no un desarrollo.**

## Los huecos reales

1. **Autorizar la ONU: no existe y NO ESTÁ VERIFICADO.** La skill de SmartOLT
   (788 líneas) no tiene la operación; solo el campo de lectura
   `authorization_date`. Escrituras conocidas: `reboot` (ejecutada en vivo) y
   las cinco de CATV (documentadas, ninguna ejecutada). Nada sobre ONU sin
   autorizar ni cómo descubrirlas — el enum de estados medido no incluye un
   «sin autorizar». **Sondear con `GET` + id imposible MIENTE acá**: seis
   candidatos de CATV dieron 405 y existían. Lo que funciona es bajar la
   colección oficial. Es trabajo de `verificador-de-api`.
2. **Sería la SEXTA herramienta `irreversible`** del sistema. Es la única de
   su familia que **crea** algo en la OLT —ocupa puerto y compromete recursos—
   y el deshacer no lo midió nadie. Entra en M06-D como `INDETERMINADA` hasta
   que haya evidencia. Obliga a actualizar `CLAUDE.md §5`, `M06-D` y
   `tests/test_m06d_matriz_autonomia.py`. Y choca con
   `SPEC/objetivos/reemplazo-de-mano-de-obra.md`, donde las críticas *«se
   quedan como están»*.
3. **Alta del cliente en WispHub**: endpoint **sí verificado en vivo**
   (`POST /api/clientes/agregar-cliente/{id_zona}/?instalacion`, respuesta
   asíncrona con `task_id`), sin herramienta y sin llamador. Y exige un cruce
   **IP ↔ zona que no está modelado en ninguna parte** — la skill dice que no
   hay forma de saberlo sin conocer la topología. Ese mapa es **configuración
   de la empresa**, no una tabla en código.
4. **Adjuntar documentos HOY NO SE PUEDE.** El backend acepta
   `foto|documento|firma` y el storage acepta PDF, pero el editor guiado solo
   emite `foto` y **la app no tiene selector de archivos** (`image_picker` sí,
   `file_picker` no existe). Solo entra una foto del documento.
5. **Grieta de contrato en la firma**: la app escribe `campoClave:
   'firma_receptor'`, un campo que ninguna plantilla declara y que el backend
   no conoce. Síntoma anotado: orden cerrada en el teléfono y trabada en el
   servidor.

## Lo que mata al agente conversacional en campo, y hay que decirlo primero

**El técnico trabaja sin señal.** La app es offline-first con cola. Un turno
de conversación **no se puede encolar**: se ejecutaría cuando el técnico ya se
fue, midiendo un momento que a nadie le importa — el mismo criterio ya escrito
para `ProbarConexionView`.

Un agente conversacional en campo es, por construcción, **una capacidad que
existe solo con red**, y la app tiene que decirlo en la cara en vez de fallar
en silencio.

## La app no habla con el motor, y no hace falta que empiece

Las ~45 rutas de la app van todas a Django. El motor ya se consume **desde la
app por el backend**, dos veces y con el contrato de error ya diseñado
(`probar-conexion` → `ping_cliente`, `medir-senal` → `consultar_senal_ont`).
Un segundo camino significaría una segunda credencial de servicio en un
teléfono.

Y la ruta del motor que presta el modelo ya existe y es genérica en los
hechos: su docstring dice *«No sabe de qué está hablando»*. El bucle de
razonamiento también existe y acepta `tools` como parámetro.

> **⚠️ Filo que hay que cerrar ANTES de reusar ese bucle.** El ejecutor de
> herramientas del chat es **un dict global sin dueño** y no filtra por actor.
> Pasarle `tools` acotado solo cambia lo que el modelo *ve*: si nombra
> `delegar_tarea`, se ejecuta igual — y eso **enciende tareas autónomas del
> Supervisor**. Hoy lo contiene el permiso de la ruta (jefe de operaciones),
> no el catálogo. Un agente del técnico que herede eso sería un técnico en la
> calle encendiendo autonomía. **Se arregla en el ejecutor, no en el prompt.**

## «Lo supervisa el Supervisor IA»: qué significa con lo que hay

Supervisar **el trabajo** está construido. Supervisar **a un agente** no
existe. La forma que el proyecto ya eligió para medir una IA es el par
*(lo que dijo la IA, lo que dijo la persona)* como **filas separadas**, nunca
un `UPDATE` — ver `AnalisisDeEvidencia`.

Lectura propuesta: no es una capa nueva, es eso generalizado. El agente deja
su sugerencia como fila, el técnico decide, y la revisión del cierre gana **un
punto más que puede valer `True` o `None` y nunca `False`** — la decisión
congelada del 31/10/2026. Lo que **no** es extensión es que el Supervisor
*autorice* acciones: eso es la frontera del motor, y el Supervisor **no
ejecuta nada** por diseño.

## El plan, cuando se retome

**Prerrequisitos, antes de la etapa 1:**

- **P1** — medir qué falta de la configuración de instalación en la org real.
  Es una lectura.
- **P2** — `verificador-de-api` sobre SmartOLT: existe el endpoint, con qué
  parámetros, qué devuelve y **cómo se deshace**. Sin esto no puede entrar al
  catálogo.
- **P3** — la decisión del usuario, abajo.

**Etapa 1 · «Autorizar la ONU desde la app». Sin modelo.** Hoy el técnico
instala, escribe el serial y **se sale de la app** a autorizar en el panel de
SmartOLT. Ese salto es lo que de verdad cuesta, es determinista y **funciona
con mala señal**. Herramienta en el catálogo (config, patrón de
`actualizar_sn_onu` y `reiniciar_ont`), servicio en `campo/services/` espejo
de `lazo_isp.py`, endpoint en campo, botón en el detalle de la orden como
`probar-conexion`. **Sin señal se rechaza, nunca se encola.** Es alcance, no
autonomía: sigue habiendo aprobación humana atada antes del efecto.

**Etapa 2 · El alta del cliente en WispHub.** Antes hay que modelar el mapa
IP↔zona como configuración del tenant.

**Etapa 3 · Ahí sí el agente.** Rol en `tenant_config` editable desde
`/agentes`, catálogo propio **partido por rol** (ver el filo de arriba), bucle
en Django, modelo prestado por el motor. Y el conocimiento operativo de
instalación en `directivas/`: hoy el corpus del RAG es una sola guía de
atención al cliente, **no hay manual de instalación ingestado**. Un agente de
campo sin eso no tiene nada que saber que el formulario no diga ya.

## Qué NO hay que crear

Un cliente HTTP al motor en la app · una ruta de chat nueva en el motor · un
segundo bucle de razonamiento · una tabla de conversación nueva · un canal de
aviso al técnico · una tubería de visión · un registro de «equipo instalado en
el cliente X» (eso lo sabe WispHub, frontera ya fijada) · una plantilla de
instalación nueva · un catálogo de prompts por empresa.

Y un cuidado de catálogos con la misma forma que **no son el mismo**: la
`zona` de WispHub (la del alta, con el servidor en el nombre), la `zone` de
SmartOLT (medida como ignorada en un filtro), las `ZonaDeReparto` de campo, y
`localidad`/`ciudad` del cliente son **cuatro identificadores independientes**.
El alta los cruza todos, y es donde ya costó tiempo.

## Decisiones pendientes, las dos del usuario

1. **¿Qué es este agente?** (a) un **asistente determinista** en la app:
   botones que ejecutan lo que hoy obliga a salirse, con validación en código
   y aprobación humana atada — sin modelo, anda con mala señal; o (b) un
   **agente conversacional**. No son excluyentes, pero **(b) sin (a) no tiene
   nada que ofrecer**. **Recomendación: (a) primero.**
2. **¿El agente de campo podría alguna vez autorizar una ONU solo?** Hoy la
   respuesta del repositorio es no. Si la intención es que sí, **se decide y
   se registra con fecha antes de la primera línea**, no se descubre al final
   — igual que se hizo el 31/10 con «el punto de IA nunca vale `False`».

## Bitácora

| Fecha | Qué | Evidencia | Hash |
|---|---|---|---|
| 02/11/2026 | **Encuadrado y aparcado a pedido del usuario.** Barrido completo: `apps/tecnicos-mobile/lib/` entero (91 `.dart`), `campo/` (57 módulos), la skill de SmartOLT (788 líneas), la de WispHub, `M06-D`, el catálogo (91 herramientas, 9 roles). Nada construido, ninguna API llamada, producción no leída | informe del arquitecto | — |
