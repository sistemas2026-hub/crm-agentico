<script>
  /**
   * Fields this organisation added to records that shipped without them.
   *
   * Grouped by the record they extend, because that is how anyone looks for
   * one; "what do we collect on a ticket" is the question, not "show me all
   * 40 definitions sorted by created date".
   *
   * The number that earns its place here is `records_missing_value`. Marking a
   * field required only binds writes from that moment; records saved before it
   * existed keep their gap and nothing backfills them. So "Required" on a
   * field with 23 records missing a value is a promise the data does not keep,
   * and reporting on that field will quietly exclude or mis-bucket those 23.
   */
  import { enhance } from '$app/forms';
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import SettingsCrumb from '$lib/v2/components/SettingsCrumb.svelte';
  import Pill from '$lib/v2/components/Pill.svelte';
  import StatCard from '$lib/v2/components/StatCard.svelte';
  import SettingsFormPanel from '$lib/v2/components/SettingsFormPanel.svelte';
  import ConfirmAction from '$lib/v2/components/ConfirmAction.svelte';
  import { count } from '$lib/v2/format.js';
  import { FIELD_TYPE_LABEL, TARGET_MODEL_LABEL } from '$lib/v2/enums.js';
  import { Plus, TriangleAlert, Filter } from '@lucide/svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  // `null` when the panel is closed, `'new'` when adding, or the field object
  // when editing that row. One panel, two modes, so two rows can never be
  // open for edit at once.
  let editing = $state(/** @type {any} */ (null));

  // The dropdown options being edited, as `{ value, label }` rows. Held here
  // rather than read off `editing` so a row can be added or removed before
  // submitting. A new row has an empty `value`; the server module slugifies
  // one from the label, and never rewrites an existing value.
  let optionRows = $state(/** @type {{ value: string, label: string }[]} */ ([]));

  // The type currently selected in the form, so the options editor appears
  // only for a dropdown. Seeded from the row being edited.
  let fieldType = $state('text');

  function openCreate() {
    editing = 'new';
    fieldType = 'text';
    optionRows = [];
  }

  function openEdit(f) {
    editing = f;
    fieldType = f.field_type;
    optionRows = (f.options ?? []).map((o) => ({ value: o.value, label: o.label }));
  }

  let totals = $derived(data.totals);

  /** One group per extended model, fields kept in display_order. */
  let groups = $derived.by(() => {
    /** @type {Map<string, any[]>} */
    const byModel = new Map();
    for (const f of data.fields) {
      byModel.set(f.target_model, [...(byModel.get(f.target_model) ?? []), f]);
    }
    return [...byModel.entries()].map(([model, fields]) => ({
      model,
      label: TARGET_MODEL_LABEL[model] ?? model,
      fields: [...fields].sort((a, b) => a.display_order - b.display_order)
    }));
  });

  let gaps = $derived(data.fields.filter((f) => f.is_required && f.records_missing_value > 0));
</script>

<PageHeader title="Campos personalizados">
  {#snippet crumb()}<SettingsCrumb />{/snippet}
  {#snippet sub()}
    <span class="v2-num">{count(totals.active)}</span> campos en
    <span class="v2-num">{count(totals.models_extended)}</span> tipos de registro
  {/snippet}
  {#snippet actions()}
    {#if data.can_edit && !editing}
      <button class="v2-btn v2-btn-primary" onclick={openCreate}><Plus />Nuevo campo</button>
    {/if}
  {/snippet}
</PageHeader>

<div class="v2-pad" style="padding-top:16px;flex:none">
  <div class="v2-stats">
    <StatCard label="Campos activos" value={count(totals.active)} tone="ink" />
    <StatCard label="Tipos de registro extendidos" value={count(totals.models_extended)} tone="slate" />
    <StatCard
      label="Obligatorios con vacíos"
      value={count(totals.required_with_gaps)}
      tone={totals.required_with_gaps > 0 ? 'clay' : 'slate'}
      detail="Registros anteriores a la regla"
    />
    <StatCard label="Desactivados" value={count(totals.count - totals.active)} tone="slate" />
  </div>
</div>

<div class="v2-scroll">
  <div class="v2-pad" style="padding-bottom:32px">
    {#if editing}
      <SettingsFormPanel
        title={editing === 'new' ? 'Nuevo campo personalizado' : `Editar ${editing.label}`}
        action={editing === 'new' ? '?/create' : '?/update'}
        error={editing === 'new' ? form?.create?.error : form?.update?.error}
        submitLabel={editing === 'new' ? 'Agregar campo' : 'Guardar campo'}
        oncancel={() => (editing = null)}
        ondone={() => (editing = null)}
      >
        {#snippet fields()}
          {#if editing !== 'new'}
            <input type="hidden" name="id" value={editing.id} />
          {/if}

          <div class="v2-field">
            <label for="f-label">Etiqueta</label>
            <input
              id="f-label"
              class="v2-input"
              name="label"
              maxlength="128"
              required
              value={editing === 'new' ? '' : editing.label}
            />
          </div>

          <div class="v2-field">
            <label for="f-key">Clave</label>
            {#if editing === 'new'}
              <input
                id="f-key"
                class="v2-input"
                name="key"
                maxlength="64"
                pattern="[a-z][a-z0-9_]*"
                required
                placeholder="severity"
              />
              <p class="v2-hint">
                Letras minúsculas, números y guiones bajos, empezando con una letra. Sin guiones
                medios. No se puede cambiar después.
              </p>
            {:else}
              <code class="v2-cf-key">{editing.key}</code>
              <p class="v2-hint">
                Fija después de crearla. Todo valor ya guardado está archivado bajo esta clave, y
                cambiarla los dejaría a todos atrás.
              </p>
            {/if}
          </div>

          <div class="v2-field">
            <label for="f-target">En tipo de registro</label>
            {#if editing === 'new'}
              <select id="f-target" class="v2-input" name="target_model" required>
                {#each Object.entries(TARGET_MODEL_LABEL) as [value, label] (value)}
                  <option {value}>{label}</option>
                {/each}
              </select>
            {:else}
              <div style="font-size:13px">
                {TARGET_MODEL_LABEL[editing.target_model] ?? editing.target_model}
              </div>
              <p class="v2-hint">Fijo después de crearlo.</p>
            {/if}
          </div>

          <div class="v2-field">
            <label for="f-type">Tipo</label>
            {#if editing === 'new'}
              <select id="f-type" class="v2-input" name="field_type" bind:value={fieldType}>
                {#each Object.entries(FIELD_TYPE_LABEL) as [value, label] (value)}
                  <option {value}>{label}</option>
                {/each}
              </select>
            {:else}
              <!-- No `<select>` here means nothing named `field_type` reaches
                   the form submit, but `fieldType` (below) still has to drive
                   whether the choices editor renders and, on submit, whether
                   `readValues`/`buildBody` attach `options` at all. This
                   hidden input carries the value through without offering it
                   as something to change; `UPDATE_FIELDS` drops `field_type`
                   from the outgoing body regardless of what this holds. -->
              <input type="hidden" name="field_type" value={fieldType} />
              <div style="font-size:13px">{FIELD_TYPE_LABEL[editing.field_type]}</div>
              <p class="v2-hint">
                Fijo después de crearlo. Los valores ya guardados se escribieron y validaron contra
                este tipo.
              </p>
            {/if}
          </div>

          {#if fieldType === 'dropdown'}
            <div class="v2-field v2-sfp-wide">
              <label for="f-choices">Opciones</label>
              {#each optionRows as row, i (i)}
                <div style="display:flex;gap:7px;align-items:center;margin-bottom:6px">
                  <input type="hidden" name="option_value" value={row.value} />
                  <input
                    id={i === 0 ? 'f-choices' : undefined}
                    class="v2-input"
                    name="option_label"
                    bind:value={row.label}
                    required
                  />
                  <button
                    class="v2-btn v2-btn-sm"
                    type="button"
                    onclick={() => (optionRows = optionRows.filter((_, j) => j !== i))}
                  >
                    Quitar
                  </button>
                </div>
              {/each}
              <button
                class="v2-btn v2-btn-sm"
                type="button"
                style="align-self:flex-start"
                onclick={() => (optionRows = [...optionRows, { value: '', label: '' }])}
              >
                Agregar una opción
              </button>
              <p class="v2-hint">
                Renombrar una opción mantiene los valores ya guardados con ella. Quitar una deja a
                los registros que la tienen mostrando un valor que la lista ya no ofrece.
              </p>
            </div>
          {/if}

          <div class="v2-field">
            <label for="f-order">Orden</label>
            <input
              id="f-order"
              class="v2-input"
              type="number"
              name="display_order"
              min="0"
              value={editing === 'new' ? 0 : editing.display_order}
            />
          </div>

          <div class="v2-field">
            <label for="f-required">Obligatorio</label>
            <label style="display:flex;gap:8px;align-items:center;font-weight:400">
              <input
                id="f-required"
                type="checkbox"
                name="is_required"
                value="true"
                checked={editing !== 'new' && editing.is_required}
              />
              Solo aplica a escrituras nuevas. Los registros guardados antes mantienen su vacío.
            </label>
          </div>

          <div class="v2-field">
            <label for="f-filterable">Filtrable</label>
            <label style="display:flex;gap:8px;align-items:center;font-weight:400">
              <input
                id="f-filterable"
                type="checkbox"
                name="is_filterable"
                value="true"
                checked={editing !== 'new' && editing.is_filterable}
              />
              Se puede usar para acotar una lista, no solo leerse en el registro.
            </label>
          </div>
        {/snippet}
      </SettingsFormPanel>
    {/if}

    {#if gaps.length}
      <div class="v2-cf-banner">
        <TriangleAlert size={16} style="color:var(--v2-clay);flex:none;margin-top:1px" />
        <div>
          <div style="font-weight:600;font-size:13px">
            Obligatorio no significa que todo registro lo tenga
          </div>
          <p class="v2-sub" style="font-size:12px;margin:4px 0 0;line-height:1.5">
            {gaps
              .map(
                (f) =>
                  `A ${f.label} le falta en ${f.records_missing_value} ${(TARGET_MODEL_LABEL[f.target_model] ?? f.target_model).toLowerCase()}`
              )
              .join('; ')}. Marcar un campo como obligatorio solo aplica a escrituras nuevas, nada
            retrocede a completar lo que ya se había guardado.
          </p>
        </div>
      </div>
    {/if}

    {#if form?.deactivate?.error}
      <p class="v2-error" style="margin-bottom:12px">{form.deactivate.error}</p>
    {/if}
    {#if form?.activate?.error}
      <p class="v2-error" style="margin-bottom:12px">{form.activate.error}</p>
    {/if}

    <div class="v2-cf-groups">
      {#each groups as g (g.model)}
        <div>
          <div class="v2-label" style="margin-bottom:10px">En {g.label.toLowerCase()}</div>
          <div class="v2-card" style="overflow:hidden">
            {#each g.fields as f (f.id)}
              <div class="v2-setting" style="opacity:{f.is_active ? 1 : 0.6}">
                <div class="v2-setting-body">
                  <div style="display:flex;gap:7px;align-items:baseline;flex-wrap:wrap">
                    <b>{f.label}</b>
                    <code class="v2-cf-key">{f.key}</code>
                  </div>
                  <span class="v2-sub" style="font-size:11.5px">
                    {FIELD_TYPE_LABEL[f.field_type]}{#if f.options}
                      · {f.options.map((o) => o.label).join(', ')}
                    {/if}
                    {#if f.is_required && f.records_missing_value > 0}
                      · <span style="color:var(--v2-clay)">
                        {count(f.records_missing_value)} sin valor
                      </span>
                    {/if}
                  </span>
                </div>

                {#if f.is_filterable}
                  <!-- Filterable is the difference between a field you can
                       search a list by and one you can only read once you have
                       already opened the record. -->
                  <Filter size={13} style="color:var(--v2-slate);flex:none" />
                {/if}
                {#if !f.is_active}
                  <Pill tone="slate">Apagado</Pill>
                {:else if f.is_required}
                  <Pill tone="clay">Obligatorio</Pill>
                {/if}

                {#if data.can_edit}
                  <div style="display:flex;gap:6px;align-items:center;flex:none">
                    <button class="v2-btn v2-btn-sm" type="button" onclick={() => openEdit(f)}>
                      Editar
                    </button>
                    {#if f.is_active}
                      <ConfirmAction
                        action="?/deactivate"
                        label="Apagar"
                        confirmLabel="Apagar"
                        explain="Deja de recolectarse. Los valores guardados se mantienen."
                        hidden={{ id: f.id }}
                      />
                    {:else}
                      <!-- Turning a field back on restores nothing that was
                           destroyed (the values never left), so unlike "Turn
                           off" this doesn't need the two-click confirm. A
                           plain enhanced form posting just the id keeps the
                           request to `{ is_active: true }`, see the `activate`
                           action's comment for why that has to be its own
                           action rather than a bare `update` submit. -->
                      <form method="POST" action="?/activate" use:enhance>
                        <input type="hidden" name="id" value={f.id} />
                        <button class="v2-btn v2-btn-sm" type="submit">Encender</button>
                      </form>
                    {/if}
                  </div>
                {/if}
              </div>
            {/each}
          </div>
        </div>
      {/each}
    </div>

    <p class="v2-sub" style="font-size:11.5px;margin-top:16px;max-width:66ch">
      Un campo marcado con el ícono de filtro se puede usar para acotar una lista; el resto solo se
      puede leer en el registro mismo. Apagar un campo deja de recolectarlo y lo oculta, y deja
      intactos los valores ya guardados en cada registro.
    </p>
  </div>
</div>

<style>
  .v2-cf-groups {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px 24px;
    align-items: start;
  }
  .v2-cf-key {
    font-family: var(--v2-mono);
    font-size: 11px;
    color: var(--v2-slate);
    background: var(--v2-hover);
    border-radius: 3px;
    padding: 1px 4px;
  }
  .v2-cf-banner {
    display: flex;
    gap: 11px;
    align-items: flex-start;
    padding: 14px 16px;
    margin-bottom: 18px;
    border: 1px solid var(--v2-line);
    border-radius: var(--v2-radius);
    background: var(--v2-card);
  }

  @media (max-width: 1000px) {
    .v2-cf-groups {
      grid-template-columns: 1fr;
    }
  }
</style>
