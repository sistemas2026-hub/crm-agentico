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
    Funnel,
    ChevronDown
  } from '@lucide/svelte';
  import { slide } from 'svelte/transition';
  import { untrack } from 'svelte';
  import { gruposDelMenu, estaActiva } from '$lib/v2/menu.js';
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

  const isActive = (href, exact) => estaActiva({ href, exact }, page.url.pathname);

  /*
   * LAS ENTRADAS CON SUBPANTALLAS SE DESPLIEGAN  --  13/11/2026
   * ----------------------------------------------------------
   * Hoy es Supervisor NOC. Tocarla abre o cierra la lista; no navega, para no
   * cargar Pendientes cuando uno va a Despacho. Qué queda abierto se recuerda
   * en el navegador (es comodidad de quien mira, no un dato), y si esa lectura
   * falla el menú igual funciona: abierto si se está dentro de la sección.
   *
   * Al ENTRAR a la sección desde afuera —un enlace, el buscador— se abre sola,
   * para que se vea dónde se está. Moverse dentro de ella no la reabre si la
   * persona la cerró a propósito.
   */
  const CLAVE_ABIERTOS = 'dexter.menu.abiertos';
  /** @type {Record<string, boolean>} */
  let abiertos = $state({});
  $effect(() => {
    try {
      const guardado = JSON.parse(localStorage.getItem(CLAVE_ABIERTOS) ?? '{}');
      if (guardado && typeof guardado === 'object') {
        untrack(() => (abiertos = { ...guardado, ...abiertos }));
      }
    } catch {
      /* sin almacenamiento: se queda con lo que hay */
    }
  });

  /** @param {string} href @param {boolean} valor */
  function fijarAbierto(href, valor) {
    abiertos = { ...abiertos, [href]: valor };
    try {
      localStorage.setItem(CLAVE_ABIERTOS, JSON.stringify(abiertos));
    } catch {
      /* sin almacenamiento: dura lo que dure la página */
    }
  }

  /** Secciones con hijos en las que se estaba en la navegación anterior. */
  /** @type {Set<string>} */
  let dentroAntes = new Set();
  $effect(() => {
    const ruta = page.url.pathname;
    const dentro = new Set();
    for (const g of groups) {
      for (const i of g.items) {
        if (i.hijos && estaActiva(i, ruta)) dentro.add(i.href);
      }
    }
    untrack(() => {
      for (const href of dentro) {
        if (!dentroAntes.has(href)) fijarAbierto(href, true);
      }
    });
    dentroAntes = dentro;
  });

  /** @param {{ href: string, hijos?: any[] }} item */
  const estaAbierto = (item) => abiertos[item.href] ?? estaActiva(item, page.url.pathname);

  //  El despliegue respeta a quien pidió menos movimiento: la transición de
  //  Svelte corre en JavaScript y no ve la consulta de CSS.
  const sinMovimiento =
    typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
  const DESPLIEGUE = { duration: sinMovimiento ? 0 : 160 };
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
      {#if item.hijos?.length}
        {@const abierto = estaAbierto(item)}
        {@const idLista = `v2-sub-${item.href.replace(/[^a-z0-9]+/gi, '-')}`}
        <button
          class="v2-link v2-nav-padre"
          class:v2-nav-padre-dentro={estaActiva(item, page.url.pathname)}
          type="button"
          aria-expanded={abierto}
          aria-controls={idLista}
          onclick={() => fijarAbierto(item.href, !abierto)}
        >
          <item.icon />
          <span class="v2-nav-padre-texto">{item.label}</span>
          <!-- Cerrada, la insignia va en el padre; abierta, en su subpantalla. -->
          {#if !abierto && item.count && counts[item.count]}
            <span class="v2-count">{counts[item.count]}</span>
          {/if}
          <span class="v2-nav-flecha" class:v2-nav-flecha-abierta={abierto} aria-hidden="true">
            <ChevronDown />
          </span>
        </button>
        {#if abierto}
          <div class="v2-nav-sub" id={idLista} transition:slide={DESPLIEGUE}>
            {#each item.hijos as hijo (hijo.href)}
              <a
                class="v2-link v2-nav-hijo"
                href={hijo.href}
                aria-current={estaActiva(hijo, page.url.pathname) ? 'page' : undefined}
              >
                {hijo.label}
                {#if hijo.count && counts[hijo.count]}
                  <span class="v2-count">{counts[hijo.count]}</span>
                {/if}
              </a>
            {/each}
          </div>
        {/if}
      {:else}
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
      {/if}
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
  /* El padre que despliega: un botón con la cara de un enlace del menú. */
  .v2-nav-padre {
    width: 100%;
    background: none;
    border: 0;
    font-family: inherit;
    font-size: inherit;
    text-align: left;
    cursor: pointer;
  }
  /* Con la insignia y la flecha, «Supervisor NOC IA» se partía en dos líneas
     en los 236 px de la barra: la fila se aprieta y el nombre va en una. */
  .v2-nav-padre {
    gap: 8px;
    padding-right: 4px;
  }
  .v2-nav-padre-texto {
    flex: 1;
    min-width: 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  /* Dentro de la sección pero con la lista cerrada: que se note dónde se está
     sin pintarlo como la pantalla activa (esa es la subpantalla). */
  .v2-nav-padre-dentro {
    color: #fff;
    font-weight: 650;
  }
  .v2-nav-padre .v2-count {
    margin-left: 0;
    min-width: 18px;
    padding: 0 5px;
  }
  .v2-nav-flecha {
    display: inline-flex;
    flex: none;
    margin-left: -4px;
    opacity: 0.7;
    transition: transform 160ms ease-out;
  }
  .v2-nav-flecha :global(svg) {
    width: 14px;
    height: 14px;
  }
  .v2-nav-flecha-abierta {
    transform: rotate(180deg);
  }
  @media (prefers-reduced-motion: reduce) {
    .v2-nav-flecha {
      transition: none;
    }
  }
  /* Las subpantallas: alineadas con el texto del padre (10 de margen + 17 del
     ícono + 10 de separación), con una guía a la izquierda que las agrupa. */
  .v2-nav-sub {
    position: relative;
    margin: 1px 0 4px;
  }
  .v2-nav-sub::before {
    content: '';
    position: absolute;
    left: 18px;
    top: 4px;
    bottom: 4px;
    width: 1px;
    background: var(--v2-nav-line);
  }
  .v2-nav-hijo {
    padding-left: 37px;
    min-height: 32px;
    font-size: 13px;
  }
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
