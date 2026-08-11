<script>
  /**
   * The settings hub.
   *
   * v1 has thirteen settings routes reachable only from a dropdown, so nobody
   * could tell what was configurable without opening each one. This lists them
   * with the current value beside each. A settings index that does not tell
   * you the current state is a table of contents, not a screen.
   *
   * Grouped by what a setting decides, not by which Django app owns it:
   * "who a ticket lands on" and "what closes it" belong together whether or
   * not they live in the same models file.
   *
   * `warn` is the second reason this page exists. Each destination reports
   * whether something there needs attention, so the hub is worth opening even
   * when you did not come to change anything. A warning here always has a
   * matching explanation on the page it points to, never a badge that leads
   * to a screen with nothing on it.
   *
   * Destinations v2 has not built are listed anyway and link to v1, marked as
   * such. An index that quietly omits settings is worse than one that admits
   * where they live: people go looking, find nothing, and conclude the feature
   * does not exist.
   */
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import { count, shortDate } from '$lib/v2/format.js';
  import { ChevronRight, ShieldAlert } from '@lucide/svelte';

  /** @type {{ data: any }} */
  let { data } = $props();

  let org = $derived(data.org);

  /**
   * Weekday hours as one line. When the days do not all match it says so
   * rather than printing the first day's hours; "09:00-17:00" beside a
   * calendar where four days run to 17:30 is a summary that is simply wrong,
   * and this is the number an SLA is measured against.
   */
  let hoursSummary = $derived.by(() => {
    const open = data.calendar.days.filter((d) => d.open);
    if (!open.length) return 'Sin horario configurado';
    const first = open[0];
    const uniform = open.every((d) => d.open === first.open && d.close === first.close);
    return uniform
      ? `${open.length} días, ${first.open}-${first.close}`
      : `${open.length} días, horario variable`;
  });

  /** An approval rule set to MANAGER with no named approvers matches nobody. */
  let stuckApprovalRules = $derived(
    data.approvalRules.filter(
      (r) => r.is_active && r.approver_role === 'MANAGER' && !r.approvers.length
    ).length
  );

  let groups = $derived([
    {
      label: 'Personas y acceso',
      items: [
        {
          href: '/team',
          title: 'Equipo y acceso',
          body: 'Quién puede iniciar sesión, y qué le permite hacer su rol.',
          // People counts are admin-only oversight; a member's fan-out gets no
          // totals (the endpoint 403s), so the row lists the destination with
          // no value rather than a misleading zero.
          value: data.peopleTotals
            ? `${data.peopleTotals.count} personas · ${data.peopleTotals.admins} administradores`
            : null,
          warn: data.peopleTotals ? data.peopleTotals.tokens_on_deactivated > 0 : false
        },
        {
          href: '/settings/api-tokens',
          title: 'Tokens de API',
          body: 'Tokens de acceso personal para scripts, integraciones y agentes de IA.',
          value: data.tokenTotals ? `${data.tokenTotals.live} activos` : null,
          warn: data.tokenTotals
            ? data.tokenTotals.orphaned > 0 || data.tokenTotals.unused_90d > 0
            : false
        },
        {
          href: '/settings/organization',
          title: 'Organización',
          body: 'Los datos de la empresa que se imprimen en cada factura y cotización.',
          value: org.company_name,
          warn: false
        }
      ]
    },
    {
      label: 'Cómo se gestionan los tickets',
      items: [
        {
          href: '/settings/routing',
          title: 'Enrutamiento de tickets',
          body: 'A quién le llega un ticket nuevo, en el orden en que se prueban las reglas.',
          value: `${data.routingTotals.active} reglas`,
          warn: data.routingTotals.unrouted_last_30d > 0
        },
        {
          href: '/settings/escalation',
          title: 'Escalamiento',
          body: 'Qué pasa cuando un ticket no cumple su objetivo de respuesta.',
          value: `${data.escalationTotals.active} de ${data.escalationTotals.count} prioridades`,
          warn: data.escalationTotals.breaches_unhandled_30d > 0
        },
        {
          href: '/settings/business-hours',
          title: 'Horario laboral',
          body: 'El reloj contra el que se mide cada objetivo de respuesta.',
          value: `${data.calendar.name} · ${hoursSummary}`,
          warn: false
        },
        {
          href: '/settings/ticket-approvals',
          title: 'Reglas de aprobación',
          body: 'Qué bloquea el cierre de un ticket, y quién puede destrabarlo.',
          value: `${data.approvalTotals.active} activas`,
          warn: stuckApprovalRules > 0
        },
        {
          href: '/settings/reopen',
          title: 'Política de reapertura',
          body: 'Si la respuesta de un cliente vuelve a abrir un ticket cerrado.',
          // Admin-only, like people and tokens above: a member's fan-out gets
          // null (the endpoint 403s), so the row lists the destination without
          // a value rather than guessing at the policy.
          value: !data.reopen
            ? null
            : data.reopen.is_enabled
              ? `Dentro de ${data.reopen.reopen_window_days} días`
              : 'Apagada. Lo cerrado sigue cerrado',
          // Replies arriving outside the window are normal for any window, so
          // that number belongs on the page, not on a warning here. Off is the
          // state worth flagging: it makes every reply to a closed ticket
          // vanish, not just the late ones.
          warn: data.reopen ? !data.reopen.is_enabled : false
        },
        {
          href: '/settings/inbound-email',
          title: 'Correo entrante',
          body: 'Las direcciones que convierten un correo en un ticket.',
          value: `${data.mailboxTotals.active} de ${data.mailboxTotals.count} activas`,
          // Off AND still receiving, not merely off. An address switched off
          // and left alone is a decision; one still getting mail and creating
          // nothing is a customer being ignored.
          warn: data.mailboxTotals.silently_dropping > 0
        }
      ]
    },
    {
      // El asistente es otro servicio, no una app de Django, y sus dos
      // destinos ya viven en el sidebar. Aparecen igual aca, como /team y las
      // plantillas de factura: el hub es donde se viene a saber que se puede
      // configurar, y omitirlos obligaria a saber de antemano que existen.
      //
      // Los valores quedan en null cuando el motor no contesta. No lleva
      // warn: en una instalacion sin asistente desplegado eso no es una falla
      // que nadie tenga que ir a arreglar, y una advertencia que no se puede
      // atender ensena a ignorar las advertencias.
      label: 'Asistente',
      items: [
        {
          href: '/agentes',
          title: 'Agentes y permisos',
          body: 'Que puede consultar cada agente, y que campos le devuelve cada consulta.',
          value: data.asistente ? `${count(data.asistente.roles.length)} agentes` : null,
          warn: false
        },
        {
          href: '/settings/asistente',
          title: 'Personalidad del asistente',
          body: 'Con que nombre se presenta, en que tono habla y cuanto se extiende.',
          value: data.asistente
            ? `${data.asistente.persona.nombre_asistente} · ${data.asistente.persona.tono}`
            : null,
          warn: false
        }
      ]
    },
    {
      label: 'Palabras y campos compartidos',
      items: [
        {
          href: '/settings/macros',
          title: 'Macros',
          body: 'Respuestas predefinidas, y los placeholders que reemplazan.',
          value: `${data.macroTotals.org} compartidas`,
          warn: data.macroTotals.with_unknown_placeholders > 0
        },
        {
          href: '/settings/tags',
          title: 'Etiquetas',
          body: 'Etiquetas compartidas entre cuentas, prospectos, negociaciones y tickets.',
          value: `${data.tagTotals.active} en uso`,
          // Unused tags are housekeeping, not a fault, the tags page lists
          // them without needing the hub to raise an alarm about tidiness.
          warn: false
        },
        {
          href: '/settings/custom-fields',
          title: 'Campos personalizados',
          body: 'Campos que esta organización agregó a los registros.',
          value: `${data.fieldTotals.active} en ${data.fieldTotals.models_extended} tipos de registro`,
          warn: data.fieldTotals.required_with_gaps > 0
        },
        {
          href: '/invoices/templates',
          title: 'Plantillas de factura',
          body: 'Cómo se ve una factura cuando la recibe un cliente.',
          value: 'Dentro de Facturas',
          warn: false
        }
      ]
    }
  ]);

  let warnings = $derived(groups.flatMap((g) => g.items).filter((i) => i.warn).length);
</script>

<PageHeader title="Configuración">
  {#snippet sub()}
    {org.name} · <span class="v2-num">{count(org.member_count)}</span> miembros · desde
    {shortDate(org.created_at)}
    {#if warnings}
      · <span class="v2-num">{count(warnings)}</span> necesitan revisión
    {/if}
  {/snippet}
</PageHeader>

<div class="v2-scroll">
  <div class="v2-pad" style="padding-top:18px;padding-bottom:32px">
    {#each groups as g (g.label)}
      <div class="v2-label" style="margin-bottom:10px">{g.label}</div>
      <div class="v2-card" style="overflow:hidden;margin-bottom:22px">
        {#each g.items as s (s.href)}
          <a class="v2-setting" href={s.href}>
            <div class="v2-setting-body">
              <b>{s.title}</b>
              <span class="v2-sub" style="font-size:11.5px">{s.body}</span>
            </div>
            {#if s.warn}
              <ShieldAlert size={15} style="color:var(--v2-clay);flex:none" />
            {/if}
            {#if s.value}
              <span class="v2-sub v2-setting-value">{s.value}</span>
            {/if}
            <ChevronRight size={15} style="color:var(--v2-slate);flex:none" />
          </a>
        {/each}
      </div>
    {/each}

    <!--
      The org API key is deliberately absent from this page. It is a
      credential, it was once exposed through nested serializers, and a
      settings screen that renders it is how the next leak happens. Rotating
      or revealing it belongs behind an explicit, audited action, not on an
      index anyone with the URL can load.
    -->
    <p class="v2-sub" style="font-size:11.5px;margin-top:18px;max-width:64ch">
      La clave de API de la organización no se muestra acá. Las credenciales nunca se renderizan en
      una página a la que se puede llegar navegando. Mirá
      <a href="/settings/api-tokens" style="color:inherit">Tokens de API</a> para saber cómo se manejan
      los valores de los tokens.
    </p>
  </div>
</div>

<style>
  .v2-setting-value {
    font-size: 12px;
    text-align: right;
  }

  /* At 414px the value column squeezes the title to a couple of words per
     line. Drop it. The destination and what it does are what you navigate
     by, and every value is repeated on the page it points to. */
  @media (max-width: 640px) {
    .v2-setting-value {
      display: none;
    }
  }
</style>
