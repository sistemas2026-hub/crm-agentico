<script>
  /**
   * An estimate, and the one irreversible thing a customer can do in this
   * product: accept it.
   *
   * ── ACCEPT IS A DECISION, NOT A CLICK ────────────────────────────────────
   * `PublicEstimateAcceptView` flips status to `Accepted`, stamps
   * `accepted_at`, and there is no undo endpoint. So the page makes it two
   * steps, press, then confirm against the total. Decline is one step,
   * because decline is recoverable by picking up the phone and accept is not.
   *
   * ── THE TWO THINGS THE SERVER NOW CHECKS ─────────────────────────────────
   * Both of these were once frontend-only pretences; they are enforced in the
   * view now, and this page reflects that.
   *
   * 1. EXPIRY. Accepting past `expiry_date` is rejected server-side, so an
   *    expired quote cannot be accepted at its old price even by POSTing the
   *    token directly. The button is hidden past expiry as a courtesy, not as
   *    the control.
   * 2. WHO ACCEPTED. The acceptor's name and email are required and recorded
   *    (with the request IP and user-agent), acceptance authorises an
   *    invoice, and the record of who gave it is now more than "whoever held
   *    the link".
   */
  import { enhance } from '$app/forms';
  import PortalShell from '$lib/v2/components/PortalShell.svelte';
  import PortalLineItems from '$lib/v2/components/PortalLineItems.svelte';
  import { money, longDate } from '$lib/v2/format.js';
  import { ESTIMATE_STATUS_LABEL } from '$lib/v2/enums.js';
  import { Download, CheckCircle2, XCircle, AlertTriangle } from '@lucide/svelte';

  /** @type {{ data: { estimate: any, token: string }, form: any }} */
  let { data, form } = $props();

  let est = $derived(data.estimate);
  let token = $derived(data.token);

  /** null when there is no expiry date; negative once it has passed. */
  let daysToExpiry = $derived.by(() => {
    if (!est.expiry_date) return null;
    const startOfDay = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
    return Math.round((startOfDay(new Date(est.expiry_date)) - startOfDay(new Date())) / 86400000);
  });

  let expired = $derived(daysToExpiry !== null && daysToExpiry < 0);

  /** The server's own gate, mirrored so the two cannot drift apart silently. */
  let serverWouldAllow = $derived(['Sent', 'Viewed'].includes(est.status));

  /** Already decided. The page becomes a receipt. */
  let decided = $derived(est.status === 'Accepted' || est.status === 'Declined');

  let confirming = $state(false);
  let submitting = $state(false);
  let acceptedByName = $state('');
  let acceptedByEmail = $state('');

  let addr = $derived(est.client_address || {});
  let addressLines = $derived(
    [addr.line, addr.city, addr.state, addr.postcode, addr.country].filter(Boolean)
  );

  /** Shared enhance handler: reload on completion, close the confirm step only
      when the server accepted the submission. */
  function respond() {
    submitting = true;
    return async ({ result, update }) => {
      await update();
      submitting = false;
      if (result.type === 'success') confirming = false;
    };
  }
</script>

<svelte:head>
  <title>{est.estimate_number} de {est.org.name}</title>
</svelte:head>

<PortalShell>
  <article class="doc">
    <header class="doc-head">
      <div>
        <div class="from">{est.org.name}</div>
        <h1>{est.title}</h1>
        <div class="ref">
          Cotización <span class="v2-num">{est.estimate_number}</span> · emitida
          {longDate(est.issue_date)}
        </div>
      </div>
      <!-- A backend download endpoint, not a SvelteKit route: rel="external"
           forces a real navigation (and the file download) rather than a
           client-side one. -->
      <a
        class="v2-btn v2-btn-sm"
        href="/api/public/estimate/{token}/pdf/"
        rel="external"
        aria-label="Descargar esta cotización como PDF"
      >
        <Download size={13} />PDF
      </a>
    </header>

    <section class="amount">
      <div>
        <div class="amount-label">Total si se acepta</div>
        <div class="amount-value v2-num">{money(est.total_amount, est.currency)}</div>
        <div class="amount-sub">
          {#if expired}
            Venció {longDate(est.expiry_date)}
          {:else if daysToExpiry === 0}
            Válida hasta el final de hoy
          {:else if daysToExpiry !== null}
            Válida hasta {longDate(est.expiry_date)} · quedan {daysToExpiry}
            {daysToExpiry === 1 ? 'día' : 'días'}
          {:else}
            Sin fecha de vencimiento definida
          {/if}
        </div>
      </div>
    </section>

    {#if form?.error}
      <section class="formerr">
        <AlertTriangle size={16} />
        <p>{form.error}</p>
      </section>
    {/if}

    <!-- The decision. -->
    {#if decided}
      <section class="decided" class:no={est.status === 'Declined'}>
        {#if est.status === 'Accepted'}<CheckCircle2 size={18} />{:else}<XCircle size={18} />{/if}
        <div>
          <b>{ESTIMATE_STATUS_LABEL[est.status] ?? est.status}</b>
          {#if est.status === 'Accepted'}
            <p>
              Se notificó a {est.org.name} y va a emitir una factura por
              {money(est.total_amount, est.currency)}. Se envió una copia a {est.client_email}.
            </p>
          {:else}
            <p>
              Se notificó a {est.org.name}. Si rechazaste por error, respondé al correo del que
              vino este enlace. Esta página no puede deshacerlo.
            </p>
          {/if}
        </div>
      </section>
    {:else if expired}
      <!-- Expired: no accept button. The server enforces this too, so it is a
           closed door, not a hidden one. -->
      <section class="expired">
        <AlertTriangle size={17} />
        <div>
          <b>Esta cotización venció</b>
          <p>
            Los precios se mantuvieron hasta el {longDate(est.expiry_date)}. Respondé al correo del
            que vino este enlace y {est.org.name} puede mandarte una cotización actualizada.
          </p>
        </div>
      </section>
    {:else if serverWouldAllow}
      <section class="decide">
        {#if !confirming}
          <div class="decide-copy">
            <b>¿Lista para avanzar?</b>
            <p>Aceptar autoriza a {est.org.name} a facturarte los montos de arriba.</p>
          </div>
          <div class="decide-actions">
            <button class="v2-btn v2-btn-primary" onclick={() => (confirming = true)}>
              Aceptar esta cotización
            </button>
            <form method="POST" action="?/decline" use:enhance={respond}>
              <button class="v2-btn" type="submit" disabled={submitting}>Rechazar</button>
            </form>
          </div>
        {:else}
          <!-- Step two. The total is repeated here on purpose: it is the number
               being agreed to, and it should be under the thumb that agrees. -->
          <form class="confirm" method="POST" action="?/accept" use:enhance={respond}>
            <b>Confirmar aceptación de {money(est.total_amount, est.currency)}</b>
            <p>
              Esto le indica a {est.org.name} que emita una factura. No se puede deshacer desde
              esta página.
            </p>
            <label class="field">
              <span>Tu nombre</span>
              <input
                name="name"
                bind:value={acceptedByName}
                placeholder="Quién está aceptando"
                autocomplete="name"
                required
              />
            </label>
            <label class="field">
              <span>Tu correo</span>
              <input
                name="email"
                type="email"
                bind:value={acceptedByEmail}
                placeholder="nombre@empresa.com"
                autocomplete="email"
                required
              />
            </label>
            <p class="field-note">
              Se registra junto con tu aceptación: {est.org.name} guarda esto como el registro de
              quién autorizó la factura.
            </p>
            <div class="decide-actions">
              <button class="v2-btn v2-btn-primary" type="submit" disabled={submitting}>
                {submitting ? 'Aceptando…' : 'Sí, aceptar'}
              </button>
              <button class="v2-btn" type="button" onclick={() => (confirming = false)}>
                Volver
              </button>
            </div>
          </form>
        {/if}
      </section>
    {/if}

    <section class="block">
      <div class="v2-label">Preparada para</div>
      <div class="addr">
        <div class="addr-name">{est.client_name}</div>
        {#each addressLines as line, i (i)}
          <div>{line}</div>
        {/each}
      </div>
    </section>

    <section class="block">
      <div class="v2-label">Qué incluye</div>
      <PortalLineItems
        items={est.line_items}
        currency={est.currency}
        subtotal={est.subtotal}
        discountAmount={est.discount_amount}
        discountType={est.discount_type}
        discountValue={est.discount_value}
        taxRate={est.tax_rate}
        taxAmount={est.tax_amount}
        total={est.total_amount}
      />
    </section>

    {#if est.notes}
      <section class="block">
        <div class="v2-label">Notas</div>
        <p class="note">{est.notes}</p>
      </section>
    {/if}

    {#if est.terms}
      <section class="block">
        <div class="v2-label">Condiciones</div>
        <p class="note">{est.terms}</p>
      </section>
    {/if}

    <footer class="doc-foot">
      <p>¿Preguntas? Respondé al correo con el que llegó esta cotización.</p>
      {#if est.template?.footer_text}
        <p class="foot-org">{est.template.footer_text}</p>
      {/if}
    </footer>
  </article>
</PortalShell>

<style>
  .doc {
    background: var(--v2-card);
    border: 1px solid var(--v2-line);
    border-radius: var(--v2-radius);
    padding: 30px 32px 26px;
  }
  .doc-head {
    display: flex;
    align-items: flex-start;
    gap: 16px;
    padding-bottom: 22px;
    border-bottom: 1px solid var(--v2-line);
  }
  .doc-head > div:first-child {
    min-width: 0;
  }
  .doc-head .v2-btn {
    flex: none;
    margin-left: auto;
  }
  .from {
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.02em;
    color: var(--v2-slate);
  }
  h1 {
    margin: 4px 0 0;
    font-size: 21.9px;
    font-weight: 640;
    line-height: 1.2;
    letter-spacing: -0.01em;
  }
  .ref {
    margin-top: 5px;
    font-size: 12.5px;
    color: var(--v2-slate);
  }

  .amount {
    margin: 22px 0;
    padding: 18px 20px;
    border: 1px solid var(--v2-line);
    border-radius: 8px;
    background: var(--v2-line-soft);
  }
  .amount-label {
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.09em;
    text-transform: uppercase;
    color: var(--v2-slate);
  }
  .amount-value {
    margin-top: 3px;
    font-size: 32px;
    font-weight: 650;
    letter-spacing: -0.02em;
    line-height: 1.1;
  }
  .amount-sub {
    margin-top: 5px;
    font-size: 12.5px;
    color: var(--v2-slate);
  }

  .formerr {
    display: flex;
    gap: 10px;
    align-items: flex-start;
    margin: 0 0 22px;
    padding: 13px 16px;
    border: 1px solid var(--v2-ember-line);
    border-radius: 8px;
    background: var(--v2-ember-soft);
    color: var(--v2-rust);
  }
  .formerr :global(svg) {
    flex: none;
    margin-top: 1px;
  }
  .formerr p {
    margin: 0;
    font-size: 12.5px;
    line-height: 1.5;
  }

  .decide {
    display: flex;
    align-items: center;
    gap: 18px;
    flex-wrap: wrap;
    margin: 22px 0;
    padding: 17px 20px;
    border: 1px solid var(--v2-ember-line);
    border-radius: 8px;
    background: var(--v2-ember-soft);
  }
  .decide-copy b,
  .confirm b {
    font-size: 13.5px;
    font-weight: 640;
  }
  .decide-copy p,
  .confirm p {
    margin: 4px 0 0;
    font-size: 12.5px;
    color: var(--v2-slate);
    line-height: 1.5;
  }
  .decide-actions {
    display: flex;
    gap: 8px;
    margin-left: auto;
    flex: none;
    align-items: center;
  }
  .confirm {
    width: 100%;
  }
  .confirm .decide-actions {
    margin: 14px 0 0;
  }
  .field {
    display: block;
    margin-top: 12px;
    max-width: 320px;
  }
  .field span {
    display: block;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--v2-slate);
    margin-bottom: 4px;
  }
  .field input {
    width: 100%;
    padding: 7px 10px;
    font: inherit;
    font-size: 13px;
    color: var(--v2-ink);
    background: var(--v2-card);
    border: 1px solid var(--v2-line);
    border-radius: 6px;
  }
  .field input:focus {
    outline: 2px solid var(--v2-ember);
    outline-offset: -1px;
  }
  .field-note {
    margin: 7px 0 0 !important;
    font-size: 11.5px;
  }

  .decided,
  .expired {
    display: flex;
    gap: 11px;
    align-items: flex-start;
    margin: 22px 0;
    padding: 16px 18px;
    border: 1px solid var(--v2-line);
    border-radius: 8px;
    color: var(--v2-moss);
  }
  .decided.no,
  .expired {
    color: var(--v2-clay);
  }
  .decided :global(svg),
  .expired :global(svg) {
    flex: none;
    margin-top: 1px;
  }
  .decided b,
  .expired b {
    font-size: 13.5px;
    color: var(--v2-ink);
  }
  .decided p,
  .expired p {
    margin: 4px 0 0;
    font-size: 12.5px;
    color: var(--v2-slate);
    line-height: 1.5;
  }

  .block {
    margin-top: 26px;
  }
  .addr {
    margin-top: 7px;
    font-size: 13px;
    line-height: 1.55;
    color: var(--v2-slate);
  }
  .addr-name {
    color: var(--v2-ink);
    font-weight: 500;
  }
  .note {
    margin: 7px 0 0;
    font-size: 13px;
    line-height: 1.55;
    white-space: pre-wrap;
  }

  .doc-foot {
    margin-top: 30px;
    padding-top: 18px;
    border-top: 1px solid var(--v2-line);
    font-size: 12px;
    color: var(--v2-slate);
    line-height: 1.55;
  }
  .doc-foot p {
    margin: 0;
  }
  .foot-org {
    margin-top: 7px !important;
    font-size: 11px;
  }

  @media (max-width: 560px) {
    .doc {
      padding: 22px 18px 20px;
    }
    .amount-value {
      font-size: 27px;
    }
    .decide-actions {
      margin-left: 0;
      width: 100%;
    }
    .decide-actions .v2-btn {
      flex: 1;
      justify-content: center;
    }
  }
</style>
