<script>
  /**
   * A lead: a person you are trying to reach and, if it goes well, convert.
   *
   * The page is built around that verb. The header carries the ways to reach
   * them (email, call) beside Edit; a single honest headline says what is in
   * the way of the work when something is; the activity log can be *written to*,
   * because the daily act on a lead is recording that you contacted them.
   *
   * WHAT IS NOT FAKED
   * Conversion is not a dedicated endpoint. It is a PATCH of `status` on the
   * ordinary lead detail URL (see `convertLead`), which runs
   * `convert_lead_to_account` server-side: it creates an Account, a Contact
   * when the lead has an email, and usually an Opportunity. It is a one-way
   * door, the API refuses a repeat conversion. The headline is derived only
   * from fields the model actually has; where the data cannot support a
   * sentence, there is no banner. The duplicate warning is a real query (see
   * `findDuplicates`) and renders only when there is a match.
   */
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import NextAction from '$lib/v2/components/NextAction.svelte';
  import Avatar from '$lib/v2/components/Avatar.svelte';
  import Pill from '$lib/v2/components/Pill.svelte';
  import { money, relativeDays, daysSince, shortDate } from '$lib/v2/format.js';
  import { LEAD_STATUS_TONE, LEAD_STATUS_LABEL, industryLabel } from '$lib/v2/enums.js';
  import { t } from '$lib/terminology.js';
  import { enhance } from '$app/forms';
  import {
    ChevronRight,
    Mail,
    Phone,
    Pencil,
    Paperclip,
    MessageSquare,
    Sparkles,
    X
  } from '@lucide/svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  let { lead, activity, duplicates, customFields } = $derived(data);
  let isConverted = $derived(lead.status === 'converted');
  let firstName = $derived(lead.first_name || 'este prospecto');
  let fullName = $derived(`${lead.first_name ?? ''} ${lead.last_name ?? ''}`.trim() || 'Prospecto');

  let note = $state('');
  let saving = $state(false);

  // The picked file's name, mirrored out of the input so the composer can show
  // and clear it. `fileInput` is the element itself. A file input's value can
  // only be cleared through the DOM, not by rebinding.
  let fileName = $state('');
  /** @type {HTMLInputElement | undefined} */
  let fileInput;

  /** @param {Event} e */
  function pickFile(e) {
    fileName = /** @type {HTMLInputElement} */ (e.currentTarget).files?.[0]?.name ?? '';
  }
  function clearFile() {
    if (fileInput) fileInput.value = '';
    fileName = '';
  }

  // ── activity feed ──────────────────────────────────────────────────────────
  // Three real kinds (note / file / created). The filter only appears once there
  // is a file to filter. With nothing but notes it would be a control that
  // sorts one pile.
  let hasFiles = $derived(activity.some((/** @type {any} */ e) => e.type === 'file'));
  let filter = $state(/** @type {'all'|'notes'|'files'} */ ('all'));
  let shown = $derived(
    filter === 'files'
      ? activity.filter((/** @type {any} */ e) => e.type === 'file')
      : filter === 'notes'
        ? activity.filter((/** @type {any} */ e) => e.type !== 'file')
        : activity
  );
  let newestId = $derived(shown[0]?.id ?? null);

  /**
   * The line under an event: "Attached" for a file, the author where known, then
   * how long ago, joined so no separator dangles when a part is missing.
   * @param {{type:string,by:string|null,at:string}} e
   */
  function metaFor(e) {
    const parts = [];
    if (e.type === 'file') parts.push('Adjuntado');
    if (e.by) parts.push(e.by);
    parts.push(relativeDays(e.at));
    return parts.join(' · ');
  }

  /** @param {string} iso */
  function dayGroup(iso) {
    const n = daysSince(iso);
    if (n === 0) return 'Hoy';
    if (n === 1) return 'Ayer';
    return shortDate(iso);
  }

  // Interleave day headers so each date is announced once, in order.
  let feed = $derived.by(() => {
    /** @type {Array<{kind:'day',id:string,label:string}|{kind:'event',id:string,event:any}>} */
    const out = [];
    let last = null;
    for (const e of shown) {
      const g = dayGroup(e.at);
      if (g !== last) {
        out.push({ kind: 'day', id: `day-${g}-${e.id}`, label: g });
        last = g;
      }
      out.push({ kind: 'event', id: e.id, event: e });
    }
    return out;
  });

  /**
   * One line, and only where the data can carry it and the lead is still open.
   * Ordered by what stops the work: a lead nobody can reach, then one nobody
   * owns, then one that has gone cold without a first conversation. A converted
   * lead has none of these problems, so it gets no banner. A page that always
   * shouts is a page people stop reading.
   *
   * @type {{ tone: 'ember'|'rust', label: string, text: string, action: string|null } | null}
   */
  let headline = $derived.by(() => {
    if (isConverted) return null;
    if (!lead.email && !lead.phone) {
      return {
        tone: 'rust',
        label: 'No se puede contactar',
        text: `No hay correo ni teléfono en este prospecto, así que no hay forma de contactar a ${firstName}. Agregá uno antes de poder trabajarlo.`,
        action: 'Agregar datos de contacto'
      };
    }
    if (!lead.assigned_to) {
      return {
        tone: 'ember',
        label: 'Necesita un responsable',
        text: lead.opportunity_amount
          ? `Vale ${money(lead.opportunity_amount, lead.currency)} y nadie lo tiene asignado. Asigná un responsable antes de que se enfríe.`
          : 'Nadie tiene asignado este prospecto. Asigná un responsable para que no quede sin trabajar.',
        action: 'Asignar responsable'
      };
    }
    if (!lead.last_contacted && (daysSince(lead.created_at) ?? 0) > 7) {
      return {
        tone: 'ember',
        label: 'Nunca contactado',
        text: `Creado ${relativeDays(lead.created_at)} y todavía nunca contactado. Contactalo, o reciclalo.`,
        action: null
      };
    }
    return null;
  });

  /**
   * A website is user-entered and often has no scheme. Prepend https when it is
   * missing; refuse to linkify anything carrying another scheme (a `javascript:`
   * value becomes plain text, never an href).
   *
   * @param {string} url
   * @returns {string|null}
   */
  function webHref(url) {
    const u = String(url).trim();
    if (/^https?:\/\//i.test(u)) return u;
    if (/^[a-z][a-z0-9+.-]*:/i.test(u)) return null;
    return `https://${u}`;
  }
</script>

<PageHeader title="{lead.first_name} {lead.last_name}" record>
  {#snippet leading()}
    <Avatar name={fullName} size={42} />
  {/snippet}
  {#snippet crumb()}
    <a href="/leads">{t(data.org?.terminology, 'lead.plural', 'Prospectos')}</a>
    <ChevronRight size={12} />
    <span>{lead.company_name || 'Sin empresa'}</span>
  {/snippet}
  {#snippet sub()}
    {lead.job_title || 'Sin cargo registrado'} ·
    {lead.last_contacted
      ? `último contacto ${relativeDays(lead.last_contacted)}`
      : 'nunca contactado'}
  {/snippet}
  {#snippet actions()}
    {#if lead.email}
      <a class="v2-btn" href="mailto:{lead.email}"><Mail />Correo</a>
    {/if}
    {#if lead.phone}
      <a class="v2-btn" href="tel:{lead.phone}"><Phone />Llamar</a>
    {/if}
    <a class="v2-btn" href="/leads/{lead.id}/edit"><Pencil />Editar</a>
  {/snippet}
</PageHeader>

<div style="display:flex;flex:1;min-height:0;overflow:hidden">
  <div class="v2-main">
    <div class="v2-scroll">
      <div class="v2-pad" style="padding-top:16px;padding-bottom:32px">
        {#if headline}
          <div style="margin-bottom:18px">
            <NextAction
              label={headline.label}
              text={headline.text}
              action={headline.action}
              href={headline.action ? `/leads/${lead.id}/edit` : null}
              tone={headline.tone}
            />
          </div>
        {/if}

        <!-- Only when the query found one. A warning that is always on is the
             fastest way to teach somebody to ignore the panel that will one day
             matter. -->
        {#if duplicates.length > 0}
          <div class="dup" role="note">
            <div class="v2-label" style="color:var(--v2-clay);margin-bottom:4px">
              Posible duplicado
            </div>
            <div style="font-size:12.5px;line-height:1.55">
              {#each duplicates as d, i (d.id)}
                {i > 0 ? ', ' : ''}<a href="/leads/{d.id}">{d.name}</a> comparte {d.matched_on}
              {/each}. Fusionalos, o vinculá ambos a una cuenta al convertir.
            </div>
          </div>
        {/if}

        <div class="v2-card" style="padding:15px 16px">
          {#if isConverted}
            <div class="v2-label" style="margin-bottom:8px">Ya convertido</div>
            <p class="v2-sub" style="margin:0;font-size:12.5px;line-height:1.55">
              La cuenta, el contacto y la negociación en que se convirtió este prospecto llevan el
              trabajo ahora. Convertir de nuevo crearía una segunda negociación contra la misma
              cuenta, y la API lo rechaza.
            </p>
          {:else}
            <div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap">
              <div style="flex:1;min-width:210px">
                <div class="v2-label" style="margin-bottom:6px">Convertir</div>
                <p class="v2-sub" style="margin:0;font-size:12.5px;line-height:1.55">
                  Crea una <b style="color:var(--v2-ink)">cuenta</b>, un
                  <b style="color:var(--v2-ink)">contacto</b> y una
                  <b style="color:var(--v2-ink)">negociación</b>{lead.opportunity_amount
                    ? ` por ${money(lead.opportunity_amount, lead.currency)}`
                    : ''}. El prospecto queda vinculado, y no hay forma de deshacerlo.
                </p>
              </div>
              <form method="POST" action="?/convert" use:enhance>
                <!-- `disabled={!lead.email}` is a UX hint that mirrors the
                     server-side guard the backend enforces on this same PATCH.
                     It is not the enforcement: a request that skips this button
                     entirely still meets the same rule server-side. The reason
                     is also rendered as visible text below, not only in
                     `title`: a disabled control is out of the tab order and
                     its title is not announced by assistive tech. -->
                <button
                  class="v2-btn"
                  type="submit"
                  disabled={!lead.email}
                  title={lead.email
                    ? 'Crea una cuenta, un contacto y una negociación a partir de este prospecto'
                    : 'Agregá primero una dirección de correo a este prospecto. El contacto se crea a partir de ella.'}
                >
                  Convertir prospecto
                </button>
                {#if !lead.email}
                  <p class="v2-sub" style="margin:4px 0 0;font-size:11.5px">
                    Agregá primero una dirección de correo. El contacto se crea a partir de ella.
                  </p>
                {/if}
              </form>
            </div>
          {/if}
        </div>

        {#if form?.converted}
          <div class="v2-card" role="status" style="margin-top:12px;padding:15px 16px">
            <div class="v2-label" style="margin-bottom:6px">Convertido</div>
            <p class="v2-sub" style="margin:0 0 8px;font-size:12.5px;line-height:1.55">
              La cuenta, el contacto y la negociación están listos.
            </p>
            <div style="display:flex;gap:8px;flex-wrap:wrap">
              <a class="v2-btn" href="/accounts/{form.account_id}">Ver cuenta</a>
              {#if form.contact_id}
                <a class="v2-btn" href="/contacts/{form.contact_id}">Ver contacto</a>
              {/if}
              {#if form.opportunity_id}
                <a class="v2-btn" href="/pipeline/{form.opportunity_id}">Ver negociación</a>
              {/if}
            </div>
          </div>
        {:else if form?.error}
          <p class="note-err" style="margin-top:10px">{form.error}</p>
        {/if}

        {#if lead.description}
          <div class="v2-label" style="margin:22px 0 10px">Acerca de</div>
          <div class="v2-card about">{lead.description}</div>
        {/if}

        <!-- Per-org custom fields. Every active definition shows, filled or
             not: on a real-estate org these ARE the record, and an unfilled
             "Possession by" is worth seeing rather than silently omitted. -->
        {#if customFields.length > 0}
          <div class="v2-label" style="margin:22px 0 10px">Detalles</div>
          <div class="v2-card cf">
            {#each customFields as f (f.key)}
              <div class="cf-row">
                <span class="cf-label">{f.label}</span>
                <span class="cf-value" class:v2-muted={!f.filled}>
                  {f.filled ? f.value : '—'}
                </span>
              </div>
            {/each}
          </div>
        {/if}

        <div class="act-head">
          <div class="v2-label">Actividad</div>
          {#if hasFiles}
            <!-- Only real kinds. There is no calls/emails/meetings split because
                 there are no such records to split on. -->
            <div class="seg" role="tablist" aria-label="Filtrar actividad">
              <button class:on={filter === 'all'} onclick={() => (filter = 'all')}>Todo</button>
              <button class:on={filter === 'notes'} onclick={() => (filter = 'notes')}>Notas</button
              >
              <button class:on={filter === 'files'} onclick={() => (filter = 'files')}>Archivos</button
              >
            </div>
          {/if}
        </div>

        <!-- The composer. `reset: false` plus clearing state by hand on success
             keeps the box and the binding in step; a failed save keeps the words
             and the picked file. A file only sends with a note. The button
             stays disabled until there is one, which matches what the API stores. -->
        <form
          method="POST"
          action="?/note"
          enctype="multipart/form-data"
          class="note-form"
          use:enhance={() => {
            saving = true;
            return async ({ result, update }) => {
              saving = false;
              if (result.type === 'success') {
                note = '';
                clearFile();
              }
              await update({ reset: false });
            };
          }}
        >
          <textarea
            name="comment"
            rows="2"
            bind:value={note}
            class="note-input"
            placeholder="Registrá una llamada, una respuesta, lo que dijeron…"></textarea>
          <div class="note-actions">
            <button class="v2-btn v2-btn-primary" type="submit" disabled={saving || !note.trim()}>
              {saving ? 'Guardando…' : 'Agregar nota'}
            </button>
            <label class="v2-btn" class:has-file={fileName}>
              <Paperclip size={14} />
              <span class="attach-label">{fileName || 'Adjuntar archivo'}</span>
              <input
                bind:this={fileInput}
                type="file"
                name="attachment"
                onchange={pickFile}
                hidden
              />
            </label>
            {#if fileName}
              <button
                type="button"
                class="v2-btn-quiet clear-file"
                onclick={clearFile}
                title="Quitar archivo"
              >
                <X size={13} />
              </button>
            {/if}
            {#if form?.message}
              <span class="note-err">{form.message}</span>
            {/if}
          </div>
        </form>

        <div class="tl">
          {#each feed as row (row.id)}
            {#if row.kind === 'day'}
              <div class="tl-day">{row.label}</div>
            {:else}
              {@const e = row.event}
              <div class="tl-row" class:latest={e.id === newestId}>
                <span class="tl-ico" data-kind={e.type}>
                  {#if e.type === 'file'}<Paperclip size={13} />
                  {:else if e.type === 'status'}<Sparkles size={13} />
                  {:else}<MessageSquare size={13} />{/if}
                </span>
                <div class="tl-body">
                  {#if e.type === 'file' && e.href}
                    <a class="tl-file" href={e.href} target="_blank" rel="noreferrer noopener">
                      {e.body}
                    </a>
                  {:else}
                    <div class="tl-text" class:note={e.type === 'note'}>{e.body}</div>
                  {/if}
                  <div class="tl-meta">{metaFor(e)}</div>
                </div>
              </div>
            {/if}
          {/each}
        </div>
      </div>
    </div>
  </div>

  <aside class="v2-rail">
    <!-- An em dash where a field is empty. A blank list reads as a page that
         failed to load; "—" reads as a fact nobody has filled in. -->
    <div class="v2-label v2-rail-head">Contacto</div>
    <dl class="v2-kv">
      <dt>Correo</dt>
      <dd style="font-size:12px">
        {#if lead.email}<a href="mailto:{lead.email}" style="color:inherit">{lead.email}</a
          >{:else}, {/if}
      </dd>
      <dt>Teléfono</dt>
      <dd class="v2-num" style="font-size:12px">
        {#if lead.phone}<a href="tel:{lead.phone}" style="color:inherit">{lead.phone}</a
          >{:else}, {/if}
      </dd>
      <dt>Sitio web</dt>
      <dd style="font-size:12px">
        {#if lead.website && webHref(lead.website)}<a
            href={webHref(lead.website)}
            target="_blank"
            rel="noreferrer noopener"
            style="color:inherit">{lead.website}</a
          >{:else}{lead.website || '—'}{/if}
      </dd>
    </dl>

    <div class="v2-label v2-rail-head">Prospecto</div>
    <dl class="v2-kv">
      <dt>Estado</dt>
      <dd><Pill tone={LEAD_STATUS_TONE[lead.status]}>{LEAD_STATUS_LABEL[lead.status]}</Pill></dd>
      <dt>Responsable</dt>
      <dd>{lead.assigned_to || 'Nadie'}</dd>
      <dt>Origen</dt>
      <dd>{lead.source || '—'}</dd>
      <dt>Rubro</dt>
      <dd>{industryLabel(lead.industry) || '—'}</dd>
      <dt>Valor est.</dt>
      <dd class="v2-num">{lead.opportunity_amount ? money(lead.opportunity_amount, lead.currency) : '—'}</dd>
    </dl>

    <div class="v2-label v2-rail-head">Cronología</div>
    <dl class="v2-kv">
      <dt>Último contacto</dt>
      <dd>{lead.last_contacted ? relativeDays(lead.last_contacted) : 'Nunca'}</dd>
      <dt>Creado</dt>
      <dd>{relativeDays(lead.created_at)}</dd>
    </dl>
  </aside>
</div>

<style>
  /* A caution, not an alarm: a clay edge on an otherwise ordinary card. */
  .dup {
    border: 1px solid var(--v2-line);
    border-left: 3px solid var(--v2-clay);
    border-radius: var(--v2-radius);
    background: var(--v2-card);
    padding: 11px 14px;
    margin-bottom: 18px;
  }
  .dup a {
    color: var(--v2-clay);
    font-weight: 600;
  }
  .about {
    padding: 14px 16px;
    font-size: 13px;
    line-height: 1.6;
    white-space: pre-wrap;
  }
  .cf {
    padding: 4px 16px;
    font-size: 13px;
  }
  .cf-row {
    display: flex;
    gap: 16px;
    align-items: baseline;
    padding: 9px 0;
    border-bottom: 1px solid var(--v2-line);
  }
  .cf-row:last-child {
    border-bottom: 0;
  }
  .cf-label {
    flex: 0 0 40%;
    color: var(--v2-ink-soft);
  }
  .cf-value {
    flex: 1 1 auto;
    min-width: 0;
    overflow-wrap: anywhere;
  }
  /* Stack on narrow screens, matching the list's data-m card treatment. */
  @media (max-width: 767px) {
    .cf-row {
      display: block;
    }
    .cf-label {
      display: block;
      margin-bottom: 2px;
    }
  }
  .note-form {
    margin-bottom: 22px;
  }
  .note-input {
    width: 100%;
    padding: 9px 11px;
    font: inherit;
    font-size: 13px;
    color: var(--v2-ink);
    background: var(--v2-card);
    border: 1px solid var(--v2-line);
    border-radius: 8px;
    resize: vertical;
    line-height: 1.5;
  }
  .note-input:focus {
    outline: 2px solid var(--v2-ember);
    outline-offset: -1px;
  }
  .note-actions {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 8px;
    flex-wrap: wrap;
  }
  /* The attach control is a label wrapping a hidden input, so the whole chip is
     the click target. */
  .note-actions label {
    cursor: pointer;
  }
  .note-actions .attach-label {
    max-width: 190px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .note-actions .has-file {
    border-color: var(--v2-slate);
    color: var(--v2-ink);
  }
  .clear-file {
    padding: 5px 7px;
  }
  .note-err {
    color: var(--v2-rust);
    font-size: 12px;
  }

  /* ── activity ─────────────────────────────────────────────────────────── */
  .act-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin: 22px 0 12px;
  }
  .seg {
    display: flex;
    border: 1px solid var(--v2-line);
    border-radius: 7px;
    overflow: hidden;
    flex: none;
  }
  .seg button {
    padding: 4px 11px;
    font: inherit;
    font-size: 11.8px;
    color: var(--v2-slate);
    background: var(--v2-card);
    border: 0;
    cursor: pointer;
  }
  .seg button + button {
    border-left: 1px solid var(--v2-line);
  }
  .seg button.on {
    color: var(--v2-ink);
    background: var(--v2-hover);
    font-weight: 600;
  }

  .tl-day {
    font-size: 11px;
    font-weight: 650;
    letter-spacing: 0.02em;
    color: var(--v2-slate);
    margin: 14px 0 9px;
  }
  .tl-day:first-child {
    margin-top: 0;
  }
  .tl-row {
    display: flex;
    gap: 11px;
    align-items: flex-start;
    padding-bottom: 15px;
  }
  /* A small icon chip instead of a bare dot: the kind of event is legible at a
     glance, which is the whole point of a mixed feed. */
  .tl-ico {
    flex: none;
    width: 26px;
    height: 26px;
    border-radius: 50%;
    display: grid;
    place-items: center;
    background: var(--v2-line-soft);
    border: 1px solid var(--v2-line);
    color: var(--v2-slate);
    margin-top: 1px;
  }
  .tl-row.latest .tl-ico {
    background: var(--v2-ink);
    border-color: var(--v2-ink);
    color: var(--v2-paper);
  }
  .tl-body {
    min-width: 0;
    padding-top: 3px;
  }
  .tl-text {
    font-size: 13px;
    line-height: 1.5;
    color: var(--v2-ink);
  }
  .tl-file {
    display: inline-flex;
    font-size: 13px;
    font-weight: 550;
    color: var(--v2-ink);
    text-decoration: none;
    overflow-wrap: anywhere;
  }
  .tl-file:hover {
    text-decoration: underline;
  }
  .tl-meta {
    font-size: 11.5px;
    color: var(--v2-slate);
    margin-top: 2px;
    overflow-wrap: anywhere;
  }
</style>
