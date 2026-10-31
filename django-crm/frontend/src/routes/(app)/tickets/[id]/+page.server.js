import { fail } from '@sveltejs/kit';
import { getTicket, replyToTicket, updateTicket, tomarTicket } from '$lib/server/v2/tickets.js';
import { readableError } from '$lib/server/v2/form-errors.js';
import { leerResumenDelAgente } from '$lib/server/v2/resumen-agente.js';
import { leerAreas } from '$lib/server/v2/areas.js';
import { areaDelCaso, SIN_AREA } from '$lib/v2/tickets-resumen.js';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';
import { autorDeSesion, claveIdempotencia } from '$lib/server/v2/autor.js';
import { tenantDeLaSesion } from '$lib/server/v2/tenant.js';
import { getOrgPeopleAndTeams, resolveMe } from '$lib/server/v2/org-people.js';
import { reparteTickets } from '$lib/v2/roles.js';
import { hoyDeLaEmpresa } from '$lib/server/v2/hoy-de-la-empresa.js';

/** @type {import('./$types').PageServerLoad} */
export async function load({ locals, cookies, params, fetch }) {
  // La gente de la organizacion va en paralelo con el caso, y para TODOS: el
  // control de asignar es solo de un admin, pero la linea de tiempo de
  // cualquiera necesita los nombres para decir a quien se asigno (el evento
  // trae ids de perfil). `getOrgPeopleAndTeams` no lanza: si falla, listas
  // vacias, y la pantalla cae a "Asignado" sin nombre.
  const [datos, gente] = await Promise.all([
    getTicket({ cookies }, params.id),
    getOrgPeopleAndTeams(cookies)
  ]);
  //  Quien reparte (ADMIN, SUPERVISOR, OPERACIONES), no solo ADMIN: ver
  //  lib/v2/roles.js y cases/access.py::reparte_tickets.
  const reparte = reparteTickets(/** @type {any} */ (locals)?.profile?.role);

  // El area del caso, para el panel lateral. Misma regla que la cola
  // (areaDelCaso): la escrita en el caso manda, y la de la persona asignada
  // solo decide mientras el caso no la tenga. Hasta el 16/10/2026 se deducia
  // siempre del responsable, y un ticket de ventas asignado a un tecnico
  // decia "Soporte Técnico" aca tambien.
  //
  // Se pide a '/agentes/areas', no a '/agentes/asignaciones': aquella sale
  // ademas al sistema externo a buscar candidatos, que esta pantalla no usa.
  let area = null;
  const escrita = datos.ticket?.area;
  const responsable = datos.ticket?.assignee_id;
  if (escrita || responsable) {
    const { areas, areaPorPersona } = await leerAreas(locals, fetch);
    const nombre = areaDelCaso(escrita, responsable, areaPorPersona);
    if (nombre !== SIN_AREA) {
      // Un area escrita que la configuracion no declara se muestra con su
      // nombre crudo, igual que en la cola: esconderla diria "sin area" de
      // un caso que si la tiene.
      area = areas.find((/** @type {any} */ a) => a.nombre === nombre)
        ?? { nombre, etiqueta: nombre };
    }
  }

  // Una sola llamada al motor que devuelve DOS cosas distintas:
  //
  //   conversacion  de donde vino el caso -- canal, etiqueta, motivo de la
  //                 escalada. El CRM no lo guarda; el asistente si, porque es
  //                 la misma fila que marco al escalar. Null para un ticket
  //                 cargado a mano o importado del sistema del ISP.
  //   contexto      que hay del otro lado -- cliente, equipo, enlaces. Desde
  //                 el 10/09/2026 existe aunque NO haya conversacion: se
  //                 resuelve con el identificador de servicio del propio caso.
  //
  // Estaban pegadas en un solo objeto porque hasta entonces la segunda solo
  // se podia obtener a traves de la primera.
  //
  // Va SIN await: la promesa se devuelve tal cual y el navegador la recibe
  // cuando resuelve. Adentro hay hasta tres consultas a sistemas externos (la
  // ficha del cliente y el estado del equipo), y esperarlas antes de contestar
  // dejaba el ticket sin abrirse varios segundos -- con la pantalla anterior
  // todavia puesta, o sea el clic pareciendo perdido. El caso, la
  // conversacion y la respuesta no dependen de esto: llegan primero y esto
  // completa las tarjetas tecnicas cuando llega.
  const delMotor = (async () => {
    try {
      const base = env.PRIVATE_ASISTENTE_URL;
      const tenant = await tenantDeLaSesion(locals, fetch);
      if (!base || !tenant) return null;
      const params_ = new URLSearchParams({ tenant });
      // El identificador de servicio del caso importado. El motor no puede
      // leerlo por su cuenta: corre con su propio usuario de base y no ve las
      // tablas del CRM. Se lo pasamos nosotros, que ya lo tenemos cargado.
      const servicio = datos.ticket?.external_service_id;
      if (servicio) params_.set('servicio', servicio);
      const r = await fetch(
        `${base}/conversaciones/por-caso/${params.id}?${params_}`,
        { headers: headersMotor(), signal: AbortSignal.timeout(20000) }
      );
      return r.ok ? await r.json() : null;
    } catch {
      // Se traga a proposito: sin esto una promesa rechazada tumba la
      // pagina entera, y lo que hay en juego son dos tarjetas de contexto.
      return null;
    }
  })();

  return {
    ...datos,
    area,
    // Quien puede reasignar desde el encabezado. El backend solo deja a un
    // admin ver y escribir casos ajenos; un colaborador ve al responsable sin
    // control, en vez de un selector que el API le iba a rechazar.
    reparte,
    // Solo id y nombre: el selector no necesita el correo de nadie.
    personas: gente.people.map((p) => ({ id: p.id, name: p.name })),
    yo: resolveMe(gente.people, /** @type {any} */ (locals)?.user?.email),
    origen: delMotor.then((d) => d?.conversacion ?? null),
    // Si el ticket tiene un chat al que la respuesta pueda salir. Es la MISMA
    // busqueda que hace el envio (`conversacion_de_caso` en el motor, en las
    // dos rutas), asi que lo que esto dice es lo que el envio va a encontrar.
    //   'si'          hay conversacion detras.
    //   'no'          el motor contesto y no hay: ticket a mano o importado.
    //   'no_se_pudo'  el motor no contesto o no esta configurado. NO es "no
    //                 hay": decir que no le llega cuando quiza si, tampoco.
    estadoConversacion: delMotor.then((d) =>
      d === null ? 'no_se_pudo' : d?.conversacion ? 'si' : 'no'
    ),
    contexto: delMotor.then((d) => d?.contexto ?? null),
    // Null cuando el caso no lo escribio el asistente (uno cargado a mano, o
    // uno viejo con otro formato): la pantalla vuelve entonces a mostrar la
    // descripcion tal cual, sin tarjetas a medio llenar.
    agente: leerResumenDelAgente(datos.ticket?.description ?? '')
  };
}

/** @type {import('./$types').Actions} */
export const actions = {
  /**
   * Post a reply, or an internal note.
   *
   * A reply may also move the ticket; "answer and set to Pending" is one
   * decision, not two, so the status change goes with it when the composer
   * asked for one. The reply is posted first: if the status change is refused
   * (the close gate, say) the customer has still been answered, which is the
   * order that loses the least.
   */
  reply: async ({ cookies, params, request, fetch, locals }) => {
    const form = await request.formData();
    const body = form.get('body')?.toString().trim() ?? '';
    const internal = form.get('internal') === 'on';
    // Con esta respuesta la persona da por terminada su parte y el asistente
    // vuelve a atender. Una nota interna nunca devuelve nada: no salio de
    // esta pantalla.
    const devolver = !internal && form.get('devolver') === 'on';
    const status = form.get('status')?.toString().trim() ?? '';

    const picked = form.get('attachment');
    const file =
      picked && typeof picked === 'object' && 'size' in picked && picked.size > 0 ? picked : null;

    // A ticket accepts a file on its own, the API saves the attachment in a
    // block separate from the comment, so this refuses only the empty case.
    if (!body && !file) {
      return fail(400, {
        body,
        internal,
        error: 'Escribí algo o adjuntá un archivo antes de enviar.'
      });
    }

    // Al CLIENTE primero, y sólo si no es una nota interna.
    //
    // Hasta el 28/08/2026 esta caja escribía únicamente un comentario en el
    // caso del CRM. Se lee como si le hablara al cliente ("una respuesta
    // abajo es la primera respuesta") y no le llegaba a nadie: quien
    // contestaba daba el caso por atendido mientras el cliente seguía
    // esperando. El motor la manda por el canal por el que escribió, la deja
    // en el hilo y la copia al ticket del sistema del ISP firmada con el
    // nombre de quien la escribió.
    let entrega = null;
    // Que el motor dijo "no hay chat": la respuesta quedo en el ticket y al
    // cliente no le llego. Se devuelve para decirlo tambien DESPUES de enviar,
    // no solo en el aviso de antes. No cambia nada de la entrega.
    let sinConversacion = false;
    if (!internal) {
      try {
        const base = env.PRIVATE_ASISTENTE_URL;
        const tenant = await tenantDeLaSesion(locals, fetch);
        if (base && tenant) {
          const r = await fetch(`${base}/casos/${params.id}/mensajes`, {
            method: 'POST',
            headers: { ...headersMotor(), 'content-type': 'application/json' },
            body: JSON.stringify({
              tenant,
              mensaje: body,
              ...autorDeSesion(locals),
              // Una por envío del formulario: evita el doble POST, no un
              // reenvío manual del formulario (que es otro mensaje).
              clave_idempotencia: claveIdempotencia(null),
              devolver_al_asistente: devolver
            }),
            signal: AbortSignal.timeout(20000)
          });
          // 404 con 'sin_conversacion' es lo normal en un ticket cargado a
          // mano: no hay chat detrás, y el comentario del caso alcanza.
          //
          // CUALQUIER OTRO rechazo se dice (auditor independiente, 21/10/2026):
          // un 409 --la IA atiende el chat, o el chat ya sigue en otra
          // conversación-- se leía igual que "no había a quién", y quien
          // respondía creía que el cliente lo había recibido.
          const cuerpo = await r.json().catch(() => ({}));
          if (r.ok) entrega = cuerpo;
          else if (r.status === 404 && cuerpo?.sin_conversacion) sinConversacion = true;
          else if (!(r.status === 404 && cuerpo?.sin_conversacion)) {
            entrega = { ok: false, aceptado_por_meta: false, aceptacion_registrada: false,
              resultado: 'rechazado',
              aviso: `No le llegó al cliente: ${cuerpo?.error || 'el asistente rechazó el envío.'}` };
          }
        }
      } catch (/** @type {any} */ err) {
        console.error('[tickets] no se pudo entregar la respuesta al cliente', err);
        entrega = { ok: false, aceptado_por_meta: false,
          aceptacion_registrada: false, resultado: 'incierto' };
      }
    }

    try {
      //  Si hubo chat detrás (el motor tomó la entrega, haya salido o no), la
      //  primera respuesta la marca el motor y sólo si WhatsApp la aceptó: el
      //  comentario no la marca (28/10/2026). Sin chat -- un ticket cargado a
      //  mano -- el comentario ES la respuesta y la marca como siempre.
      await replyToTicket({ cookies }, params.id, {
        body,
        internal,
        file,
        sinPrimeraRespuesta: entrega !== null
      });
    } catch (/** @type {any} */ err) {
      return fail(400, { body, internal, error: readableError(err, 'No se pudo publicar esta respuesta.') });
    }

    if (status) {
      try {
        await updateTicket({ cookies }, params.id, { status });
      } catch (/** @type {any} */ err) {
        return fail(400, {
          sent: true,
          error: readableError(err, `Se publicó la respuesta, pero el estado no cambió.`)
        });
      }
    }

    // 'aceptado_por_meta' es null cuando no había a dónde entregar (nota interna, o
    // un ticket sin conversación detrás): eso no es un fallo y no se avisa.
    return {
      sent: true,
      internal,
      sin_conversacion: sinConversacion,
      aceptado_por_meta: entrega ? entrega.aceptado_por_meta : null,
      aceptacion_registrada: entrega ? entrega.aceptacion_registrada : null,
      resultado: entrega ? entrega.resultado : null,
      aviso: entrega && entrega.resultado === 'rechazado'
        ? (entrega.aviso || 'La respuesta quedó guardada, pero no se pudo entregar al cliente.')
        : ''
    };
  },

  /**
   * Move the ticket without saying anything.
   *
   * Closing needs a date; `Case.clean()` has always said so and the serializer
   * now enforces it, so the button supplies today rather than bouncing the
   * user into a form to type a date they were never going to change. Where an
   * approval rule covers the ticket, the API refuses and says which rule.
   */
  setStatus: async ({ cookies, params, request, locals }) => {
    const form = await request.formData();
    const status = form.get('status')?.toString().trim() ?? '';
    if (!status) return fail(400, { error: 'No se eligió ningún estado.' });

    /** @type {Record<string, any>} */
    const values = { status };
    //  The company's day (27/10/2026): `toISOString()` is the server's (UTC),
    //  and a ticket closed from 19:00 in Bogotá was dated tomorrow.
    if (status === 'Closed') values.closed_on = await hoyDeLaEmpresa(locals, cookies);

    try {
      await updateTicket({ cookies }, params.id, values);
    } catch (/** @type {any} */ err) {
      return fail(400, { error: readableError(err, 'No se pudo cambiar el estado.') });
    }

    return { moved: status };
  },

  /**
   * Cambiar al responsable desde el encabezado. Solo para un admin.
   *
   * `updateTicket` recibe UN id y no una lista: `toBody()` de tickets.js ya lo
   * envuelve en `[id]`, y '' lo deja sin responsable. Pasarle `[id]` mandaria
   * una lista dentro de otra.
   *
   * Es PATCH con `assigned_to`, asi que REEMPLAZA a todos los responsables
   * por uno, igual que el formulario de edicion. La pantalla lo avisa cuando
   * hay mas de uno.
   *
   * "Asignarme" no confia en un id que mande el navegador: se resuelve aca,
   * desde la sesion, con la misma regla que los presets "Mios" (resolveMe).
   */
  asignar: async ({ cookies, params, request, locals }) => {
    if (!reparteTickets(/** @type {any} */ (locals)?.profile?.role)) {
      return fail(403, { error: 'Solo quien reparte el trabajo puede reasignar un ticket desde acá.' });
    }
    const form = await request.formData();
    const { people } = await getOrgPeopleAndTeams(cookies);

    /** @type {string} */
    let persona;
    if (form.get('yo') === '1') {
      const yo = resolveMe(people, /** @type {any} */ (locals)?.user?.email);
      if (!yo) return fail(400, { error: 'No se encontró tu perfil en esta organización.' });
      persona = yo;
    } else {
      persona = form.get('persona')?.toString().trim() ?? '';
      // Vacio = sin responsable, a proposito. Un id que no es de la gente de
      // la organizacion se rechaza aca, antes de ir al API (que igual lo
      // validaria): el mensaje es mejor que un 400 generico.
      if (persona && !people.some((p) => p.id === persona)) {
        return fail(400, { error: 'Esa persona no está en la organización.' });
      }
    }

    try {
      await updateTicket({ cookies }, params.id, { assigned_to: persona });
    } catch (/** @type {any} */ err) {
      return fail(400, { error: readableError(err, 'No se pudo cambiar el responsable.') });
    }
    return {
      asignado: persona,
      asignadoNombre: people.find((p) => p.id === persona)?.name ?? ''
    };
  },

  //  Tomar un ticket sin responsable, para quien no reparte: un colaborador lo
  //  ve porque es de su area, y esta es la unica escritura que tiene sobre el
  //  antes de ser responsable. Decide el backend ('/tomar/').
  tomar: async ({ cookies, params }) => {
    try {
      await tomarTicket({ cookies }, params.id);
    } catch (/** @type {any} */ err) {
      if (err?.status === 409) return fail(409, { error: 'Otra persona tomó este ticket primero.' });
      if (err?.status === 403) return fail(403, { error: 'Este ticket no es de tu área.' });
      return fail(400, { error: readableError(err, 'No se pudo tomar el ticket.') });
    }
    return { tomado: true };
  }
};
