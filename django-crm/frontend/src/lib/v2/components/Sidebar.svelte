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
    Network,
    MessageCircle,
    ListChecks
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

  const GROUPS = [
    {
      label: 'Vender',
      items: [
        { href: '/', label: 'Hoy', icon: Sun, exact: true },
        {
          href: '/pipeline',
          label: 'Negociaciones',
          icon: Columns3,
          count: 'pipeline',
          termKey: 'opportunity.plural'
        },
        { href: '/leads', label: 'Prospectos', icon: Target, count: 'leads', termKey: 'lead.plural' },
        { href: '/accounts', label: 'Cuentas', icon: Building2, termKey: 'account.plural' },
        { href: '/contacts', label: 'Contactos', icon: Users, termKey: 'contact.plural' },
        { href: '/goals', label: 'Objetivos', icon: Trophy }
      ]
    },
    {
      label: 'Atender',
      items: [
        { href: '/tasks', label: 'Tareas', icon: CircleCheck, count: 'tasks' },
        // Approvals and Analytics live under Tickets as section tabs. They are
        // not separate destinations, so they do not get separate nav entries,
        // one level of navigation, and the tab strip carries the rest.
        { href: '/tickets', label: 'Tickets', icon: LifeBuoy, count: 'tickets' },
        { href: '/asistente', label: 'Asistente', icon: Sparkles },
        { href: '/conversaciones', label: 'Conversaciones', icon: MessageCircle },
        { href: '/simulador-whatsapp', label: 'Simulador WhatsApp', icon: Smartphone },
        { href: '/agentes', label: 'Agentes', icon: Network },
        { href: '/manual', label: 'Manual', icon: ListChecks },
        { href: '/solutions', label: 'Base de conocimiento', icon: BookOpen },
        { href: '/documents', label: 'Documentos', icon: FileText }
      ]
    },
    {
      label: 'Facturar',
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
      // Administration, kept apart from the work. Someone who never touches
      // these should not read past them four times a day.
      //
      // Team is admin-only. A member reaches it only to be told so. Settings
      // is not: the hub is readable by any member (it just omits admin-only
      // counts), so it stays for everyone.
      label: 'Administrar',
      items: [
        { href: '/team', label: 'Equipo y accesos', icon: UserCog, admin: true },
        { href: '/settings', label: 'Configuración', icon: SlidersHorizontal }
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
  <div class="v2-org">
    <span class="v2-mark">{org.name.slice(0, 1)}</span>
    <b>{org.name}</b>
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
      <Smartphone />
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
</style>
