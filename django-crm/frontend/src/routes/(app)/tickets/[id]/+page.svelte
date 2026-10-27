<script>
  import { enhance } from '$app/forms';
  import { page } from '$app/state';
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import NextAction from '$lib/v2/components/NextAction.svelte';
  import Pill from '$lib/v2/components/Pill.svelte';
  import Avatar from '$lib/v2/components/Avatar.svelte';
  import { relativeDays, shortAge, longDate } from '$lib/v2/format.js';
  import {
    PRIORITY_TONE,
    CASE_STATUS_TONE,
    CASE_PRIORITY_LABEL,
    CASE_STATUS_LABEL,
    CASE_TYPE_LABEL
  } from '$lib/v2/enums.js';
  import {
    ChevronRight,
    Lock,
    Paperclip,
    Pencil,
    Ticket,
    X,
    Sparkles,
    CircleCheck,
    CircleAlert,
    ArrowRight,
    MessageCircle,
    TriangleAlert,
    LoaderCircle,
    UserRound,
    Cog,
    Hand,
    Inbox
  } from '@lucide/svelte';
  import { nombreLegible } from '$lib/v2/nombre-herramienta.js';
  import { destinoDeLaRespuesta } from '$lib/v2/respuesta-destino.js';
  import { plazoPrimeraRespuesta } from '$lib/v2/plazo-primera-respuesta.js';
  import { partirNombreDelTicket, actorDelEvento, textoDelEvento } from '$lib/v2/ticket-detalle.js';
  import { origenDelTicket } from '$lib/v2/ticket-origen.js';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  /*
   * Lo que paso con WispHub al crear el ticket desde "Nuevo ticket"
   * (26/10/2026). Viaja en la direccion porque el caso ya existia cuando se
   * intento: pase lo que pase, quien lo creo cae aca y tiene que saberlo.
   */
  let avisoWispHub = $derived.by(() => {
    const q = page.url.searchParams;
    const id = q.get('wisphub');
    if (id && q.get('wisphub_sin_atar')) {
      return {
        tono: 'clay',
        texto: `Se creó en WispHub (#${id}), pero no quedó atado a este ticket. Avisá a un administrador para que la importación no lo traiga duplicado.`
      };
    }
    if (id) return { tono: 'moss', texto: `Creado también en WispHub: ticket #${id}.` };
    const error = q.get('wisphub_error');
    if (error) return { tono: 'clay', texto: `El ticket quedó solo en Dexter. ${error}` };
    return null;
  });
  //  El adjunto de "Nuevo ticket" se sube despues de crear el caso: si falla,
  //  el ticket existe igual y esto lo dice (27/10/2026).
  let avisoAdjunto = $derived(page.url.searchParams.get('adjunto_error'));
  //  Y si llego a Dexter pero no al ticket de WispHub.
  let adjuntoSinWispHub = $derived(
    !avisoAdjunto && page.url.searchParams.get('wisphub_sin_adjunto') === '1'
  );

  let { ticket, conversation, articles, alsoOpen, contacts, attachments, activity, canReply } =
    $derived(data);

  /**
   * Lo que el asistente dejo escrito al escalar, ya separado en bloques por
   * el servidor. Null cuando el caso no vino del asistente.
   */
  let agente = $derived(data.agente);

  /*
   * La conversacion arranca ABIERTA, no cerrada.
   *
   * El resumen existe para no tener que leerla, pero cerrarla de entrada
   * obliga a un clic a quien SI necesita verla -- y sobre todo esconde que
   * existe. Quien ya leyo el resumen la pliega y queda plegada mientras dure
   * la visita a este ticket.
   */
  let verConversacion = $state(true);

  /*
   * El asunto limpio para el titulo, y de donde vino el ticket.
   *
   * El nombre crudo es "Asunto · Cliente · #id8" (lo arma el asistente al
   * escalar); de titulo se leia como una linea de log. El asunto va arriba y
   * el resto baja a los chips. `origenDelTicket` es la regla compartida con la
   * cola: no se escribe una segunda.
   */
  let nombre = $derived(partirNombreDelTicket(ticket.name));
  let origenTicket = $derived(origenDelTicket(ticket));
  /** El nombre del sistema del ISP, para el chip "WispHub #N". */
  let sistemaExterno = $derived(
    ticket.provider ? origenDelTicket({ provider: ticket.provider }).etiqueta : 'WispHub'
  );
  const ICONO_ORIGEN = { whatsapp: MessageCircle, wisphub: Inbox, manual: Hand };
  let IconoOrigen = $derived(ICONO_ORIGEN[origenTicket.clave] ?? Hand);

  /** Nombres por id de perfil, para la linea de tiempo. */
  let nombrePorId = $derived(
    Object.fromEntries((data.personas ?? []).map((/** @type {any} */ p) => [p.id, p.name]))
  );

  /*
   * El reloj de la primera respuesta, con el vencimiento del SERVIDOR (ver
   * lib/v2/plazo-primera-respuesta.js). `ahora` avanza cada 30 s para que la
   * franja no se quede quieta mientras alguien tiene el ticket abierto.
   */
  let ahora = $state(Date.now());
  $effect(() => {
    const reloj = setInterval(() => (ahora = Date.now()), 30000);
    return () => clearInterval(reloj);
  });
  let plazo = $derived(plazoPrimeraRespuesta(ticket, ahora));
  const TONO_PLAZO = {
    moss: 'var(--v2-moss)',
    rust: 'var(--v2-rust)',
    clay: 'var(--v2-clay)',
    ember: 'var(--v2-ember)',
    slate: 'var(--v2-slate)'
  };
  /** El texto en indigo usa la variante para texto: la de relleno es para la barra. */
  const TEXTO_PLAZO = { ...TONO_PLAZO, ember: 'var(--v2-ember-text)' };

  /**
   * La conversación como está AHORA, no como estaba cuando se escaló.
   *
   * La transcripción que guarda el caso es una foto del momento del traspaso
   * -- el registro que se audita, y por eso no se reescribe. Pero la
   * conversación sigue: el cliente contesta, y quien atiende está mirando
   * esta pantalla. Sin esto tenía que abrir la bandeja en otra pestaña para
   * enterarse de si le respondieron.
   *
   * Vacío mientras no llegue (o si el caso no vino de una conversación), y
   * entonces se muestra la transcripción del caso, que es lo que había antes.
   */
  let hilo = $state([]);
  let conversacionId = $state('');

  async function traerHilo() {
    if (!conversacionId) return;
    try {
      const r = await fetch(`/api/conversaciones/${conversacionId}/mensajes`);
      if (!r.ok) return;
      const d = await r.json();
      if (d.mensajes?.length) hilo = d.mensajes;
    } catch {
      // Silencio: corre cada pocos segundos.
    }
  }

  /**
   * La conversacion de origen, cuando llega: su canal y el nombre del cliente
   * dicen a donde va la respuesta. Y si HAY chat o no, que es lo que decide
   * el aviso de la caja (`estadoConversacion`, ver +page.server.js).
   *
   * Null mientras no llego: la caja dice "Comprobando…" y no afirma nada.
   * @type {any}
   */
  let conversacionOrigen = $state(null);
  /** @type {'si'|'no'|'no_se_pudo'|null} */
  let estadoConversacion = $state(null);
  // Plano, no $state: solo sirve para notar que se cambio de ticket sin
  // desmontar la pagina, y no tiene que disparar nada.
  let ticketDelEstado = '';

  $effect(() => {
    // 'origen' llega despues que la pagina (ver +page.server.js), asi que el
    // id se toma cuando resuelve y no al montar.
    Promise.resolve(data.origen).then((o) => {
      if (o?.id) conversacionId = o.id;
      conversacionOrigen = o ?? null;
    });
  });

  $effect(() => {
    const id = data.ticket?.id;
    // Otro ticket en la misma pagina: lo que se sabia del anterior no vale.
    // Una revalidacion del MISMO ticket (tras enviar) conserva el valor hasta
    // que llegue el nuevo, para que el aviso no parpadee a "Comprobando".
    if (id !== ticketDelEstado) {
      ticketDelEstado = id;
      estadoConversacion = null;
    }
    Promise.resolve(data.estadoConversacion).then((e) => {
      if (data.ticket?.id === id) estadoConversacion = e ?? 'no_se_pudo';
    });
  });

  $effect(() => {
    if (!conversacionId) return;
    traerHilo();
    // Cada 5 segundos: quien atiende mira esta pantalla mientras escribe, y
    // el cliente contesta a ritmo de chat, no de segundo.
    const reloj = setInterval(traerHilo, 5000);
    return () => clearInterval(reloj);
  });

  /**
   * Los enlaces a los sistemas del ISP, si el caso vino del asistente y llego
   * a identificar al cliente. Null en cualquier otro caso -- y eso no es un
   * error, es lo normal en buena parte de los tickets.
   *
   * Es una funcion y no un $derived porque 'data.origen' ya no es un objeto:
   * es una promesa que llega despues (ver +page.server.js). El ticket abre
   * enseguida y estas tarjetas se completan cuando responden los sistemas.
   *
   * @param {any} origen
   */
  const enlacesDe = (origen) =>
    Object.keys(origen?.enlaces ?? {}).length ? origen.enlaces : null;

  /**
   * La hora que reporta SmartOLT, legible.
   *
   * Llega como '2026-02-27 10:08:35.000000': texto crudo del proveedor, con
   * microsegundos y SIN zona horaria. En una pantalla donde todo lo demás es
   * hora de Bogotá, dejarlo así invita a leerlo como si lo fuera.
   *
   * No se convierte de zona, justamente porque el proveedor no dice cuál es:
   * inventarle una sería peor que el formato feo. Se reformatea y se marca de
   * dónde viene, para que quien compare sepa que está mirando el reloj de
   * SmartOLT y no el de Dexter.
   *
   * @param {string} crudo
   */
  const fechaEquipo = (crudo) => {
    const m = String(crudo ?? '').match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/);
    if (!m) return crudo;
    const [, a, mes, d, h, min] = m;
    return `${d}/${mes}/${a} · ${h}:${min}`;
  };

  /**
   * El contexto tecnico ya no cuelga de la conversacion: un caso importado del
   * sistema del ISP no tiene ninguna y aun asi tiene cliente y equipo. Se
   * considera dibujable si trae algo mas que la marca de identidad, que sola
   * no le dice nada a nadie.
   * @param {any} contexto
   */
  const contextoDe = (contexto) =>
    Object.keys(contexto ?? {}).some((k) => k !== 'identidad') ? contexto : null;

  /**
   * El canal por el que entro la conversacion, legible.
   *
   * Se muestra el valor REAL y no un 'WhatsApp' fijo: el canal lo declara
   * cada despliegue, y esta instancia distingue hoy el de produccion del
   * simulador. Poner siempre 'WhatsApp' haria pasar una prueba por una
   * conversacion de un cliente de verdad.
   *
   * @param {string} canal
   */
  const canalLegible = (canal) => {
    const limpio = (canal ?? '').replace(/-/g, ' ').trim();
    return limpio ? limpio[0].toUpperCase() + limpio.slice(1) : 'Desconocido';
  };

  /*
   * The composer owns its own text rather than reading it back from `data`, so
   * a revalidation cannot wipe a half-written reply. It is cleared only on a
   * send that actually succeeded; `update({ reset: false })` below leaves it
   * alone otherwise, which is what makes a rejected send recoverable.
   */
  let body = $state('');
  let internal = $state(false);
  /** Al enviar, el asistente vuelve a atender la conversación. */
  let devolverAlAsistente = $state(true);
  let sending = $state(false);

  /** A quien se le habla, para el aviso "Sale por WhatsApp a {cliente}". */
  let cliente = $derived(
    conversacionOrigen?.nombre_cliente ||
      ticket.external_client_name ||
      nombre.cliente ||
      contacts?.[0]?.name ||
      ticket.account?.name ||
      ''
  );

  /** A DONDE VA lo que se escribe. Ver lib/v2/respuesta-destino.js. */
  let destino = $derived(
    destinoDeLaRespuesta({
      interna: internal,
      hayConversacion:
        estadoConversacion === 'si'
          ? true
          : estadoConversacion === 'no'
            ? false
            : estadoConversacion === 'no_se_pudo'
              ? 'no_se_pudo'
              : null,
      cliente,
      canal: conversacionOrigen?.canal
    })
  );
  const ICONO_DESTINO = {
    nota: Lock,
    chat: MessageCircle,
    sin_chat: TriangleAlert,
    comprobando: LoaderCircle,
    no_se_pudo: CircleAlert
  };

  /**
   * Las dos pestañas de la caja, con flechas como manda el patron de
   * pestañas: izquierda/derecha (y Inicio/Fin) cambian y llevan el foco.
   * @param {KeyboardEvent} e
   */
  function teclaPestana(e) {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) return;
    e.preventDefault();
    internal = e.key === 'Home' ? false : e.key === 'End' ? true : !internal;
    document.getElementById(internal ? 'tab-nota' : 'tab-cliente')?.focus();
  }

  /*
   * Asignar desde el encabezado. Sin reset: un form.reset() devolveria el
   * selector a su primera opcion ("Sin asignar") aunque el caso ya tenga
   * responsable, porque Svelte fija la PROPIEDAD value y no el atributo.
   */
  let asignando = $state(false);
  /** @type {import('@sveltejs/kit').SubmitFunction} */
  const asignar = () => {
    asignando = true;
    return async ({ update }) => {
      asignando = false;
      await update({ reset: false });
    };
  };

  // The picked file's name, mirrored out of the input so the composer can show
  // and clear it. `fileInput` is the element itself. A file input's value can
  // only be cleared through the DOM, not by rebinding.
  let fileName = $state('');
  /** @type {HTMLInputElement | undefined} */
  let fileInput = $state();

  /** @param {Event} e */
  function pickFile(e) {
    fileName = /** @type {HTMLInputElement} */ (e.currentTarget).files?.[0]?.name ?? '';
  }
  function clearFile() {
    if (fileInput) fileInput.value = '';
    fileName = '';
  }

  // A ticket accepts a file on its own, the API saves the attachment in a block
  // separate from the comment, so the composer sends when there is either text
  // or a file.
  let canSend = $derived(Boolean(body.trim() || fileName));

  /** @type {import('@sveltejs/kit').SubmitFunction} */
  const send = () => {
    sending = true;
    return async ({ result, update }) => {
      sending = false;
      if (result.type === 'success') {
        body = '';
        clearFile();
      }
      await update({ reset: false });
    };
  };

  /**
   * The one thing that needs a person right now, said as the state it is.
   * Ember when the ball is in our court, rust when a target has already been
   * missed. Only "needs you" states earn a banner: a ticket waiting on the
   * customer is not blocked on us, so it stays a quiet line below, and a healthy
   * open ticket gets nothing at all.
   *
   * The mock had a `next_action` sentence telling the agent what to do; nothing
   * on `Case` supports inventing that, so this states the situation and stops.
   *
   * @type {{ tone: 'ember'|'rust', label: string, text: string } | null}
   */
  //
  // La primera respuesta ya NO es un banner (24/10/2026): la franja de plazo
  // de arriba dice lo mismo, con el numero, y la caja para contestar quedo
  // justo debajo. Dos avisos del mismo reloj, uno al lado del otro, competian.
  let alert = $derived.by(() => {
    if (!ticket.is_open) return null;
    if (!ticket.first_response_at) return null;
    // Waiting on the customer is not something we can act on, so it is not a
    // banner. It falls through to the quiet line below.
    if (ticket.status === 'Pending') return null;
    if (!ticket.assignee) {
      return {
        tone: 'ember',
        label: 'Sin responsable',
        text: 'Ya se respondió, pero nadie está a cargo. Asigná a alguien para que no se estanque entre personas.'
      };
    }
    return null;
  });

  let waiting = $derived(
    ticket.is_open && ticket.status === 'Pending' && Boolean(ticket.first_response_at)
  );
</script>

<PageHeader title={nombre.asunto} record>
  {#snippet leading()}
    <!-- Whose ticket this is, at a glance. The account's mark where there is
         one; a ticket glyph where nobody is attached. -->
    {#if ticket.account}
      <Avatar name={ticket.account.name} size={42} />
    {:else}
      <span class="ticket-glyph" aria-hidden="true"><Ticket size={20} /></span>
    {/if}
  {/snippet}
  {#snippet crumb()}
    <a href="/tickets">Tickets</a>
    {#if ticket.account}
      <ChevronRight size={12} />
      <a href="/accounts/{ticket.account.id}">{ticket.account.name}</a>
    {/if}
  {/snippet}
  {#snippet sub()}
    <!-- Lo que identifica al ticket, en chips debajo del asunto. Antes iba
         todo pegado en el titulo ("Asunto · Cliente · #id8") y el numero del
         ticket de WispHub no se mostraba en el detalle, aunque el caso lo
         trae: era lo que une esta pantalla con el panel del proveedor. -->
    <span class="chips">
      <span class="chip v2-num" title="Identificador del ticket en Dexter">
        Ticket {nombre.id || `#${String(ticket.id).slice(0, 8)}`}
      </span>
      <span class="chip chip-origen">
        <IconoOrigen size={11} aria-hidden="true" />
        {origenTicket.etiqueta}
      </span>
      {#if ticket.external_ticket_id}
        <span class="chip">
          {sistemaExterno} #{ticket.external_ticket_id}{#if ticket.external_status}
            · {ticket.external_status}{/if}
        </span>
      {/if}
      <Pill tone={PRIORITY_TONE[ticket.priority]}>{CASE_PRIORITY_LABEL[ticket.priority] ?? ticket.priority}</Pill>
      <Pill tone={CASE_STATUS_TONE[ticket.status]}>{CASE_STATUS_LABEL[ticket.status] ?? ticket.status}</Pill>
      {#if ticket.case_type}<Pill tone="slate">{CASE_TYPE_LABEL[ticket.case_type] ?? ticket.case_type}</Pill>{/if}
    </span>
    <!-- EL RESPONSABLE. Para un admin, el control para cambiarlo; para
         cualquier otro, el nombre y nada mas: el backend solo deja a un
         admin escribir casos ajenos, y un selector que el API iba a rechazar
         es un control que miente. -->
    {#if data.reparte}
      <form method="POST" action="?/asignar" use:enhance={asignar} class="asignar">
        <label for="f-asignar">Responsable</label>
        <select id="f-asignar" name="persona" class="v2-input" value={ticket.assignee_id ?? ''}>
          <option value="">Sin asignar</option>
          {#each data.personas ?? [] as p (p.id)}
            <option value={p.id}>{p.name}</option>
          {/each}
        </select>
        <button class="v2-btn v2-btn-sm" disabled={asignando}>Asignar</button>
        {#if data.yo && !(ticket.assignee_ids ?? []).includes(data.yo)}
          <button class="v2-btn v2-btn-sm" name="yo" value="1" disabled={asignando}>Asignarme</button>
        {/if}
        {#if ticket.assignee_count > 1}
          <!-- PATCH con assigned_to REEMPLAZA la lista entera: decirlo antes. -->
          <span class="asignar-nota">Hoy tiene {ticket.assignee_count} responsables; asignar deja uno solo.</span>
        {/if}
      </form>
    {:else}
      <span class="asignar">
        <span class="asignar-rotulo">Responsable</span>
        <b>{ticket.assignee ?? 'Sin asignar'}</b>
        {#if ticket.assignee_count > 1}<span>+{ticket.assignee_count - 1}</span>{/if}
        {#if !ticket.assignee_count}
          <!-- Sin responsable y a la vista: es de su area (si no, el backend
               no se lo mostraria). Tomarlo lo decide '/tomar/'. -->
          <form method="POST" action="?/tomar" use:enhance={asignar}>
            <button class="v2-btn v2-btn-sm" disabled={asignando}>Asignarme</button>
          </form>
        {/if}
      </span>
    {/if}
  {/snippet}
  {#snippet actions()}
    <a class="v2-btn" href="/tickets/{ticket.id}/edit"><Pencil size={12} />Editar</a>
    {#if ticket.is_open}
      <form method="POST" action="?/setStatus" use:enhance style="display:contents">
        {#if ticket.status !== 'Pending'}
          <button class="v2-btn" name="status" value="Pending">Poner en espera</button>
        {/if}
        <!-- Secundario desde el 24/10/2026: la accion principal de esta
             pantalla es contestar (la caja de arriba), y la regla Fibra es una
             sola principal por pantalla. -->
        <button class="v2-btn" name="status" value="Closed">Cerrar</button>
      </form>
    {:else}
      <form method="POST" action="?/setStatus" use:enhance style="display:contents">
        <button class="v2-btn" name="status" value="New">Reabrir</button>
      </form>
    {/if}
  {/snippet}
</PageHeader>

<div style="display:flex;flex:1;min-height:0;overflow:hidden">
  <div class="v2-main">
    <!-- ============================================================
         LA FRANJA DE PLAZO. Lo primero que se lee debajo del asunto: como
         esta el reloj de la primera respuesta. El vencimiento es el del
         servidor (calendario laboral y pausas ya descontados), no
         `abierto + horas`. Ver lib/v2/plazo-primera-respuesta.js.
         ============================================================ -->
    <div class="v2-pad franja" style="--tono:{TONO_PLAZO[plazo.tono]};--tono-texto:{TEXTO_PLAZO[plazo.tono]}">
      <div class="franja-linea">
        <span class="franja-estado">{plazo.texto}</span>
        <span class="v2-sub franja-dato">
          {#if plazo.plazo}{plazo.plazo} · {/if}abierto hace {shortAge(ticket.opened_at)}
          {#if ticket.escalation_count > 0}
            · <span style="color:var(--v2-rust)">escalado {ticket.escalation_count}×</span>
          {/if}
        </span>
      </div>
      {#if plazo.pct !== null}
        <div
          class="franja-barra"
          role="progressbar"
          aria-label="Tiempo usado del plazo de primera respuesta"
          aria-valuemin="0"
          aria-valuemax="100"
          aria-valuenow={plazo.pct}
        >
          <i style="width:{plazo.pct}%"></i>
        </div>
      {/if}
    </div>

    <div class="v2-scroll">
      <div class="v2-pad" style="padding-top:14px;padding-bottom:24px">
        {#if avisoWispHub}
          <p
            class="v2-card"
            role="status"
            style="padding:10px 13px;margin-bottom:16px;font-size:13px;border-left:3px solid var(--v2-{avisoWispHub.tono})"
          >
            {avisoWispHub.texto}
          </p>
        {/if}
        {#if avisoAdjunto}
          <p
            class="v2-card"
            role="status"
            style="padding:10px 13px;margin-bottom:16px;font-size:13px;border-left:3px solid var(--v2-clay)"
          >
            El ticket se creó, pero el archivo no se adjuntó: {avisoAdjunto} Podés subirlo desde la
            respuesta de abajo.
          </p>
        {:else if adjuntoSinWispHub}
          <p
            class="v2-card"
            role="status"
            style="padding:10px 13px;margin-bottom:16px;font-size:13px;border-left:3px solid var(--v2-clay)"
          >
            El archivo quedó en este ticket, pero no llegó al de WispHub. Si el técnico lo necesita,
            subilo allá a mano.
          </p>
        {/if}
        {#if form?.error}
          <p
            class="v2-card"
            style="padding:10px 13px;margin-bottom:16px;color:var(--v2-rust);font-size:13px"
          >
            {form.error}
          </p>
        {:else if form?.aviso}
          <!-- La respuesta se guardó y quedó en el ticket, pero al cliente no
               le llegó -- casi siempre la ventana de 24 h de WhatsApp. Se dice
               aquí y no en silencio: creer que ya se contestó es exactamente
               lo que deja a alguien esperando. -->
          <p
            class="v2-card"
            style="padding:10px 13px;margin-bottom:16px;color:var(--v2-rust);font-size:13px"
          >
            {form.aviso}
          </p>
        {:else if form?.sent && form?.aceptado_por_meta && form?.aceptacion_registrada}
          <p
            class="v2-card"
            style="padding:10px 13px;margin-bottom:16px;font-size:13px"
          >
            Enviado al cliente y copiado al ticket de la operación.
          </p>
        {:else if form?.sent && form?.resultado && form.resultado !== 'aceptado' && form.aceptado_por_meta !== null}
          <!-- Ni éxito ni fallo: NO CONSTA. Pasa cuando el canal aceptó sin
               devolver identificador, cuando la red se cortó, o cuando el
               recibo no se pudo guardar. Antes este caso no decía nada y se
               leía como si hubiera salido bien.

               Deliberadamente sin "Reintentar": el mensaje pudo haber salido,
               y reenviarlo se lo mandaría al cliente dos veces. -->
          <p
            class="v2-card"
            style="padding:10px 13px;margin-bottom:16px;color:var(--v2-rust);font-size:13px"
          >
            La respuesta quedó guardada y copiada al ticket, pero no podemos confirmar
            que le haya llegado al cliente. No la envíes de nuevo: si salió, la
            recibiría dos veces.
          </p>
        {:else if form?.sent && form?.sin_conversacion}
          <!-- El motor dijo "no hay chat" (404 sin_conversacion). Antes esto
               no decia nada y se leia como enviado. El aviso de la caja ya lo
               anticipaba; esto confirma lo que paso. -->
          <p class="v2-card resultado-atencion">
            Quedó guardada en el ticket. Al cliente no le llegó: este ticket no tiene un chat
            de WhatsApp. Para avisarle, llamalo o escribile por otro medio.
          </p>
        {/if}

        {#if alert}
          <div style="margin-bottom:18px">
            <NextAction label={alert.label} text={alert.text} tone={alert.tone} />
          </div>
        {:else if waiting}
          <p class="v2-sub" style="margin:0 0 18px;font-size:12.5px">
            Esperando al cliente: el reloj de primera respuesta está en pausa mientras está en Pendiente.
          </p>
        {/if}

        <!-- ============================================================
             LA CAJA DE RESPUESTA, ARRIBA (24/10/2026). Estaba al final de
             todo, debajo del resumen, la ficha tecnica y el hilo: quien abria
             el ticket para contestar tenia que bajar la pantalla entera.

             Dos pestañas en vez de la casilla "Nota interna": las dos mandan
             el mismo campo `internal` que siempre (on = nota), asi que el
             servidor no cambia. Y debajo, A DONDE VA el mensaje -- decidido
             por destinoDeLaRespuesta() con la misma señal que usa el envio.
             ============================================================ -->
        {#if canReply}
          {@const IconoDestino = ICONO_DESTINO[destino.clave]}
          <form
            method="POST"
            action="?/reply"
            enctype="multipart/form-data"
            use:enhance={send}
            class="compositor-form"
          >
            <div class="v2-card compositor">
              <div class="compositor-pestanas" role="tablist" aria-label="A quién le escribís">
                <button
                  type="button"
                  role="tab"
                  id="tab-cliente"
                  aria-selected={!internal}
                  aria-controls="panel-respuesta"
                  tabindex={internal ? -1 : 0}
                  onclick={() => (internal = false)}
                  onkeydown={teclaPestana}>Responder al cliente</button
                >
                <button
                  type="button"
                  role="tab"
                  id="tab-nota"
                  aria-selected={internal}
                  aria-controls="panel-respuesta"
                  tabindex={internal ? 0 : -1}
                  onclick={() => (internal = true)}
                  onkeydown={teclaPestana}><Lock size={11} aria-hidden="true" /> Nota interna</button
                >
              </div>

              <div
                role="tabpanel"
                id="panel-respuesta"
                aria-labelledby={internal ? 'tab-nota' : 'tab-cliente'}
                class="compositor-panel"
              >
                <!-- El mismo campo de siempre: el servidor lee internal === 'on'. -->
                {#if internal}<input type="hidden" name="internal" value="on" />{/if}

                <p class="destino destino-{destino.tono}" class:destino-sin-chat={destino.clave === 'sin_chat'} aria-live="polite">
                  <IconoDestino size={13} aria-hidden="true" />
                  <span>{destino.aviso}</span>
                </p>

                <label for="f-cuerpo" class="v2-sr-only">
                  {internal ? 'Nota para el equipo' : 'Respuesta al cliente'}
                </label>
                <textarea
                  id="f-cuerpo"
                  name="body"
                  bind:value={body}
                  rows="3"
                  placeholder={internal ? 'Nota para el equipo…' : 'Escribí la respuesta…'}
                  class="compositor-texto"
                ></textarea>

                <div class="compositor-pie">
                  <!-- Lo decide quien responde, no el sistema: acaba de hacer el
                       trabajo y sabe si su parte terminó o si todavía le está
                       preguntando algo al cliente. Marcado por defecto porque
                       ese es el caso normal --se aplicó el cambio y se avisa--
                       y desmarcarlo es un clic para quien sigue en la charla.
                       Solo con chat detras: sin conversacion no hay nada que
                       devolverle al asistente. -->
                  {#if destino.ofreceDevolver}
                    <label
                      class="v2-sub compositor-casilla"
                      title="El asistente vuelve a atender: responde lo que siga y pregunta si puede cerrar."
                    >
                      <input type="checkbox" name="devolver" bind:checked={devolverAlAsistente} />
                      Devolver la conversación a Dexter
                    </label>
                  {/if}
                  <!-- The whole chip is the click target: a label wrapping a hidden
                       input. A file may ride with the reply or go on its own. -->
                  <label class="attach" class:has-file={fileName}>
                    <Paperclip size={13} />
                    <span class="attach-label">{fileName || 'Adjuntar'}</span>
                    <input
                      bind:this={fileInput}
                      type="file"
                      name="attachment"
                      onchange={pickFile}
                      hidden
                    />
                  </label>
                  {#if fileName}
                    <button type="button" class="clear-file" onclick={clearFile} title="Quitar archivo">
                      <X size={12} />
                    </button>
                  {/if}
                  <label for="f-estado" class="v2-sub" style="margin-left:auto;font-size:11.5px">Estado al enviar</label>
                  <!-- Answering and moving the ticket is one decision, so it is
                       one submit. Empty means "leave the status alone". -->
                  <select id="f-estado" name="status" class="v2-input" style="width:auto;font-size:12px">
                    <option value="">Sin cambios</option>
                    <option value="Assigned">Asignado</option>
                    <option value="Pending">Pendiente</option>
                  </select>
                  <!-- Principal SOLO cuando el mensaje sale de verdad al cliente.
                       Una nota, o una respuesta que se queda en el ticket, no es
                       la accion de esta pantalla: un boton indigo ahi prometeria
                       un envio que no ocurre. -->
                  <button
                    class={destino.primario ? 'v2-btn v2-btn-primary' : 'v2-btn'}
                    disabled={sending || !canSend}
                  >
                    {sending
                      ? internal || destino.clave === 'sin_chat'
                        ? 'Guardando…'
                        : 'Enviando…'
                      : !body.trim() && fileName
                        ? 'Adjuntar archivo'
                        : destino.boton}
                  </button>
                </div>
              </div>
            </div>
          </form>
        {:else}
          <p class="v2-sub" style="margin:0 0 18px;font-size:12.5px">
            Podés leer este ticket pero no responderlo. Pedile a un administrador, o a quien esté
            asignado.
          </p>
        {/if}

        {#if agente}
          <!-- ============================================================
               RESUMEN DE LA CONVERSACION
               Cuatro bloques, y ninguno se escribe aca: los cuatro salen de
               la descripcion que el asistente dejo al escalar, con la traza
               real delante. Esta pantalla los separa y los muestra, no los
               interpreta ni los vuelve a redactar -- un resumen de un
               resumen puede contradecir lo que midieron las herramientas, y
               quien lee no tendria como notarlo.
               ============================================================ -->
          <section class="resumen">
            <header class="resumen-cab">
              <h2>Resumen de la conversación</h2>
              <span class="marca-ia"><Sparkles size={11} /> Generado por el asistente</span>
            </header>

            <div class="resumen-grilla">
              {#if agente.situacion}
                <article class="bloque">
                  <h3>Situación</h3>
                  <p>{agente.situacion}</p>
                  {#if agente.ticketOperativo}
                    <p class="dato-suelto">{agente.ticketOperativo}</p>
                  {/if}
                </article>
              {/if}

              {#if agente.verificado.length}
                <article class="bloque">
                  <h3>Qué ya se consultó</h3>
                  <!-- Dice QUE se consulto y si la herramienta respondio o
                       fallo. NO dice si el resultado fue bueno: un tilde
                       verde al lado de una identidad sin verificar afirmaria
                       lo contrario de lo que devolvio la herramienta. El
                       valor exacto esta abajo, en el detalle tecnico. -->
                  <ul class="lista-chequeos">
                    <!-- La clave es la POSICION, no el nombre de la
                         herramienta: la misma herramienta aparece varias veces
                         en una conversacion normal, y con razon. En el caso que
                         destapo esto, 'consultar_mi_servicio' figura dos veces
                         -- fallo por identidad sin verificar, y volvio a
                         correr bien despues de verificarla. Con el nombre de
                         clave, Svelte tiraba 'each_key_duplicate' al renderizar
                         y el ticket NO se abria: la direccion cambiaba y la
                         pantalla se quedaba en la lista, como si el clic no
                         hubiera pasado (visto en produccion el 28/08/2026). -->
                    {#each agente.verificado as v, i (i)}
                      <li class:fallo={v.fallo}>
                        {#if v.fallo}<CircleAlert size={13} />{:else}<CircleCheck size={13} />{/if}
                        <span>
                          {nombreLegible(v.herramienta)}
                          {#if v.fallo}<em>— no se pudo</em>{/if}
                        </span>
                      </li>
                    {/each}
                  </ul>
                </article>
              {/if}

              {#if agente.noComprobado}
                <article class="bloque destacado">
                  <h3>Qué falta por comprobar</h3>
                  <p>{agente.noComprobado}</p>
                </article>
              {/if}

              {#if agente.siguientePaso}
                <article class="bloque">
                  <h3><ArrowRight size={13} /> Siguiente paso sugerido</h3>
                  <p>{agente.siguientePaso}</p>
                </article>
              {/if}
            </div>

            {#if agente.adjuntos}
              <p class="aviso-adjuntos"><Paperclip size={12} /> {agente.adjuntos}</p>
            {/if}

            <!-- Normalmente no se dibuja nada aca. Es la red para que no se
                 pierda texto en silencio: si el motor empieza a escribir un
                 bloque que esta pantalla todavia no conoce, aparece; si todo
                 encajo en las tarjetas de arriba, no sobra nada y no se ve. -->
            {#if agente.resto}
              <p class="aviso-adjuntos">
                <b>Texto del caso que no encajó en ninguna sección:</b>
                {agente.resto}
              </p>
            {/if}
          </section>

          <!-- Mientras los sistemas del ISP responden, el ticket ya esta en
               pantalla. Sin bloque de espera a proposito: la mayoria de los
               tickets no tiene estas tarjetas, y un cargando que casi siempre
               termina en nada distrae mas de lo que informa. -->

          {#if agente.turnos.length}
            <section class="conversacion-cliente">
              <header class="conv-cab">
                <!-- Sin pestaña de adjuntos desde el 24/10/2026: los mismos
                     archivos estaban aca Y en el panel derecho. Quedan en el
                     panel, donde se ven siempre, sin abrir nada.

                     Al lado del titulo, CUAL conversacion se esta viendo: la
                     viva (se refresca cada 5 s) o la transcripcion que quedo
                     guardada al pasar a una persona. Reemplaza al viejo "Fin de
                     la conversación", que se mostraba aunque el chat siguiera. -->
                <h2 class="conv-titulo">
                  Conversación
                  <span class="conv-fuente">
                    {hilo.length ? 'En vivo · se actualiza sola' : 'Transcripción del momento del pase'}
                  </span>
                </h2>
                <button type="button" class="v2-btn v2-btn-sm" onclick={() => (verConversacion = !verConversacion)}
                  aria-expanded={verConversacion}>
                  {verConversacion ? 'Colapsar' : 'Expandir'} conversación
                </button>
              </header>

              {#if verConversacion}
                <div class="turnos">
                  <!-- El hilo VIVO si se pudo traer; si no, la transcripción
                       que quedó guardada en el caso. Lo segundo es lo que
                       había antes de esto y sigue sirviendo para un ticket
                       cargado a mano, que no tiene conversación detrás. -->
                  {#each (hilo.length ? hilo : agente.turnos) as t, i (i)}
                    <div class="turno" class:propio={t.quien !== 'cliente'}>
                      <span class="turno-avatar" aria-hidden="true">
                        {t.quien === 'cliente' ? 'C' : t.quien === 'humano' ? 'E' : 'A'}
                      </span>
                      <div>
                        <div class="turno-quien">
                          {t.quien === 'cliente'
                            ? 'Cliente'
                            : t.quien === 'humano'
                              ? 'Equipo'
                              : 'Asistente IA'}
                        </div>
                        <div class="burbuja">{t.texto}</div>
                      </div>
                    </div>
                  {/each}
                </div>
              {/if}
            </section>
          {/if}
        {:else if ticket.description}
          <!-- Un caso que no escribio el asistente: se muestra tal cual, que
               es como se mostraba antes de que existiera el resumen. -->
          <div class="v2-card" style="padding:13px 15px;margin-bottom:18px">
            <div class="v2-label" style="margin-bottom:7px">Qué se reportó</div>
            <div style="font-size:13.5px;line-height:1.55;white-space:pre-wrap">
              {ticket.description}
            </div>
          </div>
        {/if}
        <!-- ============================================================
             FUERA del condicional del resumen del agente, y es lo unico que
             la hacia invisible para un caso importado.

             Este bloque vivia dentro de ese condicional, que solo es cierto
             cuando la descripcion del caso es el resumen estructurado que
             escribe el asistente. Un caso traido de WispHub trae la
             descripcion del importador, asi que 'agente' era null y la
             seccion no se dibujaba -- aunque el motor ya hubiera contestado
             con la ficha entera. Se veia en su log: 200 con el contexto
             adentro, y la pantalla sin nada.

             Antes de la Fase 3 no se notaba: un caso sin resumen del agente
             tampoco tenia conversacion, asi que no habia ficha que mostrar.
             La Fase 3 rompio ese acoplamiento -- ahora la ficha sale del
             identificador de servicio -- y la plantilla se habia quedado con
             el condicional viejo.
             ============================================================ -->
        {#await data.contexto then contexto}
          {@const enlaces = contextoDe(contexto)}
          {#if enlaces}
          <!-- ============================================================
               A DONDE SALTAR SIN VOLVER A BUSCAR AL CLIENTE
               Los enlaces los arma el motor, no esta pantalla: es el que
               conoce el identificador de cada sistema y el dominio de cada
               empresa. Y se arman con el IDENTIFICADOR, nunca con el
               nombre -- dos clientes con nombre parecido dan un enlace
               parecido, y ahi se abre la ficha de otra persona.
               ============================================================ -->
          <section class="tecnica">
            <h2>Información técnica del cliente</h2>
            <!-- Los dos orígenes de identidad dicen servicios distintos. Se
                 muestra en vez de resolverse en silencio: el motor eligió el
                 del caso para poder mostrar algo, pero cuál de los dos está
                 mal es una pregunta para una persona. Si esto aparece
                 seguido, lo que falla es el emparejamiento del importador. -->
            {#if enlaces.identidad_en_conflicto}
              <p class="conflicto-identidad">
                <strong>Inconsistencia de servicio.</strong>
                El servicio asociado al caso no coincide con el registrado en
                la conversación. Se muestra la información del servicio del
                caso.
                <span class="conflicto-ids">
                  Servicio del caso <code>{enlaces.identidad_en_conflicto.case}</code>
                  · Servicio de la conversación
                  <code>{enlaces.identidad_en_conflicto.conversacion}</code>
                </span>
              </p>
            {/if}
            <div class="tecnica-grilla">
              <article class="ficha ficha-olt">
                <header>
                  <span class="ficha-nombre">Equipo del cliente — ONT</span>
                </header>
                {#if enlaces.smartolt_ont}
                  <!-- Las dos potencias van con etiqueta de qué significan, no
                       con el nombre de la longitud de onda que usa el
                       proveedor. 1490 nm es la bajada -- lo que RECIBE el
                       equipo del cliente, y el número que mira primero quien
                       diagnostica-- y 1310 nm es la subida, lo que recibe la
                       OLT de vuelta.

                       'onu_signal_value' NO se dibuja: es esas dos mismas
                       cifras pegadas en una sola cadena ("-20.81 dBm / -26.58
                       dBm"), así que sería el mismo dato por tercera vez. -->
                  <dl>
                    {#if enlaces.equipo?.onu_status}
                      <dt>Estado</dt>
                      <dd>{enlaces.equipo.onu_status}</dd>
                    {/if}
                    {#if enlaces.equipo?.onu_signal_1490}
                      <dt>Recibe la ONT</dt>
                      <dd>
                        {enlaces.equipo.onu_signal_1490}
                        {#if enlaces.equipo.onu_signal_1490_veredicto}
                          <span class="veredicto-senal"
                                class:mal={enlaces.equipo.onu_signal_1490_veredicto !== 'aceptable'}
                          >{enlaces.equipo.onu_signal_1490_veredicto}</span>
                        {/if}
                      </dd>
                    {/if}
                    {#if enlaces.equipo?.onu_signal_1310}
                      <dt>Recibe la OLT</dt>
                      <dd>{enlaces.equipo.onu_signal_1310}</dd>
                    {/if}
                    {#if enlaces.equipo?.onu_signal}
                      <dt>Calificación</dt>
                      <dd>{enlaces.equipo.onu_signal} <span class="v2-sub">(SmartOLT)</span></dd>
                    {/if}
                    {#if enlaces.equipo?.last_status_change}
                      <dt>Últ. cambio</dt>
                      <dd>{fechaEquipo(enlaces.equipo.last_status_change)}</dd>
                    {/if}
                    <dt>Serial</dt>
                    <dd><code>{enlaces.sn_onu}</code></dd>
                  </dl>
                  <!-- Si la consulta no respondio, el enlace igual se
                       muestra: sin refresco automatico, una tarjeta vacia
                       no se arregla sola. -->
                  {#if !enlaces.equipo || !Object.keys(enlaces.equipo).length}
                    <p class="sin-dato">
                      No se pudo leer el estado del equipo. El enlace sigue
                      sirviendo para verlo en el panel.
                    </p>
                  {/if}
                  <a class="v2-btn v2-btn-sm" href={enlaces.smartolt_ont}
                     target="_blank" rel="noopener">Ver la ONT ↗</a>
                {:else if enlaces.equipo_no_disponible === 'serial_desactualizado'}
                  <!-- El serial que tiene WispHub no existe en SmartOLT, y hay
                       ONU a nombre del cliente con OTRO serial. Casi siempre le
                       cambiaron el equipo y actualizaron un sistema y no el
                       otro -- confirmado sobre cuatro casos reales, a dos de
                       ellos ese mismo día y el anterior.

                       Se OFRECEN candidatas, no se sustituye: probado que una
                       coincidencia laxa propone el equipo de otro cliente que
                       comparte palabras del nombre, y mostrar su potencia como
                       si fuera la del titular sería exactamente el error que
                       este proyecto ya decidió no cometer con los enlaces
                       armados por nombre. -->
                  <p class="sin-dato">
                    <strong>El serial no existe en SmartOLT.</strong>
                    WispHub tiene <code>{enlaces.sn_onu}</code>, que la OLT no
                    reconoce. Hay {enlaces.equipo_candidatos.length === 1
                      ? 'una ONU'
                      : enlaces.equipo_candidatos.length + ' ONU'} a nombre de
                    este cliente — probablemente le cambiaron el equipo y falta
                    actualizar el serial en WispHub.
                  </p>
                  <ul class="candidatos-onu">
                    {#each enlaces.equipo_candidatos as c}
                      <li>
                        <code>{c.sn}</code>
                        <span class="v2-sub">alta {c.alta} · {c.zona}</span>
                        <span class="v2-sub">{c.nombre}</span>
                      </li>
                    {/each}
                  </ul>
                {:else if enlaces.equipo_no_disponible === 'onu_no_vinculada'}
                  <!-- El servicio SI se identifico; lo que falta es el
                       serial del otro lado. Medido el 10/09/2026 sobre 600
                       clientes: el 19 % no lo tiene cargado, y casi nunca
                       es que no haya equipo. Por eso el texto no culpa al
                       asistente y dice que se arregla solo: el serial se
                       relee en cada apertura, no se guarda aca. -->
                  <p class="sin-dato">
                    <strong>ONU no vinculada.</strong>
                    El servicio está identificado, pero todavía no tiene un
                    serial de ONU registrado en WispHub. Cuando se registre,
                    Dexter mostrará automáticamente la información del equipo.
                  </p>
                {:else}
                  <!-- Caso NORMAL, no una falla: se escala una conversacion
                       justamente cuando el asistente no pudo avanzar, y eso
                       muchas veces incluye no haber identificado el equipo.
                       Medido: de 85 conversaciones, las que llegan a ticket
                       tienden a ser las que no lo tienen. -->
                  <p class="sin-dato">
                    Sin identificador del equipo. El asistente no llegó a
                    identificarlo en esta conversación.
                  </p>
                {/if}
              </article>

              <article class="ficha ficha-isp">
                <header>
                  <span class="ficha-nombre">Servicio del cliente</span>
                </header>
                {#if enlaces.wisphub_perfil}
                  <!-- El orden no es casual: primero con QUIEN se habla
                       (nombre y cedula, para confirmarlo sin salir a
                       buscarlo), despues QUE tiene contratado, y al final
                       el dato tecnico. -->
                  {#if enlaces.cliente}
                    <dl>
                      {#if enlaces.cliente.nombre}
                        <dt>Cliente</dt>
                        <dd>{enlaces.cliente.nombre}</dd>
                      {/if}
                      {#if enlaces.cliente.cedula}
                        <dt>Cédula</dt>
                        <dd><code>{enlaces.cliente.cedula}</code></dd>
                      {/if}
                      {#if enlaces.cliente.estado}
                        <dt>Servicio</dt>
                        <dd>{enlaces.cliente.estado}</dd>
                      {/if}
                      {#if enlaces.cliente.telefono}
                        <dt>Teléfono</dt>
                        <dd>
                          <!-- Separados y marcables: el proveedor los manda en
                               una sola cadena con comas, y quien tiene que
                               llamar no debería recortarlos a mano. -->
                          {#each String(enlaces.cliente.telefono).split(',') as tel}
                            <a class="tel" href="tel:{tel.trim()}">{tel.trim()}</a>
                          {/each}
                        </dd>
                      {/if}
                      {#if enlaces.cliente.direccion}
                        <dt>Dirección</dt>
                        <dd>{enlaces.cliente.direccion}</dd>
                      {/if}
                      {#if enlaces.cliente.localidad}
                        <dt>Barrio</dt>
                        <dd>{enlaces.cliente.localidad}</dd>
                      {/if}
                      {#if enlaces.cliente.plan}
                        <dt>Plan</dt>
                        <dd>{enlaces.cliente.plan}</dd>
                      {/if}
                      {#if enlaces.ip}
                        <dt>IP</dt>
                        <dd><code>{enlaces.ip}</code></dd>
                      {/if}
                    </dl>
                  {/if}
                  <div class="ficha-acciones">
                    <a class="v2-btn v2-btn-sm" href={enlaces.wisphub_perfil}
                       target="_blank" rel="noopener">Ficha ↗</a>
                    {#if enlaces.wisphub_ping}
                      <a class="v2-btn v2-btn-sm" href={enlaces.wisphub_ping}
                         target="_blank" rel="noopener">Ping ↗</a>
                    {/if}
                    {#if enlaces.wisphub_trafico}
                      <a class="v2-btn v2-btn-sm" href={enlaces.wisphub_trafico}
                         target="_blank" rel="noopener">Tráfico ↗</a>
                    {/if}
                    {#if enlaces.router}
                      <a class="v2-btn v2-btn-sm" href={enlaces.router}
                         target="_blank" rel="noopener">Router ↗</a>
                    {/if}
                  </div>
                {:else}
                  <p class="sin-dato">
                    Sin identificador del cliente. No se puede abrir su ficha
                    desde acá sin arriesgar abrir la de otra persona.
                  </p>
                {/if}
              </article>
            </div>
          </section>
          {/if}
        {/await}


        {#if conversation.length === 0}
          <p class="v2-sub" style="margin:0 0 18px;font-size:12.5px">
            Todavía no se dijo nada en este ticket.
          </p>
        {/if}

        {#each conversation as m (m.id)}
          {#if m.direction === 'note'}
            <!-- An internal note is not part of the conversation with the
                 customer, so it does not sit on either side of it. -->
            <div
              class="v2-card"
              style="padding:11px 13px;margin-bottom:14px;border-style:dashed;background:transparent"
            >
              <div
                class="v2-sub"
                style="font-size:11.5px;margin-bottom:5px;display:flex;align-items:center;gap:5px"
              >
                <Lock size={11} />
                <b style="color:var(--v2-ink);font-weight:600">{m.author}</b>
                · nota interna · hace {shortAge(m.at)}
              </div>
              <div style="font-size:13.5px;line-height:1.55;white-space:pre-wrap">{m.body}</div>
            </div>
          {:else}
            <div
              style="display:flex;gap:12px;margin-bottom:14px;{m.direction === 'out'
                ? 'flex-direction:row-reverse'
                : ''}"
            >
              <Avatar name={m.author} size={30} />
              <div
                class="v2-card"
                style="padding:12px 14px;max-width:72%;{m.direction === 'out'
                  ? 'background:var(--v2-line-soft)'
                  : ''}"
              >
                <div class="v2-sub" style="font-size:11.5px;margin-bottom:5px">
                  <b style="color:var(--v2-ink);font-weight:600">{m.author}</b>
                  {#if m.kind === 'email'}· correo{/if}
                  <!-- De dónde salió el mensaje. Sin esto, el hilo del
                       proveedor y el de Dexter se leen como una sola
                       conversación y nadie sabe dónde contestar para que el
                       otro lado se entere. -->
                  {#if m.kind === 'externo'}<span class="origen-externo">{m.origen}</span>{/if}
                  {#if m.adjuntos}· {m.adjuntos} adjunto{m.adjuntos > 1 ? 's' : ''}{/if}
                  · hace {shortAge(m.at)}
                </div>
                {#if m.subject}
                  <div style="font-size:12.5px;font-weight:600;margin-bottom:4px">{m.subject}</div>
                {/if}
                <div style="font-size:13.5px;line-height:1.55;white-space:pre-wrap">{m.body}</div>
              </div>
            </div>
          {/if}
        {/each}

      </div>
    </div>
  </div>

  <aside class="v2-rail">
    <div class="v2-label v2-rail-head">Ticket</div>
    <!-- Prioridad, estado, tipo y responsable viven en el encabezado, y el
         reloj de primera respuesta en la franja de arriba (24/10/2026): aca
         quedan los datos que no estan en ningun otro lado. -->
    <dl class="v2-kv">
      <!-- El area es la escrita en el caso ('Case.area'); la de la persona
           asignada solo decide mientras el caso no la tenga -- misma regla
           que la cola (areaDelCaso). Un caso sin ninguna de las dos no tiene
           area, y decirlo es mas util que dejar el renglon en blanco. -->
      <dt>Área</dt>
      <dd>
        {#if data.area}
          <span class="punto-area" style="--c: {data.area.color || 'var(--v2-slate)'}"></span>
          {data.area.etiqueta}
        {:else}
          <span class="v2-sub">Sin área asignada</span>
        {/if}
      </dd>
      <dt>Abierto</dt>
      <dd>{longDate(ticket.opened_at)}</dd>
      {#if ticket.first_response_at}
        <dt>Primera respuesta</dt>
        <dd>{longDate(ticket.first_response_at)}</dd>
      {/if}
      {#if ticket.resolved_at}
        <dt>Resuelto</dt>
        <dd>{longDate(ticket.resolved_at)}</dd>
      {/if}
    </dl>

    {#await data.origen then origen}
      {#if origen}
        <div class="v2-label v2-rail-head">Más información</div>
        <dl class="v2-kv">
          <dt>ID del caso</dt>
          <!-- El mismo fragmento que va al final del asunto, para poder
               cruzarlo con la bandeja de conversaciones. -->
          <dd><code>#{origen.id.slice(0, 8)}</code></dd>
          <dt>Canal</dt>
          <dd>{canalLegible(origen.canal)}</dd>
          {#if origen.etiqueta}
            <dt>Etiqueta</dt>
            <dd><Pill tone="slate">{origen.etiqueta}</Pill></dd>
          {/if}
          {#if origen.motivo_escalamiento}
            <dt>Motivo del pase</dt>
            <dd>{origen.motivo_escalamiento.replace(/_/g, ' ')}</dd>
          {/if}
        </dl>
      {/if}
    {/await}

    {#if ticket.account}
      <div class="v2-label v2-rail-head">Cuenta</div>
      <a
        class="v2-rail-row"
        href="/accounts/{ticket.account.id}"
        style="color:inherit;text-decoration:none"
      >
        <Avatar name={ticket.account.name} size={29} />
        <div>
          <div style="font-size:12.5px;font-weight:550">{ticket.account.name}</div>
          <div class="v2-sub" style="font-size:11px">
            {#if contacts.length === 1}
              Reportado por {contacts[0].name}
            {:else if contacts.length > 1}
              {contacts.length} personas en este ticket
            {:else}
              Nadie identificado en este ticket
            {/if}
          </div>
        </div>
      </a>
    {/if}

    {#if contacts.length}
      <div class="v2-label v2-rail-head">Personas</div>
      {#each contacts as c (c.id)}
        <a class="v2-rail-row" href="/contacts/{c.id}" style="color:inherit;text-decoration:none">
          <Avatar name={c.name} size={26} />
          <div style="font-size:12.5px;font-weight:550">{c.name}</div>
        </a>
      {/each}
    {/if}

    {#if articles.length}
      <!-- Articles filed against this ticket, not keyword guesses. The mock
           called these "suggested"; suggestions are a different endpoint. -->
      <div class="v2-label v2-rail-head">Artículos vinculados</div>
      {#each articles as a (a.id)}
        <a class="v2-rail-row" href="/solutions/{a.id}" style="color:inherit;text-decoration:none">
          <div>
            <div style="font-size:12.5px;font-weight:550;line-height:1.35">{a.title}</div>
            <div class="v2-sub" style="font-size:11px">
              {a.is_published ? 'Publicado' : 'No publicado'} · actualizado {relativeDays(
                a.updated_at
              )}
            </div>
          </div>
        </a>
      {/each}
    {/if}

    {#if attachments.length}
      <div class="v2-label v2-rail-head">Adjuntos</div>
      {#each attachments as f (f.id)}
        {#if f.url}
          <!-- A download now, not dead text: the path was always in the payload
               and the rail simply never linked it. -->
          <a
            class="v2-rail-row att"
            href={f.url}
            target="_blank"
            rel="noreferrer noopener"
            style="color:inherit;text-decoration:none"
          >
            <Paperclip size={13} />
            <div style="font-size:12.5px;font-weight:550;overflow-wrap:anywhere">{f.name}</div>
          </a>
        {:else}
          <div class="v2-rail-row">
            <Paperclip size={13} />
            <div style="font-size:12.5px;font-weight:550;overflow-wrap:anywhere">{f.name}</div>
          </div>
        {/if}
      {/each}
    {/if}

    {#if alsoOpen.length}
      <div class="v2-label v2-rail-head">También abiertos acá</div>
      {#each alsoOpen as t (t.id)}
        <a class="v2-rail-row" href="/tickets/{t.id}" style="color:inherit;text-decoration:none">
          <div>
            <div style="font-size:12.5px;font-weight:550;line-height:1.35">{t.name}</div>
            <div class="v2-sub" style="font-size:11px">
              {CASE_PRIORITY_LABEL[t.priority] ?? t.priority} · {shortAge(t.opened_at)} de antigüedad
            </div>
          </div>
        </a>
      {/each}
    {/if}

    {#if activity.length}
      <div class="v2-label v2-rail-head">Línea de tiempo</div>
      <!-- Se dibuja como linea y no como lista suelta porque lo que importa
           es el ORDEN: que paso primero y que despues. Una lista de filas
           iguales obliga a leer las fechas para reconstruirlo. -->
      <ol class="linea">
        {#each activity.slice(0, 8) as a (a.id)}
          {@const actor = actorDelEvento(a, { delAsistente: origenTicket.clave === 'whatsapp' || Boolean(agente) })}
          <li>
            <span class="hito" aria-hidden="true"></span>
            <!-- Con NOMBRES: una asignacion trae ids de perfil en su metadata
                 y antes solo decia "Asignado". -->
            <div class="hito-texto">{textoDelEvento(a, nombrePorId)}</div>
            <div class="v2-sub hito-pie">
              <!-- Quien hizo cada cosa, para poder auditarlo: persona, IA o
                   sistema SOLO donde el dato lo permite. El CRM guarda
                   'user_id' vacio para todo lo que no hizo una persona, asi que
                   el resto se dice como es -- "IA o sistema" -- en vez de
                   adivinar dentro de la parte de la pantalla que existe para
                   poder confiar en ella. La regla: lib/v2/ticket-detalle.js. -->
              <span
                class="quien quien-{actor.clave}"
                title={actor.clave === 'ambos'
                  ? 'Sin persona registrada: lo hizo el asistente o un automatismo del CRM, y el registro no distingue cuál.'
                  : undefined}
              >
                {#if actor.clave === 'persona'}<UserRound size={10} aria-hidden="true" />
                {:else if actor.clave === 'ia'}<Sparkles size={10} aria-hidden="true" />
                {:else}<Cog size={10} aria-hidden="true" />{/if}
                {actor.rotulo}
              </span>
              <span>{#if a.by}{a.by} · {/if}{longDate(a.at)}</span>
            </div>
          </li>
        {/each}
      </ol>
    {/if}
  </aside>
</div>

<style>
  .linea {
    list-style: none;
    margin: 0 0 4px;
    padding: 0;
  }
  .linea li {
    position: relative;
    padding: 0 0 14px 18px;
  }
  /* La raya se dibuja en cada hito menos el ultimo: bajarla mas alla del
     ultimo evento sugiere que falta algo por venir. */
  .linea li:not(:last-child)::before {
    content: '';
    position: absolute;
    left: 4px;
    top: 12px;
    bottom: 0;
    width: 1px;
    background: var(--v2-line, #e3e4e1);
  }
  .hito {
    position: absolute;
    left: 0;
    top: 4px;
    width: 9px;
    height: 9px;
    border-radius: 50%;
    border: 2px solid var(--v2-ember);
    background: var(--v2-card, #fff);
  }
  /* El mas reciente, relleno: es donde esta parado el caso ahora. */
  .linea li:first-child .hito {
    background: var(--v2-ember);
  }
  .hito-texto {
    font-size: 12.5px;
    font-weight: 550;
    line-height: 1.35;
  }
  .hito-pie {
    font-size: 11px;
    margin-top: 2px;
    display: flex;
    align-items: center;
    gap: 5px;
    flex-wrap: wrap;
  }

  /* ---- encabezado: chips y responsable -------------------------------- */
  .chips {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
  }
  .chip {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 1px 8px;
    border-radius: 999px;
    font-size: 11.5px;
    line-height: 1.6;
    color: var(--v2-slate);
    background: var(--v2-line-soft);
  }
  /* De donde vino: el fondo neutro de origen, nunca un color de plazo. */
  .chip-origen {
    background: var(--v2-origen);
    color: var(--v2-origen-ink);
  }
  .asignar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
    margin-top: 8px;
    font-size: 12px;
    color: var(--v2-slate);
  }
  .asignar b {
    color: var(--v2-ink);
    font-weight: 600;
  }
  .asignar select {
    width: auto;
    max-width: 220px;
    font-size: 12px;
  }
  .asignar-nota {
    font-size: 11.5px;
    color: var(--v2-clay);
  }

  /* ---- franja de plazo ------------------------------------------------- */
  .franja {
    flex: none;
    padding-top: 10px;
    padding-bottom: 2px;
  }
  .franja-linea {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: 4px 12px;
  }
  .franja-estado {
    font-size: 13px;
    font-weight: 650;
    color: var(--tono-texto);
  }
  .franja-dato {
    font-size: 12px;
  }
  .franja-barra {
    margin-top: 6px;
    height: 4px;
    border-radius: 3px;
    background: var(--v2-line);
    overflow: hidden;
  }
  .franja-barra i {
    display: block;
    height: 100%;
    background: var(--tono);
  }

  /* ---- la caja de respuesta ------------------------------------------- */
  .compositor-form {
    margin-bottom: 20px;
  }
  .compositor {
    padding: 0;
    overflow: hidden;
  }
  .compositor-pestanas {
    display: flex;
    gap: 2px;
    padding: 0 12px;
    border-bottom: 1px solid var(--v2-line);
  }
  .compositor-pestanas button {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 10px 10px 9px;
    margin-bottom: -1px;
    background: none;
    border: 0;
    border-bottom: 2px solid transparent;
    font: inherit;
    font-size: 13px;
    font-weight: 600;
    color: var(--v2-slate);
    cursor: pointer;
  }
  .compositor-pestanas button:hover {
    color: var(--v2-ink);
  }
  .compositor-pestanas button[aria-selected='true'] {
    color: var(--v2-ink);
    font-weight: 650;
    border-bottom-color: var(--v2-ember);
  }
  .compositor-pestanas button:focus-visible {
    outline: 2px solid var(--v2-ember);
    outline-offset: -2px;
    border-radius: 6px 6px 0 0;
  }
  .compositor-panel {
    padding: 12px 14px 13px;
  }
  .compositor-texto {
    width: 100%;
    border: none;
    background: transparent;
    resize: vertical;
    font: inherit;
    font-size: 13.5px;
    line-height: 1.55;
    color: var(--v2-ink);
    outline: none;
  }
  .compositor-pie {
    display: flex;
    gap: 9px;
    align-items: center;
    border-top: 1px solid var(--v2-line);
    padding-top: 12px;
    flex-wrap: wrap;
  }
  .compositor-casilla {
    display: flex;
    align-items: center;
    gap: 5px;
    font-size: 12px;
    cursor: pointer;
  }

  /* A DONDE VA. Gris = se queda adentro; indigo suave = sale al cliente;
     ambar = el cliente NO lo va a recibir. */
  .destino {
    display: flex;
    align-items: flex-start;
    gap: 7px;
    margin: 0 0 10px;
    padding: 8px 10px;
    border-radius: 8px;
    font-size: 12.5px;
    line-height: 1.45;
  }
  .destino :global(svg) {
    flex: none;
    margin-top: 2px;
  }
  .destino-neutro {
    background: var(--v2-line-soft);
    color: var(--v2-slate);
  }
  .destino-accion {
    background: var(--v2-ember-soft);
    color: var(--v2-ember-text);
  }
  .destino-atencion {
    background: color-mix(in srgb, var(--v2-clay) 9%, transparent);
    color: var(--v2-clay);
    border-left: 3px solid var(--v2-clay);
  }
  .destino-sin-chat span {
    color: var(--v2-ink);
  }
  .resultado-atencion {
    padding: 10px 13px;
    margin-bottom: 16px;
    font-size: 13px;
    border-left: 3px solid var(--v2-clay);
  }

  .tecnica {
    margin-bottom: 18px;
  }
  .tecnica h2 {
    font-size: 11.5px;
    font-weight: 650;
    letter-spacing: 0.03em;
    text-transform: uppercase;
    color: var(--v2-slate);
    margin: 0 0 9px;
  }
  .tecnica-grilla {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 12px;
  }
  .ficha {
    border: 1px solid var(--v2-line, #e3e4e1);
    border-radius: 10px;
    background: var(--v2-card, #fff);
    padding: 12px 14px 13px;
    /* El color entra por un filete lateral y no por el fondo: dos tarjetas
       de fondo saturado compiten entre si y ninguna resalta. */
    border-left: 3px solid var(--acento);
  }
  .ficha-olt {
    --acento: #0e7490;
  }
  .ficha-isp {
    --acento: #2f6fed;
  }
  .ficha-nombre {
    font-size: 12.5px;
    font-weight: 650;
  }
  .ficha dl {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 2px 10px;
    margin: 8px 0 10px;
    font-size: 12px;
  }
  .ficha dt {
    color: var(--v2-slate);
  }
  .ficha dd {
    margin: 0;
  }
  .ficha-acciones {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .sin-dato {
    margin: 8px 0 0;
    font-size: 12px;
    line-height: 1.5;
    color: var(--v2-slate);
  }

  .quien {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    padding: 0 5px;
    border-radius: 4px;
    font-size: 10px;
    font-weight: 650;
    letter-spacing: 0.02em;
    background: var(--v2-line-soft, #f0f0ee);
    color: var(--v2-slate);
  }
  /* Persona en tinta, IA con la marca del asistente, sistema neutro. Ninguno
     usa un color de plazo: quien hizo algo no es una alarma. */
  .quien-persona {
    background: var(--v2-origen);
    color: var(--v2-ink);
  }
  .quien-ia {
    background: var(--v2-ember-soft);
    color: var(--v2-ember-text);
  }
  .quien-sistema,
  .quien-ambos {
    background: var(--v2-line-soft);
    color: var(--v2-slate);
  }

  .punto-area {
    display: inline-block;
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--c);
    margin-right: 4px;
    vertical-align: middle;
  }

  /* ---- resumen del asistente ------------------------------------------ */
  .resumen {
    border: 1px solid var(--v2-line, #e3e4e1);
    border-radius: 12px;
    background: var(--v2-card, #fff);
    padding: 15px 17px 17px;
    margin-bottom: 16px;
  }
  .resumen-cab {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
    margin-bottom: 14px;
  }
  .resumen-cab h2 {
    font-size: 14.5px;
    font-weight: 650;
    margin: 0;
  }
  .marca-ia {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 11px;
    color: var(--v2-slate);
    border: 1px solid var(--v2-line, #e3e4e1);
    border-radius: 999px;
    padding: 2px 9px 2px 7px;
  }
  /* Cuatro bloques que se acomodan solos: en una pantalla angosta caen uno
     debajo del otro sin puntos de corte escritos a mano. */
  .resumen-grilla {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(215px, 1fr));
    gap: 16px 22px;
  }
  .bloque h3 {
    display: flex;
    align-items: center;
    gap: 5px;
    font-size: 11.5px;
    font-weight: 650;
    letter-spacing: 0.03em;
    text-transform: uppercase;
    color: var(--v2-slate);
    margin: 0 0 6px;
  }
  .bloque p {
    margin: 0;
    font-size: 13px;
    line-height: 1.55;
  }
  /* El unico bloque con acento: "que falta por comprobar" es donde tiene que
     empezar quien toma el caso. Si los cuatro gritaran, ninguno guiaria. */
  .bloque.destacado h3 {
    color: var(--v2-clay, #a8560b);
  }
  .dato-suelto {
    margin-top: 6px !important;
    font-size: 12px !important;
    color: var(--v2-slate);
  }
  .lista-chequeos {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 5px;
  }
  .lista-chequeos li {
    display: flex;
    align-items: flex-start;
    gap: 6px;
    font-size: 12.5px;
    line-height: 1.45;
    color: var(--v2-moss);
  }
  .lista-chequeos li.fallo {
    color: var(--v2-rust, #b0400c);
  }
  .lista-chequeos li span {
    color: var(--v2-ink, #1c1f21);
  }
  .lista-chequeos em {
    font-style: normal;
    color: var(--v2-rust, #b0400c);
  }
  .aviso-adjuntos {
    display: flex;
    align-items: flex-start;
    gap: 6px;
    margin: 14px 0 0;
    padding-top: 12px;
    border-top: 1px solid var(--v2-line, #e3e4e1);
    font-size: 12.5px;
    color: var(--v2-slate);
  }

  /* ---- la conversacion del asistente ---------------------------------- */
  .conversacion-cliente {
    margin-bottom: 20px;
  }
  .conv-cab {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 12px;
  }
  .turnos {
    display: flex;
    flex-direction: column;
    gap: 11px;
  }
  .turno {
    display: flex;
    gap: 10px;
    align-items: flex-start;
  }
  .turno-avatar {
    flex: none;
    width: 26px;
    height: 26px;
    border-radius: 50%;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: 11px;
    font-weight: 700;
    background: var(--v2-line-soft, #f0f0ee);
    color: var(--v2-slate);
  }
  .turno.propio .turno-avatar {
    background: color-mix(in srgb, var(--v2-ember) 10%, transparent);
    color: var(--v2-ember-text);
  }
  .turno-quien {
    font-size: 11px;
    font-weight: 600;
    color: var(--v2-slate);
    margin-bottom: 3px;
  }
  .turno.propio .turno-quien {
    color: var(--v2-ember-text);
  }
  .burbuja {
    display: inline-block;
    padding: 8px 12px;
    border-radius: 10px;
    background: var(--v2-line-soft, #f4f4f2);
    font-size: 13px;
    line-height: 1.5;
    white-space: pre-wrap;
    max-width: 62ch;
  }
  .turno.propio .burbuja {
    background: var(--v2-card, #fff);
    border: 1px solid var(--v2-line, #e3e4e1);
  }
  .conv-titulo {
    display: flex;
    align-items: baseline;
    flex-wrap: wrap;
    gap: 4px 9px;
    margin: 0;
    font-size: 14.5px;
    font-weight: 650;
  }
  .conv-fuente {
    font-size: 11.5px;
    font-weight: 500;
    color: var(--v2-slate);
  }

  /* Identity mark for a ticket that has no account to show a face for. */
  .ticket-glyph {
    display: grid;
    place-items: center;
    width: 42px;
    height: 42px;
    border-radius: 50%;
    background: var(--v2-line-soft);
    border: 1px solid var(--v2-line);
    color: var(--v2-slate);
  }

  /* The composer's attach control, sized to sit in the action row beside the
     Internal-note toggle. */
  .attach {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 5px 9px;
    font-size: 12px;
    color: var(--v2-slate);
    border: 1px solid var(--v2-line);
    border-radius: 7px;
    cursor: pointer;
  }
  .attach:hover,
  .attach.has-file {
    color: var(--v2-ink);
    border-color: var(--v2-slate);
  }
  .attach .attach-label {
    max-width: 140px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .clear-file {
    display: grid;
    place-items: center;
    padding: 4px;
    border: none;
    background: transparent;
    color: var(--v2-slate);
    cursor: pointer;
    border-radius: 6px;
  }
  .clear-file:hover {
    color: var(--v2-rust);
    background: var(--v2-hover);
  }

  /* The whole attachment row lifts slightly on hover to read as a download. */
  .att:hover {
    background: var(--v2-hover);
  }

  /* El conflicto de identidad. Se ve, no se esconde: es el unico aviso de
     esta pantalla que puede significar que el importador emparejo mal. */
  .conflicto-identidad {
    margin: 0 0 var(--v2-space-3);
    padding: var(--v2-space-3);
    border-left: 3px solid var(--v2-clay);
    background: color-mix(in srgb, var(--v2-clay) 6%, transparent);
    border-radius: 4px;
    font-size: 0.875rem;
    line-height: 1.5;
  }
  .conflicto-ids {
    display: block;
    margin-top: var(--v2-space-2);
    font-size: 0.8125rem;
    color: var(--v2-slate);
  }

  /* El veredicto de la potencia, al lado del numero. Cuando no es aceptable
     el texto del proveedor explica la causa probable -- "problema en el drop
     (conector, cable o tensores)" -- y eso es justo lo que hace falta antes de
     mandar una cuadrilla. */
  .veredicto-senal {
    display: inline-block;
    margin-left: 6px;
    font-size: 11.5px;
    line-height: 1.35;
    padding: 1px 6px;
    border-radius: 3px;
    background: var(--v2-line-soft);
    color: var(--v2-slate);
  }
  .veredicto-senal.mal {
    background: color-mix(in srgb, var(--v2-clay) 10%, transparent);
    color: var(--v2-clay);
  }
  .tel { display: inline-block; margin-right: 10px; }

  /* El origen de cada mensaje del hilo: lo que se escribio en el sistema del
     ISP contra lo que se escribio desde Dexter. Discreto, pero en cada
     burbuja: sin esto las dos conversaciones se leen como una sola. */
  .origen-externo {
    display: inline-block;
    margin: 0 3px;
    padding: 0 5px;
    border-radius: 3px;
    font-size: 10.5px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    background: var(--v2-origen);
    color: var(--v2-origen-ink);
  }
  .candidatos-onu {
    list-style: none;
    margin: 8px 0 10px;
    padding: 0;
    display: grid;
    gap: 6px;
  }
  .candidatos-onu li {
    display: grid;
    gap: 1px;
    padding: 6px 8px;
    border-left: 2px solid var(--v2-clay);
    background: color-mix(in srgb, var(--v2-clay) 5%, transparent);
    font-size: 12px;
  }
  .candidatos-onu .v2-sub { font-size: 11px; }
</style>
