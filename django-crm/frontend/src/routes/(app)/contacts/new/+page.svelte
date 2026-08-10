<script>
  /**
   * Adding a person.
   *
   * Deliberately shorter than the edit form. Everything optional is left off
   * until there is a record to hang it on: address, LinkedIn, notes and the
   * inactive flag are all on the edit page, and a new contact is by definition
   * somebody who still works there.
   *
   * `?account=<id>` preselects the company, so "add somebody at this account"
   * arrives with the account already chosen.
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
      first_name: '',
      last_name: '',
      email: '',
      phone: '',
      title: '',
      department: '',
      organization: '',
      account: data.defaults.account ?? '',
      assigned_to: '',
      do_not_call: false,
      ...(result?.values ?? {})
    }))
  );
  let touched = $state(/** @type {Record<string, boolean>} */ ({}));
  let submitted = $state(false);

  let errors = $derived.by(() => {
    /** @type {Record<string, string>} */
    const e = {};
    if (!form.first_name.trim()) e.first_name = 'Una persona necesita un nombre.';
    if (!form.last_name.trim()) e.last_name = 'Una persona necesita un apellido.';

    if (form.email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(form.email))
      e.email = 'Eso no parece una dirección de correo.';

    // The exact regex from `flexible_phone_validator`. Extensions like "x123"
    // are rejected by the model, so they are caught at the field rather than
    // as an opaque whole-form refusal after the save.
    if (form.phone && !/^[\d\s\-()+.]{7,25}$/.test(form.phone))
      e.phone = 'De 7 a 25 caracteres: números, espacios, paréntesis, puntos, guiones. Sin extensiones.';

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

  let chosenAccount = $derived(
    data.accounts.find((/** @type {any} */ a) => a.id === form.account) ?? null
  );
</script>

<PageHeader title="Nuevo contacto" center>
  {#snippet crumb()}
    <a href="/contacts">Contactos</a>
    <ChevronRight size={12} />
    <span>Nuevo</span>
  {/snippet}
  {#snippet sub()}
    Una persona en una cuenta. Todo lo opcional puede esperar hasta que exista.
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
          <div style="font-weight:600">El servidor rechazó este contacto</div>
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
          <div class="v2-sub" style="margin-top:2px">No se creó nada.</div>
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
        {#if chosenAccount}
          <p class="v2-hint">También lo agrega a las personas de {chosenAccount.name}.</p>
        {:else if data.account_total > data.accounts.length}
          <p class="v2-hint">
            Mostrando <span class="v2-num">{data.accounts.length}</span> de
            <span class="v2-num">{data.account_total}</span> cuentas.
          </p>
        {:else}
          <p class="v2-hint">Se puede dejar vacío y definir después.</p>
        {/if}
      </div>
      <div class="v2-field">
        <label for="f-owner">Responsable</label>
        <select id="f-owner" name="assigned_to" class="v2-input" bind:value={form.assigned_to}>
          <option value="">Nadie</option>
          {#each data.owners as o (o.id)}
            <option value={o.id}>{o.name}</option>
          {/each}
        </select>
      </div>
    </div>

    <div class="v2-field">
      <label for="f-org">Empresa escrita a mano</label>
      <input id="f-org" name="organization" class="v2-input" bind:value={form.organization} />
      <p class="v2-hint">
        Solo hace falta cuando no hay una cuenta para vincular, es un registro importado, o una
        empresa que todavía nadie creó.
      </p>
    </div>

    <label class="flag">
      <input type="checkbox" name="do_not_call" bind:checked={form.do_not_call} />
      <span>
        <strong>No llamar</strong>
        <span class="v2-sub">Marcá si ya pidió que no lo llamen.</span>
      </span>
    </label>

    <div class="actions">
      <button class="v2-btn v2-btn-primary" type="submit">Crear contacto</button>
      <a class="v2-btn" href="/contacts">Cancelar</a>
    </div>
  </form>
</div>

<style>
  .pair {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 14px;
  }
  .flag {
    display: flex;
    gap: 9px;
    align-items: flex-start;
    font-size: 13px;
    margin: 4px 0 18px;
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
    .pair {
      grid-template-columns: 1fr;
    }
  }
</style>
