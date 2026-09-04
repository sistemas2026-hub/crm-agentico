<script>
  /**
   * A new catalogue product: a name, a list price, and where it sits.
   *
   * VALIDATION HERE IS A UX HINT, NOT A RULE. The serializer requires a name and
   * a numeric price and rejects a duplicate SKU within the org; a non-admin is
   * refused outright. curl and the mobile client reach the API without passing
   * through this page. The view is the trust boundary (see CLAUDE.md).
   */
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import { enhance } from '$app/forms';
  import { ChevronRight, Lock } from '@lucide/svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  let values = $derived(form?.values ?? {});
</script>

<PageHeader title="Nuevo producto" record center width="62ch">
  {#snippet crumb()}
    <a href="/invoices/products">Productos</a>
    <ChevronRight size={12} />
    <span>Nuevo</span>
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
            El catálogo de productos es compartido en toda la organización, así que solo un
            administrador puede agregar productos. Igual podés usar cualquier producto en tus
            facturas y cotizaciones.
          </div>
        </div>
      </div>
      <a class="v2-btn" href="/invoices/products" style="margin-top:16px">Volver a productos</a>
    </div>
  {:else}
    <form
      method="POST"
      action="?/create"
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
          maxlength="255"
          value={values.name ?? ''}
          placeholder="Licencia de plataforma, por puesto"
        />
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
            placeholder="100.00"
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
          <input
            class="v2-input"
            name="category"
            maxlength="100"
            value={values.category ?? ''}
            placeholder="Licencia, Módulo, Servicio…"
          />
        </label>
        <label class="v2-field" style="flex:1;min-width:160px">
          <span class="v2-label">SKU</span>
          <input
            class="v2-input"
            name="sku"
            maxlength="100"
            value={values.sku ?? ''}
            placeholder="PLAT-SEAT"
          />
        </label>
      </div>
      <p class="v2-sub" style="font-size:11.5px;margin:-6px 0 16px">
        La categoría agrupa el catálogo; dejala en blanco y el producto queda bajo "Sin categoría". El
        SKU es opcional, pero si lo ponés tiene que ser único acá.
      </p>

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
      </label>

      <label class="v2-field">
        <span class="v2-label">Descripción</span>
        <textarea
          class="v2-input"
          name="description"
          rows="3"
          placeholder="Qué es, con las palabras que vería un cliente en una factura."
          >{values.description ?? ''}</textarea
        >
      </label>

      <div style="display:flex;gap:9px;margin-top:6px">
        <button class="v2-btn v2-btn-primary" type="submit">Agregar producto</button>
        <a class="v2-btn" href="/invoices/products">Cancelar</a>
      </div>
    </form>
  {/if}
</div>
