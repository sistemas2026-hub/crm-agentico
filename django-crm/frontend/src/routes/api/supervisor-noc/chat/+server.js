import { json } from '@sveltejs/kit';
import { apiRequest } from '$lib/api-helpers.js';
import { traducirError } from '$lib/server/v2/supervisor-noc.js';

/**
 * EL CANAL DE LA BURBUJA DEL SUPERVISOR NOC
 * ==========================================
 *
 * GET   recupera el hilo persistido de esta persona.
 * POST  manda un mensaje y devuelve la respuesta.
 *
 * ESTE ARCHIVO ES EL RESULTADO DE RECONCILIAR DOS ARQUITECTURAS
 * -------------------------------------------------------------
 * Dos ramas construyeron esta misma ruta, y las dos funcionaban:
 *
 *   origin  burbuja -> motor `POST /chat` -- el agente GENERICO del tenant, con
 *           un bloque de contexto en texto por delante. Persistia el hilo en el
 *           motor y lo recuperaba con `GET /chat/historial`.
 *   local   burbuja -> Django `POST /operaciones/supervisor/chat/` -- el
 *           Supervisor DEDICADO, con sus 15 herramientas de lectura y el bucle
 *           de tool calling en `operaciones/chat.py`.
 *
 * Se conserva la SEGUNDA, y el motivo no es preferencia: por el camino generico
 * el Supervisor no puede consultar una situacion, ni una propuesta, ni el estado
 * de las fuentes, porque esas herramientas no existen de ese lado. Un bloque de
 * contexto en texto es una foto; las herramientas son poder preguntar.
 *
 * LO QUE SE CONSERVA DE `origin`, Y NO ES POCO
 * --------------------------------------------
 *  1. LA BURBUJA. `lib/supervisor/ChatBurbuja.svelte` y su `chat-sesion.js`
 *     siguen siendo la interfaz, sin tocar.
 *  2. EL HISTORIAL. La burbuja hace `GET` al abrir y espera `{mensajes}` con
 *     roles `user`/`assistant`. Ese contrato se respeta tal cual -- la
 *     traduccion desde los roles de Django vive en el `get()` de la vista, no
 *     aca ni en el componente, asi que `chat-sesion.test.js` no se toca.
 *  3. LA LECCION DE AUTENTICACION de `6d32108`, que se pago contra produccion:
 *
 *         "Organization context is required. Please login again."
 *
 *     `apiRequest` saca el JWT con `locals.cookies || locals` y despues
 *     `cookies.get("jwt_access")`. En un `+server.js` el evento trae `cookies`
 *     APARTE de `locals`, y `hooks.server.js` solo deja ahi user/org/...,
 *     nunca `cookies`. El fallback agarraba `locals`, `.get` no existia, no
 *     salia cabecera `Authorization` y Django contestaba 403 -- con un sintoma
 *     que senalaba al login, que estaba perfecto. Por eso aca se pasa
 *     `{ cookies }` SIEMPRE, en el GET y en el POST.
 *
 * LO QUE SE DEJO DE USAR, Y POR QUE
 * ---------------------------------
 * `claveDeSesion`, `bloqueDeContexto` y `mensajeParaElMotor` resolvian cosas que
 * en la arquitectura dedicada ya estan resueltas en otro lado:
 *
 *   la clave de sesion   el hilo se separa por tabla: `ConversacionSupervisor`
 *                        esta atada a (org, actor). No hay un hilo compartido
 *                        con `/api/asistente` del que haya que distinguirse.
 *   el contexto          lo arma `operaciones/chat.py::_instrucciones`, junto a
 *                        la identidad y la autonomia. Mandarlo tambien desde
 *                        aca dejaria DOS lugares decidiendo que sabe el
 *                        Supervisor, y ninguno de los dos seria el verdadero.
 *
 * Siguen exportadas y probadas en `chat-sesion.js`: no se borran por si el
 * camino generico vuelve a hacer falta, pero esta ruta ya no las llama.
 *
 * ES UN PROXY, Y ESO ES TODO LO QUE DEBE SER
 * ------------------------------------------
 * El navegador no habla con el modelo ni con ningun proveedor: habla con esta
 * ruta, que habla con Django, que habla con el motor -- el unico que tiene la
 * credencial. Aca NO hay logica del Supervisor: si esta ruta decidiera algo,
 * habria dos lugares donde buscar por que contesto lo que contesto.
 *
 * LA IDENTIDAD NO SE ACEPTA DEL NAVEGADOR, NUNCA
 * ----------------------------------------------
 * No hace falta resolver `profile_id` ni el tenant aca: Django los saca de la
 * credencial (`request.org`, `request.user`). Un `profile_id` que viajara en el
 * cuerpo seria poder preguntar como otra persona.
 *
 * El rol NO se comprueba aca: lo decide Django. Ver `quienPregunta`, que
 * explica por que la comprobacion que habia estaba rota y por que se quito en
 * vez de arreglarse.
 */

/** Lo mismo que exige la vista de Django. */
const TOPE_MENSAJE = 4000;

/** Cuantos mensajes se recuperan al abrir la burbuja. */
const LIMITE_HISTORIAL = 60;

/**
 * Quien pregunta, comprobado del lado del servidor.
 *
 * Devuelve `{ error, status }` si algo falta: quien llama lo propaga tal cual
 * en vez de seguir con una identidad a medias.
 *
 * SOLO COMPRUEBA LA SESION. EL ROL LO DECIDE DJANGO, Y HAY UN MOTIVO MEDIDO
 * ------------------------------------------------------------------------
 * La version local de esta ruta hacia ademas
 *
 *     ROLES_GESTION.has(locals.profile?.role)
 *
 * y eso estaba ROTO: `hooks.server.js` deja en `locals` user, org, org_name y
 * org_settings -- nunca `profile` (medido el 05/10/2026 leyendo sus
 * asignaciones). O sea que la expresion era `has(undefined)` y la ruta
 * contestaba 403 a TODO EL MUNDO, siempre. No se habia notado porque esa rama
 * nunca llego a desplegarse; el defecto salio al reconciliarla con la prueba
 * que `origin` habia escrito despues de pagar el error analogo en produccion.
 *
 * Se quita en vez de arreglarse, y no es pereza: la justificacion que tenia
 * --"da un mensaje util sin gastar un salto"-- era falsa. Resolver el rol exige
 * consultar `/profile/`, que ES un salto. Quedaba una capa que no ahorraba nada
 * y, encima, no funcionaba. `EsJefeDeOperaciones` del lado de Django es la
 * garantia real, ya corre, y su 403 lo traduce `traducirError`.
 *
 * DOS CAPAS SOLO VALEN CUANDO LAS DOS FUNCIONAN. Una capa de verdad es mejor
 * que dos donde una es decorativa -- que es, ademas, la forma en que un permiso
 * parece comprobado dos veces y no lo esta ni una.
 *
 * @param {any} locals
 */
function quienPregunta(locals) {
  if (!locals?.user) {
    return { error: 'Tu sesión expiró. Volvé a iniciar sesión.', status: 401 };
  }
  return {};
}

/** @type {import('./$types').RequestHandler} */
export async function GET({ locals, cookies }) {
  const quien = quienPregunta(locals);
  if (quien.error) return json({ error: quien.error }, { status: quien.status });

  try {
    const d = await apiRequest(
      `/operaciones/supervisor/chat/?limite=${LIMITE_HISTORIAL}`,
      {},
      { cookies }
    );
    return json({
      conversacion_id: d?.conversacion_id ?? null,
      //  La forma que espera `aBurbujas`: rol `user`/`assistant` y `contenido`.
      //  La traduccion la hace Django, no esta ruta -- ver la docstring.
      mensajes: Array.isArray(d?.mensajes) ? d.mensajes : []
    });
  } catch (/** @type {any} */ err) {
    const e = traducirError(err, 'el historial del Supervisor');
    return json({ error: e.mensaje, codigo: e.codigo }, { status: e.status ?? 502 });
  }
}

/** @type {import('./$types').RequestHandler} */
export async function POST({ request, locals, cookies }) {
  const quien = quienPregunta(locals);
  if (quien.error) return json({ error: quien.error }, { status: quien.status });

  /** @type {{ mensaje?: string, conversacion_id?: string, situacion?: string, caso?: string }} */
  let cuerpo;
  try {
    cuerpo = await request.json();
  } catch {
    return json({ error: 'El cuerpo tiene que ser JSON.' }, { status: 400 });
  }

  const mensaje = (cuerpo?.mensaje ?? '').trim();
  if (!mensaje) {
    //  Antes de gastar un turno: un mensaje vacio no se le manda al modelo.
    return json({ error: 'Escribí algo para preguntarle al Supervisor.' }, { status: 400 });
  }
  if (mensaje.length > TOPE_MENSAJE) {
    return json(
      { error: `El mensaje es muy largo (máximo ${TOPE_MENSAJE} caracteres).` },
      { status: 400 }
    );
  }

  //  Solo se reenvia lo que la vista entiende. Un campo de mas viajaria sin que
  //  nada lo valide.
  /** @type {Record<string, string>} */
  const envio = { mensaje };
  if (cuerpo?.conversacion_id) envio.conversacion_id = String(cuerpo.conversacion_id);
  if (cuerpo?.situacion) envio.situacion = String(cuerpo.situacion);
  if (cuerpo?.caso) envio.caso = String(cuerpo.caso);

  try {
    const d = await apiRequest(
      '/operaciones/supervisor/chat/',
      { method: 'POST', body: envio },
      { cookies }
    );
    return json({
      conversacion_id: d?.conversacion_id ?? null,
      contexto: d?.contexto ?? null,
      respuesta: d?.respuesta ?? '',
      es_error: Boolean(d?.es_error),
      //  Que consulto para contestar. Viaja a proposito: una respuesta del
      //  Supervisor sin poder ver de donde salio es una afirmacion sin respaldo.
      herramientas: d?.herramientas ?? [],
      duracion_ms: d?.duracion_ms ?? null,
      error: null
    });
  } catch (/** @type {any} */ err) {
    //  `traducirError` es el mismo que usa el resto del Supervisor NOC: no se
    //  escribe una segunda tabla de mensajes de error. El detalle tecnico se
    //  queda del lado de Django, que es donde se depura -- puede traer el
    //  nombre de un host interno.
    const e = traducirError(err, 'el chat del Supervisor');
    return json({ error: e.mensaje, codigo: e.codigo }, { status: e.status ?? 502 });
  }
}
