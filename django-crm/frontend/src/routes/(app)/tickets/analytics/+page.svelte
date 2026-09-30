<script>
  /**
   * Service health. Four questions, in the order a support lead asks them:
   * is the queue growing, are we answering in time, who is carrying it, and
   * what is it made of.
   *
   * No chart library. Every mark here is a div sized by a percentage, which
   * keeps the page honest about how little it is actually drawing, and a
   * fourteen-bar series does not need an axis, a legend and 90kb of SVG.
   *
   * WHAT THIS PAGE DOES NOT DO
   * It never averages across priorities. "SLA attainment: 92%" folds four
   * different promises into one number that describes none of them; an urgent
   * incident answered in ninety minutes and a low-priority question answered
   * in ninety minutes are not the same event. Attainment is reported per
   * priority, against that priority's own target, or not at all.
   */
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import SectionTabs from '$lib/v2/components/SectionTabs.svelte';
  import StatCard from '$lib/v2/components/StatCard.svelte';
  import Avatar from '$lib/v2/components/Avatar.svelte';
  import { count, shortDate } from '$lib/v2/format.js';
  import { CASE_PRIORITY_LABEL, CASE_TYPE_LABEL } from '$lib/v2/enums.js';
  import { Clock } from '@lucide/svelte';

  /** @type {{ data: any }} */
  let { data } = $props();

  let canView = $derived(data.can_view);
  let totals = $derived(data.totals);
  // Floor at 1 so an empty or all-zero window scales cleanly to flat bars
  // rather than dividing by a zero (or -Infinity) peak.
  let peak = $derived(Math.max(1, ...data.volume.map((d) => Math.max(d.opened, d.closed))));

  /**
   * Minutes → "41m" / "2h 20m" / "1d 3h" / "1d". A number of minutes is not a
   * duration, and neither is "1d 0h". A zero remainder is dropped rather than
   * printed, at every scale.
   */
  function duration(mins) {
    if (mins == null) return '—';
    if (mins < 60) return `${mins}m`;
    const h = Math.floor(mins / 60);
    const m = mins % 60;
    if (h < 24) return m ? `${h}h ${m}m` : `${h}h`;
    const d = Math.floor(h / 24);
    return h % 24 ? `${d}d ${h % 24}h` : `${d}d`;
  }

  // Attainment among *decided* cases (met vs missed). A priority with no
  // decided cases yet (all in-flight, or none at all) has no percentage to
  // report, so it returns null and the row shows "—" rather than "NaN%".
  const attainment = (r) => {
    const decided = r.met + r.missed;
    return decided ? Math.round((r.met / decided) * 100) : null;
  };
  const barColor = (pct) =>
    pct == null
      ? 'var(--v2-line)'
      : pct >= 95
        ? 'var(--v2-moss)'
        : pct >= 85
          ? 'var(--v2-clay)'
          : 'var(--v2-rust)';

  /** Net change over the window. Opened minus closed is the backlog's direction. */
  let net = $derived(totals.opened - totals.closed);
</script>

<PageHeader title="Análisis del servicio">
  {#snippet sub()}
    {#if canView}
      Últimos <span class="v2-num">{totals.window_days}</span> días
      {#if totals.business_hours_applied}
        · medido en horario laboral ({totals.calendar_name})
      {/if}
    {:else}
      Salud del servicio
    {/if}
  {/snippet}
</PageHeader>

<SectionTabs set="tickets" />

{#if !canView}
  <div class="v2-pad" style="padding-top:40px">
    <!-- Centred, not left-hugging: this is all a non-admin sees on this page,
         so a capped card pinned to the left leaves the rest of a wide screen
         empty. margin-inline centres the column. -->
    <div class="v2-card" style="padding:20px 22px;max-width:520px;margin-inline:auto">
      <strong>Este panel es para administradores.</strong>
      <p>
        El volumen de abiertos y cerrados, el cumplimiento de primera respuesta y el desglose de la
        cola son cifras de toda la organización, así que están limitadas a administradores. Tus
        propios tickets están en la pestaña <a href="/tickets">Tickets</a>.
      </p>
    </div>
  </div>
{:else}
  <div class="v2-pad" style="padding-top:16px;flex:none">
    <div class="v2-stats">
      <StatCard label="Abiertos" value={count(totals.opened)} tone="ink" />
      <StatCard label="Cerrados" value={count(totals.closed)} tone="moss" />
      <StatCard
        label="Backlog"
        value={count(totals.open_now)}
        tone={net > 0 ? 'clay' : 'slate'}
        detail={net > 0
          ? `Creció ${net} en el período`
          : net < 0
            ? `Bajó ${Math.abs(net)} en el período`
            : 'Estable en el período'}
      />
      <StatCard
        label="Resolución mediana"
        value={`${totals.median_resolution_hours}h`}
        tone="slate"
        detail="Mediana, no promedio. Un ticket de tres semanas no debería moverla"
      />
    </div>
  </div>

  <div class="v2-scroll">
    <div class="v2-pad" style="padding-bottom:32px">
      <!-- Volume -->
      <div class="v2-card" style="padding:16px 18px 14px;margin-bottom:18px">
        <div style="display:flex;align-items:baseline;gap:14px;margin-bottom:14px">
          <div class="v2-label">Abiertos y cerrados, por día</div>
          <span class="v2-sub" style="font-size:11.5px;margin-left:auto">
            <i class="v2-swatch v2-swatch-in"></i>abiertos
            <i class="v2-swatch" style="margin-left:10px"></i>cerrados
          </span>
        </div>
        <div class="v2-cols">
          {#each data.volume as d (d.date)}
            <div class="v2-col" title="{shortDate(d.date)}, {d.opened} abiertos, {d.closed} cerrados">
              <i class="in" style="height:{(d.opened / peak) * 100}%"></i>
              <i class="out" style="height:{(d.closed / peak) * 100}%"></i>
            </div>
          {/each}
        </div>
        <div class="v2-cols-axis">
          {#each data.volume as d, i (d.date)}
            <!-- Every other label. Fourteen dates at 10px overlap; seven do not. -->
            <span>{i % 2 === 0 ? shortDate(d.date) : ''}</span>
          {/each}
        </div>
      </div>

      <div class="v2-split" style="margin-bottom:18px">
        <!-- First response -->
        <div class="v2-card" style="padding:16px 18px">
          <div class="v2-label" style="margin-bottom:4px">Primera respuesta, contra el objetivo</div>
          <p class="v2-sub" style="font-size:11.5px;margin:0 0 14px">
            Cada prioridad tiene su propio objetivo según la política de escalamiento, así que cada
            una se mide contra su propia promesa.
          </p>
          {#each data.firstResponse as r (r.priority)}
            {@const pct = attainment(r)}
            <div style="margin-bottom:14px">
              <div
                style="display:flex;align-items:baseline;gap:8px;font-size:12.5px;margin-bottom:5px"
              >
                <b style="font-weight:600">{CASE_PRIORITY_LABEL[r.priority] ?? r.priority}</b>
                <span class="v2-sub" style="font-size:11.5px">
                  objetivo {duration(r.target_minutes)} · mediana {duration(r.median_minutes)}
                </span>
                <span
                  class="v2-num"
                  style="margin-left:auto;font-weight:650;color:{pct == null
                    ? 'var(--v2-slate)'
                    : barColor(pct)}"
                >
                  {pct == null ? '—' : `${pct}%`}
                </span>
              </div>
              <div class="v2-bar">
                <i style="width:{pct ?? 0}%;background:{barColor(pct)}"></i>
              </div>
              <div class="v2-bar-legend">
                <span><span class="v2-num">{r.met}</span> a tiempo</span>
                <span>
                  {#if r.missed}
                    <span class="v2-num" style="color:var(--v2-rust)">{r.missed}</span> tarde
                  {:else}
                    ninguno tarde
                  {/if}
                </span>
              </div>
            </div>
          {/each}
        </div>

        <!-- Mix -->
        <div class="v2-card" style="padding:16px 18px">
          <div class="v2-label" style="margin-bottom:4px">De qué está hecha la cola</div>
          <p class="v2-sub" style="font-size:11.5px;margin:0 0 14px">
            Incidentes y problemas son trabajo; las preguntas suelen ser un vacío en la base de
            conocimiento.
          </p>
          {#each data.byType as t (t.case_type)}
            {@const share = Math.round(
              (t.count / data.byType.reduce((a, x) => a + x.count, 0)) * 100
            )}
            <div style="margin-bottom:13px">
              <div style="display:flex;align-items:baseline;font-size:12.5px;margin-bottom:5px">
                <span>{CASE_TYPE_LABEL[t.case_type] ?? t.case_type}</span>
                <span class="v2-sub v2-num" style="margin-left:auto;font-size:12px">
                  {t.count} · {share}%
                </span>
              </div>
              <div class="v2-bar"><i style="width:{share}%"></i></div>
            </div>
          {/each}

          {#if data.byType.find((t) => t.case_type === 'Question')}
            <p class="v2-sub" style="font-size:11.5px;margin:16px 0 0">
              <a href="/solutions" style="color:inherit">
                {data.byType.find((t) => t.case_type === 'Question').count} preguntas en este período
              </a>.
              Las que se repiten pertenecen a la base de conocimiento.
            </p>
          {/if}
        </div>
      </div>

      <!-- Per agent -->
      <div class="v2-label" style="margin-bottom:10px">Quién lo está llevando</div>
      <div class="v2-table-wrap">
        <table class="v2-table">
          <thead>
            <tr>
              <th>Agente</th>
              <th class="v2-r">Abiertos ahora</th>
              <th class="v2-r">Cerrados esta semana</th>
              <th class="v2-r">Primera respuesta mediana</th>
              <th class="v2-r">Objetivo incumplido</th>
            </tr>
          </thead>
          <tbody>
            {#each data.byAgent as a (a.id ?? a.name)}
              <tr>
                <td>
                  <span style="display:flex;gap:8px;align-items:center">
                    {#if a.id}
                      <Avatar name={a.name} size={24} />
                    {:else}
                      <!-- Unassigned is not a person and does not get a face. -->
                      <span
                        style="width:24px;height:24px;border-radius:50%;border:1px dashed var(--v2-line);flex:none"
                      ></span>
                    {/if}
                    <span class="v2-table-primary">{a.name}</span>
                  </span>
                </td>
                <td class="v2-r v2-num">{a.open}</td>
                <td class="v2-r v2-num">{a.closed_this_week}</td>
                <td class="v2-r v2-num">{duration(a.median_first_response_minutes)}</td>
                <td
                  class="v2-r v2-num"
                  style={a.breached ? 'color:var(--v2-rust);font-weight:600' : ''}
                >
                  {a.breached || '—'}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>

      <!--
      The clock these figures are measured on. Without it "answered in 4h" is
      ambiguous: a ticket opened at 17:20 on Friday and answered at 09:10 on
      Monday is either fifteen hours late or fifty minutes early, and only the
      calendar says which.
    -->
      <div style="display:flex;gap:9px;align-items:flex-start;margin-top:16px">
        <Clock size={15} style="color:var(--v2-slate);flex:none;margin-top:2px" />
        <p class="v2-sub" style="font-size:12px;margin:0">
          {#if totals.business_hours_applied}
            El tiempo transcurrido se cuenta dentro de {totals.calendar_name}, así que las tardes,
            fines de semana y feriados no cuentan contra un objetivo.
            <a href="/settings/business-hours" style="color:inherit">Cambiar el calendario</a>.
          {:else}
            El tiempo transcurrido se cuenta las 24 horas, no hay un calendario de horario laboral
            configurado, así que las tardes y fines de semana cuentan contra un objetivo.
            <a href="/settings/business-hours" style="color:inherit">Configurar un calendario</a>.
          {/if}
        </p>
      </div>
    </div>
  </div>
{/if}
