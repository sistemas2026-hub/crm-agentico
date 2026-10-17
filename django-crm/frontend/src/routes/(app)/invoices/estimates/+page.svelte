<script>
  /**
   * Estimates, sorted so the one thing worth doing is at the top.
   *
   * Accepted-and-not-converted is money the customer has already agreed to and
   * nobody has billed. v1 gave it the same green "Accepted" pill as an
   * estimate that had become an invoice weeks ago, so the two were
   * indistinguishable and the gap only surfaced at month end. Status and
   * "has it been billed" are two separate facts and get two separate columns.
   */
  import { page } from '$app/state';
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import SectionTabs from '$lib/v2/components/SectionTabs.svelte';
  import StatCard from '$lib/v2/components/StatCard.svelte';
  import FilterBar from '$lib/v2/components/FilterBar.svelte';
  import Pill from '$lib/v2/components/Pill.svelte';
  import EmptyState from '$lib/v2/components/EmptyState.svelte';
  import { enhance } from '$app/forms';
  import { money, count, daysSince } from '$lib/v2/format.js';
  import { ESTIMATE_STATUS_TONE, ESTIMATE_STATUS_LABEL } from '$lib/v2/enums.js';
  import { Plus, FileText } from '@lucide/svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  let totals = $derived(data.totals);

  /** Only an estimate that can still be accepted has a meaningful validity. */
  const LIVE = ['Sent', 'Viewed'];

  function validity(e) {
    if (!e.valid_until) return null;
    if (!LIVE.includes(e.status)) return null;
    const n = daysSince(e.valid_until);
    if (n > 0) return { text: `venció hace ${n}d`, urgent: true };
    if (n === 0) return { text: 'vence hoy', urgent: true };
    return { text: `${Math.abs(n)}d restantes`, urgent: Math.abs(n) <= 7 };
  }

  const needsBilling = (e) => e.status === 'Accepted' && !e.converted_invoice;
</script>

<PageHeader title="Cotizaciones">
  {#snippet sub()}
    <span class="v2-num">{count(totals.count)}</span> cotizaciones ·
    <span class="v2-num">{money(totals.awaiting_reply, data.org.currency)}</span> esperando respuesta
  {/snippet}
  {#snippet actions()}
    <!-- An estimate is raised from a deal, not typed from scratch here. The
         empty state has always said so. Send the button where estimates are
         born rather than to a form this page does not own. -->
    <a class="v2-btn v2-btn-primary" href="/pipeline"><Plus />Nueva cotización</a>
  {/snippet}
</PageHeader>

{#if page.url.search}
  <p class="v2-sub" style="font-size:11.5px;margin:8px 0 0">
    Estos números describen la lista filtrada.
  </p>
{/if}

<SectionTabs set="invoices" />

{#if form?.error}
  <div class="v2-pad" style="padding-top:12px;flex:none">
    <p class="est-error" role="alert">{form.error}</p>
  </div>
{/if}

<div class="v2-pad" style="padding-top:16px;flex:none">
  <div class="v2-stats">
    <StatCard
      label="Aceptadas, sin facturar"
      value={money(totals.accepted_unconverted, data.org.currency)}
      tone="clay"
      detail="Acordadas y esperando una factura"
    />
    <StatCard
      label="Esperando respuesta"
      value={money(totals.awaiting_reply, data.org.currency)}
      tone="ink"
    />
    <StatCard
      label="Vencen en 7 días"
      value={count(totals.expiring_within_7d)}
      tone={totals.expiring_within_7d ? 'clay' : 'slate'}
    />
    <StatCard label="Cotizaciones" value={count(totals.count)} tone="slate" />
  </div>
</div>

<FilterBar
  page="estimates"
  url={page.url}
  accounts={data.accounts}
  meta="Aceptadas sin facturar primero, después las enviadas más recientemente"
/>

<div class="v2-scroll">
  {#if data.estimates.length === 0}
    <EmptyState
      title="Todavía no hay cotizaciones"
      body="Una cotización es una propuesta con precio que podés convertir en factura una vez que el cliente la acepta. La mayoría arranca desde una negociación que ya tiene el monto y la cuenta."
    >
      {#snippet icon()}<FileText size={21} />{/snippet}
      {#snippet actions()}
        <a class="v2-btn v2-btn-primary" href="/pipeline">Arrancar desde una negociación</a>
      {/snippet}
    </EmptyState>
  {:else}
    <div class="v2-table-wrap">
      <table class="v2-table">
        <thead>
          <tr>
            <th>Cotización</th>
            <th>Cuenta</th>
            <th>Estado</th>
            <th>Facturada</th>
            <th class="v2-r">Monto</th>
            <th class="v2-r">Vigencia</th>
          </tr>
        </thead>
        <tbody>
          {#each data.estimates as e (e.id)}
            {@const v = validity(e)}
            <tr>
              <td>
                <span class="v2-table-primary">{e.title}</span>
                <span class="v2-table-secondary" style="display:block">
                  <span class="v2-num">{e.estimate_number}</span> · {e.contact}
                </span>
              </td>
              <td>
                <a href="/accounts/{e.account.id}" style="color:inherit">{e.account.name}</a>
                {#if e.opportunity}
                  <span class="v2-table-secondary" style="display:block">{e.opportunity.name}</span>
                {/if}
              </td>
              <td><Pill tone={ESTIMATE_STATUS_TONE[e.status]}>{ESTIMATE_STATUS_LABEL[e.status] ?? e.status}</Pill></td>
              <td>
                {#if e.converted_invoice}
                  <a href="/invoices/{e.converted_invoice.id}" class="v2-num" style="color:inherit">
                    {e.converted_invoice.invoice_number}
                  </a>
                {:else if needsBilling(e)}
                  <!-- The one place ember belongs on this page: an accepted
                       estimate is the only row with an action nobody has taken.
                       Convert copies it to a Draft invoice and opens that. -->
                  <form method="POST" action="?/convert" use:enhance>
                    <input type="hidden" name="id" value={e.id} />
                    <button class="v2-btn v2-btn-sm v2-btn-primary" type="submit">
                      Generar factura
                    </button>
                  </form>
                {:else}
                  <span class="v2-muted">—</span>
                {/if}
              </td>
              <td class="v2-r v2-num" style="font-weight:600"
                >{money(e.total_amount, e.currency)}</td
              >
              <td class="v2-r" style={v?.urgent ? 'color:var(--v2-rust);font-weight:600' : ''}>
                {#if v}
                  {v.text}
                {:else}
                  <span class="v2-muted">—</span>
                {/if}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
    <p class="v2-sub v2-pad" style="font-size:12px;padding-bottom:24px">
      Mostrando <span class="v2-num">{data.estimates.length}</span> de
      <span class="v2-num">{count(totals.count)}</span>
    </p>
  {/if}
</div>

<style>
  .est-error {
    margin: 0;
    padding: 8px 12px;
    border: 1px solid color-mix(in srgb, var(--v2-rust) 40%, transparent);
    border-radius: 6px;
    background: color-mix(in srgb, var(--v2-rust) 8%, transparent);
    color: var(--v2-rust);
    font-size: 13px;
  }
</style>
