<script>
  /**
   * The labels shared across accounts, leads, deals and tickets.
   *
   * A tag list without usage counts is a list of words. The two questions an
   * admin actually has are "which of these is nobody using" and "have we ended
   * up with two tags for one idea", and both need the counts to answer.
   *
   * `slug` is unique per org and derived from `name`, so two tags can never
   * collide on the slug, but "Renewal" and "Renewals" slug differently while
   * meaning the same thing, and the work splits silently across them.
   */
  import { enhance } from '$app/forms';
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import SettingsCrumb from '$lib/v2/components/SettingsCrumb.svelte';
  import Pill from '$lib/v2/components/Pill.svelte';
  import StatCard from '$lib/v2/components/StatCard.svelte';
  import EmptyState from '$lib/v2/components/EmptyState.svelte';
  import ConfirmAction from '$lib/v2/components/ConfirmAction.svelte';
  import { count } from '$lib/v2/format.js';
  import { Plus, Merge, Tags as TagsIcon } from '@lucide/svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  // The "New tag" disclosure. Open while adding, closed on a successful
  // create; a failed one stays open so the error next to the input is
  // actually visible instead of vanishing the instant the form action
  // returns.
  let adding = $state(false);

  // Disables the Create button while the submit is in flight, so a
  // double-click cannot fire two creates: the second would either duplicate
  // the tag or, for a same-named resubmit, come back as "already exists"
  // right after the first one succeeded.
  let busy = $state(false);

  let totals = $derived(data.totals);

  /**
   * Total usage across every model a tag can be applied to.
   *
   * Summed over the keys the backend sends rather than a list written out
   * here, so it cannot drift from `_TAGGABLE`
   * (`backend/common/views/tags_views.py`) the way the old hard-coded four
   * did: contacts, tasks and API settings were all missing, so a tag in real
   * use on contacts read as unused both here and on the totals card. A test
   * on the backend now walks the model registry to keep that list complete;
   * this sums whatever it sends.
   */
  const used = (t) => Object.values(t.usage ?? {}).reduce((sum, n) => sum + (n || 0), 0);

  let tags = $derived(
    [...data.tags].sort((a, b) => used(b) - used(a) || a.name.localeCompare(b.name))
  );

  /**
   * Tags that probably mean the same thing.
   *
   * A suggestion, computed over every active tag in the org. Settings lists
   * are not paginated, so this is not an aggregate over rows we cannot see.
   * The match is deliberately crude (case, spacing, punctuation and a
   * trailing plural), and it decides nothing on its own: it puts two names
   * next to each other and offers the merge, because "Invoice" and "Invoices"
   * might genuinely be two ideas in some org.
   */
  const normalise = (name) =>
    name
      .toLowerCase()
      .replace(/[^a-z0-9]/g, '')
      .replace(/s$/, '');

  let duplicateGroups = $derived.by(() => {
    /** @type {Map<string, any[]>} */
    const groups = new Map();
    // Active tags only. The list itself is fetched with
    // `?include_archived=true` so an admin can see what has been turned off,
    // but an archived tag is not offered on new records and so cannot be
    // splitting anyone's work: it is not a duplicate, it is a former one.
    // Grouping over the full list also meant the banner never went away.
    // Turning one of the pair off used to leave it nagging forever, and once
    // Merge was wired that got worse: the merge archives the tag it empties,
    // so the banner would come straight back offering to merge a tag that no
    // longer had any records.
    for (const t of data.tags.filter((/** @type {any} */ t) => t.is_active)) {
      const key = normalise(t.name);
      groups.set(key, [...(groups.get(key) ?? []), t]);
    }
    return [...groups.values()]
      .filter((g) => g.length > 1)
      .map((g) => {
        // Most-used first, so `keep` is the tag the org already voted for and
        // a merge moves the smaller pile. `keep` is necessarily active now
        // that the grouping is, which matters because `TagsMergeView` refuses
        // an archived destination: moving records onto a tag the page renders
        // as "Off" reads as data loss.
        const ranked = [...g].sort((a, b) => used(b) - used(a) || a.name.localeCompare(b.name));
        return { all: ranked, keep: ranked[0], merge: ranked.slice(1) };
      });
  });
</script>

<PageHeader title="Etiquetas">
  {#snippet crumb()}<SettingsCrumb />{/snippet}
  {#snippet sub()}
    <span class="v2-num">{count(totals.active)}</span> en uso entre cuentas, prospectos, negociaciones
    y tickets
  {/snippet}
  {#snippet actions()}
    {#if data.can_edit}
      {#if adding}
        <form
          class="v2-tag-add-form"
          method="POST"
          action="?/create"
          use:enhance={() => {
            busy = true;
            return async (/** @type {any} */ { result, update }) => {
              await update();
              busy = false;
              // Only close on success. A failed submit (the empty-name guard, a
              // duplicate name) has to leave the form open, or the error rendered
              // below never gets seen: it lives inside this same `{#if adding}`
              // block.
              if (result.type === 'success') adding = false;
            };
          }}
        >
          {#if form?.create?.error}
            <p class="v2-error">{form.create.error}</p>
          {/if}
          <!-- svelte-ignore a11y_autofocus -->
          <input
            class="v2-input"
            name="name"
            placeholder="Nombre de la etiqueta"
            required
            autofocus
            disabled={busy}
          />
          <button class="v2-btn v2-btn-primary" type="submit" disabled={busy}>Crear</button>
          <button class="v2-btn" type="button" disabled={busy} onclick={() => (adding = false)}>
            Cancelar
          </button>
        </form>
      {:else}
        <button class="v2-btn v2-btn-primary" onclick={() => (adding = true)}
          ><Plus />Nueva etiqueta</button
        >
      {/if}
    {/if}
  {/snippet}
</PageHeader>

<div class="v2-pad" style="padding-top:16px;flex:none">
  <div class="v2-stats">
    <StatCard label="Activas" value={count(totals.active)} tone="ink" />
    <StatCard
      label="Sin aplicar a nada"
      value={count(totals.unused)}
      tone={totals.unused > 0 ? 'clay' : 'slate'}
      detail="Solo cuenta cuentas, prospectos, negociaciones y tickets"
    />
    <StatCard label="Apagadas" value={count(totals.count - totals.active)} tone="slate" />
  </div>
</div>

<div class="v2-scroll">
  <div class="v2-pad" style="padding-bottom:32px">
    {#each duplicateGroups as group (group.all[0].id)}
      <div class="v2-tag-banner">
        <Merge size={16} style="color:var(--v2-clay);flex:none;margin-top:1px" />
        <div>
          <div style="font-weight:600;font-size:13px">
            {group.all.map((t) => t.name).join(' y ')} parecen la misma etiqueta
          </div>
          <p class="v2-sub" style="font-size:12px;margin:4px 0 0;line-height:1.5">
            {group.all.map((t) => `${t.name} está en ${used(t)} registros`).join('; ')}. Quien
            filtre por una se pierde la otra.
          </p>
        </div>
        {#if data.can_edit}
          <!-- One control per tag being emptied, rather than one "Merge" for
               the group: the endpoint takes a pair, and a group of three needs
               a person to say which two go where. Confirmed, because unlike
               "Turn off" this cannot be undone by clicking the other button.
               The source is archived so its name survives, but nothing records
               which records came from where. -->
          <div style="flex:none;align-self:center;display:flex;gap:6px">
            {#each group.merge as loser (loser.id)}
              <ConfirmAction
                action="?/merge"
                label={group.merge.length > 1 ? `Combinar ${loser.name}` : 'Combinar'}
                confirmLabel="Combinar"
                explain={`${used(loser)} ${used(loser) === 1 ? 'registro se mueve' : 'registros se mueven'} de ${loser.name} a ${group.keep.name}, y ${loser.name} se apaga. Los registros que ya están en ${group.keep.name} quedan intactos. Esto no se puede deshacer combinando al revés.`}
                hidden={{ id: loser.id, into: group.keep.id }}
              />
            {/each}
          </div>
        {/if}
      </div>
    {/each}

    {#if form?.merge?.error}
      <p class="v2-error" style="margin-bottom:12px">{form.merge.error}</p>
    {/if}
    {#if form?.merged}
      <p class="v2-sub" style="margin-bottom:12px">
        Combinada en {form.merged.name}. Se {form.merged.moved === 1 ? 'movió' : 'movieron'}
        {count(form.merged.moved)}
        {form.merged.moved === 1 ? 'registro' : 'registros'}.
      </p>
    {/if}

    {#if form?.archive?.error}
      <p class="v2-error" style="margin-bottom:12px">{form.archive.error}</p>
    {/if}
    {#if form?.restore?.error}
      <p class="v2-error" style="margin-bottom:12px">{form.restore.error}</p>
    {/if}

    <div class="v2-label" style="margin-bottom:10px">Todas las etiquetas</div>
    <div class="v2-table-wrap">
      <table class="v2-table">
        <thead>
          <tr>
            <th>Etiqueta</th>
            <th style="text-align:right">Cuentas</th>
            <th style="text-align:right">Contactos</th>
            <th style="text-align:right">Prospectos</th>
            <th style="text-align:right">Negociaciones</th>
            <th style="text-align:right">Tickets</th>
            <th style="text-align:right">Tareas</th>
            <th style="text-align:right">Total</th>
            <th></th>
            {#if data.can_edit}<th></th>{/if}
          </tr>
        </thead>
        <tbody>
          {#each tags as t (t.id)}
            <tr style="opacity:{t.is_active ? 1 : 0.62}">
              <td class="v2-table-primary">
                {t.name}
                <!-- The stored colour, named rather than painted. The model
                     offers eighteen named hues; v2's palette has six tones and
                     renders every tag in them, so a swatch here would be the
                     only place in the product those eighteen exist. -->
                <span class="v2-sub" style="font-size:11px;margin-left:7px">{t.color}</span>
              </td>
              <td class="v2-num" style="text-align:right">{t.usage.accounts || '—'}</td>
              <td class="v2-num" style="text-align:right">{t.usage.contacts || '—'}</td>
              <td class="v2-num" style="text-align:right">{t.usage.leads || '—'}</td>
              <td class="v2-num" style="text-align:right">{t.usage.opportunities || '—'}</td>
              <td class="v2-num" style="text-align:right">{t.usage.cases || '—'}</td>
              <td class="v2-num" style="text-align:right">{t.usage.tasks || '—'}</td>
              <td class="v2-num" style="text-align:right;font-weight:600">{used(t) || '—'}</td>
              <td style="text-align:right">
                {#if !t.is_active}
                  <Pill tone="slate">Apagada</Pill>
                {:else if used(t) === 0}
                  <Pill tone="clay">Sin usar</Pill>
                {/if}
              </td>
              {#if data.can_edit}
                <td style="text-align:right">
                  {#if t.is_active}
                    <!-- `TagsDetailView.delete` soft-archives: it flips
                         `is_active` to false and leaves the row (and every
                         record's link to it) in place. "Turn off", not
                         "Delete", says what actually happens, and the count
                         below is the real number already computed by `used`,
                         not a vague warning. -->
                    <ConfirmAction
                      action="?/archive"
                      label="Apagar"
                      confirmLabel="Apagar"
                      explain={used(t) > 0
                        ? `${used(t)} ${used(t) === 1 ? 'registro mantiene' : 'registros mantienen'} esta etiqueta. Apagarla deja de ofrecerla en registros nuevos, y la mantiene en los que ya la tienen. Se puede volver a encender.`
                        : 'Nada tiene esta etiqueta. Apagarla deja de ofrecerla en registros nuevos. Se puede volver a encender.'}
                      hidden={{ id: t.id }}
                    />
                  {:else}
                    <!-- Turning a tag back on restores nothing that was
                         destroyed, so unlike "Turn off" this doesn't need the
                         two-click confirm. -->
                    <form method="POST" action="?/restore" use:enhance>
                      <input type="hidden" name="id" value={t.id} />
                      <button class="v2-btn v2-btn-sm" type="submit">Volver a encender</button>
                    </form>
                  {/if}
                </td>
              {/if}
            </tr>
          {:else}
            <tr>
              <td colspan={data.can_edit ? 8 : 7}>
                <EmptyState
                  title="Todavía no hay etiquetas"
                  body="Las etiquetas se comparten entre todos los tipos de registro, así que vale la pena nombrar bien la primera."
                >
                  {#snippet icon()}<TagsIcon size={21} />{/snippet}
                </EmptyState>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>

    <p class="v2-sub" style="font-size:11.5px;margin-top:14px;max-width:64ch">
      Apagar una etiqueta la oculta de los selectores y la deja en los registros que ya la tienen.
      No se elimina nada, y se puede volver a encender en cualquier momento.
    </p>
  </div>
</div>

<style>
  .v2-tag-banner {
    display: flex;
    gap: 11px;
    align-items: flex-start;
    padding: 14px 16px;
    margin-bottom: 16px;
    border: 1px solid var(--v2-line);
    border-radius: var(--v2-radius);
    background: var(--v2-card);
  }

  /* The inline "New tag" disclosure lives in the page header's actions row
     (a flex container), alongside the plain Create/Cancel buttons, so it has
     to lay out as a single line rather than stack like a full-page form. */
  .v2-tag-add-form {
    display: flex;
    align-items: center;
    gap: 7px;
    position: relative;
  }
  .v2-tag-add-form .v2-input {
    width: 200px;
  }
  /* The error sits above the input per the leads/new convention, but there is
     no room to grow the header's height for it, so it floats instead of
     pushing the row down. `right: 0` plus `white-space: normal` (rather than
     the `nowrap` a one-line floating label would default to) let it wrap
     within the row's own width instead of running off narrow viewports; a
     duplicate-name rejection ("A tag with this name already exists.") is
     long enough to hit this in practice. */
  .v2-tag-add-form .v2-error {
    position: absolute;
    bottom: 100%;
    left: 0;
    right: 0;
    margin: 0 0 4px;
    white-space: normal;
  }
  /* Below 768px `.v2-header .v2-actions` goes full width (v2.css), but this
     form's own children do not: a 200px input plus two buttons is wider than
     a phone screen, and a flex item does not shrink past its content's fixed
     width on its own. Confirmed by emulating a 320px viewport: the row
     overflowed and clipped "Cancel" before this rule existed. Wrapping the
     input onto its own full-width line, with the buttons below it, keeps
     everything on screen and touchable instead of cut off. */
  @media (max-width: 768px) {
    .v2-tag-add-form {
      flex-wrap: wrap;
      width: 100%;
    }
    .v2-tag-add-form .v2-input {
      width: 100%;
      flex: 1 1 100%;
    }
  }
</style>
