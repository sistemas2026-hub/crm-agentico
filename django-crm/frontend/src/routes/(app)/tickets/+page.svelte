<script>
  import { page } from '$app/state';
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import SectionTabs from '$lib/v2/components/SectionTabs.svelte';
  import FilterBar from '$lib/v2/components/FilterBar.svelte';
  import Pill from '$lib/v2/components/Pill.svelte';
  import Avatar from '$lib/v2/components/Avatar.svelte';
  import EmptyState from '$lib/v2/components/EmptyState.svelte';
  import { count, shortAge } from '$lib/v2/format.js';
  import { PRIORITY_TONE, CASE_STATUS_TONE, CASE_PRIORITY_LABEL, CASE_STATUS_LABEL } from '$lib/v2/enums.js';
  import { Plus, LifeBuoy } from '@lucide/svelte';

  /** @type {{ data: any }} */
  let { data } = $props();

  let tickets = $derived(data.tickets);
  let totals = $derived(data.totals);

  /**
   * How the first-reply clock stands.
   *
   * The deadline arrives from the server, where it is walked through the org's
   * business calendar and pushed forward by any time the ticket spent waiting
   * on the customer. Recomputing it here from `opened_at + hours`, which is
   * what the mock did, would put a second, quietly different answer on the
   * same screen.
   *
   * A progress bar only means something while there is still time on the
   * clock. Past the deadline a bar pinned at 100% says nothing about how bad
   * it is, so we stop drawing one and say how far over it went instead.
   *
   * @param {any} t
   */
  function responsePressure(t) {
    if (t.first_response_at) {
      const took =
        (new Date(t.first_response_at).getTime() - new Date(t.opened_at).getTime()) / 6e4;
      return { state: 'met', label: `Cumplido en ${fmtMins(took)}`, tone: 'moss' };
    }
    if (!t.first_response_deadline) {
      return { state: 'none', label: 'Sin objetivo', tone: 'slate' };
    }
    const now = Date.now();
    const opened = new Date(t.opened_at).getTime();
    const due = new Date(t.first_response_deadline).getTime();
    if (now >= due) {
      return { state: 'breached', label: `${fmtMins((now - due) / 6e4)} de más`, tone: 'rust' };
    }
    const pct = Math.max(0, Math.min(100, Math.round(((now - opened) / (due - opened)) * 100)));
    return {
      state: 'running',
      pct,
      label: `${fmtMins((due - now) / 6e4)} restantes`,
      tone: pct >= 75 ? 'rust' : pct >= 50 ? 'clay' : 'slate'
    };
  }

  /** @param {number} m */
  function fmtMins(m) {
    const n = Math.max(0, Math.round(m));
    if (n < 60) return `${n}m`;
    if (n < 1440) return `${Math.round(n / 60)}h`;
    return `${Math.round(n / 1440)}d`;
  }

  const TONE_VAR = {
    moss: 'var(--v2-moss)',
    rust: 'var(--v2-rust)',
    clay: 'var(--v2-clay)',
    slate: 'var(--v2-slate)'
  };
</script>

<PageHeader title="Tickets">
  {#snippet sub()}
    <span class="v2-num">{count(totals.open)}</span> abiertos ·
    <span class="v2-num" style="color:var(--v2-rust)">{totals.urgent}</span> urgentes ·
    <!-- Not "breaching today". A breach depends on the org's business calendar
         and is a per-row calculation; nobody having replied yet is a fact the
         queue can establish, and it is the one that decides what to open. -->
    <span class="v2-num">{count(totals.awaiting_reply)}</span> sin respuesta todavía
  {/snippet}
  {#snippet actions()}
    <a class="v2-btn v2-btn-primary" href="/tickets/new"><Plus />Nuevo ticket</a>
  {/snippet}
</PageHeader>

{#if page.url.search}
  <p class="v2-sub" style="font-size:11.5px;margin:8px 0 0">Estos números describen la cola filtrada.</p>
{/if}

<!-- Approvals and Analytics were buttons in this header that went nowhere.
     They are sibling pages, so they belong in a tab strip that also tells you
     which one you are on. -->
<SectionTabs set="tickets" />

<FilterBar
  page="tickets"
  url={page.url}
  people={data.people}
  tags={data.tags}
  meId={data.meId}
  meta="Los objetivos de primera respuesta vienen de las horas de SLA de cada ticket"
/>

<div class="v2-scroll">
  {#if tickets.length === 0}
    <!-- An empty queue is good news, so it does not read like a failure. -->
    <EmptyState
      title={data.showAll ? 'Todavía no hay tickets acá' : 'La cola está despejada'}
      body={data.showAll
        ? 'No se creó nada en este espacio de trabajo. Los tickets llegan acá por correo, el portal, y cualquiera que responda a uno cerrado.'
        : 'Nada está esperando a tu equipo ahora mismo. Los tickets cerrados y rechazados siguen acá. Simplemente no estorban.'}
    >
      {#snippet icon()}<LifeBuoy size={21} />{/snippet}
      {#snippet actions()}
        <a class="v2-btn v2-btn-primary" href="/tickets/new">Nuevo ticket</a>
        {#if !data.showAll}
          <a class="v2-btn" href="/tickets?all=1">Mostrar los cerrados también</a>
        {/if}
        <a class="v2-btn" href="/solutions">Base de conocimiento</a>
      {/snippet}
    </EmptyState>
  {:else}
    <div class="v2-table-wrap">
      <table class="v2-table">
        <thead>
          <tr>
            <th>Asunto</th>
            <th>Prioridad</th>
            <th>Estado</th>
            <th>Tipo</th>
            <th>Cuenta</th>
            <th>Asignado a</th>
            <th class="v2-r">Antigüedad</th>
            <th style="width:130px">Primera respuesta</th>
          </tr>
        </thead>
        <tbody>
          {#each tickets as t (t.id)}
            {@const p = responsePressure(t)}
            <tr>
              <td data-m="title">
                <a class="v2-row-link" href="/tickets/{t.id}">
                  <span class="v2-table-primary">{t.name}</span>
                </a>
              </td>
              <td><Pill tone={PRIORITY_TONE[t.priority]}>{CASE_PRIORITY_LABEL[t.priority] ?? t.priority}</Pill></td>
              <td data-m="tag"><Pill tone={CASE_STATUS_TONE[t.status]}>{CASE_STATUS_LABEL[t.status] ?? t.status}</Pill></td>
              <!-- Nullable on the model and null on plenty of rows, so it says
                   so rather than printing an empty cell. -->
              <td class="v2-muted" data-m="hide" style="font-size:12.5px">
                {t.case_type ?? '—'}
              </td>
              <td class="v2-muted" style="font-size:12.5px">
                {#if t.account}
                  <a class="v2-row-link" href="/accounts/{t.account.id}">{t.account.name}</a>
                {:else}
                  Sin cuenta
                {/if}
              </td>
              <td data-m="hide">
                {#if t.assignee}
                  <Avatar name={t.assignee} size={22} />
                {:else}
                  <span class="v2-muted" style="font-size:12.5px">Sin asignar</span>
                {/if}
              </td>
              <td class="v2-r v2-num v2-muted" data-m="meta">{shortAge(t.opened_at)}</td>
              <!-- Kept on a phone, unlike the other trailing columns: a running
                   first-reply clock is the one thing in this queue that decides
                   what to open next. It takes its own line so the meter has a
                   width to fill. -->
              <td data-m="bar">
                {#if p.state === 'running'}
                  <div style="display:flex;align-items:center;gap:8px">
                    <span
                      style="flex:1;height:4px;border-radius:3px;background:var(--v2-line);overflow:hidden;display:block"
                    >
                      <i
                        style="display:block;height:100%;width:{p.pct}%;background:{TONE_VAR[
                          p.tone
                        ]}"
                      ></i>
                    </span>
                    <span class="v2-num" style="font-size:11px;color:{TONE_VAR[p.tone]}"
                      >{p.label}</span
                    >
                  </div>
                {:else}
                  <span class="v2-num" style="font-size:11.5px;color:{TONE_VAR[p.tone]}"
                    >{p.label}</span
                  >
                {/if}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
    <p class="v2-sub v2-pad" style="font-size:12px;padding-bottom:24px">
      Mostrando <span class="v2-num">{tickets.length}</span> de
      <span class="v2-num">{count(totals.count)}</span>
      {#if !data.showAll}
        · <a href="/tickets?all=1" style="color:inherit">incluir cerrados</a>
      {:else}
        · <a href="/tickets" style="color:inherit">solo abiertos</a>
      {/if}
    </p>
  {/if}
</div>
