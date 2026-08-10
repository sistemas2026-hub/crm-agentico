<script>
  /**
   * Billing schedules. Each row answers one question: when does this next
   * generate an invoice, and does anyone have to do anything when it does.
   *
   * `auto_send` is the field that decides that, and v1 buried it inside an
   * edit form. A schedule with auto_send off generates a draft and stops, so
   * unless somebody remembers, the customer never gets billed. The failure is
   * silent and looks exactly like success. It is a column here.
   */
  import { page } from '$app/state';
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import SectionTabs from '$lib/v2/components/SectionTabs.svelte';
  import StatCard from '$lib/v2/components/StatCard.svelte';
  import FilterBar from '$lib/v2/components/FilterBar.svelte';
  import Pill from '$lib/v2/components/Pill.svelte';
  import EmptyState from '$lib/v2/components/EmptyState.svelte';
  import { enhance } from '$app/forms';
  import { money, count, shortDate, daysSince } from '$lib/v2/format.js';
  import { RECURRING_FREQUENCY_LABEL, PAYMENT_TERMS_LABEL } from '$lib/v2/enums.js';
  import { Plus, RefreshCw, Hand, Pause, Play } from '@lucide/svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  let totals = $derived(data.totals);

  const frequency = (s) =>
    s.frequency === 'CUSTOM'
      ? `Cada ${s.custom_days} días`
      : RECURRING_FREQUENCY_LABEL[s.frequency];

  /** Next run, or why there isn't one. A paused schedule has no next run. */
  function nextRun(s) {
    if (!s.is_active) return { text: 'Pausada', tone: 'muted' };
    const n = daysSince(s.next_generation_date);
    if (n > 0) return { text: `${n}d de atraso`, tone: 'late' };
    if (n === 0) return { text: 'Hoy', tone: 'soon' };
    if (Math.abs(n) <= 7) return { text: `en ${Math.abs(n)}d`, tone: 'soon' };
    return { text: shortDate(s.next_generation_date), tone: 'normal' };
  }

  /** An end date that has nearly arrived stops the schedule without warning. */
  const endingSoon = (s) => {
    if (!s.end_date || !s.is_active) return false;
    const n = daysSince(s.end_date);
    return n <= 0 && Math.abs(n) <= 14;
  };
</script>

<PageHeader title="Facturas recurrentes">
  {#snippet sub()}
    <span class="v2-num">{count(totals.active)}</span> activas ·
    <span class="v2-num">{money(totals.monthly_run_rate, data.org.currency)}</span> por mes
  {/snippet}
  {#snippet actions()}
    <a class="v2-btn v2-btn-primary" href="/invoices/recurring/new"><Plus />Nueva factura recurrente</a>
  {/snippet}
</PageHeader>

<SectionTabs set="invoices" />

{#if page.url.search}
  <p class="v2-sub" style="font-size:11.5px;margin:8px 0 0">
    Estos números describen la lista filtrada.
  </p>
{/if}

{#if form?.error}
  <div class="v2-pad" style="padding-top:12px;flex:none">
    <p class="rec-error" role="alert">{form.error}</p>
  </div>
{/if}

<div class="v2-pad" style="padding-top:16px;flex:none">
  <div class="v2-stats">
    <StatCard
      label="Ritmo mensual"
      value={money(totals.monthly_run_rate, data.org.currency)}
      tone="ink"
      detail="Todas las facturas recurrentes activas, normalizadas a un mes"
    />
    <StatCard label="Activas" value={count(totals.active)} tone="moss" />
    <StatCard
      label="Generan dentro de 7 días"
      value={count(totals.due_within_7d)}
      tone="clay"
      detail="Borradores para revisar antes de que se envíen"
    />
    <StatCard label="Facturas recurrentes" value={count(totals.count)} tone="slate" />
  </div>
</div>

<FilterBar page="recurring" url={page.url} meta="Activas primero, después las más próximas a generarse" />

<div class="v2-scroll">
  {#if data.schedules.length === 0}
    <EmptyState
      title="Todavía no hay ninguna factura recurrente"
      body="Una factura recurrente es una plantilla más una frecuencia. Configurá una para cualquier cosa que factures el mismo día todos los meses y dejá de volver a escribirla."
    >
      {#snippet icon()}<RefreshCw size={21} />{/snippet}
      {#snippet actions()}
        <a class="v2-btn v2-btn-primary" href="/invoices/recurring/new">Nueva factura recurrente</a>
      {/snippet}
    </EmptyState>
  {:else}
    <div class="v2-table-wrap">
      <table class="v2-table">
        <thead>
          <tr>
            <th>Factura recurrente</th>
            <th>Cuenta</th>
            <th>Cada</th>
            <th>Cuando genera</th>
            <th class="v2-r">Monto</th>
            <th class="v2-r">Próxima</th>
          </tr>
        </thead>
        <tbody>
          {#each data.schedules as s (s.id)}
            {@const next = nextRun(s)}
            <tr style={s.is_active ? '' : 'opacity:.6'}>
              <td>
                <span class="v2-table-primary">{s.title}</span>
                <span class="v2-table-secondary" style="display:block">
                  {PAYMENT_TERMS_LABEL[s.payment_terms]} ·
                  <span class="v2-num">{s.invoices_generated}</span> generadas hasta ahora
                </span>
              </td>
              <td>
                <a href="/accounts/{s.account.id}" style="color:inherit">{s.account.name}</a>
                <span class="v2-table-secondary" style="display:block">{s.contact}</span>
              </td>
              <td>{frequency(s)}</td>
              <td>
                <!-- Sends itself, or waits for a person. Two different jobs,
                     and the row says which one this is. -->
                {#if s.auto_send}
                  <Pill tone="moss" dot>Se envía automáticamente</Pill>
                {:else}
                  <span style="display:inline-flex;gap:6px;align-items:center">
                    <Hand size={13} style="color:var(--v2-clay)" />
                    <span style="font-size:12.5px">Genera borrador, espera que la envíes</span>
                  </span>
                {/if}
                {#if endingSoon(s)}
                  <span class="v2-table-secondary" style="display:block;color:var(--v2-clay)">
                    Termina {shortDate(s.end_date)}, después esa es la última factura
                  </span>
                {/if}
              </td>
              <td class="v2-r v2-num" style="font-weight:600"
                >{money(s.total_amount, s.currency)}</td
              >
              <td class="v2-r">
                <div class="rec-next">
                  <span
                    style={next.tone === 'late'
                      ? 'color:var(--v2-rust);font-weight:600'
                      : next.tone === 'soon'
                        ? 'color:var(--v2-clay);font-weight:600'
                        : next.tone === 'muted'
                          ? 'color:var(--v2-slate)'
                          : ''}
                  >
                    {next.text}
                  </span>
                  <!-- Pause a live schedule or resume a paused one. The one
                       write a schedule worklist needs, next to the state it
                       changes. The API refuses schedules that aren't yours. -->
                  <form method="POST" action="?/toggle" use:enhance>
                    <input type="hidden" name="id" value={s.id} />
                    <button class="v2-btn v2-btn-sm rec-toggle" type="submit">
                      {#if s.is_active}<Pause size={12} />Pausar{:else}<Play size={12} />Reanudar{/if}
                    </button>
                  </form>
                </div>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
    <p class="v2-sub v2-pad" style="font-size:12px;padding-bottom:24px">
      Mostrando <span class="v2-num">{data.schedules.length}</span> de
      <span class="v2-num">{count(totals.count)}</span>
    </p>
  {/if}
</div>

<style>
  .rec-error {
    margin: 0;
    padding: 8px 12px;
    border: 1px solid color-mix(in srgb, var(--v2-rust) 40%, transparent);
    border-radius: 6px;
    background: color-mix(in srgb, var(--v2-rust) 8%, transparent);
    color: var(--v2-rust);
    font-size: 13px;
  }
  /* Next-run text with its pause/resume control stacked beneath, right-aligned. */
  .rec-next {
    display: inline-flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 5px;
  }
  .rec-toggle {
    gap: 4px;
  }
</style>
