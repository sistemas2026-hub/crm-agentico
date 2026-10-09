<script>
  /**
   * Where the money is.
   *
   * The one decision that shapes this page: **"not yet due" is not aging.**
   * The API returns it in the same aging response, and v1 draws it as the
   * first bucket, where it is by far the biggest bar, so the chart reads as
   * mostly healthy while $80,150 is genuinely late. Here the not-yet-due
   * figure is stated once, as context, and the aging chart contains only money
   * that is actually overdue.
   *
   * No chart library. Two bar shapes and a table do everything this page
   * needs, and shipping a charting dependency to draw sixteen rectangles costs
   * more than it explains.
   *
   * Every figure is server-computed over the whole window, nothing here is
   * summed from a page of invoices.
   */
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import SectionTabs from '$lib/v2/components/SectionTabs.svelte';
  import StatCard from '$lib/v2/components/StatCard.svelte';
  import { money, count } from '$lib/v2/format.js';

  /** @type {{ data: any }} */
  let { data } = $props();

  let canView = $derived(data.can_view);
  let d = $derived(data.dashboard);
  let aging = $derived(data.aging);

  let peak = $derived(Math.max(...data.revenue.flatMap((r) => [r.invoiced, r.paid])));
  let agingPeak = $derived(Math.max(...aging.buckets.map((b) => b.amount)));

  /** "2026-07" → "Jul". The year only appears where it changes. */
  const MONTH = [
    'Ene',
    'Feb',
    'Mar',
    'Abr',
    'May',
    'Jun',
    'Jul',
    'Ago',
    'Sep',
    'Oct',
    'Nov',
    'Dic'
  ];
  const monthLabel = (period) => MONTH[Number(period.slice(5, 7)) - 1];

  let collected = $derived(Math.round((d.total_paid / d.total_invoiced) * 100));
</script>

<PageHeader title="Facturas">
  {#snippet sub()}
    {#if canView}
      Últimos <span class="v2-num">{d.window_months}</span> meses ·
      <span class="v2-num">{count(d.invoice_count)}</span> facturas
    {:else}
      Reportes financieros
    {/if}
  {/snippet}
</PageHeader>

<SectionTabs set="invoices" />

{#if !canView}
  <div class="v2-pad" style="padding-top:40px">
    <div class="v2-card rep-locked">
      <strong>Estos reportes son para administradores.</strong>
      <p>
        Los totales facturados y cobrados, los ingresos por mes y la antigüedad de cuentas por
        cobrar cubren el dinero de toda la organización, así que están limitados a administradores.
        Tus propias facturas y cotizaciones están en las pestañas <a href="/invoices">Facturas</a> y
        <a href="/invoices/estimates">Cotizaciones</a>.
      </p>
    </div>
  </div>
{:else}
  <div class="v2-pad" style="padding-top:16px;flex:none">
    <div class="v2-stats">
      <StatCard label="Facturado" value={money(d.total_invoiced, data.org.currency)} tone="ink" />
      <StatCard
        label="Cobrado"
        value={money(d.total_paid, data.org.currency)}
        tone="moss"
        detail="{collected}% de lo facturado"
      />
      <StatCard
        label="Vencido"
        value={money(d.overdue_amount, data.org.currency)}
        tone={d.overdue_amount > 0 ? 'rust' : 'slate'}
        detail="{count(aging.overdue_count)} facturas pasaron su vencimiento"
      />
      <StatCard
        label="Tiempo promedio de cobro"
        value={`${d.average_days_to_pay}d`}
        tone="slate"
        detail="Desde la emisión hasta el pago"
      />
    </div>
  </div>

  <div class="v2-scroll">
    <div class="v2-pad" style="padding-bottom:32px">
      <div class="v2-split-wide">
        <div>
          <div class="v2-label" style="margin-bottom:12px">Facturado y cobrado, por mes</div>
          <div class="v2-card" style="padding:16px 18px 14px">
            <!-- Side by side, never stacked: a stacked column's height would
               read as invoiced + paid, which is not a quantity anyone has. -->
            <div class="v2-cols">
              {#each data.revenue as r (r.period)}
                <div
                  class="v2-col"
                  title="{monthLabel(r.period)}: {money(
                    r.invoiced,
                    data.org.currency
                  )} facturado, {money(r.paid, data.org.currency)} cobrado"
                >
                  <i class="in" style="height:{(r.invoiced / peak) * 100}%"></i>
                  <i class="out" style="height:{(r.paid / peak) * 100}%"></i>
                </div>
              {/each}
            </div>
            <div class="v2-cols-axis">
              {#each data.revenue as r (r.period)}
                <span>{monthLabel(r.period)}</span>
              {/each}
            </div>

            <div class="v2-sub" style="font-size:11.5px;margin-top:12px">
              <i class="v2-swatch v2-swatch-in"></i>facturado
              <i class="v2-swatch" style="margin-left:10px"></i>cobrado
            </div>

            <!-- Said once, here, rather than left to be misread every month. -->
            <p class="v2-sub" style="font-size:11.5px;margin:11px 0 0;line-height:1.5">
              Cada uno se cuenta en el mes en que ocurrió, así que no coinciden: la brecha en el mes
              más reciente es facturas anteriores que todavía se están cobrando, no una caída en las
              ventas.
            </p>
          </div>
        </div>

        <div>
          <div class="v2-label" style="margin-bottom:12px">Qué tan atrasado está el dinero vencido</div>
          <div class="v2-card" style="padding:16px 18px">
            <div style="display:flex;flex-direction:column;gap:13px">
              {#each aging.buckets as b (b.key)}
                <div>
                  <div style="display:flex;align-items:baseline;gap:8px;margin-bottom:5px">
                    <span style="font-size:12.5px">{b.label}</span>
                    <span class="v2-sub" style="font-size:11px">
                      <span class="v2-num">{count(b.count)}</span>
                      {b.count === 1 ? 'factura' : 'facturas'}
                    </span>
                    <span class="v2-num" style="margin-left:auto;font-size:13px;font-weight:600">
                      {money(b.amount, data.org.currency)}
                    </span>
                  </div>
                  <div class="v2-bar">
                    <i
                      style="width:{(b.amount / agingPeak) * 100}%;{b.key === '90_plus'
                        ? 'background:var(--v2-rust)'
                        : ''}"
                    ></i>
                  </div>
                </div>
              {/each}
            </div>

            <!--
            Not-yet-due money stated as context, deliberately outside the
            chart. In the API response it is just another bucket, and drawn as
            one it dwarfs the rest and makes late money look small.
          -->
            <div class="v2-aging-note">
              <span class="v2-sub">Todavía no vence</span>
              <span class="v2-num" style="font-size:13px"
                >{money(aging.not_yet_due.amount, data.org.currency)}</span
              >
              <span class="v2-sub" style="font-size:11px">
                en {count(aging.not_yet_due.count)} facturas, no está atrasado, no se muestra arriba
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- Full width, below the split. The chart and the aging bars are close
         enough in height to sit side by side; adding the table to either
         column left the other one blank for a third of the page. -->
      <div>
        <div class="v2-label" style="margin:22px 0 10px">Quién debe</div>
        <div class="v2-table-wrap">
          <table class="v2-table">
            <thead>
              <tr>
                <th>Cuenta</th>
                <th style="text-align:right">Facturas</th>
                <th style="text-align:right">Más antigua</th>
                <th style="text-align:right">Vencido</th>
              </tr>
            </thead>
            <tbody>
              {#each data.overdueByAccount as a (a.id)}
                <tr>
                  <td class="v2-table-primary">
                    <a href="/accounts/{a.id}" style="color:inherit;text-decoration:none">
                      {a.name}
                    </a>
                  </td>
                  <td class="v2-num" style="text-align:right">{a.count}</td>
                  <td
                    class="v2-num"
                    style="text-align:right;{a.oldest_days > 90 ? 'color:var(--v2-rust)' : ''}"
                  >
                    {a.oldest_days}d
                  </td>
                  <td class="v2-num" style="text-align:right;font-weight:600"
                    >{money(a.amount, data.org.currency)}</td
                  >
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
        <p class="v2-sub" style="font-size:11.5px;margin-top:10px">
          Estas {data.overdueByAccount.length} cuentas son todo el saldo vencido, no las primeras de
          una lista más larga.
        </p>
      </div>
    </div>
  </div>
{/if}

<style>
  .rep-locked {
    max-width: 560px;
    /* Centre it: this card is the whole page for a non-admin, so left-hugging
       it strands the rest of a wide screen. Matches the tickets/analytics gate. */
    margin-inline: auto;
    padding: 20px 22px;
  }
  .rep-locked p {
    margin: 8px 0 0;
    font-size: 13px;
    line-height: 1.55;
    color: var(--v2-slate);
  }
  .rep-locked a {
    color: var(--v2-ink);
  }
  .v2-aging-note {
    display: flex;
    align-items: baseline;
    gap: 8px;
    flex-wrap: wrap;
    margin-top: 16px;
    padding-top: 13px;
    border-top: 1px solid var(--v2-line-soft);
    font-size: 12.5px;
  }
</style>
