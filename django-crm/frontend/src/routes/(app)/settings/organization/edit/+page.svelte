<script>
  /**
   * Editing the organisation.
   *
   * Admin-only. A non-admin who reaches this URL directly gets an "Admins only"
   * state, not the form, but that is the courtesy, not the control: the save
   * posts to `PATCH /api/org/settings/`, which the backend refuses for anyone
   * whose role is not ADMIN. `result.error` reports that refusal.
   *
   * What this form owns is the org's own settings: the company profile printed
   * on invoices, the locale defaults, and the two org-wide case-handling
   * switches. What it deliberately does NOT own: the org API key (a credential,
   * rotated through its own audited action) and `is_active` (the org kill
   * switch). Neither is a field here, and the server would not accept them if
   * they were smuggled into the request.
   *
   * The two switches submit an explicit on/off, so turning one OFF is a real
   * choice the save records, not the "left blank, so unchanged" behaviour of
   * the text fields.
   */
  import { tick, untrack } from 'svelte';
  import { enhance } from '$app/forms';
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import SettingsCrumb from '$lib/v2/components/SettingsCrumb.svelte';
  import NextAction from '$lib/v2/components/NextAction.svelte';
  import { CURRENCY_CODES } from '$lib/constants/filters.js';
  import { ChevronRight, TriangleAlert } from '@lucide/svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form: result } = $props();

  // A supported currency is required (the column is non-blank with a default),
  // so the empty "Select Currency" placeholder is dropped from the options.
  const currencyOptions = CURRENCY_CODES.filter((/** @type {any} */ c) => c.value);

  // A compact country list. Every value is a real code in the backend COUNTRIES
  // set, so the select can never offer one the serializer rejects.
  const countryOptions = [
    { value: 'US', label: 'Estados Unidos' },
    { value: 'GB', label: 'Reino Unido' },
    { value: 'CA', label: 'Canadá' },
    { value: 'AU', label: 'Australia' },
    { value: 'DE', label: 'Alemania' },
    { value: 'FR', label: 'Francia' },
    { value: 'IN', label: 'India' },
    { value: 'JP', label: 'Japón' },
    { value: 'SG', label: 'Singapur' },
    { value: 'AE', label: 'Emiratos Árabes Unidos' },
    { value: 'BR', label: 'Brasil' },
    { value: 'MX', label: 'México' },
    { value: 'CH', label: 'Suiza' },
    { value: 'NL', label: 'Países Bajos' },
    { value: 'ES', label: 'España' },
    { value: 'IT', label: 'Italia' }
  ];

  const org = untrack(() => data.org ?? {});
  // Always includes the org's current value, because the API builds the list
  // from the same database the value was validated against. A stored zone with
  // no matching option would make the select submit its first entry instead.
  const timezones = untrack(() => data.timezones ?? [{ name: 'UTC', label: 'UTC' }]);

  let form = $state(
    untrack(() => ({
      name: org.name ?? '',
      company_name: org.company_name ?? '',
      address_line: org.address_line ?? '',
      city: org.city ?? '',
      state: org.state ?? '',
      postcode: org.postcode ?? '',
      country: org.country ?? '',
      phone: org.phone ?? '',
      email: org.email ?? '',
      website: org.website ?? '',
      tax_id: org.tax_id ?? '',
      default_currency: org.default_currency || 'USD',
      default_country: org.default_country ?? '',
      timezone: org.timezone || 'UTC',
      // Booleans travel as strings so the select always submits an explicit value.
      csat_enabled: String(org.csat_enabled ?? true),
      auto_close_children_on_parent_close: String(org.auto_close_children_on_parent_close ?? false)
    }))
  );

  let touched = $state(/** @type {Record<string, boolean>} */ ({}));
  let submitted = $state(false);

  let errors = $derived.by(() => {
    /** @type {Record<string, string>} */
    const e = {};
    if (form.email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(form.email))
      e.email = 'Eso no parece una dirección de correo.';
    // The model stores this in a URLField, which wants a real URL. A light check
    // here saves a server round-trip; the serializer is the actual rule.
    if (form.website && !/^https?:\/\/.+\..+/.test(form.website))
      e.website = 'Incluí la dirección completa, empezando con http:// o https://.';
    return e;
  });

  let valid = $derived(Object.keys(errors).length === 0);
  const show = (/** @type {string} */ field) => (touched[field] || submitted) && errors[field];

  /**
   * These checks are a UX hint. The serializer is the rule, and its 400 is what
   * `result.error` reports.
   *
   * @type {import('./$types').SubmitFunction}
   */
  const check = async ({ cancel }) => {
    submitted = true;
    if (!valid) {
      cancel();
      await tick();
      /** @type {HTMLElement | null} */
      const first = document.querySelector('[aria-invalid="true"]');
      first?.focus();
      return;
    }
    return async ({ update }) => {
      // Keep the entered values on a server rejection so nothing is retyped.
      await update({ reset: false });
    };
  };
</script>

{#if data.forbidden}
  <PageHeader title="Organización">
    {#snippet crumb()}<SettingsCrumb />{/snippet}
  </PageHeader>
  <div class="v2-pad" style="padding-top:40px">
    <NextAction
      label="Solo administradores"
      text="Editar los datos de la organización está limitado a administradores. Pedile a un administrador de tu equipo si hay que cambiar un dato de la empresa, la moneda o la configuración de encuestas."
    />
  </div>
{:else}
  <PageHeader title="Editar organización" center>
    {#snippet crumb()}
      <a href="/settings">Configuración</a>
      <ChevronRight size={12} />
      <a href="/settings/organization">Organización</a>
    {/snippet}
  </PageHeader>

  <div class="v2-scroll v2-pad" style="padding-top:18px">
    <form class="v2-form" method="POST" action="?/save" use:enhance={check} novalidate>
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
            <div style="font-weight:600">Hay dos campos para revisar</div>
            <div class="v2-sub" style="margin-top:2px">Todavía no se guardó nada.</div>
          </div>
        </div>
      {/if}

      <div class="v2-label" style="margin-bottom:12px">Lo que ven los clientes</div>
      <p class="v2-hint" style="margin-top:-4px;margin-bottom:14px">
        Se imprime en cada factura y cotización. Los cambios aplican de ahora en adelante; los
        documentos ya enviados mantienen con lo que se enviaron.
      </p>

      <div class="v2-field">
        <label for="f-company">Razón social</label>
        <input
          id="f-company"
          name="company_name"
          class="v2-input"
          maxlength="255"
          bind:value={form.company_name}
        />
        <p class="v2-hint">El nombre legal registrado de la empresa, como debe aparecer en un documento.</p>
      </div>

      <div class="v2-field">
        <label for="f-name">Nombre comercial</label>
        <input id="f-name" name="name" class="v2-input" maxlength="100" bind:value={form.name} />
        <p class="v2-hint">Cómo se llama esta organización en toda la aplicación.</p>
      </div>

      <div class="pair">
        <div class="v2-field">
          <label for="f-tax">Identificación fiscal</label>
          <input
            id="f-tax"
            name="tax_id"
            class="v2-input"
            maxlength="50"
            bind:value={form.tax_id}
          />
        </div>
        <div class="v2-field">
          <label for="f-phone">Teléfono</label>
          <input
            id="f-phone"
            name="phone"
            class="v2-input"
            maxlength="25"
            bind:value={form.phone}
          />
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
          <label for="f-website">Sitio web</label>
          <input
            id="f-website"
            name="website"
            class="v2-input"
            type="url"
            bind:value={form.website}
            onblur={() => (touched.website = true)}
            aria-invalid={show('website') ? 'true' : undefined}
          />
          {#if show('website')}<p class="v2-error">{errors.website}</p>{/if}
        </div>
      </div>

      <div class="v2-field">
        <label for="f-address">Dirección</label>
        <input
          id="f-address"
          name="address_line"
          class="v2-input"
          maxlength="255"
          bind:value={form.address_line}
        />
      </div>

      <div class="triple">
        <div class="v2-field">
          <label for="f-city">Ciudad</label>
          <input id="f-city" name="city" class="v2-input" maxlength="100" bind:value={form.city} />
        </div>
        <div class="v2-field">
          <label for="f-state">Provincia</label>
          <input
            id="f-state"
            name="state"
            class="v2-input"
            maxlength="100"
            bind:value={form.state}
          />
        </div>
        <div class="v2-field">
          <label for="f-postcode">Código postal</label>
          <input
            id="f-postcode"
            name="postcode"
            class="v2-input"
            maxlength="20"
            bind:value={form.postcode}
          />
        </div>
      </div>

      <div class="v2-field">
        <label for="f-country">País</label>
        <select id="f-country" name="country" class="v2-input" bind:value={form.country}>
          <option value="">No registrado</option>
          {#each countryOptions as c (c.value)}
            <option value={c.value}>{c.label}</option>
          {/each}
        </select>
      </div>

      <div class="v2-label" style="margin:24px 0 12px">Valores por defecto</div>
      <div class="pair">
        <div class="v2-field">
          <label for="f-currency">Moneda</label>
          <select
            id="f-currency"
            name="default_currency"
            class="v2-input"
            bind:value={form.default_currency}
          >
            {#each currencyOptions as c (c.value)}
              <option value={c.value}>{c.label}</option>
            {/each}
          </select>
          <p class="v2-hint">Se aplica a facturas y cotizaciones nuevas. Las existentes mantienen la suya.</p>
        </div>
        <div class="v2-field">
          <label for="f-defcountry">País por defecto</label>
          <select
            id="f-defcountry"
            name="default_country"
            class="v2-input"
            bind:value={form.default_country}
          >
            <option value="">Sin definir</option>
            {#each countryOptions as c (c.value)}
              <option value={c.value}>{c.label}</option>
            {/each}
          </select>
          <p class="v2-hint">Se precarga en direcciones nuevas.</p>
        </div>
      </div>

      <div class="v2-field">
        <label for="f-timezone">Zona horaria</label>
        <select id="f-timezone" name="timezone" class="v2-input" bind:value={form.timezone}>
          {#each timezones as zone (zone.name)}
            <option value={zone.name}>{zone.label}</option>
          {/each}
        </select>
        <p class="v2-hint">
          Cuándo empieza el día para esta organización. Cambiarlo mueve qué cuenta como vencido hoy
          y atrasado, para todos acá.
        </p>
      </div>

      <div class="v2-label" style="margin:24px 0 12px">Comportamiento</div>

      <div class="v2-field">
        <label for="f-csat">Encuestas de satisfacción</label>
        <select id="f-csat" name="csat_enabled" class="v2-input" bind:value={form.csat_enabled}>
          <option value="true">Enviando. Se manda una encuesta después de cerrar un ticket</option>
          <option value="false">Apagado, sin encuestas, en toda la organización</option>
        </select>
        <p class="v2-hint">
          Apagado detiene todas las encuestas en toda la organización. No hay excepción por equipo
          ni aviso en el ticket.
        </p>
      </div>

      <div class="v2-field">
        <label for="f-cascade">Cerrar tickets hijos junto con el padre</label>
        <select
          id="f-cascade"
          name="auto_close_children_on_parent_close"
          class="v2-input"
          bind:value={form.auto_close_children_on_parent_close}
        >
          <option value="true">Ofrecerlo activado. La pregunta de cierre arranca marcada</option>
          <option value="false">Ofrecerlo apagado. La pregunta de cierre arranca sin marcar</option>
        </select>
        <p class="v2-hint">
          Solo define cómo arranca la pregunta. Cerrar un ticket padre nunca cierra un hijo por su
          cuenta, la persona siempre lo confirma.
        </p>
      </div>

      <div class="actions">
        <button class="v2-btn v2-btn-primary" type="submit">Guardar cambios</button>
        <a class="v2-btn" href="/settings/organization">Cancelar</a>
      </div>
    </form>
  </div>
{/if}

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
