# Avisarle al técnico

**Estado:** canal de chat **construido y probado**, sin desplegar. Push a medias
a propósito: falta una credencial que no está en este repositorio. App Link **no
construido**, y abajo está por qué.

## De dónde sale

De una pregunta sobre la app: *«¿qué le gustaría ver a un técnico?»*. Al medir
las respuestas apareció que **la información sobre el trabajo vive fuera del
sistema**:

- cuando falta un dato, el técnico **llama al NOC o escribe al grupo**;
- cuando le devuelven un trabajo, **se lo avisan por Google Chat**.

## Lo que se midió antes de construir

**La app no tiene forma de decirle nada al técnico.** No hay push ni en la app
(`pubspec.yaml` sin `firebase_messaging` ni equivalentes) ni en el backend
(`campo/` sin nada de push). Y la cola de sincronización **solo corre cuando
alguien toca la pantalla**: no hay `Timer.periodic` ni escucha de conectividad —
que es la misma razón por la que `minutos_contacto_reciente` viene apagado.

Es cien por ciento *pull*. Google Chat no es una maña: **es el único canal que
alcanza al técnico.**

**Y el mensaje escrito a mano dice menos que lo que la app ya sabe.** La ficha
muestra la devolución completa —vuelta, observación del supervisor, y qué
evidencia hay que volver a tomar— y el chat solo dice que te devolvieron algo.

**El costo es de los caros.** Si el técnico sigue en la casa, volver a sacar una
foto no cuesta nada; si ya se fue, es un viaje. Es lo que la industria mide como
*first-time fix rate*: el promedio está en 70-75% y una de cada cuatro visitas
vuelve.

## Las decisiones

**1 · Se adopta el atajo en vez de pelearle.** El sistema publica donde el
técnico ya mira. No entra un tercero nuevo y es backend puro: no hay versión
nueva de la app que instalar en los teléfonos.

**1 bis · Ningún proveedor nombrado en el esquema (corregido el 04/10/2026).**
La primera versión tenía un campo llamado `chat_webhook` y mandaba el formato de
Google Chat. Lo escribí mal: eso pone el nombre de un proveedor en la
estructura, y la empresa siguiente usa Teams, o Slack, o quiere un correo.

Ahora hay un `tipo` y **N canales por empresa** —una puede querer el chat de la
cuadrilla **y** una copia al correo del coordinador—. Y los proveedores no son
todos distintos: Google Chat, Slack, Teams, Discord y Mattermost son el mismo
gesto, un POST con un JSON de una clave. Lo único que cambia es **cómo se llama
esa clave**, y eso cabe en una tabla del modelo: agregar un proveedor es una
línea, no una clase.

El correo es el mínimo común denominador: funciona en toda empresa sin que nadie
configure nada del otro lado.

**1 ter · Lo configura la empresa, no un programador (corregido el 04/10/2026).**
La primera versión guardaba el webhook en una fila que solo se podía cargar por
consola. La regla del proyecto no dice «configuración por empresa»: dice
*editable desde la interfaz y persistida por tenant, nunca un valor fijo en
código **ni en un archivo que solo un desarrollador sabe editar***. Una fila
cargada a mano es la misma falla con otra cara.

Hay pantalla en `/settings/canales/avisos`, con el patrón que el repositorio ya
tenía resuelto para SmartOLT y las credenciales del asistente:

- **el rol decide quién edita** — un técnico no decide a dónde sale la
  información de la empresa, aunque sí puede mirar;
- **el destino va en un solo sentido y no vuelve** — en un webhook esa URL *es*
  la credencial: la pantalla recibe una pista, no el valor;
- **hay botón de probar, y recorre el mismo camino que un aviso de verdad.**
  Pegar una URL y no saber si sirve es como se pudren estas configuraciones:
  alguien la carga, nadie la prueba, y el día que hay una devolución el aviso no
  llega y nadie sabe desde cuándo. Una prueba que usa otro camino prueba otra
  cosa.

Y **qué tipos existen lo dice el backend**, no una lista escrita en el frontend:
el día que se agregue Mattermost aparece solo en el desplegable.

**2 · El aviso sale DESPUÉS del commit.** `requerir_correccion` es
`@transaction.atomic` y el proyecto tiene una decisión congelada: *ninguna
transacción de base abierta mientras se espera una operación externa*. Se
engancha con `transaction.on_commit`, que además da la garantía correcta: **si la
devolución se deshace, el aviso no sale**.

**3 · Un aviso que falla no rompe el hecho.** El supervisor devolvió el trabajo;
que el webhook esté caído es otro problema y no puede revertir una transición.

**4 · El mismo hecho se avisa una sola vez**, por clave primaria y no por un
`select` previo —ahí vive la carrera—. La clave describe el hecho
(`devolucion|<orden>|<vuelta>`), no el intento. Un técnico que recibe el mismo
aviso repetido apaga las notificaciones.

**5 · Sin datos del cliente.** Un mensaje de chat sale del sistema y queda en una
conversación que nadie audita. Lleva el número de la OT, qué hay que rehacer y un
enlace: quien lo abre se autentica y ahí sí ve la ficha.

**6 · El webhook es dato de la empresa**, no una constante. Regla multi-tenant.

**7 · El título, no el id.** El aviso dice «Fotografía de la medición», no
`foto_medicion`, y sale de la plantilla **inmutable** de la orden — así un cambio
posterior del tipo de trabajo no reescribe lo que se pidió ese día.

## Qué se midió

```
16 pruebas del aviso, contra PostgreSQL real y con COMMITS REALES
19 pruebas de la configuración
```

Lo último no es un detalle del andamiaje: todo esto depende de
`transaction.on_commit`, y con la base envuelta en una transacción que nunca se
confirma —el modo normal de pytest-django— **esos callbacks no corren nunca**.
Las pruebas habrían pasado en verde sin haber enviado nada: exactamente el tipo
de prueba que §6 llama *en verde con el síntoma vivo*. Por eso el módulo corre
con `transaction=True`.

Cinco mutaciones las atacan: avisar dentro de la transacción, avisar dos veces el
mismo hecho, mandar el id del campo en vez del título, poner el nombre del
cliente en el aviso, y afirmar un push que no ocurrió.

## Push: lo que está y lo que falta

**Construido:** el registro del teléfono (`POST /api/campo/dispositivo/`,
idempotente porque la app lo manda en cada arranque), la baja al cerrar sesión
—un teléfono de cuadrilla pasa de mano en mano—, y el despacho completo: a quién,
con qué texto, sin duplicar, sin datos del cliente.

**Falta el proveedor**, y necesita dos cosas que no están en el repositorio: un
proyecto de Firebase con su `google-services.json`, y una cuenta de servicio para
que el backend llame a FCM.

Hoy `_enviar_una` devuelve `False` y lo registra en el log. **A propósito**: el
ledger queda con `canales: ["chat"]` y no afirma un envío que no ocurrió. Hay una
prueba sobre eso.

**Supabase no cambia esto.** Se consultó (04/10/2026): no tiene servicio de push
propio —no existe un `supabase.notifications.send()`— y su propia documentación
describe el patrón *trigger → Edge Function → FCM*. La razón de fondo no es de
Supabase: en Android, la notificación que llega con la app cerrada la entrega el
sistema operativo y el único canal es FCM. Su **Realtime** avisa con la app
abierta, que es justo el caso que no hay que cubrir.

Y el aviso **no sale de un trigger de base** aunque la base sea Supabase: el
servidor de aplicación es Django, la devolución es una transición con reglas —no
un `INSERT` suelto—, y poner la lógica del aviso en una Edge Function la dejaría
viviendo en dos lugares.

**Una pregunta que se contesta antes de encenderlo, no después:** el token del
dispositivo viaja a Google. En este proyecto un tercero nuevo exige resolver la
autorización de tratamiento primero — la misma regla que tiene a Sentry apagado.
El aviso no lleva datos del cliente, así que el riesgo es acotado, pero la
decisión se registra antes.

## App Link: por qué NO se construyó

El enlace del chat podría abrir la orden **dentro de la app** en vez del
navegador. Es un App Link de Android y necesita tres cosas:

1. un dominio de la empresa sirviendo `https://<dominio>/.well-known/assetlinks.json`;
2. la huella SHA-256 del certificado con que se firma el APK, dentro de ese archivo;
3. un `intent-filter` en el manifiesto y un paquete en Flutter para recibirlo.

**Sin (1) y (2) el filtro no se verifica y el enlace abre el navegador igual.**
Construir solo (3) dejaría código muerto esperando una configuración que no
existe — que es exactamente el defecto que este módulo pasó el día quitando: la
«Guía FTTH», los botones de llamar y mapa, el «Escanear QR».

Mientras tanto el enlace **funciona y degrada bien**: abre el CRM en el
navegador, y al supervisor en el escritorio le sirve igual.

**Y hay una decisión de forma que conviene tomar antes de construirlo.** El host
del App Link es de **tiempo de compilación**: Android lo verifica contra ese
dominio. Un host por empresa obligaría a **una compilación por empresa**, que es
contra la regla multi-tenant. Lo correcto es **un host del producto con el tenant
en la ruta** (`https://campo.<producto>/t/<slug>/ot/<id>`): una compilación, un
`assetlinks.json`, N empresas.

## Lo que hace falta de afuera

| Para | Qué se necesita |
|---|---|
| Encender el chat | La URL del webhook del espacio, y el dominio para los enlaces |
| Encender push | Proyecto de Firebase + `google-services.json` + cuenta de servicio |
| Construir el App Link | El dominio del producto, control del `/.well-known/`, y la huella del certificado de firma |
