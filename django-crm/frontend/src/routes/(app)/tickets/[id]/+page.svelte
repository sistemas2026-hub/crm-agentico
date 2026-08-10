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
  import { ChevronRight, Lock, Paperclip, Pencil, Ticket, X } from '@lucide/svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  let { ticket, conversation, articles, alsoOpen, contacts, attachments, activity, canReply } =
    $derived(data);

  /*
   * The composer owns its own text rather than reading it back from `data`, so
   * a revalidation cannot wipe a half-written reply. It is cleared only on a
   * send that actually succeeded; `update({ reset: false })` below leaves it
   * alone otherwise, which is what makes a rejected send recoverable.
   */
  let body = $state('');
  let internal = $state(false);
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

        {#if ticket.description}
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
                placeholder={internal ? 'Nota para el equipo…' : 'Escribir una respuesta…'}
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
      <div class="v2-label v2-rail-head">Historial</div>
      {#each activity.slice(0, 8) as a (a.id)}
        <div class="v2-rail-row">
          <div>
            <div style="font-size:12.5px;font-weight:550;line-height:1.35">{a.label}</div>
            <div class="v2-sub" style="font-size:11px">
              {a.by ?? 'Sistema'} · hace {shortAge(a.at)}
            </div>
          </div>
        </div>
      {/each}
    {/if}
  </aside>
</div>

<style>
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
