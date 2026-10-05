# El aviso push a la app de campo

Qué hay que hacer una vez, quién lo hace, y qué pasa si falta.

---

## 1 · Qué resuelve, y qué no

Antes de esto la app era cien por ciento *pull*: el técnico se enteraba de las
cosas cuando abría una pantalla. Por eso una devolución se le avisaba **a mano
por el chat de Google**, que no era una maña sino el único canal que lo
alcanzaba — y que decía *menos* que lo que la app ya sabía (qué evidencia hay que
volver a tomar está en la ficha).

Hoy un trabajo devuelto produce tres cosas, en este orden y con esta jerarquía:

| # | Qué | Dónde vive | Puede faltar |
|---|---|---|---|
| 1 | **La notificación** — el hecho | `common.Notification`, dentro de la transacción | No. Si la devolución se deshace, se deshace con ella |
| 2 | **El push** — el golpecito en el hombro | FCM, después del commit | Sí. Sin credencial no sale y el log lo dice |
| 3 | **El canal externo** — la entrega opcional | Chat, Slack, Teams, Discord, correo | Sí. Lo configura cada empresa en `/settings/canales/avisos` |

**El push no es la fuente de verdad.** Si no llega —teléfono sin señal, avisos
apagados, batería en ahorro— el registro está igual del otro lado y aparece en la
próxima sincronización. `aceptado ≠ entregado ≠ leído`: un 200 de FCM significa
que Google aceptó el mensaje, no que el teléfono lo mostró.

---

## 2 · Por qué FCM, y por qué no Supabase

En Android **no hay alternativa**. Una app cerrada solo despierta por el canal
del sistema operativo, y ese canal es Firebase Cloud Messaging. Supabase Realtime,
un WebSocket, SSE o un `poll` necesitan proceso vivo — o sea la app en primer
plano, que es justo el caso en que el técnico ya está mirando la pantalla.

Esto se preguntó explícitamente y la respuesta es la misma para cualquier backend:
el proveedor del backend no cambia quién despierta el teléfono.

---

## 3 · Por qué la credencial es de la plataforma y no del tenant

**No es una excepción a `CLAUDE.md` §3.3.** La credencial de FCM no identifica a
una empresa: identifica al **binario** de la app. Hay un solo APK
—`com.dexter.campo`— y todos los técnicos de todas las empresas instalan ese
mismo. El aislamiento por empresa lo da `campo_dispositivo_tecnico.org`, que es
una fila por teléfono, y está medido: `test_d2_el_telefono_de_OTRA_empresa_no_recibe`.

Poner esto en `tenant_config` sería una perilla que nadie puede girar: dos
empresas no pueden tener proyectos de Firebase distintos para el mismo paquete de
Android.

El día que un ISP quiera su app con su marca —otro `applicationId`, otra ficha en
Play— eso cambia, y entonces sí es configuración por empresa. Ese día la decisión
se toma con ese caso adelante.

Lo que **sí** es configuración por empresa y ya está construido: los canales
externos y el dominio de los enlaces, en `/settings/canales/avisos`.

---

## 4 · Los pasos, una sola vez

### 4.1 · En la consola de Firebase — hecho

| Paso | Dónde | Resultado |
|---|---|---|
| Crear el proyecto | console.firebase.google.com | `dexter-app-d4b93` |
| Agregar una app Android | Project settings → Your apps | paquete `com.dexter.campo` |
| Bajar `google-services.json` | la misma pantalla | va a `android/app/google-services.json` |

`google-services.json` **sí va al repositorio**, y no es un descuido: no es un
secreto —la clave de Android que contiene está restringida al paquete más la
huella de la firma, y el `mobilesdk_app_id` es público—. Dejarlo afuera lo
convertiría en un archivo obligatorio que existe en una sola máquina, que es
exactamente la falla que `CLAUDE.md` §6 llama *código construido no es código que
corre*. El que **no** va es la clave de la cuenta de servicio del paso 4.2.

**El paquete tiene que coincidir exactamente** con `applicationId` de
`android/app/build.gradle.kts`. Un `google-services.json` de otro paquete no
falla al compilar: falla en el teléfono, al arrancar, y el mensaje no señala a la
causa. (Pasó: el primer archivo decía `app.dexter_android`.)

### 4.2 · La clave de la cuenta de servicio — lo único que falta

En **Firebase → Project settings → Service accounts → Generate new private key**
se baja un JSON. Ese archivo **es un secreto**: no va al repositorio, no se pega
en un chat, no se lee con una herramienta que deje su contenido en una
transcripción.

Se carga como variable de entorno del servicio `backend`:

```
FCM_CUENTA_DE_SERVICIO=<el JSON completo, en una línea>
```

Acepta las dos formas, y las dos están medidas (`test_f1`, `test_f2`):

- **el JSON completo** pegado como valor — es la que sirve en Dokploy, que
  reparte variables y no archivos;
- **la ruta a un archivo** montado en el contenedor — más cómoda en una máquina
  de desarrollo, donde un JSON de 2 KB en el historial del shell es un problema.

En Dokploy: panel del servicio `crm` → **Environment**. `docker-compose.prod.yml`
ya la reparte al `backend`.

### 4.3 · Qué NO hace falta

- **No hace falta Google Workspace.** Eso era para los *webhooks del chat de
  Google*, que son otra cosa y son opcionales. FCM funciona con una cuenta
  personal.
- **No hace falta suscripción.** FCM no se cobra por mensaje.
- **No hace falta un App Link.** Tocar el aviso abre la app porque el aviso *es*
  de la app. Que un mensaje del chat de Google abra la app directamente sí
  necesitaría un App Link —y eso necesita un dominio del producto sirviendo
  `/.well-known/assetlinks.json` más la huella SHA-256 de la firma—, así que **no
  está construido**: hoy ese mensaje abre el navegador.

---

## 5 · Qué pasa sin la credencial

Nada se rompe, y eso es a propósito:

```
la notificación se escribe        ->  SÍ   (está en la bandeja de la app y en la web)
el canal externo publica          ->  SÍ   (si la empresa configuró uno)
el push sale                      ->  NO
campo_aviso_enviado.canales       ->  sin "push"  (no se afirma un envío que no ocurrió)
el log dice                       ->  push_sin_proveedor
```

Lo que **no** pasa: ni una llamada a Google. Un viaje que va a fallar seguro solo
demoraría el aviso por los canales que sí están configurados. Está medido en
negativo: `test_d1_sin_credencial_no_se_hace_ni_una_llamada`.

Que una **empresa** no tenga canales configurados es el estado normal. Que la
**plataforma** no tenga credencial es un despliegue a medias, y se ve en el log.

---

## 6 · Cómo verificar que funciona, en orden

Cada paso se puede comprobar solo, y el orden importa: si el 2 falla, el 3 no
dice nada.

**1. El teléfono se registró.** Entrar a la app con una sesión válida y mirar:

```sql
select plataforma, activo, created_at, visto_en
from campo_dispositivo_tecnico
where org_id = '<org>' and profile_id = '<perfil>';
```

Si no hay fila: o Firebase no arrancó (falta `google-services.json` en el APK), o
el `POST /api/campo/dispositivo/` falló. El log de la app lo dice con
`push: …`.

**2. El servidor tiene credencial.** Devolver un trabajo y mirar el log del
`backend`. `push_sin_proveedor` significa que falta la variable; `fcm_rechazado`
con un código, que la credencial está pero algo más está mal;
`fcm_credencial_invalida`, que el JSON no se pudo leer.

**3. El aviso llega.** Devolver un trabajo desde la bandeja de validación con el
teléfono **en segundo plano** (no cerrado ni abierto: es el caso intermedio y el
que más se rompe). Tiene que aparecer la notificación del sistema, con sonido.

Sin sonido y con la notificación visible = el `channel_id` no coincide con el del
AndroidManifest: Android metió el aviso en un canal `Miscellaneous` sin sonido.
Está medido (`test_a6`), pero el desajuste puede venir del lado de la app.

**4. Tocarlo abre la orden.** No la pantalla de inicio. Probarlo con la app
**cerrada**, que es el camino distinto: el toque llega antes de que exista el
contenedor, así que el servicio lo guarda y el shell lo reclama al montarse
(`AvisosPush.tomarOrdenPendiente`).

**5. El aviso quedó en la bandeja de la app, completo.** Inicio → bloque
"Avisos". Tiene que decir qué pasó, qué escribió el supervisor y qué hay que
volver a tomar. Un aviso vacío significa que el espejado guardó la fila con las
claves equivocadas — es lo que miden `a1` y `a2` de
`test/push_al_telefono_test.dart`.

---

## 6.bis · Probarlo sin teléfono, de punta a punta

Las cinco comprobaciones de arriba necesitan un teléfono. Hay una que no, y es la
que contesta *«¿esto corre de verdad en la topología real, o solo en las
pruebas?»* — la pregunta que `CLAUDE.md` §6 llama **código construido no es código
que corre**.

La idea: registrar un teléfono con un token deliberadamente falso y disparar el
aviso. FCM contesta de verdad, el código interpreta esa respuesta de verdad, y el
resultado correcto es que **el aviso no llegue y el teléfono quede dado de baja**.
Eso recorre la cadena entera —búsqueda por empresa, credencial, llamada HTTPS a
Google, lectura del error real, baja del token— sin inventar nada.

```python
from common.models import Profile
from campo.avisos import DispositivoDeTecnico
from campo.services import avisos

perfil = Profile.objects.filter(is_active=True).select_related('org').first()
TOKEN = 'TOKEN-DE-HUMO-QUE-NO-EXISTE-EN-NINGUN-TELEFONO'
d = DispositivoDeTecnico.objects.create(
    org=perfil.org, profile=perfil, token=TOKEN, activo=True)

llego = avisos._notificar_a_telefonos(
    org=perfil.org, perfiles=[perfil],
    titulo='OT #9401 devuelta', texto='Prueba de puesta en marcha',
    enlace='/ot/00000000-0000-0000-0000-000000000000',
    avisos_por_perfil={perfil.id: 'aviso-de-humo'},
    contenido={'vuelta': 2, 'rehacer': [], 'orden_numero': 9401})

d.refresh_from_db()
assert llego is False          # el token es falso
assert d.activo is False       # FCM dijo que no existe, y se dio de baja
d.delete()
```

Corrido el 04/10/2026 contra `dexter-app-d4b93`: **las dos afirmaciones se
cumplen**. Si en cambio `d.activo` quedara en `True`, hay que mirar el log: o no
hay credencial (`push_sin_proveedor`), o FCM contestó otra cosa (`fcm_rechazado`
con su código) — y entonces el problema no es el teléfono.

Montar el secreto en un contenedor de laboratorio se hace **por ruta**, nunca
pegando el JSON: así su contenido no pasa por una consola ni por una
transcripción.

```
-v C:/secretos/fcm.json:/etc/secrets/fcm.json:ro
-e FCM_CUENTA_DE_SERVICIO=/etc/secrets/fcm.json
```

---

## 7 · Un token que deja de servir

Un token muere al reinstalar la app, al limpiar datos o por decisión de Google.
FCM lo dice con `UNREGISTERED`, y entonces el teléfono se marca `activo = false`
**sin borrar la fila**: que dejó de servir y *cuándo* es lo que permite contestar
por qué un aviso no llegó.

**Cómo se reconoce uno, y por qué no alcanza con el código HTTP.** Medido contra
FCM el 04/10/2026 con la credencial de `dexter-app-d4b93`: un token inválido y un
cuerpo mal armado devuelven **el mismo 400 con el mismo `status: INVALID_ARGUMENT`**.
Lo único que los separa es que el cuerpo mal armado **no trae `errorCode`**:

| Qué se mandó | `errorCode` | `fieldViolations` |
|---|---|---|
| token inválido | `INVALID_ARGUMENT` | `message.token` |
| un entero en `data` | *ninguno* | `message.data[0].value` |
| un campo inexistente | *ninguno* | `message` |
| una prioridad inválida | *ninguno* | `message.android.priority` |

Por eso `_es_token_muerto` mira `errorCode` y no `status`. Si mirara el `status`,
un error de programación nuestro daría de baja los teléfonos de toda la cuadrilla
de un saque, y el síntoma aparecería días después sin señalar a la causa. Lo
cuidan `test_c7` y `test_c8`, con las respuestas reales de esa corrida.

La misma corrida confirmó lo otro que no se podía saber leyendo: **el cuerpo que
arma el código es válido para FCM** — con un token falso, la única violación que
devuelve es `message.token`.

La distinción importa en las dos direcciones, y las dos están medidas:

- dar de baja por un **500 de Google** dejaría al técnico sin avisos hasta que
  reinstale, y nadie relacionaría las dos cosas (`test_c4`);
- no dar de baja un `UNREGISTERED` haría que cada aviso futuro pague un viaje a
  Google para que lo rechacen (`test_c1`).

Si el técnico vuelve a abrir la app, el registro **revive** la fila (`test_g2`).
Si cerró sesión, el teléfono se da de baja antes de borrar las llaves — un
teléfono de cuadrilla pasa de mano en mano, y el que entra no tiene por qué
recibir los avisos del que salió.

---

## 8 · Privacidad

El push **no lleva datos del cliente**: ni nombre, ni dirección, ni teléfono.
Está medido afirmando sobre el cuerpo completo del mensaje
(`test_b1_el_push_no_lleva_nombre_direccion_ni_telefono_del_cliente`), no sobre
las claves que se mandan — así sigue valiendo cuando alguien agregue un campo.

La razón: un push se queda en la bandeja del sistema operativo, que es lo más
parecido a un lugar público que tiene un teléfono. Lo que va es lo que hace falta
para actuar — la vuelta, qué hay que rehacer, lo que escribió el supervisor — y el
detalle del cliente sigue en la ficha, detrás de la sesión.

El **token** tampoco se registra en el log, ni completo ni truncado
(`test_e3_el_token_no_aparece_en_el_log`): identifica un teléfono y vive en el log
mucho más que en la base.

**Pendiente, y es una decisión de producto, no técnica:** el token del dispositivo
viaja a Google. La autorización de tratamiento que firma el cliente (Ley 1581
art. 26) nombra al proveedor del modelo; un tercero nuevo exige resolver eso. Lo
que atenúa el caso: a Google no va ningún dato personal, solo un identificador de
dispositivo y un texto sin PII. La decisión es del usuario; el código está listo
para quedarse apagado hasta entonces, y apagado es exactamente lo que es sin la
variable.

---

## 9 · Dónde vive cada pieza

| Pieza | Archivo |
|---|---|
| El envío a FCM | `django-crm/backend/campo/services/push_fcm.py` |
| A quién y con qué texto | `django-crm/backend/campo/services/avisos.py` |
| El registro del teléfono | `django-crm/backend/campo/views.py::DispositivoDeCampoView` |
| El modelo del teléfono | `django-crm/backend/campo/avisos.py::DispositivoDeTecnico` |
| El lado de la app | `apps/tecnicos-mobile/lib/core/avisos/avisos_push.dart` |
| La bandeja de avisos | `apps/tecnicos-mobile/lib/features/notificaciones/notificaciones_screen.dart` |
| Guarda del servidor | `django-crm/backend/campo/tests/test_push_al_telefono.py` |
| Guarda de la app | `apps/tecnicos-mobile/test/push_al_telefono_test.dart` |
