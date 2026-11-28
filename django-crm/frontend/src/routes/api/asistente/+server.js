import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { apiRequest } from '$lib/api-helpers.js';
import { headersMotor } from '$lib/server/v2/motor-headers.js';
import { tenantDeLaSesion } from '$lib/server/v2/tenant.js';

/**
 * Proxy hacia el motor del asistente (crm-agentico, repo aparte, ver
 * PRIVATE_ASISTENTE_URL en .env.docker.local). El browser nunca le habla
 * directo -- ni conoce su URL ni necesita CORS -- se reenvia
 * server-to-server, mismo patron que /api/search.
 *
 * Antes esto mandaba `rol: 'soporte'` fijo, asi que los otros agentes
 * configurados (facturacion, administracion) no eran alcanzables por nadie:
 * quien preguntaba por una factura le hablaba a un agente sin
 * consultar_facturas. Ahora se manda QUIEN pregunta y el motor resuelve que
 * agentes tiene asignados, fusionandolos si son varios.
 *
 * EL profile_id SE RESUELVE ACA, NUNCA LLEGA DEL CLIENTE. Es lo que decide a
 * que datos accede el turno: si viniera en el cuerpo de la peticion,
 * cualquiera podria mandar el de otra persona y quedarse con sus agentes.
 * Cuesta una llamada extra al backend por mensaje, en red interna y de pocos
 * milisegundos -- despreciable al lado de los 5-12 s que tarda un turno.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function POST({ request, locals, fetch }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }

  const cuerpo = await request.json();
  const { mensaje, rol, imagen } = cuerpo ?? {};
  if (!mensaje && !imagen) {
    return json({ error: 'Falta el mensaje' }, { status: 400 });
  }

  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = await tenantDeLaSesion(locals, fetch);
  if (!baseUrl || !tenant) {
    // Sin nombrar variables de entorno: a quien escribe no le sirven, y el
    // detalle de la instalacion no es para la pantalla (mismo criterio que
    // centro-mando/+page.server.js desde el 31/10/2026).
    return json({ error: !baseUrl
        ? 'No hay un asistente desplegado para esta instalación.'
        : 'Esta empresa todavía no tiene un asistente configurado.' },
      { status: 503 });
  }

  /**
   * HABLARLE A UN AGENTE CONCRETO, Y SOLO SI SOS ADMIN  --  02/11/2026
   *
   * Sin `rol`, esto sigue funcionando como siempre: el motor resuelve los
   * agentes asignados a tu perfil y los fusiona. Con `rol`, le hablás a ese
   * agente aunque no lo tengas asignado -- que es lo que hace falta para
   * probar uno recién creado antes de asignárselo a nadie.
   *
   * Y por eso es solo ADMIN: elegir cualquier agente saltea el modelo de
   * asignaciones (/agentes/asignaciones), que es lo que decide a qué datos
   * llega cada colaborador. El mismo gate que usa POST /api/agentes.
   *
   * `rol` y `profile_id` son EXCLUYENTES del lado del motor, así que se
   * manda uno u otro, nunca los dos.
   */
  const esAdmin = locals.profile?.role === 'ADMIN';
  const rolPedido = String(rol || '').trim();
  if (rolPedido && !esAdmin) {
    return json({ error: 'Solo un administrador puede elegir a qué agente le habla.' },
      { status: 403 });
  }

  /**
   * LA FOTO SE MIRA EN EL MOTOR, Y SU ANÁLISIS ENTRA AL TURNO COMO TEXTO.
   *
   * Es el mismo camino que ya usa WhatsApp: el modelo conversacional no
   * recibe la imagen, recibe lo que otra pasada vio en ella, rotulado como
   * lectura automática no verificada. El rótulo lo arma el motor --no esta
   * pantalla-- porque es lo que impide que el agente repita la descripción
   * como un hecho comprobado.
   *
   * Si la empresa no lo tiene habilitado, o el análisis falla, el turno
   * sigue con el texto que escribió la persona. Una foto que no se pudo
   * mirar no puede dejar a nadie sin respuesta.
   */
  let textoDelTurno = String(mensaje || '').trim();
  let avisoFoto = '';
  if (imagen) {
    try {
      const binario = Uint8Array.from(atob(String(imagen).split(',').pop() ?? ''), (c) =>
        c.charCodeAt(0)
      );
      const formulario = new FormData();
      formulario.append('imagen', new Blob([binario]), 'adjunta.jpg');
      formulario.append('pie', textoDelTurno);
      formulario.append('proposito', 'asistente_interno');
      const respFoto = await fetch(
        `${baseUrl}/interno/vision/analizar-evidencia?tenant=${encodeURIComponent(tenant)}`,
        { method: 'POST', headers: headersMotor(), body: formulario }
      );
      const datosFoto = await respFoto.json().catch(() => ({}));
      if (datosFoto?.para_el_turno) {
        textoDelTurno = datosFoto.para_el_turno;
      } else {
        avisoFoto =
          datosFoto?.motivo || datosFoto?.error || 'No se pudo mirar la foto.';
      }
    } catch (/** @type {any} */ err) {
      console.error('[asistente] no se pudo analizar la foto:', err?.message ?? err);
      avisoFoto = 'No se pudo mirar la foto.';
    }
  }
  if (!textoDelTurno) {
    return json({ error: avisoFoto || 'Falta el mensaje' }, { status: 400 });
  }

  /**
   * EL PERFIL SOLO HACE FALTA SI NO ELEGISTE AGENTE  --  02/11/2026
   *
   * `/profile/` del CRM devuelve 403 «Organization context is required» con
   * el mismo JWT que estas rutas aceptan. No es nuevo: `lib/server/v2/
   * inventario.js:185` documenta exactamente el mismo 403 en
   * `/users/get-teams-and-users/`, y es la razon por la que esta pantalla
   * no se usaba -- fallaba antes de hablarle al motor.
   *
   * Con un agente ELEGIDO, el `profile_id` no se manda (es excluyente con
   * `rol`), asi que pedirlo era bloquear por un dato que no se iba a usar.
   * Sin agente elegido sigue haciendo falta: es lo que decide a que datos
   * llega el turno, y ahi un fallo SI tiene que frenar.
   *
   * El nombre cae a la sesion, que lo tiene del JWT. Nunca se acepta del
   * cliente: con eso cualquiera firmaria con el nombre de otro.
   */
  /** @type {string | undefined} */
  let profileId;
  let nombreColaborador = (locals.user.name || locals.user.email || '').trim();
  try {
    const perfil = await apiRequest('/profile/', {}, locals);
    profileId = perfil?.user_obj?.id;
    nombreColaborador =
      (perfil?.user_obj?.name || perfil?.user_obj?.email || '').trim() || nombreColaborador;
  } catch (/** @type {any} */ err) {
    if (!rolPedido) {
      return json(
        {
          error:
            'No se pudo identificar tu perfil en esta organización. ' +
            'Elegí un agente en «Le habla a» para seguir, o volvé a iniciar sesión. ' +
            `(${err?.message || 'sin detalle'})`
        },
        { status: 502 }
      );
    }
  }
  if (!profileId && !rolPedido) {
    return json({ error: 'No se pudo identificar tu perfil en esta organizacion' },
      { status: 403 });
  }

  try {
    const resp = await fetch(`${baseUrl}/chat`, {
      method: 'POST',
      headers: headersMotor({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({
        tenant,
        ...(rolPedido ? { rol: rolPedido } : { profile_id: profileId }),
        identificador_sesion: locals.user.id,
        nombre_colaborador: nombreColaborador,
        mensaje: textoDelTurno
      })
    });
    const datos = await resp.json();
    if (!resp.ok) {
      return json({ error: datos.error || 'El asistente no respondio' }, { status: resp.status });
    }
    //  El aviso de la foto viaja aparte de la respuesta: que no se haya
    //  podido mirar no es un error del turno, y mezclarlo con el texto del
    //  agente haría que la pantalla no pueda distinguirlos.
    return json(avisoFoto ? { ...datos, aviso_foto: avisoFoto } : datos);
  } catch (/** @type {any} */ err) {
    return json({ error: err?.message || 'No se pudo contactar al asistente' }, { status: 502 });
  }
}
