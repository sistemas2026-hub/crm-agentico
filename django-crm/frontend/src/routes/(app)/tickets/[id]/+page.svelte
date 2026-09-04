<script>
  import { enhance } from '$app/forms';
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import NextAction from '$lib/v2/components/NextAction.svelte';
  import Pill from '$lib/v2/components/Pill.svelte';
  import Avatar from '$lib/v2/components/Avatar.svelte';
  import { relativeDays, shortAge, longDate, relativeTime } from '$lib/v2/format.js';
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
    ArrowRight
  } from '@lucide/svelte';
  import { nombreLegible } from '$lib/v2/nombre-herramienta.js';
  import { accionLegible } from '$lib/v2/acciones-historial.js';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

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

  /** Que pestaña se ve: la conversacion o lo que el cliente adjunto. */
  let pestana = $state('conversacion');

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

  $effect(() => {
    // 'origen' llega despues que la pagina (ver +page.server.js), asi que el
    // id se toma cuando resuelve y no al montar.
    Promise.resolve(data.origen).then((o) => {
      if (o?.id) conversacionId = o.id;
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
  let alert = $derived.by(() => {
    if (!ticket.is_open) return null;
    if (!ticket.first_response_at) {
      return ticket.first_response_breached
        ? {
            tone: 'rust',
            label: 'Primera respuesta atrasada',
            text: 'Pasó su objetivo de primera respuesta y sigue sin contestar. Una respuesta abajo es la primera respuesta. Detiene el reloj.'
          }
        : {
            tone: 'ember',
            label: 'Necesita una primera respuesta',
            text: 'Todavía nadie respondió. Una respuesta abajo es la primera respuesta. Es lo que detiene el reloj de primera respuesta.'
          };
    }
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

<PageHeader title={ticket.name} record>
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
  {#snippet actions()}
    <a class="v2-btn" href="/tickets/{ticket.id}/edit"><Pencil size={12} />Editar</a>
    {#if ticket.is_open}
      <form method="POST" action="?/setStatus" use:enhance style="display:contents">
        {#if ticket.status !== 'Pending'}
          <button class="v2-btn" name="status" value="Pending">Poner en espera</button>
        {/if}
        <button class="v2-btn v2-btn-primary" name="status" value="Closed">Cerrar</button>
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
    <div
      class="v2-pad"
      style="padding-top:12px;display:flex;gap:7px;align-items:center;flex-wrap:wrap;flex:none"
    >
      <Pill tone={PRIORITY_TONE[ticket.priority]}>{CASE_PRIORITY_LABEL[ticket.priority] ?? ticket.priority}</Pill>
      <Pill tone={CASE_STATUS_TONE[ticket.status]}>{CASE_STATUS_LABEL[ticket.status] ?? ticket.status}</Pill>
      {#if ticket.case_type}<Pill tone="slate">{CASE_TYPE_LABEL[ticket.case_type] ?? ticket.case_type}</Pill>{/if}
      <span class="v2-sub">
        <!-- There is no ticket number. `Case` has a UUID and a subject, so the
             subject is the identifier and the age is the useful fact. -->
        Abierto hace {shortAge(ticket.opened_at)}
        {#if ticket.first_response_at}
          · primera respuesta {relativeTime(ticket.first_response_at)}
        {/if}
        {#if ticket.escalation_count > 0}
          · <span style="color:var(--v2-rust)">escalado {ticket.escalation_count}×</span>
        {/if}
      </span>
    </div>

    <div class="v2-scroll">
      <div class="v2-pad" style="padding-top:14px;padding-bottom:24px">
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
        {:else if form?.sent && form?.entregado}
          <p
            class="v2-card"
            style="padding:10px 13px;margin-bottom:16px;font-size:13px"
          >
            Enviado al cliente y copiado al ticket de la operación.
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
          {#await data.origen then origen}
            {@const enlaces = enlacesDe(origen)}
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
              <div class="tecnica-grilla">
                <article class="ficha ficha-olt">
                  <header>
                    <span class="ficha-nombre">Equipo del cliente — ONT</span>
                  </header>
                  {#if enlaces.smartolt_ont}
                    <dl>
                      {#if enlaces.equipo?.onu_status}
                        <dt>Estado</dt>
                        <dd>{enlaces.equipo.onu_status}</dd>
                      {/if}
                      {#if enlaces.equipo?.onu_signal}
                        <dt>Señal</dt>
                        <dd>
                          {enlaces.equipo.onu_signal}
                          {#if enlaces.equipo.onu_signal_1490}
                            <span class="v2-sub">({enlaces.equipo.onu_signal_1490})</span>
                          {/if}
                        </dd>
                      {/if}
                      {#if enlaces.equipo?.last_status_change}
                        <dt>Últ. cambio</dt>
                        <dd>{enlaces.equipo.last_status_change}</dd>
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

          {#if agente.turnos.length}
            <section class="conversacion-cliente">
              <header class="conv-cab">
                <!-- Pestañas, no dos secciones: la conversacion y lo que el
                     cliente mando son la misma evidencia mirada de dos
                     formas. Los adjuntos siguen ademas en el panel derecho,
                     donde estan SIEMPRE visibles -- esto no los mueve de
                     ahi, agrega el lugar donde uno los busca cuando esta
                     leyendo la conversacion. -->
                <nav class="v2-tabs conv-pestanas" aria-label="Conversación">
                  <button type="button" onclick={() => (pestana = 'conversacion')}
                    aria-current={pestana === 'conversacion' ? 'page' : undefined}
                    >Conversación</button>
                  <button type="button" onclick={() => (pestana = 'adjuntos')}
                    aria-current={pestana === 'adjuntos' ? 'page' : undefined}>
                    Adjuntos
                    {#if attachments.length}
                      <span class="v2-tab-count v2-num">{attachments.length}</span>
                    {/if}
                  </button>
                </nav>
                {#if pestana === 'conversacion'}
                  <button type="button" class="v2-btn v2-btn-sm" onclick={() => (verConversacion = !verConversacion)}>
                    {verConversacion ? 'Colapsar' : 'Expandir'} conversación
                  </button>
                {/if}
              </header>

              {#if pestana === 'adjuntos'}
                {#if attachments.length}
                  <ul class="lista-adjuntos">
                    {#each attachments as f (f.id)}
                      <li>
                        <a href={f.url} target="_blank" rel="noopener">{f.name}</a>
                        <span class="v2-sub">hace {shortAge(f.at)}</span>
                      </li>
                    {/each}
                  </ul>
                {:else}
                  <p class="fin-conv">Esta conversación no trajo archivos.</p>
                {/if}
              {:else if verConversacion}
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
                <p class="fin-conv">Fin de la conversación con el asistente</p>
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

        {#if conversation.length === 0}
          <p class="v2-sub" style="margin:0 0 18px;font-size:12.5px">
            Todavía no se dijo nada en este ticket. Una respuesta abajo es la primera respuesta. Es
            lo que detiene el reloj de primera respuesta.
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

        {#if canReply}
          <form method="POST" action="?/reply" enctype="multipart/form-data" use:enhance={send}>
            <div class="v2-card" style="padding:13px 14px;margin-top:18px">
              <textarea
                name="body"
                bind:value={body}
                rows="3"
                placeholder={internal
                  ? 'Nota para el equipo — el cliente no la ve…'
                  : 'Responder al cliente por donde escribió…'}
                style="width:100%;border:none;background:transparent;resize:vertical;font:inherit;font-size:13.5px;line-height:1.55;color:var(--v2-ink);outline:none"
              ></textarea>
              <div
                style="display:flex;gap:9px;align-items:center;border-top:1px solid var(--v2-line);padding-top:12px;flex-wrap:wrap"
              >
                <label
                  class="v2-sub"
                  style="display:flex;align-items:center;gap:5px;font-size:12px;cursor:pointer"
                >
                  <input type="checkbox" name="internal" bind:checked={internal} />
                  Nota interna
                </label>
                <!-- Lo decide quien responde, no el sistema: acaba de hacer el
                     trabajo y sabe si su parte terminó o si todavía le está
                     preguntando algo al cliente. Marcado por defecto porque
                     ese es el caso normal --se aplicó el cambio y se avisa--
                     y desmarcarlo es un clic para quien sigue en la charla. -->
                {#if !internal}
                  <label
                    class="v2-sub"
                    style="display:flex;align-items:center;gap:5px;font-size:12px;cursor:pointer"
                    title="El asistente vuelve a atender: responde lo que siga y pregunta si puede cerrar."
                  >
                    <input
                      type="checkbox"
                      name="devolver"
                      bind:checked={devolverAlAsistente}
                    />
                    Devolver al asistente
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
                <span class="v2-sub" style="margin-left:auto;font-size:11.5px">Estado al enviar</span>
                <!-- Answering and moving the ticket is one decision, so it is
                     one submit. Empty means "leave the status alone". -->
                <select name="status" class="v2-input" style="width:auto;font-size:12px">
                  <option value="">Sin cambios</option>
                  <option value="Assigned">Asignado</option>
                  <option value="Pending">Pendiente</option>
                </select>
                <button class="v2-btn v2-btn-primary" disabled={sending || !canSend}>
                  {sending
                    ? 'Enviando…'
                    : body.trim()
                      ? internal
                        ? 'Agregar nota'
                        : 'Enviar respuesta'
                      : fileName
                        ? 'Adjuntar archivo'
                        : internal
                          ? 'Agregar nota'
                          : 'Enviar respuesta'}
                </button>
              </div>
            </div>
            {#if internal}
              <p class="v2-sub" style="margin:8px 2px 0;font-size:11.5px">
                Una nota queda dentro del equipo y no detiene el reloj de primera respuesta.
              </p>
            {/if}
          </form>
        {:else}
          <p class="v2-sub" style="margin-top:18px;font-size:12.5px">
            Podés leer este ticket pero no responderlo. Pedile a un administrador, o a quien esté
            asignado.
          </p>
        {/if}
      </div>
    </div>
  </div>

  <aside class="v2-rail">
    <div class="v2-label v2-rail-head">Ticket</div>
    <dl class="v2-kv">
      <dt>Prioridad</dt>
      <dd><Pill tone={PRIORITY_TONE[ticket.priority]}>{CASE_PRIORITY_LABEL[ticket.priority] ?? ticket.priority}</Pill></dd>
      <dt>Estado</dt>
      <dd><Pill tone={CASE_STATUS_TONE[ticket.status]}>{CASE_STATUS_LABEL[ticket.status] ?? ticket.status}</Pill></dd>
      <dt>Tipo</dt>
      <dd>{ticket.case_type ? (CASE_TYPE_LABEL[ticket.case_type] ?? ticket.case_type) : 'Sin definir'}</dd>
      <!-- El area sale de a quien esta asignado, igual que en la cola: el CRM
           no tiene campo de area, la tiene el asistente y es por persona. Un
           caso sin dueño no tiene area, y decirlo es mas util que dejar el
           renglon en blanco. -->
      <dt>Área</dt>
      <dd>
        {#if data.area}
          <span class="punto-area" style="--c: {data.area.color || 'var(--v2-muted)'}"></span>
          {data.area.etiqueta}
        {:else}
          <span class="v2-sub">Sin área asignada</span>
        {/if}
      </dd>
      <dt>Asignado a</dt>
      <dd>
        {ticket.assignee ?? 'Sin asignar'}
        {#if ticket.assignee_count > 1}
          <span class="v2-sub">+{ticket.assignee_count - 1}</span>
        {/if}
      </dd>
      <dt>Abierto</dt>
      <dd>{longDate(ticket.opened_at)}</dd>
      <dt>Primera respuesta</dt>
      <dd>
        {#if ticket.first_response_at}
          {relativeTime(ticket.first_response_at)}
        {:else if ticket.first_response_deadline}
          <span style={ticket.first_response_breached ? 'color:var(--v2-rust)' : ''}>
            vence {relativeTime(ticket.first_response_deadline)}
          </span>
        {:else}
          Sin objetivo
        {/if}
      </dd>
      {#if ticket.resolved_at}
        <dt>Resuelto</dt>
        <dd>{longDate(ticket.resolved_at)}</dd>
      {/if}
      {#if ticket.paused_at}
        <dt>SLA</dt>
        <dd>Pausado mientras está pendiente</dd>
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
          <li>
            <span class="hito" aria-hidden="true"></span>
            <div class="hito-texto">{accionLegible(a)}</div>
            <div class="v2-sub hito-pie">
              <!-- Quien hizo cada cosa, para poder auditarlo.
                   Solo hay DOS etiquetas, no tres, y es una limitacion real y
                   no una simplificacion: el CRM guarda 'user_id' vacio para
                   todo lo que no hizo una persona, asi que lo que ejecuto el
                   asistente y lo que hizo un automatismo del CRM llegan aca
                   indistinguibles. Poner "IA" adivinando cual es cual seria
                   inventar dentro de la parte de la pantalla que existe
                   justamente para poder confiar en ella. -->
              <span class="quien" class:humano={a.by}>{a.by ? 'Humano' : 'Sistema'}</span>
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
    border: 2px solid var(--v2-indigo, #5b52d6);
    background: var(--v2-card, #fff);
  }
  /* El mas reciente, relleno: es donde esta parado el caso ahora. */
  .linea li:first-child .hito {
    background: var(--v2-indigo, #5b52d6);
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

  .conv-pestanas {
    margin-bottom: 0;
  }
  .conv-pestanas button {
    background: none;
    border: 0;
    font: inherit;
    cursor: pointer;
  }
  .lista-adjuntos {
    list-style: none;
    margin: 10px 0 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 7px;
    font-size: 13px;
  }
  .lista-adjuntos li {
    display: flex;
    align-items: baseline;
    gap: 8px;
  }
  .lista-adjuntos .v2-sub {
    font-size: 11.5px;
  }

  .tecnica {
    margin-bottom: 18px;
  }
  .tecnica h2 {
    font-size: 11.5px;
    font-weight: 650;
    letter-spacing: 0.03em;
    text-transform: uppercase;
    color: var(--v2-muted, #6b7378);
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
    --acento: #e8590c;
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
    color: var(--v2-muted, #8a9196);
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
    color: var(--v2-muted, #8a9196);
  }

  .quien {
    display: inline-block;
    padding: 0 5px;
    border-radius: 4px;
    font-size: 10px;
    font-weight: 650;
    letter-spacing: 0.02em;
    background: var(--v2-line-soft, #f0f0ee);
    color: var(--v2-muted, #6b7378);
  }
  .quien.humano {
    background: color-mix(in srgb, var(--v2-teal, #0d7a6f) 13%, transparent);
    color: var(--v2-teal, #0d7a6f);
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
    color: var(--v2-muted, #6b7378);
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
    color: var(--v2-muted, #6b7378);
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
    color: var(--v2-muted, #6b7378);
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
    color: var(--v2-teal, #0d7a6f);
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
    color: var(--v2-muted, #6b7378);
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
    color: var(--v2-muted, #6b7378);
  }
  .turno.propio .turno-avatar {
    background: color-mix(in srgb, var(--v2-indigo, #5b52d6) 14%, transparent);
    color: var(--v2-indigo, #5b52d6);
  }
  .turno-quien {
    font-size: 11px;
    font-weight: 600;
    color: var(--v2-muted, #6b7378);
    margin-bottom: 3px;
  }
  .turno.propio .turno-quien {
    color: var(--v2-indigo, #5b52d6);
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
  .fin-conv {
    text-align: center;
    margin: 14px 0 0;
    font-size: 11.5px;
    color: var(--v2-muted, #a3a9ad);
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
</style>
