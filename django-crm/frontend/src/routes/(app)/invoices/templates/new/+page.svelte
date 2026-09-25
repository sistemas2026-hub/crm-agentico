<script>
  /**
   * A new invoice template: name, the two brand colours, an optional logo, and
   * the boilerplate text (notes, terms, footer) new invoices start with.
   *
   * SCOPE, ON PURPOSE. No `template_html` / `template_css` input anywhere on
   * this page, and no `{@html}` anywhere in this app. Both fields are org-
   * authored markup that WeasyPrint renders into a PDF server-side; every read
   * serializer (list AND detail) strips them, so a value written from a form
   * here could never be read back or edited afterwards, a write-once field
   * that is invisible from the moment it is saved. See `templates.js` for the
   * full reasoning.
   *
   * VALIDATION HERE IS A UX HINT, NOT A RULE. `POST /api/invoices/templates/`
   * is admin-gated (`_forbid_non_admin_template`) and enforces that
   * regardless of what this page shows; curl and the mobile client reach the
   * API without passing through here. The two colour inputs use
   * `type="color"` so the browser can only ever submit a valid six-digit hex
   * value: the server has no format validator on either field (only
   * `max_length=7`), so a text input would make the client check the only
   * thing standing between "purple" and a broken PDF.
   */
  import { enhance } from '$app/forms';
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import { ChevronRight, Lock } from '@lucide/svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  let values = $derived(form?.values ?? {});
</script>

<PageHeader title="Nueva plantilla" record center width="62ch">
  {#snippet crumb()}
    <a href="/invoices/templates">Plantillas</a>
    <ChevronRight size={12} />
    <span>Nueva</span>
  {/snippet}
</PageHeader>

<div class="v2-scroll">
  {#if !data.can_manage}
    <div class="v2-pad" style="padding-top:24px;max-width:56ch;margin-left:auto;margin-right:auto">
      <div class="v2-next" role="note">
        <Lock size={17} style="flex:none" />
        <div class="v2-next-body">
          <div style="font-weight:600">Solo administradores</div>
          <div class="v2-sub" style="margin-top:2px">
            Las plantillas de factura son configuración compartida de toda la organización, el
            aspecto de cada factura, así que solo un administrador puede crear una. Igual podés ver
            cómo lucen las plantillas existentes en la página de plantillas.
          </div>
        </div>
      </div>
      <a class="v2-btn" href="/invoices/templates" style="margin-top:16px">Volver a plantillas</a>
    </div>
  {:else}
    <form
      method="POST"
      action="?/create"
      enctype="multipart/form-data"
      use:enhance
      class="v2-pad"
      style="padding-top:18px;padding-bottom:36px;max-width:62ch;margin-left:auto;margin-right:auto"
    >
      {#if form?.error}
        <p style="color:var(--v2-rust);font-size:12.5px;margin:0 0 14px" role="alert">
          {form.error}
        </p>
      {/if}

      <label class="v2-field">
        <span class="v2-label">Nombre</span>
        <input
          class="v2-input"
          name="name"
          required
          maxlength="100"
          value={values.name ?? ''}
          placeholder="Factura estándar"
        />
      </label>

      <div class="color-row">
        <label class="color-field">
          <span class="v2-label">Color primario</span>
          <input
            class="color-swatch"
            type="color"
            name="primary_color"
            value={values.primary_color || '#3B82F6'}
          />
        </label>
        <label class="color-field">
          <span class="v2-label">Color secundario</span>
          <input
            class="color-swatch"
            type="color"
            name="secondary_color"
            value={values.secondary_color || '#1E40AF'}
          />
        </label>
      </div>
      <p class="v2-sub" style="font-size:11.5px;margin:-6px 0 16px">
        Se elige, no se escribe, así el valor enviado siempre es un hexadecimal válido de seis
        dígitos. La API guarda lo que se le dé acá sin verificar el formato.
      </p>

      <label class="v2-field">
        <span class="v2-label">Logo <span class="opt">(opcional)</span></span>
        <input class="v2-input" type="file" name="logo" accept="image/*" />
      </label>

      <label class="v2-field">
        <span class="v2-label">Notas predeterminadas <span class="opt">(opcional)</span></span>
        <textarea
          class="v2-input"
          name="default_notes"
          rows="3"
          placeholder="Gracias por tu compra."
          >{values.default_notes ?? ''}</textarea
        >
      </label>

      <label class="v2-field">
        <span class="v2-label">Condiciones predeterminadas <span class="opt">(opcional)</span></span>
        <textarea
          class="v2-input"
          name="default_terms"
          rows="3"
          placeholder="Pago dentro de los 30 días."
          >{values.default_terms ?? ''}</textarea
        >
      </label>

      <label class="v2-field">
        <span class="v2-label">Texto de pie de página <span class="opt">(opcional)</span></span>
        <textarea class="v2-input" name="footer_text" rows="2"
          >{values.footer_text ?? ''}</textarea
        >
      </label>

      <label class="flag">
        <input type="checkbox" name="is_default" checked={values.is_default === true} />
        <span>
          <strong>Convertir esta en la plantilla predeterminada</strong>
          <span class="v2-sub">
            Solo una plantilla puede ser la predeterminada a la vez. Activar esto reemplaza a la que
            la tenga ahora; las facturas nuevas se van a imprimir con esta en su lugar.
          </span>
        </span>
      </label>

      <div style="display:flex;gap:9px;margin-top:6px">
        <button class="v2-btn v2-btn-primary" type="submit">Crear plantilla</button>
        <a class="v2-btn" href="/invoices/templates">Cancelar</a>
      </div>
    </form>
  {/if}
</div>

<style>
  .opt {
    text-transform: none;
    font-weight: 500;
    letter-spacing: 0;
    color: var(--v2-slate);
  }
  .color-row {
    display: flex;
    gap: 16px;
  }
  .color-field {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .color-swatch {
    width: 56px;
    height: 38px;
    padding: 3px;
    border: 1px solid var(--v2-line);
    border-radius: 8px;
    background: var(--v2-card);
    cursor: pointer;
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
</style>
