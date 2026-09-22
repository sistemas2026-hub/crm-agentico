<script>
  import '../../app.css';
  import '$lib/v2/styles/v2.css';
  import { page } from '$app/state';
  import { afterNavigate } from '$app/navigation';
  import Sidebar from '$lib/v2/components/Sidebar.svelte';
  import CommandPalette from '$lib/v2/components/CommandPalette.svelte';
  import { Search, Sun, Columns3, LifeBuoy, Receipt, Plus, Menu } from '@lucide/svelte';
  import { barra, recordarPreferencia, resumenRecogido } from '$lib/conversaciones/barra-lateral.svelte.js';

  /** @type {{ data: { counts: Record<string, number>, org: { name: string, terminology?: Record<string, string> | null }, role: string }, children: import('svelte').Snippet }} */
  let { data, children } = $props();

  let paletteOpen = $state(false);

  // The sidebar is hidden below 768px, and the tab bar only carries four of the
  // ~16 destinations. This drawer is how a phone reaches the rest of the nav and
  // the footer: profile, notifications, help, sign out. It reuses the same
  // <Sidebar>, so the two can never drift apart. Closes itself on navigation.
  let menuOpen = $state(false);
  afterNavigate(() => (menuOpen = false));

  /** Focus the panel on open so Escape reaches it and keyboard users land inside. */
  function autofocus(/** @type {HTMLElement} */ node) {
    node.focus();
  }

  /**
   * The five things worth a thumb on a phone. Fewer than the sidebar on
   * purpose. A tab bar that scrolls is a menu wearing a tab bar's clothes.
   */
  const TABS = [
    { href: '/', label: 'Hoy', icon: Sun, exact: true },
    { href: '/pipeline', label: 'Negociaciones', icon: Columns3 },
    { href: '/tickets', label: 'Tickets', icon: LifeBuoy },
    { href: '/invoices', label: 'Facturas', icon: Receipt }
  ];

  const isActive = (href, exact) =>
    exact ? page.url.pathname === href : page.url.pathname.startsWith(href);

  /* La Bandeja se dibuja a pantalla completa, sin la barra lateral ni la
     barra superior de teléfono: tiene su propia barra de consola con la
     marca, los módulos y los indicadores. Es la única ruta así, y es
     deliberado -- es la pantalla donde alguien pasa el turno entero. */
  let esBandeja = $derived(page.url.pathname.startsWith('/conversaciones'));

  /* La preferencia de barra recogida se lee del navegador, así que recién
     cuando hay navegador. En el servidor no existe `localStorage`. */
  /* Las dos preferencias de la Bandeja se leen en el mismo sitio y por el
     mismo motivo: `localStorage` no existe en el servidor, asi que leerlo
     durante el renderizado lo rompe. Un `$effect` corre solo en el navegador. */
  $effect(() => {
    recordarPreferencia();
    resumenRecogido.recordar();
  });

  /* La barra se oculta SÓLO en la Bandeja y SÓLO si esta persona la recogió.
     En el resto del CRM está siempre: es su única navegación. */
  let barraRecogida = $derived(esBandeja && barra.recogida);

  function onkeydown(e) {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      paletteOpen = !paletteOpen;
    } else if (e.key === 'Escape' && menuOpen) {
      menuOpen = false;
    }
  }
</script>

<svelte:head>
  <title>BottleCRM v2</title>
  <meta name="robots" content="noindex" />
</svelte:head>

<svelte:window {onkeydown} />

<!-- `sin-barra`: la Bandeja ocupa la pantalla entera.
     Es una consola de operación, no una página del CRM: se entra y se pasan
     horas ahí, y los 222px de la barra lateral salían de las tres columnas
     --la cola, la conversación y el contexto-- que son lo único que se usa.
     Con la barra oculta, la referencia congelada cierra: 360/730/350 sobre
     1440 en vez de 304/610/304.
     La navegación NO se pierde: la barra de consola de la Bandeja lleva la
     marca (que vuelve al inicio) y los módulos operativos. Ver
     `conversaciones/+layout.svelte`. -->
<div class="v2-root v2-shell" class:sin-barra={barraRecogida}>
  {#if !barraRecogida}
    <Sidebar
      counts={data.counts}
      org={data.org}
      role={data.role}
      terminology={data.org.terminology}
      onsearch={() => (paletteOpen = true)}
    />
  {/if}
  <div class="v2-main">
    <!-- Phone top bar. The sidebar is hidden below 768px; this replaces the
         org mark and the search affordance it carried.
         No en la Bandeja: ahí la barra de consola ya lleva marca, módulos y
         buscador, y dos barras superiores en un teléfono se comen la
         pantalla. -->
    {#if !esBandeja}
    <div class="v2-mobile-top">
      <button
        class="v2-btn v2-btn-quiet"
        type="button"
        onclick={() => (menuOpen = true)}
        aria-label="Abrir menú"
        aria-expanded={menuOpen}
      >
        <Menu />
      </button>
      <span class="v2-mark">{data.org.name.slice(0, 1)}</span>
      <h2>{data.org.name}</h2>
      <button
        class="v2-btn v2-btn-quiet"
        type="button"
        style="margin-left:auto"
        onclick={() => (paletteOpen = true)}
        aria-label="Buscar"
      >
        <Search />
      </button>
    </div>
    {/if}

    {@render children()}

    <!-- Tampoco en la Bandeja: sus 58px salían del hilo, que a 390px ya era
         lo más apretado de la pantalla. Los módulos están arriba, en la barra
         de consola, que en angosto se desplaza en horizontal. -->
    {#if !esBandeja}
      <nav class="v2-tabbar" aria-label="Secciones">
        {#each TABS as tab (tab.href)}
          <a href={tab.href} aria-current={isActive(tab.href, tab.exact) ? 'page' : undefined}>
            <tab.icon />
            {tab.label}
          </a>
        {/each}
      </nav>
    {/if}
  </div>

  <!-- Both live inside .v2-root so they inherit the scoped tokens; both are
       position:fixed, so the shell's overflow:hidden does not clip them.

       NOT on the inbox. The FAB is "nueva negociación" -- a sales shortcut with
       nothing to do with answering a client -- and it is `position: fixed;
       z-index: 30`, so on a phone it lands ON TOP of the composer. Measured on
       21/09/2026 at 390px: it covered 40% of the "Enviar" button, and a tap on
       that corner navigated to /pipeline/new, losing the reply being typed.
       Raising the composer instead would only move the collision somewhere
       else; on this screen the shortcut simply does not belong. -->
  {#if !page.url.pathname.startsWith('/conversaciones')}
    <a class="v2-fab" href="/pipeline/new" aria-label="Nueva negociación"><Plus size={21} /></a>
  {/if}

  <!-- Mobile navigation drawer. Only openable from the mobile top bar, so it
       never surfaces on desktop; a backdrop click, Escape, or navigating all
       close it. It renders the same <Sidebar> the desktop shows. -->
  {#if menuOpen}
    <div
      class="v2-drawer-scrim"
      role="presentation"
      onclick={(e) => {
        if (e.target === e.currentTarget) menuOpen = false;
      }}
    >
      <div
        class="v2-drawer"
        role="dialog"
        aria-modal="true"
        aria-label="Navegación"
        tabindex="-1"
        use:autofocus
        onkeydown={(e) => {
          if (e.key === 'Escape') {
            e.preventDefault();
            menuOpen = false;
          }
        }}
      >
        <Sidebar
          counts={data.counts}
          org={data.org}
          role={data.role}
          terminology={data.org.terminology}
          onsearch={() => {
            menuOpen = false;
            paletteOpen = true;
          }}
        />
      </div>
    </div>
  {/if}

  <CommandPalette open={paletteOpen} onclose={() => (paletteOpen = false)} />
</div>
