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
    TrendingUp,
    ClipboardCheck,
    Radar,
    Boxes,
    Activity,
    Bot,
    Cable,
    BookMarked,
    Moon,
    Funnel
  } from '@lucide/svelte';
  import { gruposDelMenu } from '$lib/v2/menu.js';
  import { alternarTema, leerTema } from '$lib/v2/tema.js';

  // El tema se lee del navegador, asi que recien cuando hay navegador: en el
  // servidor no existe localStorage. Arranca en claro (ver lib/v2/tema.js).
  let oscuro = $state(false);
  $effect(() => {
    oscuro = leerTema() === 'oscuro';
  });

  /**
   * El árbol del menú vive en `$lib/v2/menu.js` desde el 12/11/2026, como
   * función pura y con su prueba: qué ve cada rol, qué renombra la terminología
   * de la empresa y qué módulos heredados ocultó la empresa
   * (`/settings/modulos`). Acá solo se pone el ícono y se dibuja.
   *
   * `role` sale del JWT en el servidor (layout). Solo decide qué se MUESTRA:
   * cada destino oculto lo sigue exigiendo su backend.
   *
   * `ocultos` viaja en la misma respuesta de la organización que ya trae la
   * terminología: si esa lectura falla o vence, llega vacío y el menú se
   * dibuja ENTERO. Ante la duda se muestra -- ocultar no protege nada, y
   * esconder sin saber deja a alguien sin camino a su pantalla.
   *
   * @type {{
   *   counts?: Record<string, number>,
   *   org?: { name: string },
   *   role?: string,
   *   terminology?: Record<string, string> | null,
   *   ocultos?: string[],
   *   onsearch?: () => void
   * }}
   */
  let {
    counts = {},
    org = { name: '' },
    role = 'USER',
    terminology = undefined,
    ocultos = [],
    onsearch = () => {}
  } = $props();

  /** @type {Record<string, any>} */
  const ICONOS = {
    Sun, Columns3, Target, Building2, Users, CircleCheck, LifeBuoy, BookOpen, Receipt,
    Trophy, Clock, UserCog, FileText, SlidersHorizontal, Smartphone, Sparkles,
    MessageCircle, PlugZap, GraduationCap, Gauge, TrendingUp, ClipboardCheck, Radar,
    Boxes, Activity, Bot, Cable, BookMarked, Funnel
  };

  let groups = $derived(
    gruposDelMenu({ role, terminology, ocultos }).map((g) => ({
      ...g,
      items: g.items.map((i) => ({ ...i, icon: ICONOS[i.icono] ?? Search }))
    }))
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
    <!-- Un boton, no un enlace: cambia el tema en el lugar, no navega. -->
    <button
      class="v2-link v2-nav-search"
      type="button"
      aria-pressed={oscuro}
      onclick={() => (oscuro = alternarTema() === 'oscuro')}
    >
      <Moon />
      Tema oscuro
      <span class="v2-count">{oscuro ? 'Sí' : 'No'}</span>
    </button>
    <!-- Aca iba "Descargar app", que abria la app de BottleCRM en Play Store
         (io.bottlecrm). La de Dexter es la de campo (com.dexter.campo): un
         solo APK para todas las empresas, que hoy se instala a mano y no esta
         publicado en ningun lado. Cuando tenga una URL de descarga, vuelve con
         esa URL; mientras tanto un enlace a otra app es peor que ninguno. -->
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
