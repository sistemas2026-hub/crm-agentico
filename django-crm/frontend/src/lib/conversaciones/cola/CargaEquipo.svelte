<script>
  /**
   * La carga del equipo, para quien supervisa (29/10/2026). Solo ADMIN.
   *
   * Dos cosas: cuántas abiertas tiene cada persona y cuánto lleva la más
   * vieja, y «pasar todas a…» -- el caso real es alguien que termina el turno
   * o se enferma. No inventa una operación nueva: es REASIGNAR (T4), la misma
   * de la conversación, una por una, con motivo, y queda en la auditoría de
   * cada una. Lo que no se pudo pasar se dice con su motivo, no se esconde.
   */
  import { cargaPorOperador } from '$lib/conversaciones/carga.js';
  import { shortAge } from '$lib/v2/format.js';

  let {
    /** Las filas de la cola, ya cargadas por el layout. */
    conversaciones = [],
    /** El usuario_id por el que se está filtrando la cola, o null. */
    filtro = null,
    onFiltrar = undefined,
    /** Para refrescar la cola después de mover conversaciones. */
    onCambio = undefined
  } = $props();

  const carga = $derived(cargaPorOperador(conversaciones));

  /** @type {{ usuario_id: string, nombre: string }[]} */
  let operadores = $state([]);
  let errorOperadores = $state('');
  $effect(() => {
    fetch('/api/bandeja/operadores')
      .then((r) => r.json().then((d) => ({ ok: r.ok, d })))
      .then(({ ok, d }) => {
        if (ok) operadores = d.operadores ?? [];
        else errorOperadores = d.error || 'No se pudo leer el equipo.';
      })
      .catch(() => (errorOperadores = 'No se pudo leer el equipo.'));
  });

  /** De quién se están pasando, o null. */
  let pasandoDe = $state(/** @type {string|null} */ (null));
  let destino = $state('');
  let motivo = $state('');
  let moviendo = $state(false);
  let resultado = $state(/** @type {{ pasadas: number, fallidas: { id: string, error: string }[] } | null} */ (null));

  async function pasarTodas(/** @type {{ usuario_id: string, nombre: string, ids: string[] }} */ p) {
    if (!destino || !motivo.trim() || moviendo) return;
    moviendo = true;
    resultado = null;
    let pasadas = 0;
    /** @type {{ id: string, error: string }[]} */
    const fallidas = [];
    // Una por una y no en paralelo: cada una es una transición con su lock y
    // su versión, y veinte a la vez contra el mismo motor solo compiten.
    for (const id of p.ids) {
      try {
        const r = await fetch(`/api/conversaciones/${id}/reasignar`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            destino_usuario_id: destino,
            motivo: motivo.trim(),
            clave_operacion: crypto.randomUUID()
          })
        });
        if (r.ok) pasadas += 1;
        else {
          const d = await r.json().catch(() => ({}));
          fallidas.push({ id, error: d.error || `respondió ${r.status}` });
        }
      } catch {
        fallidas.push({ id, error: 'no se pudo contactar al servidor' });
      }
    }
    resultado = { pasadas, fallidas };
    moviendo = false;
    pasandoDe = null;
    motivo = '';
    onCambio?.();
  }
</script>

<section class="carga" aria-label="Carga del equipo">
  <p class="carga-titulo">Carga del equipo</p>
  {#if carga.length === 0}
    <p class="carga-vacia">Nadie tiene conversaciones abiertas asignadas.</p>
  {:else}
    <ul class="carga-lista">
      {#each carga as p (p.usuario_id)}
        <li class="carga-fila" class:carga-filtrada={filtro === p.usuario_id}>
          <span class="carga-nombre">{p.nombre}</span>
          <span class="carga-num v2-num">{p.abiertas}</span>
          <span class="carga-espera v2-num">
            {p.esperandoDesde ? `espera ${shortAge(p.esperandoDesde)}` : ''}
          </span>
          <span class="carga-acciones">
            <button type="button" class="v2-btn v2-btn-sm v2-btn-quiet"
              onclick={() => onFiltrar?.(filtro === p.usuario_id ? null : p.usuario_id)}>
              {filtro === p.usuario_id ? 'Ver todas' : 'Ver'}
            </button>
            <button type="button" class="v2-btn v2-btn-sm v2-btn-quiet"
              onclick={() => { pasandoDe = pasandoDe === p.usuario_id ? null : p.usuario_id; destino = ''; }}
              aria-expanded={pasandoDe === p.usuario_id}>
              Pasar todas a…
            </button>
          </span>
          {#if pasandoDe === p.usuario_id}
            <form class="carga-pasar" onsubmit={(e) => { e.preventDefault(); pasarTodas(p); }}>
              <select class="v2-input" bind:value={destino} aria-label="A quién">
                <option value="">Elegí a quién…</option>
                {#each operadores.filter((o) => o.usuario_id !== p.usuario_id) as o (o.usuario_id)}
                  <option value={o.usuario_id}>{o.nombre}</option>
                {/each}
              </select>
              <input class="v2-input" bind:value={motivo} maxlength="200"
                placeholder="Motivo (queda en la auditoría)" aria-label="Motivo" />
              <button type="submit" class="v2-btn v2-btn-sm v2-btn-ink"
                disabled={!destino || !motivo.trim() || moviendo}>
                {moviendo ? 'Pasando…' : `Pasar ${p.abiertas}`}
              </button>
            </form>
          {/if}
        </li>
      {/each}
    </ul>
  {/if}
  {#if errorOperadores}<p class="v2-error">{errorOperadores}</p>{/if}
  {#if resultado}
    <p class="carga-resultado">
      {resultado.pasadas} pasada{resultado.pasadas === 1 ? '' : 's'}.
      {#if resultado.fallidas.length}
        {resultado.fallidas.length} no se pudo:
        {#each resultado.fallidas as f (f.id)}<span class="carga-fallo">{f.error}</span>{/each}
      {/if}
    </p>
  {/if}
</section>

<style>
  .carga {
    padding: 8px 12px 10px;
    border-bottom: 1px solid var(--bandeja-borde);
    background: var(--bandeja-superficie);
  }
  .carga-titulo {
    margin: 0 0 6px;
    font-family: var(--bandeja-mono);
    font-size: 9.5px;
    font-weight: 700;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: var(--bandeja-texto-2);
  }
  .carga-vacia {
    margin: 0;
    font-size: 12px;
    color: var(--bandeja-texto-3);
  }
  .carga-lista {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .carga-fila {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto auto;
    align-items: center;
    gap: 2px 8px;
    padding: 3px 4px;
    border-radius: var(--bandeja-radio-sm);
    font-size: 12px;
  }
  .carga-filtrada {
    background: var(--bandeja-humano-fondo);
  }
  .carga-nombre {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-weight: 600;
  }
  .carga-num {
    font-weight: 700;
  }
  .carga-espera {
    font-size: 11px;
    color: var(--bandeja-texto-3);
  }
  .carga-acciones {
    grid-column: 1 / -1;
    display: flex;
    gap: 4px;
  }
  .carga-pasar {
    grid-column: 1 / -1;
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    padding: 4px 0 6px;
  }
  .carga-pasar select,
  .carga-pasar input {
    flex: 1 1 8rem;
    min-width: 0;
  }
  .carga-resultado {
    margin: 6px 0 0;
    font-size: 11.5px;
    color: var(--bandeja-texto-2);
  }
  .carga-fallo {
    display: block;
    color: var(--bandeja-error);
  }
</style>
