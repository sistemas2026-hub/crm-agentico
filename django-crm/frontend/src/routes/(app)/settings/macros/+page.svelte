<script>
  /**
   * Canned replies.
   *
   * The body is the whole point of a macro, so it is on the page. V1 hides it
   * behind an edit dialog and lists titles, which means you cannot tell two
   * similarly-named macros apart without opening both.
   *
   * Placeholders are marked inline. `%customer_name%` is substituted by the
   * server; anything outside its seven supported tokens is left literal and
   * goes to the customer exactly as typed. That is the failure this page
   * exists to make visible: `%custmer_name%` has shipped twelve times.
   *
   * The body is org-authored text and is rendered as TEXT, split into
   * segments and placed in elements, never through {@html}. A canned reply is
   * a string a colleague wrote; putting it in the DOM as markup would make the
   * macro editor a stored-XSS form.
   *
   * PERMISSIONS, WHICH ARE NOT ROLE-GATED THE WAY THE REST OF SETTINGS IS
   * Every signed-in member may create, edit and delete their own `personal`
   * macros; only an admin may do any of that to an `org`-scope one.
   * `data.can_create_org` and `data.my_profile_id` are display hints decoded
   * server-side from the JWT (see `macros.js`'s `getMacros`), never the
   * authorization: the backend re-derives both and is what actually decides
   * whether a write succeeds. `canWrite` below mirrors that split so a row
   * only offers Edit/Delete when the click would not just come back as an
   * error.
   */
  import { enhance } from '$app/forms';
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import SettingsCrumb from '$lib/v2/components/SettingsCrumb.svelte';
  import Pill from '$lib/v2/components/Pill.svelte';
  import StatCard from '$lib/v2/components/StatCard.svelte';
  import SettingsFormPanel from '$lib/v2/components/SettingsFormPanel.svelte';
  import ConfirmAction from '$lib/v2/components/ConfirmAction.svelte';
  import { count, relativeDays } from '$lib/v2/format.js';
  import { MACRO_SCOPE_LABEL } from '$lib/v2/enums.js';
  import { Plus, TriangleAlert } from '@lucide/svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  // `null` when the panel is closed, `'new'` when adding, or the macro
  // object when editing that row. One panel, two modes, so two rows can
  // never be open for edit at once.
  let editing = $state(/** @type {any} */ (null));

  // The scope currently selected in the form. Bound separately from `editing`
  // so the select works the same way in both modes: seeded from the row on
  // edit, defaulted to 'personal' on create, since every member can make a
  // personal macro but not every member can make an org one.
  let scope = $state('personal');

  function openCreate() {
    editing = 'new';
    scope = 'personal';
  }

  function openEdit(m) {
    editing = m;
    scope = m.scope;
  }

  /**
   * May the signed-in viewer write this row. An org macro is writable only
   * by an admin (`data.can_create_org`); a personal macro is writable only
   * by its owner, compared by Profile id (`m.owner.id`, from `getMacros`'s
   * reshape, against `data.my_profile_id`). This is a display decision, not
   * an authorization one: the backend enforces the same split independently
   * (403 on someone else's org macro, 404 on someone else's personal one)
   * and would refuse the write even if this returned true by mistake.
   */
  function canWrite(m) {
    return m.scope === 'org' ? data.can_create_org : m.owner?.id === data.my_profile_id;
  }

  let totals = $derived(data.totals);
  let byUse = $derived([...data.macros].sort((a, b) => b.usage_count - a.usage_count));
  let orgMacros = $derived(byUse.filter((m) => m.scope === 'org'));
  let personalMacros = $derived(byUse.filter((m) => m.scope === 'personal'));

  /**
   * Split a body into text and placeholder segments for rendering.
   *
   * Whether a token is real is decided by the server's `unknown_placeholders`,
   * not by matching against a list kept here. The supported set lives in
   * `macros/render.py` precisely so clients cannot drift from it. A copy in
   * this file would eventually mark a working macro as broken.
   */
  function segments(macro) {
    const re = /%[a-zA-Z_][a-zA-Z0-9_]*%/g;
    const out = [];
    let last = 0;
    let m;
    while ((m = re.exec(macro.body)) !== null) {
      if (m.index > last) out.push({ text: macro.body.slice(last, m.index), token: false });
      out.push({
        text: m[0],
        token: true,
        known: !macro.unknown_placeholders.includes(m[0])
      });
      last = m.index + m[0].length;
    }
    if (last < macro.body.length) out.push({ text: macro.body.slice(last), token: false });
    return out;
  }
</script>

<PageHeader title="Macros">
  {#snippet crumb()}<SettingsCrumb />{/snippet}
  {#snippet sub()}
    <span class="v2-num">{count(totals.org)}</span> compartidas ·
    <span class="v2-num">{count(totals.personal)}</span> tuyas
  {/snippet}
  {#snippet actions()}
    {#if !editing}
      <button class="v2-btn v2-btn-primary" onclick={openCreate}><Plus />Nueva macro</button>
    {/if}
  {/snippet}
</PageHeader>

<div class="v2-pad" style="padding-top:16px;flex:none">
  <div class="v2-stats">
    <StatCard label="Compartidas con todos" value={count(totals.org)} tone="ink" />
    <StatCard label="Solo tuyas" value={count(totals.personal)} tone="slate" />
    <StatCard
      label="Placeholders rotos"
      value={count(totals.with_unknown_placeholders)}
      tone={totals.with_unknown_placeholders > 0 ? 'rust' : 'slate'}
      detail="Enviados a clientes tal como se escribieron"
    />
    <StatCard label="Apagadas" value={count(totals.inactive)} tone="slate" />
  </div>
</div>

<div class="v2-scroll">
  <div class="v2-pad" style="padding-bottom:32px">
    {#if editing}
      <SettingsFormPanel
        title={editing === 'new' ? 'Nueva macro' : `Editar ${editing.title}`}
        action={editing === 'new' ? '?/create' : '?/update'}
        error={editing === 'new' ? form?.create?.error : form?.update?.error}
        submitLabel={editing === 'new' ? 'Agregar macro' : 'Guardar macro'}
        oncancel={() => (editing = null)}
        ondone={() => (editing = null)}
      >
        {#snippet fields()}
          {#if editing !== 'new'}
            <input type="hidden" name="id" value={editing.id} />
          {/if}

          <div class="v2-field">
            <label for="m-title">Título</label>
            <input
              id="m-title"
              class="v2-input"
              name="title"
              maxlength="255"
              required
              value={editing === 'new' ? '' : editing.title}
            />
          </div>

          <div class="v2-field">
            <label for="m-scope">Quién la ve</label>
            <select id="m-scope" class="v2-input" name="scope" bind:value={scope}>
              <option value="personal">Solo yo</option>
              {#if data.can_create_org}
                <option value="org">Todos en la organización</option>
              {/if}
            </select>
            {#if !data.can_create_org}
              <p class="v2-hint">Solo un administrador puede compartir una macro con todos.</p>
            {/if}
          </div>

          <div class="v2-field v2-sfp-wide">
            <label for="m-body">Contenido</label>
            <textarea id="m-body" class="v2-input" name="body" rows="5" required
              >{editing === 'new' ? '' : editing.body}</textarea
            >
            <p class="v2-hint">
              Los placeholders como %customer_name% se reemplazan cuando se envía la macro. Los
              siete tokens soportados están listados a la derecha; cualquier otra cosa le llega al
              cliente exactamente como se escribió.
            </p>
          </div>
        {/snippet}
      </SettingsFormPanel>
    {/if}

    {#if form?.delete?.error}
      <p class="v2-error" style="margin-bottom:12px">{form.delete.error}</p>
    {/if}
    {#if form?.activate?.error}
      <p class="v2-error" style="margin-bottom:12px">{form.activate.error}</p>
    {/if}

    <div class="v2-split-wide">
      <div>
        <div class="v2-label" style="margin-bottom:10px">Compartidas con todos</div>
        <div style="display:flex;flex-direction:column;gap:9px;margin-bottom:24px">
          {#each orgMacros as m (m.id)}
            {@render macro(m)}
          {/each}
        </div>

        <div class="v2-label" style="margin-bottom:10px">Solo tuyas</div>
        <div style="display:flex;flex-direction:column;gap:9px">
          {#each personalMacros as m (m.id)}
            {@render macro(m)}
          {/each}
        </div>
        <p class="v2-sub" style="font-size:11.5px;margin-top:11px">
          Las macros personales solo son visibles para vos. Nadie más en la organización, ni
          siquiera los administradores, ve esta lista.
        </p>
      </div>

      <div>
        <div class="v2-label" style="margin-bottom:10px">Placeholders que funcionan</div>
        <div class="v2-card" style="overflow:hidden">
          {#each data.placeholders as p (p.token)}
            <div class="v2-setting" style="padding:10px 15px">
              <div class="v2-setting-body">
                <code class="v2-token">{p.token}</code>
              </div>
              <span class="v2-sub" style="font-size:11.5px;text-align:right">{p.resolves}</span>
            </div>
          {/each}
        </div>
        <p class="v2-sub" style="font-size:11.5px;margin-top:11px;line-height:1.5">
          Estos siete son todo el conjunto. Cualquier otra cosa entre signos de porcentaje se deja
          exactamente como se escribió y se envía así. El servidor no adivina, a propósito, así que
          un error de tipeo se ve en el compositor en vez de quedar en blanco en la bandeja del
          cliente.
        </p>
      </div>
    </div>
  </div>
</div>

{#snippet macro(m)}
  <div class="v2-card" style="padding:14px 16px;opacity:{m.is_active ? 1 : 0.62}">
    <div style="display:flex;gap:10px;align-items:baseline;flex-wrap:wrap">
      <b style="font-size:13.5px">{m.title}</b>
      {#if !m.is_active}<Pill tone="slate">Apagada</Pill>{/if}
      {#if m.unknown_placeholders.length}<Pill tone="rust">Placeholder roto</Pill>{/if}
      <span class="v2-sub" style="font-size:11.5px;margin-left:auto">
        usada <span class="v2-num">{count(m.usage_count)}</span> veces ·
        {relativeDays(m.updated_at)}
      </span>
    </div>

    <!--
      Text nodes and spans, never {@html}.

      Written on one line and held there by prettier-ignore. Svelte collapses
      the newline and indentation between two inline children into a single
      space, so a formatted version of this block renders "%customer_name% ,".
      A space the macro does not contain, in a preview whose whole job is to
      show exactly what the customer receives.
    -->
    <!-- prettier-ignore -->
    <p class="v2-macro-body">{#each segments(m) as seg, i (i)}{#if seg.token}<span class="v2-token" class:v2-token-bad={!seg.known}>{seg.text}</span>{:else}{seg.text}{/if}{/each}</p>

    {#if m.unknown_placeholders.length}
      <div class="v2-macro-flag">
        <TriangleAlert size={14} style="color:var(--v2-rust);flex:none" />
        <span>
          {m.unknown_placeholders.join(' y ')}
          {m.unknown_placeholders.length === 1 ? 'no es un placeholder' : 'no son placeholders'},
          {m.unknown_placeholders.length === 1 ? 'le llega' : 'le llegan'} al cliente exactamente como
          se escribieron.
          {#if m.usage_count > 0}
            Esta macro se envió
            <span class="v2-num">{count(m.usage_count)}</span> veces.
          {/if}
        </span>
      </div>
    {/if}

    {#if m.owner}
      <div class="v2-sub" style="font-size:11px;margin-top:8px">
        {MACRO_SCOPE_LABEL[m.scope]} · {m.owner.name}
      </div>
    {/if}

    {#if canWrite(m)}
      <div style="display:flex;gap:6px;align-items:center;justify-content:flex-end;margin-top:10px">
        <button class="v2-btn v2-btn-sm" type="button" onclick={() => openEdit(m)}>Editar</button>
        {#if !m.is_active}
          <!-- Turning a macro back on restores nothing that was destroyed, so
               unlike "Turn off"/"Delete" this doesn't need the two-click
               confirm. A plain enhanced form posting just the id keeps the
               request to `{ is_active: true }`; see `activateMacro`'s
               comment for why that has to bypass `updateMacro` rather than
               reuse it. Offered for both scopes on purpose: an org row gets
               here by "Turn off" (soft), a personal row can only be inactive
               from data written before the edit form stopped carrying
               `is_active`, and either way `_get_writable` still enforces
               admin-only for org / owner-only for personal server-side, so
               this can never write a row `canWrite` above disagrees with. -->
          <form method="POST" action="?/activate" use:enhance>
            <input type="hidden" name="id" value={m.id} />
            <button class="v2-btn v2-btn-sm" type="submit">Encender</button>
          </form>
        {:else if m.scope === 'org'}
          <!-- `MacroDetailView.delete` soft-deletes an org macro: it flips
               `is_active` and leaves the row (and its usage count) in place.
               "Turn off", not "Delete", says what actually happens. -->
          <ConfirmAction
            action="?/delete"
            label="Apagar"
            confirmLabel="Apagar"
            explain="La apaga para todos. Deja de aparecer en el selector."
            hidden={{ id: m.id }}
          />
        {:else}
          <!-- A personal macro is hard-deleted, not soft-deactivated: this
               button removes the row outright, so once it's gone there is
               nothing left to turn back on. -->
          <ConfirmAction
            action="?/delete"
            label="Eliminar"
            confirmLabel="Eliminar"
            explain="La elimina de forma permanente."
            hidden={{ id: m.id }}
          />
        {/if}
      </div>
    {/if}
  </div>
{/snippet}

<style>
  .v2-macro-body {
    font-size: 12.5px;
    color: var(--v2-slate);
    line-height: 1.55;
    white-space: pre-wrap;
    margin: 9px 0 0;
  }
  .v2-token {
    font-family: var(--v2-mono);
    font-size: 11.5px;
    background: var(--v2-hover);
    border-radius: 3px;
    padding: 1px 4px;
    color: var(--v2-ink);
  }
  /* No side padding inside a body preview. Four pixels either side renders
     "%customer_name% ,". A space the macro does not contain, on a screen
     whose only job is to show exactly what the customer will receive. The
     background alone is enough to mark it. */
  .v2-macro-body .v2-token {
    padding: 1px 0;
  }
  /* Rust, not ember: a broken placeholder is a fact about the macro, not a
     button. Ember stays reserved for things you act on. */
  .v2-token-bad {
    color: var(--v2-rust);
    text-decoration: underline wavy;
    text-underline-offset: 2px;
  }
  .v2-macro-flag {
    display: flex;
    gap: 7px;
    align-items: flex-start;
    margin-top: 10px;
    font-size: 12px;
    color: var(--v2-slate);
    line-height: 1.45;
  }
</style>
