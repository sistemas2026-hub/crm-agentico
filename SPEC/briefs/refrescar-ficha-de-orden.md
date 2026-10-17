# Brief · Refrescar la ficha del cliente de una orden ya despachada

> Autocontenido a propósito: quien lo reciba no tiene el repositorio ni la
> conversación donde salió. Todo dato de código lleva su ruta para que lo
> **verifiques**, no para que me creas. Si algo de acá no coincide con el
> código, manda el código.

## 1 · El sistema, en cinco líneas

Dexter es un asistente de IA para ISPs (proveedores de internet), multi-empresa.
Tiene tres piezas que corren juntas:

| Pieza | Qué es | Tecnología |
|---|---|---|
| **Motor** (`nucleo/`) | El agente: habla con WispHub (el sistema del ISP) y SmartOLT | Python 3.13 · Flask |
| **CRM** (`django-crm/`) | Gestión y pantallas. Incluye el módulo `campo` | Django + DRF · SvelteKit |
| **App de campo** (`apps/tecnicos-mobile/`) | Lo que usa el técnico en el terreno | Flutter, con operación **sin señal** |

Una **orden de trabajo** (`campo.OrdenTrabajo`) es una visita que un técnico
hace a un cliente. Nace de un **caso** (`cases.Case`), que a su vez nace de un
ticket importado del ISP o de una conversación de WhatsApp.

## 2 · Qué es la "ficha" y por qué está congelada

Al crear la orden, el despacho le pide al motor los datos técnicos del cliente
y los **congela** dentro de `OrdenTrabajo.contexto` (un `JSONField`).

Código: `django-crm/backend/campo/services/despacho.py`
→ `contexto_del_caso()` · `depurar_contexto()` · `sin_contexto()`

Su docstring explica el porqué, y **no es negociable**:

> *"Al congelarse, una medición deja de ser una medición: pasa a ser un registro
> de lo que se veía en un momento. Sin la hora al lado es una afirmación sobre
> el presente que nadie puede verificar."*

Por eso el snapshot lleva `capturado_en` y `fuente`. Forma real de hoy:

```json
{
  "contexto_disponible": true,
  "capturado_en": "2026-09-24T19:39:15+00:00",
  "fuente": "motor/contexto_tecnico",
  "servicio": "5832",
  "cliente": { "nombre": "...", "direccion": "...", "telefono": "...",
               "localidad": "...", "ip": "...", "estado": "...", "plan": "..." }
}
```

Los campos del cliente pasan por una lista blanca (`CAMPOS_CLIENTE_SNAPSHOT`,
mismo archivo). **La cédula, las contraseñas y el GPS NO entran, y eso no se
toca**: la fila del cliente en el ISP trae 54 campos, cuatro de ellos
contraseñas.

## 3 · El problema

**No existe ninguna forma de volver a capturar esa ficha.** Si al despachar el
cliente tenía datos incompletos en el sistema del ISP —o directamente el motor
no respondió— la orden queda con esa foto para siempre, y el técnico ve
"Sin dirección" aunque alguien haya cargado la dirección después.

Es un caso real y frecuente: un ticket se importa apenas se abre, y los datos
del cliente se completan más tarde.

Hoy la única forma de arreglarlo es un script contra la base.

## 4 · Lo que ya existe y hay que reusar

**1 · El motor ya resuelve la ficha.**

```
GET /conversaciones/por-caso/<case_id>?tenant=<slug>&servicio=<id_servicio>
```

Devuelve el contexto crudo; `depurar_contexto()` lo filtra. El parámetro
`servicio` importa: un caso importado del ISP **no tiene conversación detrás**,
así que sin él la identidad no se resuelve.

**2 · La ausencia de ficha ya está tipificada.** `sin_contexto(motivo, motor_alcanzado=)`
produce tres casos que la app distingue, y **cada uno se arregla distinto**:

| `motivo` | Significa | Qué hace el técnico |
|---|---|---|
| `ConnectionError` (u otro fallo) | No se pudo preguntar | **Reintentar sirve** |
| `sin_identidad_resoluble` | Se preguntó y no se identificó al cliente | Preguntarle en sitio |
| `caso_sin_servicio` | El caso no tiene servicio asociado | **No se arregla nunca** |

Lo lee `apps/tecnicos-mobile/lib/features/trabajo/trabajo_vista.dart`
(enum `SinFicha`).

**3 · Hay bitácora append-only**: `campo.EventoTrabajo` (`tipo`, `profile`,
`datos`). Su texto de ayuda ya menciona `datos_actualizados` como tipo de evento.

**4 · La orden tiene `revision`** (entero), que el backend usa para detectar
escrituras concurrentes.

## 5 · Qué hay que construir

Una forma de **volver a capturar la ficha** de una orden ya despachada.

### Criterios de aceptación

| # | Qué | Cómo se comprueba |
|---|---|---|
| A1 | Refrescar reemplaza el snapshot y actualiza `capturado_en` | Contexto viejo → refrescar → `capturado_en` posterior y campos nuevos |
| A2 | **Queda registrado quién y cuándo** | Un `EventoTrabajo` por refresco, con el perfil que lo pidió |
| A3 | Un refresco fallido **no destruye la ficha que había** | Con el motor caído, el contexto anterior sigue intacto. Es la propiedad más importante |
| A4 | No pisa lo que escribió una persona | Ver §6 |
| A5 | La lista blanca sigue siendo la misma | Cédula, contraseñas y GPS no entran por este camino tampoco |
| A6 | No se puede refrescar una orden cerrada o cancelada | Su ficha es parte del acta |

### Preguntas de diseño que hay que responder, no asumir

- **¿Quién puede refrescar?** ¿El técnico desde la app, o solo el supervisor?
  Si es el técnico: la app trabaja **sin señal**, así que hay que definir qué
  pasa cuando lo pide sin conexión (¿se encola? ¿se rechaza?).
- **¿Se guarda el historial de fichas o solo la última?** Hay argumento para las
  dos. El proyecto valora poder responder *"qué se veía cuando el técnico fue"*.
- **¿Refresco manual, automático, o los dos?** Uno automático al abrir la orden
  le pega al sistema del ISP en cada apertura.

## 6 · La trampa principal

`OrdenTrabajo` tiene `cliente_nombre`, `cliente_direccion` y `cliente_telefono`
**como columnas propias**, además de la ficha. Las llena quien despacha, a mano,
desde un formulario.

**Un refresco que las sobrescriba con lo que dice el ISP puede destruir trabajo
humano.** Caso concreto: el despachador escribió *"Casa portón verde, timbre
roto, llamar al llegar"* y el ISP tiene *"Cl. 45 #12-88"*. La segunda es peor
para el técnico.

Hay que decidir explícitamente qué gana, y escribir el motivo. No lo resuelvas
en silencio.

## 7 · Reglas del proyecto que no se rompen

- **Fail-closed.** Ante la duda, no hay dato. Nunca se inventa un valor por
  defecto ni se rellena un hueco con algo plausible.
- **"Lo que la orden no trae, no se dibuja."** Un campo vacío se muestra vacío.
- **`django-crm` no habla con WispHub ni con SmartOLT.** No tiene las
  credenciales y no debe tenerlas. Todo dato externo se le pide al motor.
- **La base tiene RLS por organización.** Cualquier escritura necesita el
  contexto fijado (`common.tasks.set_rls_context`), o Postgres la rechaza.
- **Afirmar sobre el efecto, nunca sobre la presencia del mecanismo.** Una
  prueba que comprueba que una función existe no prueba que funcione.
- **Distinguir "no se pudo medir" de "se midió y falló".** Son cosas distintas y
  se muestran distinto.

## 8 · Qué NO hacer

- No agregar campos a `CAMPOS_CLIENTE_SNAPSHOT` sin decir por qué.
- No hacer que Django llame al ISP directamente.
- No refrescar automáticamente en cada apertura sin medir el costo: el sistema
  del ISP tiene límite de tasa (SmartOLT: 1.000 llamadas/hora, confirmado por
  cabecera).
- No borrar el snapshot anterior antes de tener el nuevo en mano.

## 9 · Cómo se verifica el trabajo terminado

El proyecto corre sus guardas a mano y por CI. Las que aplican acá:

```
docker exec <backend> python -m pytest campo/tests/ -q --no-cov
py -3.13 cli/correr_pruebas.py --sin-base --sin-red
```

Y la prueba que más importa escribir es **A3**: que un refresco fallido deje la
ficha anterior intacta. Es la única que, si falla, hace perder datos.
