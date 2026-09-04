<script>
  /**
   * Editing a contact.
   *
   * ── EMAIL IS UNIQUE PER ORG, CASE-INSENSITIVELY ──────────────────────────
   * `unique_contact_email_per_org` is a database constraint on `Lower(email)`.
   * `CreateContactSerializer.validate_email` catches it first and returns a
   * clean 400, so what appears below is the server's own sentence rather than
   * a 500.
   *
   * ── WHAT THIS FORM DOES NOT OWN ─────────────────────────────────────────
   * Teams, tags and co-assignees are not on it. `ContactDetailView.put` clears
   * all three unconditionally, which is why the action uses PATCH and why the
   * summary at the bottom states what is being left alone. The one relation
   * this form touches is the owner, and even that is only sent when it changed.
   *
   * Membership of other accounts is not editable here either: this form sets
   * the *primary* account, and the server adds that account's people list to
   * match. Removing somebody from an account is done from the account.
   */
  import { tick, untrack } from 'svelte';
  import { enhance } from '$app/forms';
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import { ChevronRight, TriangleAlert } from '@lucide/svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form: result } = $props();

  const { contact, server } = untrack(() => ({ contact: data.contact, server: data.server }));

  let form = $state(untrack(() => ({ ...data.form })));
  let touched = $state(/** @type {Record<string, boolean>} */ ({}));
  let submitted = $state(false);
  let saved = $state(false);

  let errors = $derived.by(() => {
    /** @type {Record<string, string>} */
    const e = {};
    if (!form.first_name.trim()) e.first_name = 'Una persona necesita un nombre.';
    if (!form.last_name.trim()) e.last_name = 'Una persona necesita un apellido.';

    if (form.email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(form.email))
      e.email = 'Eso no parece una dirección de correo.';

    // The exact regex from `flexible_phone_validator` in
    // `common/validators.py`, which Contact, Account and Lead all use.
    // Surfaced at the field, because otherwise a seeded number carrying an
    // "x123" extension rejects the entire save without naming a field, and
    // seven of the fifteen seeded contacts carry exactly that.
    if (form.phone && !/^[\d\s\-()+.]{7,25}$/.test(form.phone))
      e.phone = 'De 7 a 25 caracteres: números, espacios, paréntesis, puntos, guiones. Sin extensiones.';

    if (form.linkedin_url && !/^https?:\/\/\S+$/.test(form.linkedin_url))
      e.linkedin_url = 'Una URL de LinkedIn empieza con http:// o https://.';

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
      server.owner_count > 1 && `${server.owner_count} responsables`,
      server.team_count && `${server.team_count} equipo${server.team_count === 1 ? '' : 's'}`,
      server.tag_count && `${server.tag_count} etiqueta${server.tag_count === 1 ? '' : 's'}`,
      server.linked_account_count &&
        `${server.linked_account_count} otro${server.linked_account_count === 1 ? '' : 's'} vínculo${server.linked_account_count === 1 ? '' : 's'} de cuenta`
    ].filter(Boolean)
  );
</script>

<PageHeader title="Editar {contact.name}" center>
  {#snippet crumb()}
    <a href="/contacts">Contactos</a>
    <ChevronRight size={12} />
    <a href="/contacts/{contact.id}">{contact.name}</a>
  {/snippet}
  {#snippet sub()}
    {[
      contact.title,
      server.deal_count ? `${server.deal_count} negociación${server.deal_count === 1 ? '' : 'es'}` : null,
      server.ticket_count
        ? `${server.ticket_count} ticket${server.ticket_count === 1 ? '' : 's'}`
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
          <div class="v2-sub" style="margin-top:3px">"{contact.name}" se actualizó.</div>
        </div>
        <a class="v2-btn" href="/contacts/{contact.id}">Volver al contacto</a>
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

    <div class="pair">
      <div class="v2-field">
        <label for="f-first">Nombre</label>
        <input
          id="f-first"
          name="first_name"
          class="v2-input"
          bind:value={form.first_name}
          onblur={() => (touched.first_name = true)}
          aria-invalid={show('first_name') ? 'true' : undefined}
        />
        {#if show('first_name')}<p class="v2-error">{errors.first_name}</p>{/if}
      </div>
      <div class="v2-field">
        <label for="f-last">Apellido</label>
        <input
          id="f-last"
          name="last_name"
          class="v2-input"
          bind:value={form.last_name}
          onblur={() => (touched.last_name = true)}
          aria-invalid={show('last_name') ? 'true' : undefined}
        />
        {#if show('last_name')}<p class="v2-error">{errors.last_name}</p>{/if}
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
        {#if show('email')}
          <p class="v2-error">{errors.email}</p>
        {:else}
          <p class="v2-hint">Tiene que ser única en esta organización, sin distinguir mayúsculas.</p>
        {/if}
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

    <div class="pair">
      <div class="v2-field">
        <label for="f-title">Cargo</label>
        <input id="f-title" name="title" class="v2-input" bind:value={form.title} />
      </div>
      <div class="v2-field">
        <label for="f-dept">Departamento</label>
        <input id="f-dept" name="department" class="v2-input" bind:value={form.department} />
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
        {#if data.account_total > data.accounts.length}
          <p class="v2-hint">
            Mostrando <span class="v2-num">{data.accounts.length}</span> de
            <span class="v2-num">{data.account_total}</span> cuentas.
          </p>
        {:else}
          <p class="v2-hint">También agrega a esta persona a las personas de esa cuenta.</p>
        {/if}
      </div>
      <div class="v2-field">
        <label for="f-owner">Responsable</label>
        <!-- What the select was rendered with. The action compares against it
             so an untouched owner is not sent at all; `assigned_to` is a
             many-to-many and this select is single, so sending it always would
             cut a two-person contact down to one on every save. -->
        <input type="hidden" name="assigned_to_original" value={data.form.assigned_to} />
        <select id="f-owner" name="assigned_to" class="v2-input" bind:value={form.assigned_to}>
          <option value="">Nadie</option>
          {#each data.owners as o (o.id)}
            <option value={o.id}>{o.name}</option>
          {/each}
        </select>
        {#if server.owner_count > 1}
          <p class="v2-hint">
            <span class="v2-num">{server.owner_count}</span> personas tienen asignado este contacto. Esta
            lista muestra la primera; cambiarla las reemplaza a todas, y dejarla como está las conserva.
          </p>
        {/if}
      </div>
    </div>

    <div class="v2-field">
      <label for="f-org">Empresa escrita a mano</label>
      <input id="f-org" name="organization" class="v2-input" bind:value={form.organization} />
      <p class="v2-hint">
        Texto libre, se conserva para registros importados. Cuando no coincide con la cuenta
        vinculada, es la cuenta la que usa el resto del CRM.
      </p>
    </div>

    <div class="v2-field">
      <label for="f-linkedin">LinkedIn</label>
      <input
        id="f-linkedin"
        name="linkedin_url"
        class="v2-input"
        type="url"
        bind:value={form.linkedin_url}
        onblur={() => (touched.linkedin_url = true)}
        aria-invalid={show('linkedin_url') ? 'true' : undefined}
      />
      {#if show('linkedin_url')}<p class="v2-error">{errors.linkedin_url}</p>{/if}
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

    <!--
      A cleared checkbox submits nothing, which is indistinguishable from a
      field this form does not own, and "absent means leave alone" is what
      makes PATCH safe everywhere else. The hidden partner is always sent, so
      the action can tell the two apart and switching either flag off works.
    -->
    <div class="flags">
      <input type="hidden" name="do_not_call_present" value="1" />
      <label class="flag">
        <input type="checkbox" name="do_not_call" bind:checked={form.do_not_call} />
        <span>
          <strong>No llamar</strong>
          <span class="v2-sub">Pidió que no lo llamen. El número se conserva en el registro.</span>
        </span>
      </label>

      <input type="hidden" name="is_active_present" value="1" />
      <label class="flag">
        <input type="checkbox" name="is_active" bind:checked={form.is_active} />
        <span>
          <strong>Todavía trabaja acá</strong>
          <span class="v2-sub">
            Desmarcá esto cuando alguien se va. Sigue en el historial de la cuenta pero sale de la
            lista de trabajo.
          </span>
        </span>
      </label>
    </div>

    {#if untouchedRelations.length}
      <p class="v2-hint" style="margin-bottom:14px">
        Este formulario no toca {untouchedRelations.join(', ')} de este contacto. Se editan donde
        viven.
      </p>
    {/if}

    <div class="actions">
      <button class="v2-btn v2-btn-primary" type="submit">Guardar cambios</button>
      <a class="v2-btn" href="/contacts/{contact.id}">Cancelar</a>
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
  .flags {
    display: grid;
    gap: 10px;
    margin: 4px 0 18px;
  }
  .flag {
    display: flex;
    gap: 9px;
    align-items: flex-start;
    font-size: 13px;
  }
  .flag span {
    display: block;
  }
  .flag .v2-sub {
    display: block;
    font-size: 11.5px;
    margin-top: 2px;
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
