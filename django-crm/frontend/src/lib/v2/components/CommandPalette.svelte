<script>
  import { goto } from '$app/navigation';
  import {
    Search,
    Columns3,
    Building2,
    Users,
    Target,
    LifeBuoy,
    Receipt,
    BookOpen,
    Plus,
    CornerDownLeft,
    Sun,
    MessageCircle,
    Activity,
    ClipboardCheck,
    Bot,
    CircleCheck,
    Wrench,
    UserRound
  } from '@lucide/svelte';
  import { accionesDePaleta } from '$lib/v2/paleta.js';

  /**
   * One search across every record type, opened with ⌘K.
   *
   * Empty query shows actions rather than an empty box.
   *
   * DESDE EL 12/11/2026 llega a lo que trabaja un ISP: conversaciones (por el
   * texto de sus mensajes, con el buscador de la Bandeja), solicitudes de
   * instalación y órdenes de campo, y las acciones llevan a la Bandeja, al
   * Supervisor NOC, a Instalaciones y a Agentes. `role` y `ocultos` vienen del
   * layout (del servidor): una acción a una pantalla que el rol no abre, o a un
   * módulo que la empresa ocultó, no se ofrece (`lib/v2/paleta.js`).
   *
   * @type {{ open: boolean, onclose: () => void, role?: string, ocultos?: string[] }}
   */
  let { open = false, onclose, role = 'USER', ocultos = [] } = $props();

  /** @type {Record<string, any>} */
  const ICONO_ACCION = { Sun, MessageCircle, Activity, ClipboardCheck, Bot, Plus, CircleCheck, Receipt };
  let acciones = $derived(
    accionesDePaleta({ role, ocultos }).map((a) => ({ ...a, icon: ICONO_ACCION[a.icono] ?? Plus }))
  );

  const ICON = {
    Conversaciones: MessageCircle,
    Instalaciones: ClipboardCheck,
    'Órdenes': Wrench,
    Clientes: UserRound,
    Negociaciones: Columns3,
    Cuentas: Building2,
    Contactos: Users,
    Prospectos: Target,
    Tickets: LifeBuoy,
    Facturas: Receipt,
    'Base de conocimiento': BookOpen,
    Acciones: Plus
  };

  let query = $state('');
  let hits = $state(/** @type {any[]} */ ([]));
  /** Las fuentes que no contestaron a tiempo: la paleta lo dice en vez de
   *  afirmar que nada coincide. */
  let incompletas = $state(/** @type {string[]} */ ([]));
  let cursor = $state(0);
  /** @type {HTMLInputElement | undefined} */
  let input = $state();

  let rows = $derived(query.trim() ? hits : acciones);

  /** Grouped for display, but `rows` stays flat so ↑/↓ crosses group borders. */
  let groups = $derived(
    rows.reduce((acc, r) => {
      const g = acc.find((x) => x.kind === r.kind);
      if (g) g.rows.push(r);
      else acc.push({ kind: r.kind, rows: [r] });
      return acc;
    }, /** @type {{kind: string, rows: any[]}[]} */ ([]))
  );

  // Re-runs whenever the query changes. `seq` drops out-of-order responses,
  // and the request goes to /api/search, a server route that scopes to the
  // org and keeps the httpOnly token off the client.
  //
  // CON PAUSA (12/11/2026). Ahora cada búsqueda llega también al motor, que
  // atiende la Bandeja y los turnos de WhatsApp (PRD §8.21): una por tecla
  // eran cinco pedidos para escribir «perez». Se espera ESPERA_TECLA_MS sin
  // teclear, y un pedido viejo se aborta cuando sale el nuevo.
  const ESPERA_TECLA_MS = 250;
  let seq = 0;
  $effect(() => {
    const q = query;
    const mine = ++seq;
    if (!q.trim()) {
      hits = [];
      incompletas = [];
      cursor = 0;
      return;
    }
    const control = new AbortController();
    const reloj = setTimeout(() => {
      fetch(`/api/search?q=${encodeURIComponent(q)}`, { signal: control.signal })
        .then((r) => r.json())
        .then((r) => {
          if (mine !== seq) return;
          hits = r.results || [];
          incompletas = r.incompletas || [];
          cursor = 0;
        })
        .catch(() => {
          if (mine !== seq) return;
          hits = [];
          incompletas = ['la búsqueda'];
          cursor = 0;
        });
    }, ESPERA_TECLA_MS);
    return () => {
      clearTimeout(reloj);
      control.abort();
    };
  });

  $effect(() => {
    if (open) input?.focus();
  });

  function onkeydown(e) {
    if (e.key === 'Escape') {
      e.preventDefault();
      onclose();
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      cursor = rows.length ? (cursor + 1) % rows.length : 0;
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      cursor = rows.length ? (cursor - 1 + rows.length) % rows.length : 0;
    } else if (e.key === 'Enter') {
      e.preventDefault();
      choose(rows[cursor]);
    }
  }

  function choose(row) {
    if (!row) return;
    onclose();
    query = '';
    goto(row.href);
  }
</script>

{#if open}
  <!--
    A backdrop click closes; that is a convenience, not the only way out, so
    the keyboard handler on the dialog carries Escape. Nothing here is
    reachable by mouse alone that is not also reachable by key alone.
  -->
  <div
    class="v2-scrim"
    role="presentation"
    onclick={(e) => {
      if (e.target === e.currentTarget) onclose();
    }}
  >
    <div
      class="v2-palette"
      role="dialog"
      aria-modal="true"
      aria-label="Buscar"
      tabindex="-1"
      {onkeydown}
    >
      <div class="v2-palette-input">
        <Search size={17} style="color:var(--v2-slate);flex:none" />
        <input
          bind:this={input}
          bind:value={query}
          type="text"
          placeholder="Buscar conversaciones, tickets, instalaciones, órdenes, clientes…"
          aria-label="Buscar"
          aria-autocomplete="list"
          autocomplete="off"
          spellcheck="false"
        />
        <kbd class="v2-kbd">esc</kbd>
      </div>

      <div class="v2-palette-list" role="listbox" aria-label="Resultados">
        {#each groups as group (group.kind)}
          <div class="v2-palette-group v2-label">{group.kind}</div>
          {#each group.rows as row (row.id)}
            {@const i = rows.indexOf(row)}
            {@const Icon = row.icon ?? ICON[row.kind] ?? Search}
            <button
              class="v2-palette-row"
              type="button"
              role="option"
              aria-selected={i === cursor}
              onmouseenter={() => (cursor = i)}
              onclick={() => choose(row)}
            >
              <Icon />
              <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap"
                >{row.title}</span
              >
              {#if row.meta}<span class="v2-palette-meta">{row.meta}</span>{/if}
            </button>
          {/each}
        {:else}
          <p class="v2-sub" style="padding:22px 15px;text-align:center;margin:0">
            {#if incompletas.length}
              Nada coincide con “{query}” en lo que se pudo leer; no contestó {incompletas.join(' ni ')}.
            {:else}
              Nada coincide con “{query}”. Probá un número de orden (OT-12), el nombre de quien pidió
              una instalación, o algo que se haya escrito en una conversación.
            {/if}
          </p>
        {/each}
      </div>

      <div class="v2-palette-foot">
        <span><kbd class="v2-kbd">↑</kbd> <kbd class="v2-kbd">↓</kbd> mover</span>
        <span><CornerDownLeft size={11} style="vertical-align:-1px" /> abrir</span>
        <span><kbd class="v2-kbd">esc</kbd> cerrar</span>
        {#if query.trim()}
          <span style="margin-left:auto" class="v2-num"
            >{hits.length} encontrados{#if incompletas.length && hits.length}
              · sin {incompletas.join(' ni ')}{/if}</span
          >
        {/if}
      </div>
    </div>
  </div>
{/if}
