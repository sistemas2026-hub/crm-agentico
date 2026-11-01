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

  /*
   * Cada lectura llega APARTE (ver settings.js::getSettingsHub, 01/11/2026):
   * la carga no espera ninguna, la pagina se dibuja enseguida y cada fila
   * muestra su valor cuando llega el suyo. Mientras tanto se ve sin valor, lo
   * mismo que muestra cuando esa lectura fallo o un miembro no puede verla.
   * Las promesas nunca rechazan.
   *
   * `d` junta lo que ya llego con lo que vino resuelto desde el principio
   * (asi tambien se dibuja con datos planos, que es como lo prueba
   * hub-se-dibuja-sin-esperar.test.js).
   */
  /** @param {any} v */
  const esPromesa = (v) => !!v && typeof v.then === 'function';
  /** @type {Record<string, any>} */
  let llegado = $state({});
  $effect(() => {
    let vigente = true;
    llegado = {};
    for (const [clave, valor] of Object.entries(data)) {
      if (!esPromesa(valor)) continue;
      valor.then((/** @type {any} */ v) => {
        if (vigente) llegado[clave] = v;
      });
    }
    return () => {
      vigente = false;
    };
  });
  /** @type {any} */
  let d = $derived({
    ...Object.fromEntries(Object.entries(data).filter(([, v]) => !esPromesa(v))),
    ...llegado
  });

  let org = $derived(d.organizacion);
  /** @type {any} */
  let motor = $derived(d.motor ?? {});

  /**
   * Weekday hours as one line. When the days do not all match it says so
   * rather than printing the first day's hours; "09:00-17:00" beside a
   * calendar where four days run to 17:30 is a summary that is simply wrong,
   * and this is the number an SLA is measured against.
   */
  let hoursSummary = $derived.by(() => {
    if (!d.calendar) return null;
    const open = (d.calendar.days ?? []).filter((/** @type {any} */ dia) => dia.open);
    if (!open.length) return 'Sin horario configurado';
    const first = open[0];
    const uniform = open.every(
      (/** @type {any} */ dia) => dia.open === first.open && dia.close === first.close
    );
    return uniform
      ? `${open.length} días, ${first.open}-${first.close}`
      : `${open.length} días, horario variable`;
  });

  /**
   * Los dos ajustes de la Bandeja en una linea.
   *
   * "Sin definir" se dice, no se omite: es el estado real y el default, y un
   * destino sin valor al lado se lee como "no se pudo cargar" -- que es lo que
   * significa `null` acá, un caso distinto.
   */
  let resumenBandeja = $derived.by(() => {
    const a = motor.ajustesBandeja;
    if (!a) return null;
    const sla = Number(a.sla_toma_minutos) > 0 ? `${a.sla_toma_minutos} min` : null;
    const umbral =
      a.umbral_rx_dbm === null || a.umbral_rx_dbm === undefined
        ? null
        : `${a.umbral_rx_dbm} dBm`;
    if (sla && umbral) return `${sla} · ${umbral}`;
    if (sla) return `${sla} · sin umbral`;
    if (umbral) return `Sin plazo · ${umbral}`;
    return 'Sin definir';
  });

  /** An approval rule set to MANAGER with no named approvers matches nobody. */
  let stuckApprovalRules = $derived(
    (d.approvalRules ?? []).filter(
      (/** @type {any} */ r) => r.is_active && r.approver_role === 'MANAGER' && !r.approvers.length
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
          value: d.peopleTotals
            ? `${d.peopleTotals.count} personas · ${d.peopleTotals.admins} administradores`
            : null,
          warn: d.peopleTotals ? d.peopleTotals.tokens_on_deactivated > 0 : false
        },
        {
          href: '/settings/api-tokens',
          title: 'Tokens de API',
          body: 'Tokens de acceso personal para scripts, integraciones y agentes de IA.',
          value: d.tokenTotals ? `${d.tokenTotals.live} activos` : null,
          warn: d.tokenTotals
            ? d.tokenTotals.orphaned > 0 || d.tokenTotals.unused_90d > 0
            : false
        },
        {
          // Va en 'Personas y acceso' y no en 'Asistente' a proposito: son
          // credenciales, y quien las administra piensa en accesos, no en
          // integraciones. La fila avisa cuando el catalogo pide una clave
          // que no esta cargada -- eso es una herramienta que va a fallar.
          href: '/settings/credenciales',
          title: 'Credenciales',
          body: 'Las claves que el asistente usa para hablar con los sistemas de la empresa.',
          value: motor.credencialesTotales
            ? (motor.credencialesTotales.faltan
                ? `${motor.credencialesTotales.faltan} sin cargar`
                : `${motor.credencialesTotales.cargadas} cargadas`)
            : null,
          warn: motor.credencialesTotales ? motor.credencialesTotales.faltan > 0 : false
        },
        {
          href: '/settings/organization',
          title: 'Organización',
          body: 'Los datos de la empresa que se imprimen en cada factura y cotización.',
          value: org?.company_name || null,
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
          value: d.routingTotals ? `${d.routingTotals.active} reglas` : null,
          warn: d.routingTotals ? d.routingTotals.unrouted_last_30d > 0 : false
        },
        {
          href: '/settings/escalation',
          title: 'Escalamiento',
          body: 'Qué pasa cuando un ticket no cumple su objetivo de respuesta.',
          value: d.escalationTotals
            ? `${d.escalationTotals.active} de ${d.escalationTotals.count} prioridades`
            : null,
          warn: d.escalationTotals ? d.escalationTotals.breaches_unhandled_30d > 0 : false
        },
        {
          href: '/settings/business-hours',
          title: 'Horario laboral',
          body: 'El reloj contra el que se mide cada objetivo de respuesta.',
          value: d.calendar ? `${d.calendar.name} · ${hoursSummary}` : null,
          warn: false
        },
        {
          href: '/settings/ticket-approvals',
          title: 'Reglas de aprobación',
          body: 'Qué bloquea el cierre de un ticket, y quién puede destrabarlo.',
          value: d.approvalTotals ? `${d.approvalTotals.active} activas` : null,
          warn: stuckApprovalRules > 0
        },
        {
          href: '/settings/reopen',
          title: 'Política de reapertura',
          body: 'Si la respuesta de un cliente vuelve a abrir un ticket cerrado.',
          // Admin-only, like people and tokens above: a member's fan-out gets
          // null (the endpoint 403s), so the row lists the destination without
          // a value rather than guessing at the policy.
          value: !d.reopen
            ? null
            : d.reopen.is_enabled
              ? `Dentro de ${d.reopen.reopen_window_days} días`
              : 'Apagada. Lo cerrado sigue cerrado',
          // Replies arriving outside the window are normal for any window, so
          // that number belongs on the page, not on a warning here. Off is the
          // state worth flagging: it makes every reply to a closed ticket
          // vanish, not just the late ones.
          warn: d.reopen ? !d.reopen.is_enabled : false
        },
        {
          href: '/settings/inbound-email',
          title: 'Correo entrante',
          body: 'Las direcciones que convierten un correo en un ticket.',
          value: d.mailboxTotals
            ? `${d.mailboxTotals.active} de ${d.mailboxTotals.count} activas`
            : null,
          // Off AND still receiving, not merely off. An address switched off
          // and left alone is a decision; one still getting mail and creating
          // nothing is a customer being ignored.
          warn: d.mailboxTotals ? d.mailboxTotals.silently_dropping > 0 : false
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
          value: motor.asistente ? `${count(motor.asistente.roles.length)} agentes` : null,
          warn: false
        },
        {
          href: '/settings/areas',
          title: 'Areas de trabajo',
          body: 'Como se agrupa el equipo. Un ticket hereda el area de su responsable.',
          value: motor.asistente?.areas ? `${count(motor.asistente.areas.length)} areas` : null,
          //  Sin areas, TODOS los tickets caen juntos y los tableros por area
          //  quedan vacios. No es cosmetico: es el tablero apagado.
          warn: !!motor.asistente?.areas && motor.asistente.areas.length === 0
        },
        {
          href: '/settings/asistente',
          title: 'Personalidad del asistente',
          body: 'Con que nombre se presenta, en que tono habla y cuanto se extiende.',
          value: motor.asistente
            ? `${motor.asistente.persona.nombre_asistente} · ${motor.asistente.persona.tono}`
            : null,
          warn: false
        },
        {
          href: '/settings/bandeja',
          title: 'Bandeja',
          body: 'Los dos números con los que la Bandeja se permite emitir un veredicto: el plazo de toma y el umbral óptico.',
          value: motor.ajustesBandeja ? resumenBandeja : null,
          // Nunca avisa. Que los dos esten sin definir es el default
          // deliberado --la Bandeja entonces muestra el dato crudo sin
          // afirmar nada-- y no una falta que alguien tenga que ir a
          // corregir. Una advertencia que no hay que atender ensena a
          // ignorar las advertencias.
          warn: false
        },
        {
          // Este SÍ avisa (29/10/2026): una clave sin rótulo es una palabra sin
          // tilde en la cola de cada operador, y nadie se entera al crearla --
          // un caso nuevo de /manual nace así si no se escribió cómo se lee.
          href: '/settings/bandeja',
          title: 'Rótulos de la Bandeja',
          body: 'Cómo se leen en la cola los motivos de escalamiento, las etiquetas y los casos.',
          value:
            motor.sinRotulo === null || motor.sinRotulo === undefined
              ? null
              : motor.sinRotulo === 0
                ? 'Todos con rótulo'
                : `${motor.sinRotulo} sin rótulo`,
          warn: !!motor.sinRotulo
        },
        {
          href: '/settings/canales/whatsapp',
          title: 'WhatsApp',
          body: 'Las credenciales de Meta que activan el canal, y la URL del webhook.',
          value: motor.canalWhatsapp
            ? motor.canalWhatsapp.activo
              ? 'Activo'
              : 'Apagado'
            : null,
          // Avisa cuando esta apagado Y ya tiene numero visible cargado -- es
          // la senal de que alguien empezo la carga y no llego a activarlo,
          // no el estado de "todavia nadie lo toco".
          warn: !!motor.canalWhatsapp && !motor.canalWhatsapp.activo && !!motor.canalWhatsapp.numero_visible
        },
        {
          href: '/settings/canales/avisos',
          title: 'Avisos de campo',
          body: 'Por dónde se le avisa a la cuadrilla cuando un supervisor devuelve un trabajo.',
          // Sin canales nadie recibe nada, y eso NO es un error: es el estado
          // por defecto. Pero vale decirlo, porque hoy esos avisos los escribe
          // alguien a mano.
          value: d.avisosCampo?.cuantos
            ? `${d.avisosCampo.cuantos} canal${d.avisosCampo.cuantos === 1 ? '' : 'es'}`
            : null,
          // Solo cuando la lectura llego y dijo cero: sin dato no se acusa.
          warn: !!d.avisosCampo && !d.avisosCampo.cuantos
        },
        // Solo aparece si el catalogo del tenant declara las herramientas de
        // SmartOLT -- un tenant sin esa integracion no tiene por que ver un
        // destino que no lleva a nada util.
        ...(motor.smartolt?.instalado
          ? [
              {
                href: '/settings/canales/smartolt',
                title: 'SmartOLT',
                body: 'La clave que le da al asistente lectura y reinicio de la ONU del cliente.',
                value: motor.smartolt.tiene_clave ? 'Clave cargada' : null,
                warn: !motor.smartolt.tiene_clave
              }
            ]
          : []),
        // Solo aparece si el tenant tiene el rol 'ventas' -- mismo criterio
        // que SmartOLT arriba.
        ...(motor.asistente?.roles?.includes('ventas')
          ? [
              {
                href: '/settings/planes-venta',
                title: 'Planes de venta',
                body: 'Qué planes se ofrecen a un prospecto nuevo, y en qué localidades.',
                value: motor.planesVenta ? `${count(motor.planesVenta.cantidad)} planes` : null,
                warn: !!motor.planesVenta && motor.planesVenta.cantidad === 0
              },
              {
                href: '/settings/oferta',
                title: 'Servicios y canales',
                body: 'Qué servicios vende la empresa, y la parrilla de TV que consulta el agente.',
                value: motor.oferta
                  ? `${count(motor.oferta.servicios)} servicios · ${count(motor.oferta.canales)} canales`
                  : null,
                // Sin parrilla el agente no puede responder por canales: no es
                // un detalle cosmetico, es una funcionalidad apagada.
                warn: !!motor.oferta && motor.oferta.canales === 0
              }
            ]
          : []),
        // Fuera del gate de 'ventas': las guias de sintonizacion las usa
        // soporte, no ventas. Y van sin condicion porque cualquier ISP que
        // venda television las necesita -- si el tenant no da TV, la pantalla
        // se abre vacia, que es mas barato que esconderla y que alguien la
        // busque.
        {
          href: '/settings/guias-tv',
          title: 'Guías de sintonización',
          body: 'Qué le dice el agente al cliente para sintonizar el televisor, por marca y según use TDT.',
          value: motor.guiasTv ? `${count(motor.guiasTv.activas)} activas` : null,
          warn: !!motor.guiasTv && (!motor.guiasTv.tieneGeneral || !motor.guiasTv.tieneTdt)
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
          value: d.macroTotals ? `${d.macroTotals.org} compartidas` : null,
          warn: d.macroTotals ? d.macroTotals.with_unknown_placeholders > 0 : false
        },
        {
          href: '/settings/tags',
          title: 'Etiquetas',
          body: 'Etiquetas compartidas entre cuentas, prospectos, negociaciones y tickets.',
          value: d.tagTotals ? `${d.tagTotals.active} en uso` : null,
          // Unused tags are housekeeping, not a fault, the tags page lists
          // them without needing the hub to raise an alarm about tidiness.
          warn: false
        },
        {
          href: '/settings/custom-fields',
          title: 'Campos personalizados',
          body: 'Campos que esta organización agregó a los registros.',
          value: d.fieldTotals
            ? `${d.fieldTotals.active} en ${d.fieldTotals.models_extended} tipos de registro`
            : null,
          warn: d.fieldTotals ? d.fieldTotals.required_with_gaps > 0 : false
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
    {org?.name || data.orgNombre}
    {#if org}
      · <span class="v2-num">{count(org.member_count)}</span> miembros · desde
      {shortDate(org.created_at)}
    {/if}
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
