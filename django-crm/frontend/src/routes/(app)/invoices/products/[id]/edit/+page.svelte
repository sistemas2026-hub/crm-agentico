<script>
  /**
   * Editing a catalogue product, or retiring it.
   *
   * Retire vs delete: a product on historic invoices should be *retired*
   * (Availability → Retired), which pulls it from the line-item picker but keeps
   * the record. Deleting is also safe: line items store their own name and
   * price, so nothing historic is rewritten, but retiring is the honest default
   * for something with a past, so the form leads with it and puts delete behind
   * a confirm. Both are admin-only, enforced by the API.
   */
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import { enhance } from '$app/forms';
  import { ChevronRight, Lock, Trash2 } from '@lucide/svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  let values = $derived(form?.values ?? data.product ?? {});
  let usedOn = $derived(data.product?.used_on ?? 0);
  let confirming = $state(false);
</script>

<PageHeader title="Editar producto" record center width="62ch">
  {#snippet crumb()}
    <a href="/invoices/products">Productos</a>
    <ChevronRight size={12} />
    <span>{data.product?.name ?? 'Editar'}</span>
  {/snippet}
</PageHeader>

<div class="v2-scroll">
  {#if !data.can_edit}
    <div class="v2-pad" style="padding-top:24px;max-width:56ch;margin-left:auto;margin-right:auto">
      <div class="v2-next" role="note">
        <Lock size={17} style="flex:none" />
        <div class="v2-next-body">
          <div style="font-weight:600">Solo administradores</div>
          <div class="v2-sub" style="margin-top:2px">
            El catálogo de productos es compartido en toda la organización, así que solo un
            administrador puede modificarlo.
          </div>
        </div>
      </div>
      <a class="v2-btn" href="/invoices/products" style="margin-top:16px">Volver a productos</a>
    </div>
  {:else}
    <form
      method="POST"
      action="?/save"
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
        <input class="v2-input" name="name" required maxlength="255" value={values.name ?? ''} />
      </label>

      <div style="display:flex;gap:12px;flex-wrap:wrap">
        <label class="v2-field" style="flex:2;min-width:180px">
          <span class="v2-label">Precio de lista</span>
          <input
            class="v2-input"
            name="price"
            type="number"
            min="0"
            step="0.01"
            required
            value={values.price ?? ''}
          />
        </label>
        <label class="v2-field" style="flex:1;min-width:130px">
          <span class="v2-label">Moneda</span>
          <select class="v2-input" name="currency" value={values.currency ?? 'USD'}>
            {#each data.currencies as c (c.code)}
              <option value={c.code}>{c.label}</option>
            {/each}
          </select>
        </label>
      </div>

      <div style="display:flex;gap:12px;flex-wrap:wrap">
        <label class="v2-field" style="flex:1;min-width:160px">
          <span class="v2-label">Categoría</span>
          <input class="v2-input" name="category" maxlength="100" value={values.category ?? ''} />
        </label>
        <label class="v2-field" style="flex:1;min-width:160px">
          <span class="v2-label">SKU</span>
          <input class="v2-input" name="sku" maxlength="100" value={values.sku ?? ''} />
        </label>
      </div>

      <label class="v2-field">
        <span class="v2-label">Disponibilidad</span>
        <select
          class="v2-input"
          name="is_active"
          value={values.is_active === false ? 'false' : 'true'}
        >
          <option value="true">Vendible, aparece en el selector de ítems</option>
          <option value="false">Retirado, se conserva para el historial, oculto del selector</option>
        </select>
        {#if usedOn > 0}
          <span class="v2-sub" style="font-size:11.5px">
            Ya está en <span class="v2-num">{usedOn}</span>
            {usedOn === 1 ? 'factura' : 'facturas'}. Retirarlo las deja intactas.
          </span>
        {/if}
      </label>

      <label class="v2-field">
        <span class="v2-label">Descripción</span>
        <textarea class="v2-input" name="description" rows="3">{values.description ?? ''}</textarea>
      </label>

      <div style="display:flex;gap:9px;margin-top:6px;align-items:center">
        <button class="v2-btn v2-btn-primary" type="submit">Guardar cambios</button>
        <a class="v2-btn" href="/invoices/products">Cancelar</a>
      </div>
    </form>

    <!-- Delete lives in its own form so it never carries the edit fields. -->
    <div
      class="v2-pad"
      style="padding-top:0;padding-bottom:40px;max-width:62ch;margin-left:auto;margin-right:auto"
    >
      <div class="danger">
        {#if !confirming}
          <button class="v2-btn danger-btn" type="button" onclick={() => (confirming = true)}>
            <Trash2 size={14} /> Eliminar permanentemente
          </button>
          <span class="v2-sub" style="font-size:11.5px">
            {usedOn > 0
              ? 'Este producto ya está en facturas. Preferí Retirar arriba.'
              : 'Nunca se facturó, así que es seguro eliminarlo.'}
          </span>
        {:else}
          <form
            method="POST"
            action="?/delete"
            use:enhance
            style="display:flex;gap:8px;align-items:center"
          >
            <span class="v2-sub" style="font-size:12px">¿Eliminar este producto para siempre?</span>
            <button class="v2-btn danger-btn" type="submit"><Trash2 size={14} /> Eliminar</button>
            <button class="v2-btn" type="button" onclick={() => (confirming = false)}
              >Conservarlo</button
            >
          </form>
        {/if}
      </div>
    </div>
  {/if}
</div>

<style>
  .danger {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
    border-top: 1px solid var(--v2-line-soft);
    padding-top: 16px;
  }
  .danger-btn {
    color: var(--v2-rust);
    border-color: color-mix(in srgb, var(--v2-rust) 32%, transparent);
  }
  .danger-btn:hover {
    background: color-mix(in srgb, var(--v2-rust) 9%, transparent);
  }
</style>
