import { error, fail } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { getTicket, getTicketFormOptions, updateTicket } from '$lib/server/v2/tickets.js';
import { readableError } from '$lib/server/v2/form-errors.js';
import { headersMotor } from '$lib/server/v2/motor-headers.js';
import { tenantDeLaSesion } from '$lib/server/v2/tenant.js';
import { operadoresDeLaOrg, rolDeSesion } from '$lib/server/v2/operadores.js';

/**
 * Server load: el hilo de una conversacion puntual, mas -- si ya se escalo
 * a un humano (nucleo/seguimiento/escalamiento.py le puso un caso_id) -- el
 * ticket real de BottleCRM que le corresponde, para mostrar y editar quien
 * lo tiene asignado sin reconstruir esa pantalla acá: getTicket/
 * getTicketFormOptions/updateTicket son las mismas funciones que ya usa
 * /tickets/[id]/edit.
 *
 * @type {import('./$types').PageServerLoad}
 */
export async function load({ fetch, cookies, params, locals, depends }) {
  // Identificador PROPIO, no 'app:conversaciones'. Ese lo invalida el sondeo
  // del layout cada pocos segundos para refrescar la lista de la izquierda: si
  // este load dependiera de él, el hilo entero, las herramientas y el ticket
  // del CRM se recargarían en cada vuelta del reloj. Con uno propio, el
  // registro del relevo se refresca cuando algo lo cambió y sólo entonces.
  depends('app:relevo');

  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = await tenantDeLaSesion(locals, fetch);
  if (!baseUrl || !tenant) {
    error(500, 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)');
  }

  // Los tres pedidos son independientes entre si -- en paralelo, no uno
  // atras del otro. Antes se esperaba mensajes, DESPUES herramientas,
  // DESPUES casos: cada salto de conversacion pagaba la suma de las tres
  // idas y vueltas al motor en vez del maximo de las tres, y esa espera es
  // la que se sentia como si la pagina entera se recargara.
  const [respMensajes, respHerr, respCasos, respRelevo, respEquipo, respSync,
         respAcciones, respCliente] = await Promise.all([
    fetch(
      `${baseUrl}/conversaciones/${encodeURIComponent(params.id)}/mensajes?tenant=${encodeURIComponent(tenant)}`,
      { headers: headersMotor() }
    ),
    fetch(
      `${baseUrl}/conversaciones/${encodeURIComponent(params.id)}/herramientas?tenant=${encodeURIComponent(tenant)}`,
      { headers: headersMotor() }
    ).catch(() => null),
    fetch(`${baseUrl}/manual/casos?tenant=${encodeURIComponent(tenant)}`, { headers: headersMotor() }).catch(() => null),
    fetch(
      `${baseUrl}/conversaciones/${encodeURIComponent(params.id)}/relevo?tenant=${encodeURIComponent(tenant)}`,
      { headers: headersMotor() }
    ).catch(() => null),
    fetch(
      `${baseUrl}/conversaciones/${encodeURIComponent(params.id)}/equipo?tenant=${encodeURIComponent(tenant)}`,
      { headers: headersMotor() }
    ).catch(() => null),
    fetch(
      `${baseUrl}/conversaciones/${encodeURIComponent(params.id)}/sincronizaciones?tenant=${encodeURIComponent(tenant)}`,
      { headers: headersMotor() }
    ).catch(() => null),
    fetch(
      `${baseUrl}/conversaciones/${encodeURIComponent(params.id)}/acciones?tenant=${encodeURIComponent(tenant)}`,
      { headers: headersMotor() }
    ).catch(() => null),
    /* La ficha del cliente, leida EN VIVO del sistema del ISP por el motor.
       Va en la misma ola que las otras siete y no despues: es la llamada mas
       lenta de las ocho --sale a una API externa-- y encadenarla haria que
       cada salto de conversacion la esperara entera.
       `.catch(() => null)` como las demas: que el ISP no conteste no puede
       impedir que se lea la conversacion. La pantalla lo dice y sigue. */
    fetch(
      `${baseUrl}/conversaciones/${encodeURIComponent(params.id)}/cliente?tenant=${encodeURIComponent(tenant)}`,
      { headers: headersMotor() }
    ).catch(() => null)
  ]);

  const datos = await respMensajes.json();
  if (respMensajes.status === 404) {
    error(404, 'Esta conversación no existe.');
  }
  if (!respMensajes.ok) {
    error(500, datos.error || 'No se pudo cargar la conversación.');
  }

  // "Ver proceso": que herramientas uso el agente, para que un supervisor
  // pueda revisar el caso sin tener que leer todo el hilo. No corta la
  // pagina si falla -- es un panel mas, no el contenido principal.
  let herramientas = [];
  let diagnostico = null;
  try {
    if (respHerr?.ok) {
      const cuerpo = await respHerr.json();
      herramientas = cuerpo.herramientas;
      // Los tres contadores los cuenta el motor, no esta pagina: la
      // diferencia entre "el codigo lo freno" y "el tercero fallo" sale de
      // una columna de la base, no del texto del error.
      diagnostico = cuerpo.diagnostico ?? null;
    }
  } catch {
    // idem: el panel de proceso queda vacio, no se cae la conversacion.
  }

  // Como llego la conversacion a estas manos: un evento por transicion del
  // relevo. Mismo criterio que arriba -- es un panel, no el contenido: si el
  // motor no contesta, la actividad queda vacia y el hilo se lee igual.
  let relevo = [];
  try {
    if (respRelevo?.ok) relevo = (await respRelevo.json()).eventos ?? [];
  } catch {
    // idem
  }

  // Que se le hizo al equipo del cliente y si funciono. Es el veredicto del
  // seguimiento de acciones, no una consulta en vivo al ISP: nada se pregunta
  // al abrir la pantalla. Si el motor no contesta, el panel dice que no hubo
  // acciones registradas y la conversacion se atiende igual.
  let equipo = [];
  try {
    if (respEquipo?.ok) equipo = (await respEquipo.json()).acciones ?? [];
  } catch {
    // idem
  }

  /* La ficha del cliente en el sistema del ISP: documento, plan, estado del
     servicio y cobranza. NO se guarda: el motor la lee en vivo en cada carga
     y no persiste la respuesta.

     El objeto trae siempre `disponible` y `motivo`, así que la pantalla puede
     decir POR QUÉ no hay ficha --el asistente todavía no identificó al
     cliente, la empresa no tiene conectado su sistema, o el sistema no
     contestó-- en vez de dejar un hueco que se lee como un error. */
  let fichaCliente = { disponible: false, motivo: 'sin_respuesta', cliente: null };
  try {
    if (respCliente?.ok) fichaCliente = await respCliente.json();
  } catch {
    // Se queda con 'sin_respuesta': no poder leer la ficha no rompe la
    // conversación, que es de lo que trata esta pantalla.
  }

  /* CÓMO ESTÁ EL EQUIPO — SÓLO SI ESCALÓ.
     La lectura óptica sale a un sistema externo que pide no consultarlo en
     bucle, así que no se hace en cada apertura: se hace cuando una persona
     tiene el caso en la mano, que es cuando el diagnóstico se usa para
     decidir. Mientras la lleva el asistente, la pestaña Equipo abre con el
     botón "Consultar ahora" y nadie paga la espera.

     Va DESPUÉS de las otras ocho y no en la misma ola a propósito: depende
     de `conversacion.escalada_a_humano`, que recién se conoce al abrir la
     respuesta de mensajes. Es una ida y vuelta más, y sólo en las escaladas.

     El motor cachea cinco minutos, así que recargar la pantalla no vuelve a
     salir al proveedor. */
  let optica = { disponible: false, motivo: 'no_consultada', optica: null };
  if (datos.conversacion?.escalada_a_humano) {
    try {
      const respOptica = await fetch(
        `${baseUrl}/conversaciones/${encodeURIComponent(params.id)}/optica?tenant=${encodeURIComponent(tenant)}`,
        { headers: headersMotor() }
      );
      if (respOptica.ok) optica = await respOptica.json();
    } catch {
      // Que el sistema del ISP no conteste no puede impedir atender la
      // conversación. El panel lo dice y ofrece reintentar.
    }
  }

  // Que efectos externos quedaron sin hacer (B4). Es estado actual, no
  // historia: lo que aparece acá es lo que todavía le falta a la conversación
  // del lado del CRM o del sistema del ISP.
  let sincronizaciones = [];
  try {
    if (respSync?.ok) sincronizaciones = (await respSync.json()).sincronizaciones ?? [];
  } catch {
    // idem
  }

  // Las acciones que la IA propuso acá, con su estado REAL (B5). Antes una
  // acción terminaba en «aprobada» y nada más -- que es lo que alguien
  // decidió, no lo que pasó: el efecto podía haber fallado y la pantalla decía
  // lo mismo.
  let acciones = [];
  try {
    if (respAcciones?.ok) acciones = (await respAcciones.json()).acciones ?? [];
  } catch {
    // idem
  }

  // Casos fijos para marcar una respuesta como buen ejemplo (ver
  // MarcarEjemplo.svelte). Igual que arriba: si falla, el boton de marcar
  // simplemente no tiene opciones -- no se cae la conversacion por esto.
  let casos = [];
  try {
    if (respCasos?.ok) casos = (await respCasos.json()).casos;
  } catch {
    // idem
  }

  // El ticket de BottleCRM solo se pide si esta conversacion escalo -- va
  // aparte porque depende de 'caso_id', que recien se conoce despues de leer
  // 'datos' arriba. La mayoria de las conversaciones (las que el bot resuelve
  // solo) ni siquiera entran aca.
  let caso = null;
  let owners = [];
  if (datos.conversacion?.caso_id) {
    try {
      const [detalleCaso, opciones] = await Promise.all([
        getTicket({ cookies }, datos.conversacion.caso_id),
        getTicketFormOptions({ cookies })
      ]);
      caso = detalleCaso.ticket;
      owners = opciones.owners;
    } catch {
      // El chat sigue siendo util aunque el CRM este caido -- no se cae la
      // pagina entera por esto, mismo criterio que ya usa agentes/+page.server.js.
    }
  }

  // Quien mira y con que rol, para que la pantalla sepa si la conversacion es
  // suya y si puede reasignar (B3.4). Solo muestra: el motor decide.
  const rol = rolDeSesion(locals);
  let operadores = [];
  if (rol === 'ADMIN') {
    try {
      operadores = await operadoresDeLaOrg(cookies);
    } catch {
      // Sin la lista no se ofrece reasignar; el resto de la pantalla sigue.
    }
  }
  const yo = { id: locals.user?.id ?? '', nombre: (locals.user?.name || locals.user?.email || '').trim() };

  return { conversacion: datos.conversacion, mensajes: datos.mensajes, caso, owners, herramientas, diagnostico, casos,
    relevo, equipo, sincronizaciones, acciones, yo, rol, operadores, fichaCliente, optica };
}

/** @type {import('./$types').Actions} */
export const actions = {
  /** Cambia el responsable del ticket vinculado. Ver el mismo patron (un
   * solo valor, se empaqueta al M2M que pide la API) en tickets/[id]/edit. */
  asignar: async ({ cookies, request }) => {
    const form = await request.formData();
    const casoId = form.get('caso_id')?.toString() ?? '';
    const asignadoA = form.get('assigned_to')?.toString() ?? '';
    if (!casoId) return fail(400, { error: 'No hay ticket vinculado todavía.' });

    try {
      await updateTicket({ cookies }, casoId, { assigned_to: asignadoA });
    } catch (/** @type {any} */ err) {
      return fail(400, { error: readableError(err, 'No se pudo asignar el ticket.') });
    }
    return { asignado: true };
  }
};
