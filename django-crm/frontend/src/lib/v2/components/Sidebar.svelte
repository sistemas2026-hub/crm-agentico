<script>
  import { page } from '$app/state';
  import {
    Sun,
    Columns3,
    Target,
    Building2,
    Users,
    CircleCheck,
    LifeBuoy,
    BookOpen,
    Receipt,
    Trophy,
    Clock,
    UserCog,
    CircleUser,
    CircleHelp,
    FileText,
    Bell,
    SlidersHorizontal,
    Search,
    Smartphone,
    LogOut,
    Sparkles,
    MessageCircle,
    PlugZap,
    GraduationCap,
    Gauge,
    ClipboardCheck,
    Radar,
    Boxes,
    Activity,
    Bot,
    Cable,
    Download,
    BookMarked
  } from '@lucide/svelte';
  import { t } from '$lib/terminology.js';

  /**
   * One flat tree, grouped by what the person is doing rather than by which
   * Django app owns the model. Every label matches the route it lands on and
   * the page title it lands on; "Pipeline" goes to /v2/pipeline, which is
   * titled "Pipeline".
   *
   * v1 had /leads listed twice, as "Pipeline" and as "Leads", and a "Deals"
   * entry pointing at /opportunities while /deals 404'd.
   *
   * `role` is server-derived from the JWT (see the app layout loader). It only
   * decides which destinations to *show*. Every hidden one is still enforced
   * by the backend, so this is UX, not access control. An item marked `admin`
   * is one where a member gets nothing but a "for administrators" gate, so
   * showing it would only teach them to bounce off it.
   *
   * `termKey` marks the handful of entity destinations a vertical pack may
   * relabel (see `$lib/terminology.js`). The string in `label` below is only
   * ever the fallback an org with no pack, or no override for that key,
   * still renders; the derived `groups` below is what actually resolves it
   * against `terminology`. No other label branches on the org at all.
   *
   * @type {{
   *   counts?: Record<string, number>,
   *   org?: { name: string },
   *   role?: string,
   *   terminology?: Record<string, string> | null,
   *   onsearch?: () => void
   * }}
   */
  let {
    counts = {},
    org = { name: 'BottleCRM' },
    role = 'USER',
    terminology = undefined,
    onsearch = () => {}
  } = $props();

  /*
   * Grupos por TRABAJO, del mas urgente al menos (22/10/2026). Antes el
   * primero era "Vender" -- la portada de BottleCRM -- y toda la operacion
   * del ISP cabia en "Atender", con 14 entradas y dos iconos repetidos
   * (Radar dos veces, Network dos veces). Ningun destino se quito: solo
   * cambiaron de grupo, y cada uno tiene ahora un icono propio.
   */
  const GROUPS = [
    {
      label: 'Operación en vivo',
      items: [
        { href: '/', label: 'Hoy', icon: Sun, exact: true },
        { href: '/conversaciones', label: 'Conversaciones', icon: MessageCircle },
        { href: '/supervisor-noc', label: 'Supervisor NOC IA', icon: Activity },
        // Que hace cada agente AHORA. /agentes dice como esta configurado
        // cada uno; esto, en que anda en este momento -- son dos preguntas
        // distintas y por eso son dos entradas.
        { href: '/centro-mando', label: 'Centro de mando', icon: Radar },
        { href: '/asistente', label: 'Asistente', icon: Sparkles }
      ]
    },
    {
      label: 'Campo',
      items: [
        // La bandeja donde se decide la factibilidad de cada solicitud.
        // Existia desde el 02/09 y NO estaba enlazada en ningun lado: solo
        // se llegaba escribiendo la URL. Una pantalla sin entrada no esta
        // terminada, esta escondida.
        { href: '/instalaciones', label: 'Instalaciones', icon: ClipboardCheck },
        // Que hay en bodega y que tiene cada tecnico. Va aca y no bajo
        // Configurar porque es una pantalla de OPERACION: se abre para
        // decidir si se puede despachar, no para ajustar nada.
        { href: '/inventario', label: 'Inventario', icon: Boxes }
      ]
    },
    {
      label: 'Clientes',
      items: [
        // Approvals and Analytics live under Tickets as section tabs. They are
        // not separate destinations, so they do not get separate nav entries,
        // one level of navigation, and the tab strip carries the rest.
        { href: '/tickets', label: 'Tickets', icon: LifeBuoy, count: 'tickets' },
        { href: '/tasks', label: 'Tareas', icon: CircleCheck, count: 'tasks' },
        { href: '/accounts', label: 'Cuentas', icon: Building2, termKey: 'account.plural' },
        { href: '/contacts', label: 'Contactos', icon: Users, termKey: 'contact.plural' },
        { href: '/solutions', label: 'Base de conocimiento', icon: BookOpen },
        { href: '/documents', label: 'Documentos', icon: FileText }
      ]
    },
    {
      label: 'Ventas',
      items: [
        {
          href: '/pipeline',
          label: 'Negociaciones',
          icon: Columns3,
          count: 'pipeline',
          termKey: 'opportunity.plural'
        },
        { href: '/leads', label: 'Prospectos', icon: Target, count: 'leads', termKey: 'lead.plural' },
        { href: '/goals', label: 'Objetivos', icon: Trophy }
      ]
    },
    {
      label: 'Facturación',
      items: [
        {
          href: '/invoices',
          label: 'Facturas',
          icon: Receipt,
          count: 'invoices',
          termKey: 'invoice.plural'
        },
        { href: '/timesheet', label: 'Registro de horas', icon: Clock }
      ]
    },
    {
      // Lo que se ajusta de la IA: quien atiende, que sigue al pie de la
      // letra, de que ejemplos aprende, y donde se la prueba sin un cliente.
      label: 'Dexter',
      items: [
        { href: '/agentes', label: 'Agentes', icon: Bot },
        // ADMIN-only: una habilidad vigente es lo que un agente sigue "al pie
        // de la letra" frente a un cliente.
        { href: '/habilidades', label: 'Habilidades', icon: GraduationCap, admin: true },
        { href: '/manual', label: 'Manual', icon: BookMarked },
        { href: '/simulador-whatsapp', label: 'Simulador WhatsApp', icon: Smartphone }
      ]
    },
    {
      // Administration, kept apart from the work. Someone who never touches
      // these should not read past them four times a day.
      //
      // Team is admin-only. A member reaches it only to be told so. Settings
      // is not: the hub is readable by any member (it just omits admin-only
      // counts), so it stays for everyone.
      label: 'Administrar',
      items: [
        { href: '/team', label: 'Equipo y accesos', icon: UserCog, admin: true },
        { href: '/settings', label: 'Configuración', icon: SlidersHorizontal },
        // ADMIN-only: el rol 'configuracion_guiada' del motor solo lo
        // alcanza esta pantalla (ver /api/configuracion-guiada, mismo gate
        // que /api/agentes). Sin esto en el menu, la unica forma de llegar
        // seria escribiendo la URL a mano.
        // Dos caminos para lo mismo, y no se pisan: el catalogo es para un
        // sistema YA verificado (se elige de una lista y trae sus filtros
        // hechos); la guiada es para uno que nadie conecto todavia (se
        // describe la API, se sondea de verdad, y sale una propuesta).
        { href: '/conectores', label: 'Conectar sistema', icon: PlugZap, admin: true },
        { href: '/configuracion-guiada', label: 'Conectar API nueva', icon: Cable, admin: true },
        // ADMIN-only: es el gasto de la empresa y su tope. Un colaborador de
        // soporte no tiene por que ver la factura.
        { href: '/consumo', label: 'Consumo', icon: Gauge, admin: true }
      ]
    }
  ];

  // Drop admin-only items for members, resolve any relabelled entity through
  // the terminology map, then drop any group left with nothing.
  let groups = $derived(
    GROUPS.map((group) => ({
      ...group,
      items: group.items
        .filter((item) => role === 'ADMIN' || !item.admin)
        .map((item) =>
          item.termKey ? { ...item, label: t(terminology, item.termKey, item.label) } : item
        )
    })).filter((group) => group.items.length > 0)
  );

  const isActive = (href, exact) =>
    exact ? page.url.pathname === href : page.url.pathname.startsWith(href);
</script>

<nav class="v2-nav" aria-label="Principal">
  <!-- La marca es la del producto; la empresa va debajo. Con un solo nombre
       arriba no se sabia si se estaba en Dexter o en el sistema del ISP. -->
  <div class="v2-org">
    <span class="v2-mark" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round">
        <path d="M5 12a7 7 0 0 1 14 0M8.5 12a3.5 3.5 0 0 1 7 0M12 13v7" />
      </svg>
    </span>
    <span class="v2-org-texto">
      <b>Dexter</b>
      <span>{org.name}</span>
    </span>
  </div>

  <!--
    No entry appears here without a route behind it. v1's "Deals" pointed at
    /opportunities while /deals 404'd; an Inbox link with nothing behind it
    would be the same mistake.
  -->
  {#each groups as group (group.label)}
    <div class="v2-nav-group v2-label">{group.label}</div>
    {#each group.items as item (item.href)}
      <a
        class="v2-link"
        href={item.href}
        aria-current={isActive(item.href, item.exact) ? 'page' : undefined}
      >
        <item.icon />
        {item.label}
        {#if item.count && counts[item.count]}
          <span class="v2-count">{counts[item.count]}</span>
        {/if}
      </a>
    {/each}
  {/each}

  <div class="v2-nav-foot">
    <button class="v2-link v2-nav-search" type="button" onclick={onsearch}>
      <Search />
      Buscar
      <span class="v2-count">⌘K</span>
    </button>
    <!-- Personal, not work: your own feed sits with your own profile rather
         than in Serve, where it would read as a queue the team shares. -->
    <a
      class="v2-link"
      href="/notifications"
      aria-current={isActive('/notifications', false) ? 'page' : undefined}
    >
      <Bell />
      Notificaciones
      {#if counts.notifications}
        <span class="v2-count">{counts.notifications}</span>
      {/if}
    </a>
    <a class="v2-link" href="/profile">
      <CircleUser />
      Tu perfil
    </a>
    <a class="v2-link" href="/support">
      <CircleHelp />
      Ayuda
    </a>
    <!-- The phone app for people on the hosted service. No pulsing dot. A
         download link is not something that needs you right now, and v2 keeps
         attention for the things that do. -->
    <a
      class="v2-link"
      href="https://play.google.com/store/apps/details?id=io.bottlecrm&hl=en"
      target="_blank"
      rel="noopener noreferrer"
    >
      <Download />
      Descargar app
    </a>
    <!-- Leaving the app. Last in the list, and a plain link. /logout is a
         server load that clears the auth cookies and redirects to /login, so a
         GET navigation is all it takes and no data-fetching component follows. -->
    <a class="v2-link" href="/logout" data-sveltekit-reload>
      <LogOut />
      Cerrar sesión
    </a>
  </div>
</nav>

<style>
  /* Search opens an overlay rather than navigating, so it is a button. It
     borrows .v2-link for everything else. A control that sits in a list of
     links should not look like the odd one out. */
  .v2-nav-search {
    width: 100%;
    background: none;
    border: 0;
    font-family: inherit;
    font-size: inherit;
    text-align: left;
    cursor: pointer;
  }
  .v2-org-texto {
    display: flex;
    flex-direction: column;
    line-height: 1.2;
    min-width: 0;
  }
  .v2-org-texto span {
    font-size: 12px;
    color: var(--v2-nav-label);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
</style>
