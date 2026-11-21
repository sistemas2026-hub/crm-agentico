<!--
  EL PULSO DEL NOC  --  21/11/2026 (rediseño aprobado del Supervisor NOC).

  La misma franja arriba de las siete subpantallas: seis cifras que dicen si
  hay que ir a algún lado, y cada una lleva a su pantalla. La lógica vive en
  lib/supervisor/pulso.js; acá solo se pide y se dibuja.

  Se pide DESPUÉS de dibujar (no en el `load`), así nunca demora una
  subpantalla, y se refresca cada 60 s solo con la pestaña visible —el
  servidor recuerda el mismo minuto, así que pedirla más seguido no traería
  nada nuevo—.
-->
<script>
  import { page } from '$app/state';
  import { onMount } from 'svelte';
  import { fichaActiva } from '$lib/supervisor/pulso.js';

  const REFRESCO_MS = 60_000;

  /** @type {import('$lib/supervisor/pulso.js').Ficha[] | null} */
  let fichas = $state(null);
  let fallo = $state(false);

  const activa = $derived(fichas ? fichaActiva(fichas, page.url.pathname) : null);

  async function leer() {
    try {
      const r = await fetch('/supervisor-noc/pulso', { headers: { accept: 'application/json' } });
      if (!r.ok) throw new Error(String(r.status));
      const d = await r.json();
      fichas = Array.isArray(d?.fichas) ? d.fichas : null;
      fallo = !fichas;
    } catch {
      //  Se queda con lo último que llegó; si nunca llegó nada, lo dice.
      fallo = fichas === null;
    }
  }

  onMount(() => {
    leer();
    const t = setInterval(() => {
      if (document.visibilityState === 'visible') leer();
    }, REFRESCO_MS);
    return () => clearInterval(t);
  });
</script>

<nav class="pulso" aria-label="Pulso del NOC">
  {#if fichas}
    {#each fichas as f (f.clave)}
      <a
        class="pulso-ficha pulso-{f.tono}"
        class:pulso-activa={activa === f.clave}
        href={f.href}
        aria-current={activa === f.clave ? 'page' : undefined}
        title={f.motivo || undefined}
      >
        <span class="pulso-punto" aria-hidden="true"></span>
        <span class="pulso-texto">
          <strong>{f.valor ?? '—'}</strong>
          <span>{f.texto}</span>
        </span>
      </a>
    {/each}
  {:else}
    <span class="pulso-cargando">{fallo ? 'El pulso del NOC no se pudo leer.' : 'Leyendo el pulso del NOC…'}</span>
  {/if}
</nav>

<style>
  .pulso {
    display: grid;
    grid-template-columns: repeat(6, minmax(0, 1fr));
    background: var(--v2-card);
    border-bottom: 1px solid var(--v2-line);
    flex: none;
    min-height: 56px;
  }
  @media (max-width: 1100px) { .pulso { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
  @media (max-width: 600px) { .pulso { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
  .pulso-ficha {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 16px;
    border-right: 1px solid var(--v2-line-soft);
    color: var(--v2-ink);
    text-decoration: none;
    min-width: 0;
  }
  .pulso-ficha:hover { background: var(--v2-ember-soft); }
  .pulso-ficha:focus-visible { outline: 2px solid var(--v2-ember); outline-offset: -2px; }
  .pulso-activa { background: var(--v2-ember-soft); box-shadow: inset 0 -2px 0 var(--v2-ember); }
  .pulso-punto { width: 9px; height: 9px; border-radius: 999px; flex: none; background: var(--v2-line-strong); }
  .pulso-texto { display: grid; min-width: 0; }
  .pulso-texto strong { font-size: 18px; line-height: 22px; font-weight: 700; font-variant-numeric: tabular-nums; }
  .pulso-texto span { font-size: 11.5px; line-height: 14px; color: var(--v2-slate); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .pulso-critico .pulso-punto { background: #dc2626; }
  .pulso-critico strong { color: var(--v2-rust); }
  .pulso-alerta .pulso-punto { background: var(--v2-espera-fuerte); }
  .pulso-alerta strong { color: var(--v2-espera); }
  .pulso-ok .pulso-punto { background: var(--v2-sola-fuerte); }
  .pulso-ok strong { color: var(--v2-sola); }
  .pulso-accion .pulso-punto { background: var(--v2-ember); }
  .pulso-accion strong { color: var(--v2-ember-text); }
  .pulso-cargando { grid-column: 1 / -1; align-self: center; padding: 0 16px; font-size: 12.5px; color: var(--v2-slate); }
</style>
