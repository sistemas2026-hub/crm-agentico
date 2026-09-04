<script>
  import { page } from '$app/state';
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import FilterBar from '$lib/v2/components/FilterBar.svelte';
  import Pill from '$lib/v2/components/Pill.svelte';
  import Avatar from '$lib/v2/components/Avatar.svelte';
  import StageMeter from '$lib/v2/components/StageMeter.svelte';
  import EmptyState from '$lib/v2/components/EmptyState.svelte';
  import { money, count, shortDate } from '$lib/v2/format.js';
  import { STAGE_LABEL, AGING_TONE, AGING_LABEL } from '$lib/v2/enums.js';
  import { activeChips, activePresetKey, withoutParam } from '$lib/v2/filters.js';
  import { Columns3, List, Plus } from '@lucide/svelte';

  /** @type {{ data: any }} */
  let { data } = $props();

  let deals = $derived(data.deals);
  let totals = $derived(data.totals);
  let view = $derived(data.view);

  /* Lanes are built server-side from `/opportunities/kanban/`, which returns
     every stage with its true count. They used to be grouped on the client
     from whatever the list happened to return: correct only until the first
     page boundary, and wrong in the way that looks right: all the columns
     render, each is just short. */
  let lanes = $derived(data.lanes);

  /**
   * Whether the current view is actually narrowed, as opposed to merely
   * carrying a query string. `page.url.search` alone is the wrong test: on
   * this page `?view=board` is a layout toggle, not a filter, so a bare
   * "Board" click from the unfiltered list would otherwise claim these
   * numbers are filtered when nothing was. `'all'` is pipeline's own
   * empty-params preset (see `$lib/v2/filters.js`), its declared default, so
   * being on any other preset counts as filtered even when that preset
   * (`open`, `stalled`) sets no field a chip would represent.
   */
  let isFiltered = $derived(
    activeChips('pipeline', page.url, { people: data.people, tags: data.tags }).length > 0 ||
      activePresetKey('pipeline', page.url, data.meId) !== 'all'
  );

  /**
   * The List<->Board toggle used to be two static hrefs, `/pipeline` and
   * `/pipeline?view=board`, so switching layout silently dropped every active
   * filter. Board to List keeps every param and drops only `view`: the list
   * can run everything the board could and more. List to Board keeps
   * `view=board` plus only the params the board can actually honour
   * (`data.boardFields`, always returned by `load` regardless of the current
   * view, see the note in `+page.server.js`); the rest are deliberately
   * dropped, and it is visible rather than silent, since the chips for them
   * disappear along with the params.
   */
  let listHref = $derived(withoutParam(page.url, 'view'));
  let boardHref = $derived.by(() => {
    const next = new URLSearchParams();
    next.set('view', 'board');
    // `search` mirrors what `+page.server.js` forwards to the board itself
    // (`kanban_views.py:123` reads it); it is not one of `boardFields`
    // because it is not a descriptor field, just like on the list view.
    for (const key of [...(data.boardFields ?? []), 'search']) {
      const value = page.url.searchParams.get(key);
      if (value) next.set(key, value);
    }
    return `/pipeline?${next}`;
  });
</script>

<PageHeader title="Negociaciones">
  {#snippet sub()}
    <!-- Totals come from the API aggregate, never from the rows on screen.
         Not "open deals": the default view is now the pipeline's own "All
         deals" preset (empty params), which includes closed stages, so a word
         that was only ever true under the old hardcoded ?open=true would lie
         here as soon as somebody switched presets. -->
    <span class="v2-num">{count(totals.count)}</span> negociaciones ·
    <span class="v2-num">{money(totals.amount_sum, data.org.currency)}</span> ·
    <span class="v2-num">{money(totals.weighted_sum, data.org.currency)}</span> ponderado ·
    <span class="v2-num" style="color:var(--v2-rust)">{totals.stalled_count}</span> estancadas
  {/snippet}
  {#snippet actions()}
    {#if view === 'board'}
      <a class="v2-btn v2-btn-quiet" href={listHref}><List />Lista</a>
      <span class="v2-btn" aria-current="true"><Columns3 />Tablero</span>
    {:else}
      <span class="v2-btn" aria-current="true"><List />Lista</span>
      <a class="v2-btn v2-btn-quiet" href={boardHref}><Columns3 />Tablero</a>
    {/if}
    <a class="v2-btn v2-btn-primary" href="/pipeline/new"><Plus />Nueva negociación</a>
  {/snippet}
</PageHeader>

{#if isFiltered}
  <p class="v2-sub" style="font-size:11.5px;margin:8px 0 0">
    Estos números describen el pipeline filtrado.
  </p>
{/if}

<!-- The board meta used to read "Drag a card to move a stage". There is a real
     move endpoint, but nothing here is draggable, and an interface that names
     a gesture it does not support is the specific habit this redesign exists
     to break. It says where the stage is actually changed instead. -->
<FilterBar
  page="pipeline"
  url={page.url}
  people={data.people}
  tags={data.tags}
  meId={data.meId}
  onlyFields={data.onlyFields}
  onlyPresets={data.onlyPresets}
  meta={view === 'board'
    ? 'Solo etapas abiertas. Abrí una negociación para cambiar su etapa'
    : 'Ordenado por valor'}
/>

{#if view === 'board'}
  <div class="v2-board">
    {#each lanes as lane (lane.stage)}
      <section class="v2-lane">
        <div class="v2-lane-head">
          <span class="v2-label">{STAGE_LABEL[lane.stage]}</span>
          <span class="v2-num">{count(lane.count)} · {money(lane.sum, data.org.currency)}</span>
        </div>
        <div class="v2-lane-body">
          {#if lane.truncated}
            <!-- The API caps a column at 100 cards. Saying so beats a lane
                 that silently stops. The header count would not match the
                 cards under it and there would be nothing to explain why. -->
            <p class="v2-sub" style="padding:6px 2px;font-size:11.5px">
              Mostrando las primeras <span class="v2-num">{lane.rows.length}</span>. Filtrá para ver
              el resto.
            </p>
          {/if}
          {#each lane.rows as d (d.id)}
            <a class="v2-deal-card" href="/pipeline/{d.id}">
              <div style="font-weight:600;letter-spacing:-0.012em;line-height:1.3">{d.name}</div>
              <div class="v2-sub" style="margin-top:2px">{d.account.name}</div>
              <div style="margin-top:9px">
                <Pill tone={AGING_TONE[d.aging_status]} dot>
                  {AGING_LABEL[d.aging_status] +
                    (d.aging_status === 'green' ? '' : ` · ${d.days_in_current_stage}d`)}
                </Pill>
              </div>
              <div class="v2-deal-card-foot">
                <Avatar name={d.assigned_to} size={21} />
                <span class="v2-num" style="font-weight:600">{money(d.amount, d.currency)}</span>
                <span class="v2-sub" style="margin-left:auto;font-size:11.5px"
                  >{shortDate(d.closed_on)}</span
                >
              </div>
            </a>
          {:else}
            <p class="v2-sub" style="padding:10px 2px;font-size:12px">Nada en esta etapa.</p>
          {/each}
        </div>
      </section>
    {/each}
  </div>
{:else if deals.length === 0}
  <div class="v2-scroll">
    <EmptyState
      title="No hay negociaciones acá"
      body="Nada coincide con esta vista. Iniciá una negociación desde una cuenta con la que ya estás hablando, convertí un prospecto que esté listo, o limpiá un filtro para ver más."
    >
      {#snippet icon()}<Columns3 size={21} />{/snippet}
      {#snippet actions()}
        <a class="v2-btn v2-btn-primary" href="/pipeline/new">Nueva negociación</a>
        <a class="v2-btn" href="/leads">Ir a prospectos</a>
      {/snippet}
    </EmptyState>
  </div>
{:else}
  <div class="v2-scroll">
    <div class="v2-table-wrap">
      <table class="v2-table">
        <thead>
          <tr>
            <th>Negociación</th>
            <th>Etapa</th>
            <th>Salud</th>
            <th class="v2-r">Valor</th>
            <th>Cierre</th>
            <th class="v2-r">En la etapa</th>
            <th>Responsable</th>
          </tr>
        </thead>
        <tbody>
          {#each deals as d (d.id)}
            <tr>
              <td>
                <a class="v2-row-link" href="/pipeline/{d.id}">
                  <div class="v2-table-primary">{d.name}</div>
                  <div class="v2-table-secondary">{d.account.name}</div>
                </a>
              </td>
              <td><StageMeter stage={d.stage} /></td>
              <td data-m="tag">
                <Pill tone={AGING_TONE[d.aging_status]} dot>{AGING_LABEL[d.aging_status]}</Pill>
              </td>
              <td class="v2-r v2-num" style="font-weight:600">{money(d.amount, d.currency)}</td>
              <td>{shortDate(d.closed_on)}</td>
              <!-- Hidden on a phone: the Health pill beside the title is computed
                   from this same number, so showing both spends a line to say
                   the same thing twice. -->
              <td
                class="v2-r v2-num"
                data-m="hide"
                style={d.aging_status === 'red'
                  ? 'color:var(--v2-rust);font-weight:600'
                  : 'color:var(--v2-slate)'}
              >
                {d.days_in_current_stage}d
              </td>
              <td data-m="hide"><Avatar name={d.assigned_to} size={22} /></td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
    <p class="v2-sub v2-pad" style="font-size:12px;padding-bottom:24px">
      Mostrando <span class="v2-num">{deals.length}</span> de
      <span class="v2-num">{count(totals.count)}</span>
    </p>
  </div>
{/if}
