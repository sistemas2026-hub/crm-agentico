<script>
  /**
   * The account is a workspace, not a form.
   *
   * v1 rendered an account as ~28 stacked label/value rows, so answering
   * "what is going on with Northwind?" meant visiting four other pages. Here
   * the deals, people, tickets and invoices are on the page, and the next
   * action names the problem that spans them.
   *
   * All four panels come from the single detail response, the API already
   * returned them, so this costs no extra round trips.
   */
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import NextAction from '$lib/v2/components/NextAction.svelte';
  import StatCard from '$lib/v2/components/StatCard.svelte';
  import Pill from '$lib/v2/components/Pill.svelte';
  import Avatar from '$lib/v2/components/Avatar.svelte';
  import { money, shortDate, longDate } from '$lib/v2/format.js';
  import {
    STAGE_LABEL,
    PRIORITY_TONE,
    INVOICE_STATUS_TONE,
    invoiceStatusLabel
  } from '$lib/v2/enums.js';
  import { ChevronRight, Mail, Phone } from '@lucide/svelte';

  /** @type {{ data: any }} */
  let { data } = $props();

  let { account, deals, contacts, tickets, invoices, owners } = $derived(data);

  let openDeals = $derived(deals.filter((/** @type {any} */ d) => !d.stage.startsWith('CLOSED_')));
  let stalled = $derived(openDeals.filter((/** @type {any} */ d) => d.aging_status === 'red'));
  // `past_due` is decided by the same rule as the header figure. See
  // `isPastDue` in the data layer. The invoice's own `is_overdue` flag counts
  // drafts, and a rail that disagrees with its header discredits both.
  let pastDue = $derived(invoices.filter((/** @type {any} */ i) => i.past_due));

  /** One sentence that connects problems across objects. Every clause is a
      fact on this page: a stalled deal, or an invoice past its due date. */
  let headline = $derived(
    stalled.length && pastDue.length
      ? `${stalled[0].name} está estancada y ${pastDue[0].invoice_number} está vencida, misma cuenta, dos problemas.`
      : stalled.length
        ? `${stalled[0].name} no se mueve hace ${stalled[0].days_in_current_stage} días.`
        : pastDue.length
          ? `${pastDue[0].invoice_number} está vencida, ${money(pastDue[0].amount_due, pastDue[0].currency)}.`
          : null
  );
</script>

<PageHeader title={account.name} record>
  {#snippet crumb()}
    <a href="/accounts">Cuentas</a>
    <ChevronRight size={12} />
    <span>{account.industry || 'Sin rubro'}</span>
  {/snippet}
  {#snippet sub()}
    {[
      account.industry,
      account.number_of_employees ? `${account.number_of_employees} empleados` : null,
      /* Derived: the close date of the first deal won here. There is no
         contract model, so this is what "customer since" can honestly mean. */
      account.first_won_on
        ? `cliente desde ${longDate(account.first_won_on)}`
        : 'Todavía sin negociaciones ganadas',
      owners.length ? `a cargo de ${owners[0]}` : null
    ]
      .filter(Boolean)
      .join(' · ')}
  {/snippet}
  {#snippet actions()}
    <a class="v2-btn" href="/accounts/{account.id}/edit">Editar</a>
  {/snippet}
</PageHeader>

<div class="v2-scroll">
  <div class="v2-pad" style="padding-bottom:32px">
    <div class="v2-stats" style="margin-bottom:16px">
      <StatCard
        label="Ingresos ganados"
        value={account.won_amount ? money(account.won_amount, data.org.currency) : '—'}
        tone={account.won_amount ? 'moss' : 'slate'}
        detail={account.won_count
          ? `${account.won_count} negociación${account.won_count === 1 ? '' : 'es'} ganada${account.won_count === 1 ? '' : 's'}`
          : 'Todavía nada ganado'}
      />
      <StatCard
        label="Pipeline abierto"
        value={account.open_pipeline ? money(account.open_pipeline, data.org.currency) : '—'}
        detail={account.open_deal_count
          ? `${account.open_deal_count} negociación${account.open_deal_count === 1 ? '' : 'es'} abierta${account.open_deal_count === 1 ? '' : 's'}`
          : 'Sin negociaciones abiertas'}
      />
      <StatCard
        label="Vencido"
        value={account.overdue_amount ? money(account.overdue_amount, data.org.currency) : '—'}
        tone={account.overdue_amount ? 'rust' : 'slate'}
        detail={pastDue.length
          ? pastDue.map((/** @type {any} */ i) => i.invoice_number).join(', ')
          : 'Nada vencido'}
      />
      <StatCard
        label="Tickets abiertos"
        value={String(account.open_tickets ?? 0)}
        tone={tickets.some((/** @type {any} */ t) => t.priority === 'Urgent') ? 'rust' : 'slate'}
        detail={tickets.length ? `${tickets[0].name} · ${tickets[0].priority}` : 'Ninguno abierto'}
      />
    </div>

    {#if headline}
      <div style="margin-bottom:16px">
        <!--
          The invoice half of this had an `href` it should not have had: it
          pointed at `/invoices/<uuid>` while invoices is still fixtures
          keyed by slugs, so the one button on the page labelled "the thing
          that needs you" answered 404. Found by following the page's own
          outbound links rather than by reading it.

          Without an `href` the action stays a button that does nothing, which
          is the same wrong answer more quietly, so when the target is not
          wired the action is dropped entirely and the sentence stands on its
          own. It comes back when invoices is.
        -->
        <NextAction
          label="Te necesita"
          text={headline}
          action={stalled.length ? 'Abrir la negociación' : null}
          href={stalled.length ? `/pipeline/${stalled[0].id}` : null}
          tone="rust"
        />
      </div>
    {/if}

    <!-- align-items:start so each card is its own height. Stretched to match
         its neighbour, a one-row panel ends in a tall blank area that reads as
         content that failed to load. -->
    <div
      style="display:grid;grid-template-columns:1fr 1fr;gap:14px;align-items:start"
      class="v2-account-grid"
    >
      <!-- Deals -->
      <section class="v2-card" style="overflow:hidden">
        <div class="v2-card-head">
          <span class="v2-label">Negociaciones</span>
          <a href="/pipeline">Ver todas</a>
        </div>
        {#each deals as d (d.id)}
          <a
            href="/pipeline/{d.id}"
            style="display:flex;gap:12px;align-items:center;padding:11px 15px;border-bottom:1px solid var(--v2-line-soft);color:inherit;text-decoration:none"
          >
            <div style="flex:1;min-width:0">
              <div style="font-weight:550;font-size:13px">{d.name}</div>
              <!-- `closed_on` is labelled "Expected Close Date" on the model
                   and means two different things depending on the stage. Bare,
                   it reads as though an open deal already closed. -->
              <div class="v2-sub" style="font-size:11.5px">
                {STAGE_LABEL[d.stage]}{d.closed_on
                  ? d.stage.startsWith('CLOSED_')
                    ? ` · cerrada ${shortDate(d.closed_on)}`
                    : ` · vence ${shortDate(d.closed_on)}`
                  : ''}
              </div>
            </div>
            {#if d.aging_status === 'red' && !d.stage.startsWith('CLOSED_')}
              <Pill tone="rust">{d.days_in_current_stage}d</Pill>
            {/if}
            <span class="v2-num" style="font-weight:600;font-size:13px"
              >{money(d.amount, d.currency)}</span
            >
          </a>
        {:else}
          <p class="v2-sub" style="padding:14px 15px;font-size:12.5px">
            Todavía sin negociaciones. Creá una cuando haya algo real para vender.
          </p>
        {/each}
      </section>

      <!-- People -->
      <section class="v2-card" style="overflow:hidden">
        <div class="v2-card-head">
          <span class="v2-label">Personas</span>
          <a href="/contacts">Ver todas</a>
        </div>
        {#each contacts as c (c.id)}
          <div
            style="display:flex;gap:11px;align-items:center;padding:10px 15px;border-bottom:1px solid var(--v2-line-soft)"
          >
            <Avatar name="{c.first_name} {c.last_name}" size={29} />
            <!-- A link now. This was deliberately dead text while
                 `/contacts/<uuid>` answered 404, which is the reason
                 contacts was the module to wire next. -->
            <a
              href="/contacts/{c.id}"
              style="flex:1;min-width:0;color:inherit;text-decoration:none"
            >
              <div style="font-weight:550;font-size:13px">{c.first_name} {c.last_name}</div>
              <!-- title and department. The mock showed a "relationship"
                   (Champion / Blocker); Contact has no such field. -->
              <div class="v2-sub" style="font-size:11.5px">
                {[c.title, c.department].filter(Boolean).join(' · ') || 'Sin cargo registrado'}
              </div>
            </a>
            {#if c.email}
              <a class="v2-btn v2-btn-sm" href="mailto:{c.email}" aria-label="Enviar correo a {c.first_name}">
                <Mail size={13} />
              </a>
            {/if}
            {#if c.phone && !c.do_not_call}
              <a class="v2-btn v2-btn-sm" href="tel:{c.phone}" aria-label="Llamar a {c.first_name}">
                <Phone size={13} />
              </a>
            {/if}
          </div>
        {:else}
          <p class="v2-sub" style="padding:14px 15px;font-size:12.5px">
            Todavía no hay nadie acá. <a href="/contacts/new?account={account.id}">Agregá a la persona</a> con
            la que realmente hablás.
          </p>
        {/each}
      </section>

      <!-- Tickets -->
      <section class="v2-card" style="overflow:hidden">
        <div class="v2-card-head">
          <span class="v2-label">Tickets</span>
          <a href="/tickets">Ver todos</a>
        </div>
        {#each tickets as t (t.id)}
          <!-- A link again: tickets is wired, so a real id sent to
               `/tickets/<uuid>` opens the ticket. -->
          <a
            href="/tickets/{t.id}"
            style="display:flex;gap:12px;align-items:center;padding:11px 15px;border-bottom:1px solid var(--v2-line-soft);color:inherit;text-decoration:none"
          >
            <span style="flex:1;font-size:13px;min-width:0">{t.name}</span>
            <span class="v2-sub" style="font-size:11.5px">{t.status}</span>
            <Pill tone={PRIORITY_TONE[t.priority]}>{t.priority}</Pill>
          </a>
        {:else}
          <p class="v2-sub" style="padding:14px 15px;font-size:12.5px">
            Sin tickets. <a href="/tickets/new?account={account.id}">Creá uno</a> si algo anda mal.
          </p>
        {/each}
      </section>

      <!-- Invoices -->
      <section class="v2-card" style="overflow:hidden">
        <div class="v2-card-head">
          <span class="v2-label">Facturas</span>
          <a href="/invoices">Ver todas</a>
        </div>
        {#each invoices as inv (inv.id)}
          <!-- A link now: invoices is wired, so a real id sent to
               `/invoices/<uuid>` opens the invoice. -->
          <a
            href="/invoices/{inv.id}"
            style="display:flex;gap:12px;align-items:center;padding:11px 15px;border-bottom:1px solid var(--v2-line-soft);color:inherit;text-decoration:none"
          >
            <span class="v2-num" style="font-size:12.5px">{inv.invoice_number}</span>
            <Pill tone={inv.past_due ? 'rust' : INVOICE_STATUS_TONE[inv.status]}>
              {inv.past_due ? 'Vencida' : invoiceStatusLabel(inv.status)}
            </Pill>
            <span class="v2-num" style="margin-left:auto;font-weight:600;font-size:13px">
              {money(inv.past_due ? inv.amount_due : inv.total_amount, inv.currency)}
            </span>
          </a>
        {:else}
          <p class="v2-sub" style="padding:14px 15px;font-size:12.5px">Todavía nada facturado.</p>
        {/each}
      </section>
    </div>
  </div>
</div>

<style>
  @media (max-width: 1080px) {
    .v2-account-grid {
      grid-template-columns: 1fr !important;
    }
  }
</style>
