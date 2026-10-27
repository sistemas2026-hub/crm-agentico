<script>
  /**
   * Raising a ticket.
   *
   * Deliberately short. A ticket that has just been raised has no history, no
   * closing date and nothing linked to it, so the only questions are what
   * happened, how bad it is, and who it is for.
   *
   * `?account=<id>` preselects the company, so "raise a ticket for this
   * account" arrives with the account already chosen.
   */
  import { tick, untrack } from 'svelte';
  import { enhance } from '$app/forms';
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import { ChevronRight, TriangleAlert } from '@lucide/svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form: result } = $props();

  // `untrack` so a re-render after a failed save does not throw away what the
  // person typed; `result.values` is the server's echo of the same fields.
  let form = $state(
    untrack(() => ({
      name: '',
      status: data.defaults.status,
      priority: data.defaults.priority,
      case_type: data.defaults.case_type,
      description: '',
      account: data.defaults.account ?? '',
      assigned_to: '',
      ...(result?.values ?? {})
    }))
  );
  /*
   * TAMBIEN EN WISPHUB (26/10/2026). Solo aparece si la empresa tiene asuntos
   * habilitados. El numero de servicio se confirma con "Verificar" -- muestra
   * el titular -- antes de abrir un ticket que le va a caer a un tecnico.
   */
  /*
   * 27/10/2026: la casilla viene MARCADA -- lo normal es que un ticket del
   * ISP viva tambien en WispHub. Y el asunto se elige SIEMPRE de la lista de
   * WispHub, con la casilla o sin ella: decision del usuario, para que Dexter
   * no tenga asuntos distintos a los del ISP. Texto libre solo si la empresa
   * no tiene asuntos habilitados (o el motor no los mando).
   */
  let enWispHub = $state(
    untrack(() => (result?.values ? result.values.en_wisphub === true : true))
  );
  let servicio = $state(untrack(() => result?.values?.servicio ?? ''));
  let usaWispHub = $derived((data.asuntosWispHub?.length ?? 0) > 0);
  /** @type {any} */
  let titular = $state(null);
  let verificando = $state(false);
  const AREAS = /** @type {Record<string, string>} */ ({
    soporte_tecnico: 'Soporte técnico',
    cartera: 'Cartera'
  });
  let asuntosPorArea = $derived.by(() => {
    /** @type {Record<string, string[]>} */
    const g = {};
    for (const a of data.asuntosWispHub ?? []) (g[a.area || ''] ??= []).push(a.asunto);
    return Object.entries(g);
  });
  async function verificar() {
    verificando = true;
    try {
      const r = await fetch(`/tickets/new/titular?servicio=${encodeURIComponent(servicio.trim())}`);
      titular = await r.json();
    } catch {
      titular = { ok: false, motivo: 'No se pudo consultar ahora. Probá de nuevo.' };
    } finally {
      verificando = false;
    }
  }

  let touched = $state(/** @type {Record<string, boolean>} */ ({}));
  let submitted = $state(false);

  let errors = $derived.by(() => {
    /** @type {Record<string, string>} */
    const e = {};
    const name = form.name.trim();
    if (!name) e.name = usaWispHub ? 'Elegí el asunto de la lista.' : 'Un ticket necesita un asunto.';
    // `Case.name` is max_length=64, short for a subject line, but it is the
    // column, and a 65th character is a 400 from the serializer.
    else if (name.length > 64)
      e.name = `El asunto tiene un máximo de 64 caracteres (esto tiene ${name.length}).`;
    return e;
  });

  let valid = $derived(Object.keys(errors).length === 0);
  const show = (/** @type {string} */ field) => (touched[field] || submitted) && errors[field];

  /** @type {import('./$types').SubmitFunction} */
  const check = async ({ cancel }) => {
    submitted = true;
    if (!valid) {
      cancel();
      await tick();
      /** @type {HTMLElement | null} */
      const first = document.querySelector('[aria-invalid="true"]');
      first?.focus();
    }
  };
</script>

<PageHeader title="Nuevo ticket" center>
  {#snippet crumb()}
    <a href="/tickets">Tickets</a>
    <ChevronRight size={12} />
    <span>Nuevo</span>
  {/snippet}
  {#snippet sub()}
    Qué pasó, qué tan urgente es, y para quién es.
  {/snippet}
</PageHeader>

<div class="v2-scroll v2-pad" style="padding-top:18px">
  <form class="v2-form" method="POST" action="?/create" use:enhance={check} novalidate>
    {#if result?.error}
      <div
        class="v2-next"
        style="background:color-mix(in srgb, var(--v2-rust) 9%, transparent);border-color:color-mix(in srgb, var(--v2-rust) 28%, transparent);margin-bottom:18px"
        role="alert"
      >
        <TriangleAlert size={17} style="color:var(--v2-rust);flex:none" />
        <div class="v2-next-body">
          <div style="font-weight:600">El servidor rechazó este ticket</div>
          <div class="v2-sub" style="margin-top:2px">{result.error}</div>
        </div>
      </div>
    {/if}

    {#if data.asuntosWispHub?.length}
      <fieldset class="wisphub">
        <label class="marca">
          <input
            type="checkbox"
            name="en_wisphub"
            value="1"
            bind:checked={enWispHub} />
          Crear también en WispHub
        </label>
        {#if enWispHub}
          <div class="v2-field">
            <label for="f-servicio">Número de servicio del cliente</label>
            <div class="servicio">
              <input
                id="f-servicio"
                name="servicio"
                class="v2-input"
                inputmode="numeric"
                autocomplete="off"
                bind:value={servicio}
                oninput={() => (titular = null)} />
              <button
                type="button"
                class="v2-btn v2-btn-sm"
                onclick={verificar}
                disabled={verificando || !servicio.trim()}>Verificar</button>
            </div>
            {#if titular?.ok}
              <p class="v2-hint">Titular: <b>{titular.nombre}</b>{titular.estado ? ` · ${titular.estado}` : ''}</p>
            {:else if titular}
              <p class="v2-hint aviso">{titular.motivo}</p>
            {/if}
          </div>
          <p class="v2-hint">
            Se abre en WispHub a nombre del responsable del área, con lo que escribas en «Qué
            pasó», y queda atado a este ticket: lo que respondan allá aparece acá.
          </p>
        {/if}
      </fieldset>
    {/if}

    <div class="v2-field">
      <label for="f-name">Asunto</label>
      {#if usaWispHub}
        <select
          id="f-name"
          name="name"
          class="v2-input"
          bind:value={form.name}
          onblur={() => (touched.name = true)}
          aria-invalid={show('name') ? 'true' : undefined}>
          <option value="">Elegí uno</option>
          {#each asuntosPorArea as [area, lista] (area)}
            <optgroup label={AREAS[area] ?? (area || 'Otros')}>
              {#each lista as a (a)}
                <option value={a}>{a}</option>
              {/each}
            </optgroup>
          {/each}
        </select>
      {:else}
        <input
          id="f-name"
          name="name"
          class="v2-input"
          bind:value={form.name}
          onblur={() => (touched.name = true)}
          aria-invalid={show('name') ? 'true' : undefined}
        />
      {/if}
      {#if show('name')}
        <p class="v2-error">{errors.name}</p>
      {:else if usaWispHub}
        <p class="v2-hint">Los mismos asuntos de WispHub, aunque el ticket quede solo en Dexter.</p>
      {/if}
    </div>

    <div class="triple">
      <div class="v2-field">
        <label for="f-priority">Prioridad</label>
        <select id="f-priority" name="priority" class="v2-input" bind:value={form.priority}>
          {#each data.priorities as p (p.value)}
            <option value={p.value}>{p.label}</option>
          {/each}
        </select>
        <p class="v2-hint">Define el objetivo de primera respuesta.</p>
      </div>
      <div class="v2-field">
        <label for="f-type">Tipo</label>
        <select id="f-type" name="case_type" class="v2-input" bind:value={form.case_type}>
          <option value="">Sin definir</option>
          {#each data.caseTypes as t (t.value)}
            <option value={t.value}>{t.label}</option>
          {/each}
        </select>
      </div>
      <div class="v2-field">
        <label for="f-status">Estado</label>
        <select id="f-status" name="status" class="v2-input" bind:value={form.status}>
          {#each data.statuses as s (s.value)}
            <option value={s.value}>{s.label}</option>
          {/each}
        </select>
      </div>
    </div>

    <div class="pair">
      <div class="v2-field">
        <label for="f-account">Cuenta</label>
        <select id="f-account" name="account" class="v2-input" bind:value={form.account}>
          <option value="">Sin vincular</option>
          {#each data.accounts as a (a.id)}
            <option value={a.id}>{a.name}</option>
          {/each}
        </select>
        <p class="v2-hint">No se puede cambiar después. La API lo deja de solo lectura tras la creación.</p>
      </div>
      <div class="v2-field">
        <label for="f-owner">Asignado a</label>
        <select id="f-owner" name="assigned_to" class="v2-input" bind:value={form.assigned_to}>
          <option value="">Nadie</option>
          {#each data.owners as o (o.id)}
            <option value={o.id}>{o.name}</option>
          {/each}
        </select>
        <p class="v2-hint">Los tickets sin asignar igual cuentan contra el reloj.</p>
      </div>
    </div>

    <div class="v2-field">
      <label for="f-contacts">Personas afectadas</label>
      <select id="f-contacts" name="contacts" class="v2-input" multiple size="4">
        {#each data.contacts as c (c.id)}
          <option value={c.id}>{c.name}</option>
        {/each}
      </select>
      <p class="v2-hint">Opcional. Mantené presionado ctrl o cmd para elegir más de uno.</p>
    </div>

    <div class="v2-field">
      <label for="f-desc">Qué pasó</label>
      <textarea
        id="f-desc"
        name="description"
        class="v2-input"
        rows="4"
        bind:value={form.description}></textarea>
    </div>

    <div class="actions">
      <button class="v2-btn v2-btn-primary" type="submit">Crear ticket</button>
      <a class="v2-btn" href="/tickets">Cancelar</a>
    </div>
  </form>
</div>

<style>
  .wisphub {
    margin: 0 0 18px;
    padding: 14px 16px;
    border: 1px solid var(--v2-line);
    border-radius: var(--v2-radius-control);
    background: var(--v2-paper);
    display: grid;
    gap: 12px;
  }
  .marca {
    display: flex;
    align-items: center;
    gap: 8px;
    font-weight: 600;
    font-size: 14px;
  }
  .servicio {
    display: flex;
    gap: 8px;
    max-width: 380px;
  }
  .servicio .v2-input {
    flex: 1;
    min-width: 0;
  }
  .aviso {
    color: var(--v2-clay);
  }
  .pair {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 14px;
  }
  .triple {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 14px;
  }
  .actions {
    display: flex;
    align-items: center;
    gap: 9px;
    margin-top: 22px;
    padding-bottom: 40px;
  }
  @media (max-width: 720px) {
    .pair,
    .triple {
      grid-template-columns: 1fr;
    }
  }
</style>
