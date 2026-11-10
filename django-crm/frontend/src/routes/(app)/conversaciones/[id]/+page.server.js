import { error, fail } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { getTicket, getTicketFormOptions, updateTicket } from '$lib/server/v2/tickets.js';
import { readableError } from '$lib/server/v2/form-errors.js';
import { headersMotor } from '$lib/server/v2/motor-headers.js';
import { tenantDeLaSesion } from '$lib/server/v2/tenant.js';
import { operadoresDeLaOrg, rolDeSesion } from '$lib/server/v2/operadores.js';
import { conPlazo, leerConPlazo } from '$lib/server/v2/plazo.js';

/* LA CONVERSACIÓN NO ESPERA A LO LENTO  --  07/11/2026
   "¿Por qué queda cargando la página de conversación?" Al abrir otra
   conversación, SvelteKit no cambia de pantalla hasta que este load termina,
   y la franja de arriba se queda corriendo mientras tanto. El load esperaba
   doce lecturas, ninguna con plazo: la ficha del cliente sale EN VIVO al
   sistema del ISP, la óptica al de las OLT, el ticket y los operadores al
   CRM, y las lecturas al motor compiten con los turnos de WhatsApp por sus 8
   hilos. La más lenta decidía cuándo se veía la conversación.

   Ahora son dos tiempos:

   - LO QUE SE ESPERA: el hilo y los paneles que salen de la base del motor.
     Sin el hilo no hay pantalla; los paneles son de la misma base y llegan
     con él. Cada uno con plazo: el panel que no llega queda vacío, y si el
     que no llega es el hilo, se dice que el asistente tarda en vez de
     esperar sin fin.
   - LO QUE LLEGA DESPUÉS: la ficha del cliente, la óptica, el ticket del CRM
     y los operadores. Viajan como promesas -- SvelteKit las manda en la
     misma respuesta cuando resuelven -- y la página dibuja la conversación
     sin ellas, con su panel diciendo «consultando» mientras tanto. También
     con plazo: uno que no contesta nunca no puede dejar «consultando» para
     siempre.

   Las promesas NUNCA rechazan (ver lib/server/v2/plazo.js): la que falla o
   vence llega como el mismo aviso que el panel ya tenía para "no contestó".
   Y la que vence deja una línea en el log que dice cuál fue, que es lo que
   permite saber cuál de los sistemas es el lento sin adivinarlo. */

/** Las lecturas de la base del motor: el hilo y sus paneles. */
const PLAZO_MOTOR_MS = 10000;
/** Lo que el motor va a buscar a un sistema externo (ficha del cliente,
 *  óptica). Ya no retiene la pantalla, así que puede esperar lo que el motor
 *  necesita; el motor cachea la óptica cinco minutos. */
const PLAZO_EXTERNO_MS = 10000;
/** El ticket vinculado y la lista de operadores, del CRM. */
const PLAZO_CRM_MS = 5000;

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

  /** Una ruta del motor sobre esta conversación, con plazo. El nombre va al
   *  log solo si vence o falla: la ruta, nunca la URL con el identificador. */
  const leer = (/** @type {string} */ ruta, /** @type {number} */ ms) =>
    leerConPlazo(
      fetch,
      `${baseUrl}/conversaciones/${encodeURIComponent(params.id)}/${ruta}?tenant=${encodeURIComponent(tenant)}`,
      { headers: headersMotor() },
      ms,
      `conversacion ${ruta}`
    );
  /** @param {{ ok: boolean, cuerpo: any } | null} r */
  const siLlego = (r) => (r?.ok ? r.cuerpo : null);

  /* LO QUE LLEGA DESPUÉS, primera parte: la ficha sale ya, en la misma ola
     que el hilo -- es la más lenta y no depende de nada. NO se espera. */
  const fichaCliente = leer('cliente', PLAZO_EXTERNO_MS).then(
    (r) => siLlego(r) ?? { disponible: false, motivo: 'sin_respuesta', cliente: null }
  );
  /* LA CUENTA (10/11/2026): cuánto debe, calculado por el motor con la misma
     herramienta que el agente de cobro --dos idas al sistema del ISP, ficha y
     facturas pendientes--. Reemplaza al «saldo» de la ficha, que no es lo
     que se debe. Tampoco se espera. */
  const cuenta = leer('cuenta', PLAZO_EXTERNO_MS).then(
    (r) => siLlego(r) ?? { disponible: false, motivo: 'sin_respuesta' }
  );

  // Los pedidos son independientes entre si -- en paralelo, no uno atras del
  // otro. Antes se esperaba mensajes, DESPUES herramientas, DESPUES casos:
  // cada salto de conversacion pagaba la suma de las idas y vueltas al motor
  // en vez del maximo, y esa espera es la que se sentia como si la pagina
  // entera se recargara.
  const [rMensajes, rHerr, rCasos, rRelevo, rEquipo, rSync, rAcciones, rChat] = await Promise.all([
    leer('mensajes', PLAZO_MOTOR_MS),
    leer('herramientas', PLAZO_MOTOR_MS),
    leerConPlazo(fetch, `${baseUrl}/manual/casos?tenant=${encodeURIComponent(tenant)}`,
      { headers: headersMotor() }, PLAZO_MOTOR_MS, 'conversacion casos del manual'),
    leer('relevo', PLAZO_MOTOR_MS),
    leer('equipo', PLAZO_MOTOR_MS),
    leer('sincronizaciones', PLAZO_MOTOR_MS),
    leer('acciones', PLAZO_MOTOR_MS),
    /* EL CHAT (21/10/2026, contrato §4.5): las conversaciones ANTERIORES del
       mismo número, para mostrarlas arriba como WhatsApp. Si no llega, la
       conversación se lee igual, sola, como antes. */
    leer('hilo', PLAZO_MOTOR_MS)
  ]);
  const chat = siLlego(rChat);

  if (rMensajes?.status === 404) {
    error(404, 'Esta conversación no existe.');
  }
  if (rMensajes && !rMensajes.ok) {
    error(500, rMensajes.cuerpo?.error || 'No se pudo cargar la conversación.');
  }
  if (!rMensajes?.cuerpo) {
    // El hilo es la pantalla: sin él no hay nada que mostrar. Pero tampoco
    // se espera sin fin -- se dice qué pasa y la persona decide reintentar.
    error(503, 'El asistente está tardando en contestar. Volvé a abrir la conversación en unos segundos.');
  }
  const datos = rMensajes.cuerpo;

  // "Ver proceso": que herramientas uso el agente, para que un supervisor
  // pueda revisar el caso sin tener que leer todo el hilo. No corta la
  // pagina si falla -- es un panel mas, no el contenido principal.
  // Los tres contadores del diagnóstico los cuenta el motor, no esta pagina:
  // la diferencia entre "el codigo lo freno" y "el tercero fallo" sale de una
  // columna de la base, no del texto del error.
  const herramientas = siLlego(rHerr)?.herramientas ?? [];
  const diagnostico = siLlego(rHerr)?.diagnostico ?? null;

  // Como llego la conversacion a estas manos: un evento por transicion del
  // relevo. Mismo criterio que arriba -- es un panel, no el contenido: si el
  // motor no contesta, la actividad queda vacia y el hilo se lee igual.
  const relevo = siLlego(rRelevo)?.eventos ?? [];

  // Que se le hizo al equipo del cliente y si funciono. Es el veredicto del
  // seguimiento de acciones, no una consulta en vivo al ISP: nada se pregunta
  // al abrir la pantalla. Si el motor no contesta, el panel dice que no hubo
  // acciones registradas y la conversacion se atiende igual.
  const equipo = siLlego(rEquipo)?.acciones ?? [];

  // Que efectos externos quedaron sin hacer (B4). Es estado actual, no
  // historia: lo que aparece acá es lo que todavía le falta a la conversación
  // del lado del CRM o del sistema del ISP.
  const sincronizaciones = siLlego(rSync)?.sincronizaciones ?? [];

  // Las acciones que la IA propuso acá, con su estado REAL (B5). Antes una
  // acción terminaba en «aprobada» y nada más -- que es lo que alguien
  // decidió, no lo que pasó: el efecto podía haber fallado y la pantalla decía
  // lo mismo.
  const acciones = siLlego(rAcciones)?.acciones ?? [];

  // Casos fijos para marcar una respuesta como buen ejemplo (ver
  // MarcarEjemplo.svelte). Igual que arriba: si falla, el boton de marcar
  // simplemente no tiene opciones -- no se cae la conversacion por esto.
  const casos = siLlego(rCasos)?.casos ?? [];

  /* LO QUE LLEGA DESPUÉS, segunda parte: lo que depende de lo que dijo el
     hilo. Ninguna se espera acá. Lo que no hace falta pedir viaja como valor
     plano, no como promesa: la página acepta las dos formas.

     La ficha del cliente en el sistema del ISP (arriba): documento, plan,
     estado del servicio y cobranza. NO se guarda: el motor la lee en vivo en
     cada carga y no persiste la respuesta. El objeto trae siempre
     `disponible` y `motivo`, así que la pantalla puede decir POR QUÉ no hay
     ficha --el asistente todavía no identificó al cliente, la empresa no
     tiene conectado su sistema, o el sistema no contestó a tiempo-- en vez de
     dejar un hueco que se lee como un error.

     CÓMO ESTÁ EL EQUIPO — SÓLO SI ESCALÓ. La lectura óptica sale a un sistema
     externo que pide no consultarlo en bucle, así que no se hace en cada
     apertura: se hace cuando una persona tiene el caso en la mano, que es
     cuando el diagnóstico se usa para decidir. Mientras la lleva el
     asistente, la pestaña Equipo abre con el botón "Consultar ahora" y nadie
     paga la espera. El motor cachea cinco minutos, así que recargar la
     pantalla no vuelve a salir al proveedor.

     El ticket de BottleCRM solo se pide si esta conversacion escalo: depende
     de 'caso_id'. La mayoria de las conversaciones (las que el bot resuelve
     solo) ni siquiera lo piden. Una sola lectura alimenta `caso` y `owners`.
     Si el CRM está caído o lento, el chat sigue siendo útil sin él.

     Quien mira y con que rol, para que la pantalla sepa si la conversacion es
     suya y si puede reasignar (B3.4). Solo muestra: el motor decide. Sin la
     lista no se ofrece reasignar; el resto de la pantalla sigue. */
  const sinOptica = { disponible: false, motivo: 'no_consultada', optica: null };
  const optica = datos.conversacion?.escalada_a_humano
    ? leer('optica', PLAZO_EXTERNO_MS).then((r) => siLlego(r) ?? sinOptica)
    : sinOptica;

  const ticket = datos.conversacion?.caso_id
    ? conPlazo(
        Promise.all([
          getTicket({ cookies }, datos.conversacion.caso_id),
          getTicketFormOptions({ cookies })
        ]),
        PLAZO_CRM_MS,
        'conversacion ticket del CRM'
      )
    : null;
  const caso = ticket ? ticket.then((t) => t?.[0]?.ticket ?? null) : null;
  const owners = ticket ? ticket.then((t) => t?.[1]?.owners ?? []) : [];

  const rol = rolDeSesion(locals);
  const operadores = rol === 'ADMIN'
    ? conPlazo(operadoresDeLaOrg(cookies), PLAZO_CRM_MS, 'conversacion operadores').then((l) => l ?? [])
    : [];
  const yo = { id: locals.user?.id ?? '', nombre: (locals.user?.name || locals.user?.email || '').trim() };

  return { conversacion: datos.conversacion, mensajes: datos.mensajes, caso, owners, herramientas, diagnostico, casos,
    relevo, equipo, sincronizaciones, acciones, yo, rol, operadores, fichaCliente, cuenta, optica,
    // Sin el chat no se sabe si esta es la última del número: 'agrupa: false'
    // no ofrece escribirle a una cerrada a ciegas.
    chat: chat ?? { tramos: [], hay_anteriores: false, antes: null,
                    mas_reciente_id: datos.conversacion?.id ?? null, abiertas: [],
                    posteriores: [], agrupa: false } };
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
