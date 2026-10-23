<script>
  /**
   * Editing an account.
   *
   * The account is the record everything else hangs off: the deals, the
   * people, the tickets, the invoices. That shapes this form twice over:
   *
   * ── THE NAME IS UNIQUE PER ORG, CASE-INSENSITIVELY ───────────────────────
   * `unique_account_name_per_org` is a database constraint on `Lower(name)`.
   * `AccountCreateSerializer.validate_name` catches it and returns a clean
   * 400, so the server's message is what appears below rather than a 500.
   *
   * ── WHAT THIS FORM DOES NOT OWN ──────────────────────────────────────────
   * Contacts, teams and tags are not on it. `AccountDetailView.put` clears all
   * three unconditionally, so saving through PUT would strip every person off
   * the account, which is why the action uses PATCH and why the summary below
   * states what is being left alone. The one relation the form does touch is
   * the owner, and even that is only sent when it changed.
   *
   * Also not here, because the server derives them: `org`, `created_by`,
   * `is_active`, and every figure in the rollups.
   */
  import { tick, untrack } from 'svelte';
  import { enhance } from '$app/forms';
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import { ChevronRight, TriangleAlert } from '@lucide/svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form: result } = $props();

  const { account, server } = untrack(() => ({ account: data.account, server: data.server }));

  let form = $state(untrack(() => ({ ...data.form })));
  let touched = $state(/** @type {Record<string, boolean>} */ ({}));
  let submitted = $state(false);
  let saved = $state(false);

  let errors = $derived.by(() => {
    /** @type {Record<string, string>} */
    const e = {};
    if (!form.name.trim()) e.name = 'Ponele a la cuenta el nombre por el que la buscarías.';

    if (form.annual_revenue !== '') {
      const n = Number(form.annual_revenue);
      if (!Number.isFinite(n)) e.annual_revenue = 'Los ingresos anuales tienen que ser un número.';
      // Mirrors the `account_revenue_non_negative` check constraint. Until
      // recently a negative value reached the database and came back as a 500
      // naming no field at all.
      else if (n < 0) e.annual_revenue = 'Los ingresos anuales no pueden ser negativos.';
    }

    if (form.number_of_employees !== '') {
      const n = Number(form.number_of_employees);
      if (!Number.isInteger(n)) e.number_of_employees = 'La cantidad de empleados es un número entero.';
      else if (n < 0) e.number_of_employees = 'La cantidad de empleados no puede ser negativa.';
    }

    if (form.email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(form.email))
      e.email = 'Eso no parece una dirección de correo.';

    // The exact regex from `flexible_phone_validator` in
    // `common/validators.py`, which Account, Contact and Lead all use.
    // Surfaced at the field, because otherwise a seeded number carrying an
    // "x123" extension rejects the entire save without naming a field: see
    // the same guard on the leads form.
    if (form.phone && !/^[\d\s\-()+.]{7,25}$/.test(form.phone))
      e.phone = 'De 7 a 25 caracteres: números, espacios, paréntesis, puntos, guiones. Sin extensiones.';

    return e;
  });

  let valid = $derived(Object.keys(errors).length === 0);
  const show = (/** @type {string} */ field) => (touched[field] || submitted) && errors[field];

  /**
   * These checks are a UX hint. The serializer is the rule, and its 400 is
   * what `result.error` reports.
   *
   * @type {import('./$types').SubmitFunction}
   */
  const check = async ({ cancel }) => {
    submitted = true;
    saved = false;
    if (!valid) {
      cancel();
      await tick();
      /** @type {HTMLElement | null} */
      const first = document.querySelector('[aria-invalid="true"]');
      first?.focus();
      return;
    }
    return async ({ update, result: outcome }) => {
      await update({ reset: false });
      saved = outcome.type === 'success';
    };
  };

  let untouchedRelations = $derived(
    [
      server.contact_count &&
        `${server.contact_count} contacto${server.contact_count === 1 ? '' : 's'}`,
      server.team_count && `${server.team_count} equipo${server.team_count === 1 ? '' : 's'}`,
      server.tag_count && `${server.tag_count} etiqueta${server.tag_count === 1 ? '' : 's'}`
    ].filter(Boolean)
  );
</script>

<PageHeader title="Editar {account.name}" center>
  {#snippet crumb()}
    <a href="/accounts">Cuentas</a>
    <ChevronRight size={12} />
    <a href="/accounts/{account.id}">{account.name}</a>
  {/snippet}
  {#snippet sub()}
    {[
      account.industry,
      server.deal_count ? `${server.deal_count} negociación${server.deal_count === 1 ? '' : 'es'}` : null,
      server.invoice_count
        ? `${server.invoice_count} factura${server.invoice_count === 1 ? '' : 's'}`
        : null
    ]
      .filter(Boolean)
      .join(' · ') || 'Todavía sin registros relacionados'}
  {/snippet}
</PageHeader>

<div class="v2-scroll v2-pad" style="padding-top:18px">
  <form class="v2-form" method="POST" action="?/save" use:enhance={check} novalidate>
    {#if saved}
      <div class="v2-next" style="margin-bottom:18px" role="status">
        <div class="v2-next-body">
          <div class="v2-next-text">Guardado.</div>
          <div class="v2-sub" style="margin-top:3px">"{account.name}" se actualizó.</div>
        </div>
        <a class="v2-btn" href="/accounts/{account.id}">Volver a la cuenta</a>
      </div>
    {/if}

    {#if result?.error}
      <div
        class="v2-next"
        style="background:color-mix(in srgb, var(--v2-rust) 9%, transparent);border-color:color-mix(in srgb, var(--v2-rust) 28%, transparent);margin-bottom:18px"
        role="alert"
      >
        <TriangleAlert size={17} style="color:var(--v2-rust);flex:none" />
        <div class="v2-next-body">
          <div style="font-weight:600">El servidor rechazó este cambio</div>
          <div class="v2-sub" style="margin-top:2px">{result.error}</div>
        </div>
      </div>
    {/if}

    {#if submitted && !valid}
      <div
        class="v2-next"
        style="background:color-mix(in srgb, var(--v2-rust) 9%, transparent);border-color:color-mix(in srgb, var(--v2-rust) 28%, transparent);margin-bottom:18px"
        role="alert"
      >
        <TriangleAlert size={17} style="color:var(--v2-rust);flex:none" />
        <div class="v2-next-body">
          <div style="font-weight:600">
            Todavía {Object.keys(errors).length === 1 ? 'falta' : 'faltan'} {Object.keys(errors).length}
            {Object.keys(errors).length === 1 ? 'campo' : 'campos'}
          </div>
          <div class="v2-sub" style="margin-top:2px">No se guardó nada.</div>
        </div>
      </div>
    {/if}

    <div class="v2-field">
      <label for="f-name">Nombre de la cuenta</label>
      <input
        id="f-name"
        name="name"
        class="v2-input"
        bind:value={form.name}
        onblur={() => (touched.name = true)}
        aria-invalid={show('name') ? 'true' : undefined}
      />
      {#if show('name')}
        <p class="v2-error">{errors.name}</p>
      {:else}
        <p class="v2-hint">Tiene que ser único en esta organización, sin distinguir mayúsculas.</p>
      {/if}
    </div>

    <div class="pair">
      <div class="v2-field">
        <label for="f-industry">Rubro</label>
        <select id="f-industry" name="industry" class="v2-input" bind:value={form.industry}>
          <option value="">No registrado</option>
          {#each data.industries as i (i.value)}
            <option value={i.value}>{i.label}</option>
          {/each}
        </select>
      </div>
      <div class="v2-field">
        <label for="f-owner">Responsable</label>
        <!-- What the select was rendered with. The action compares against it
             so an untouched owner is not sent at all; `assigned_to` is a
             many-to-many and this select is single, so sending it always would
             cut a two-person account down to one on every save. -->
        <input type="hidden" name="assigned_to_original" value={data.form.assigned_to} />
        <select id="f-owner" name="assigned_to" class="v2-input" bind:value={form.assigned_to}>
          <option value="">Nadie</option>
          {#each data.owners as o (o.id)}
            <option value={o.id}>{o.name}</option>
          {/each}
        </select>
        {#if server.owner_count > 1}
          <p class="v2-hint">
            <span class="v2-num">{server.owner_count}</span> personas tienen asignada esta cuenta. Esta
            lista muestra la primera; cambiarla las reemplaza a todas, y dejarla como está las conserva.
          </p>
        {/if}
      </div>
    </div>

    <div class="pair">
      <div class="v2-field">
        <label for="f-email">Correo</label>
        <input
          id="f-email"
          name="email"
          class="v2-input"
          type="email"
          bind:value={form.email}
          onblur={() => (touched.email = true)}
          aria-invalid={show('email') ? 'true' : undefined}
        />
        {#if show('email')}<p class="v2-error">{errors.email}</p>{/if}
      </div>
      <div class="v2-field">
        <label for="f-phone">Teléfono</label>
        <input
          id="f-phone"
          name="phone"
          class="v2-input"
          bind:value={form.phone}
          onblur={() => (touched.phone = true)}
          aria-invalid={show('phone') ? 'true' : undefined}
        />
        {#if show('phone')}<p class="v2-error">{errors.phone}</p>{/if}
      </div>
    </div>

    <div class="v2-field">
      <label for="f-website">Sitio web</label>
      <input id="f-website" name="website" class="v2-input" type="url" bind:value={form.website} />
    </div>

    <div class="pair">
      <div class="v2-field">
        <label for="f-staff">Cantidad de empleados</label>
        <input
          id="f-staff"
          name="number_of_employees"
          class="v2-input v2-num"
          type="text"
          inputmode="numeric"
          bind:value={form.number_of_employees}
          onblur={() => (touched.number_of_employees = true)}
          aria-invalid={show('number_of_employees') ? 'true' : undefined}
        />
        {#if show('number_of_employees')}<p class="v2-error">{errors.number_of_employees}</p>{/if}
      </div>
      <div class="v2-field">
        <label for="f-revenue">Ingresos anuales</label>
        <input
          id="f-revenue"
          name="annual_revenue"
          class="v2-input v2-num"
          type="text"
          inputmode="decimal"
          bind:value={form.annual_revenue}
          onblur={() => (touched.annual_revenue = true)}
          aria-invalid={show('annual_revenue') ? 'true' : undefined}
        />
        {#if show('annual_revenue')}
          <p class="v2-error">{errors.annual_revenue}</p>
        {:else}
          <p class="v2-hint">
            Cuánto factura esta empresa. No lo que le vendiste vos. Eso es Ingresos ganados, y se
            calcula a partir de las negociaciones.
          </p>
        {/if}
      </div>
    </div>

    <div class="v2-field">
      <label for="f-address">Dirección</label>
      <input id="f-address" name="address_line" class="v2-input" bind:value={form.address_line} />
    </div>

    <div class="triple">
      <div class="v2-field">
        <label for="f-city">Ciudad</label>
        <input id="f-city" name="city" class="v2-input" bind:value={form.city} />
      </div>
      <div class="v2-field">
        <label for="f-state">Provincia</label>
        <input id="f-state" name="state" class="v2-input" bind:value={form.state} />
      </div>
      <div class="v2-field">
        <label for="f-postcode">Código postal</label>
        <input id="f-postcode" name="postcode" class="v2-input" bind:value={form.postcode} />
      </div>
    </div>

    <div class="v2-field">
      <label for="f-country">País</label>
      <select id="f-country" name="country" class="v2-input" bind:value={form.country}>
        <option value="">No registrado</option>
        {#each data.countries as c (c.value)}
          <option value={c.value}>{c.label}</option>
        {/each}
      </select>
    </div>

    <div class="v2-field">
      <label for="f-notes">Notas</label>
      <textarea
        id="f-notes"
        name="description"
        class="v2-input"
        rows="4"
        bind:value={form.description}></textarea>
    </div>

    {#if untouchedRelations.length}
      <p class="v2-hint" style="margin-bottom:14px">
        Este formulario no toca {untouchedRelations.join(', ')} de esta cuenta. Se editan donde
        viven.
      </p>
    {/if}

    <div class="actions">
      <button class="v2-btn v2-btn-primary" type="submit">Guardar cambios</button>
      <a class="v2-btn" href="/accounts/{account.id}">Cancelar</a>
    </div>
  </form>
</div>

<style>
  .pair {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 14px;
  }
  .triple {
    display: grid;
    grid-template-columns: 2fr 1fr 1fr;
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
