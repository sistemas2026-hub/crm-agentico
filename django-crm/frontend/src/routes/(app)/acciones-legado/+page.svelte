<script>
  /**
   * Las acciones propuestas que quedaron sin conversación (gate G3).
   *
   * Existía el endpoint de lectura y ninguna pantalla lo consumía, así que las
   * 36 eran invisibles: la revisión humana que el gate exige no se podía hacer
   * ni para decidir cuál cancelar.
   *
   * ES DE SOLO LECTURA SALVO CANCELAR. No hay botón de aprobar en ningún
   * estado —no deshabilitado: ausente—. Aprobar es ejecutar, y ejecutar una
   * intención de hace semanas sin revalidación es lo que X24 prohíbe.
   */
  import { onMount } from 'svelte';
  import { lineaDeAccion, resumenPorTipo } from '$lib/acciones/legado.js';

  let acciones = $state(/** @type {any[]} */ ([]));
  let cargando = $state(true);
  let error = $state('');
  let cancelando = $state(/** @type {string|null} */ (null));
  let motivos = $state(/** @type {Record<string, string>} */ ({}));

  let lineas = $derived(acciones.map((a) => lineaDeAccion(a)));
  let porTipo = $derived(resumenPorTipo(acciones));

  async function cargar() {
    cargando = true;
    error = '';
    try {
      const resp = await fetch('/api/acciones-legado?estado=pendiente');
      const datos = await resp.json();
      if (!resp.ok) throw new Error(datos?.error || 'No se pudieron leer las acciones.');
      acciones = datos.acciones ?? [];
    } catch (/** @type {any} */ e) {
      error = e?.message || 'No se pudieron leer las acciones.';
    } finally {
      cargando = false;
    }
  }

  async function cancelar(/** @type {string} */ id) {
    const motivo = (motivos[id] ?? '').trim();
    if (!motivo || cancelando) return;
    cancelando = id;
    error = '';
    try {
      const resp = await fetch(`/api/acciones-legado/${id}/cancelar`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ motivo })
      });
      const datos = await resp.json();
      if (!resp.ok) throw new Error(datos?.error || 'No se pudo cancelar.');
      // Se relee en vez de sacarla de la lista a mano: si alguien más la
      // resolvió mientras tanto, la lista tiene que decir la verdad.
      await cargar();
    } catch (/** @type {any} */ e) {
      error = e?.message || 'No se pudo cancelar.';
    } finally {
      cancelando = null;
    }
  }

  onMount(cargar);
</script>

<svelte:head><title>Acciones sin conversación</title></svelte:head>

<div class="legado">
  <h1>Acciones sin conversación</h1>

  <p class="explicacion">
    Son escrituras reales contra sistemas externos que se propusieron antes de que
    las acciones quedaran vinculadas a una conversación, y que nadie resolvió nunca.
    <strong>No se pueden aprobar</strong>: sin conversación no hay nada contra qué
    comprobar que todavía tienen sentido, y aprobarlas ejecutaría los argumentos
    congelados de entonces.
  </p>
  <p class="explicacion">
    Si el problema sigue vivo, la conversación de hoy lo vuelve a proponer con su
    contexto y pasa por la revisión normal. Eso es más seguro que revivir una
    intención vieja, así que lo que corresponde acá es <strong>cancelar</strong>.
  </p>

  {#if cargando}
    <p class="v2-muted">Leyendo…</p>
  {:else if error}
    <p class="v2-error">{error}</p>
  {/if}

  {#if !cargando && porTipo.length}
    <ul class="por-tipo">
      {#each porTipo as t (t.herramienta)}
        <li><strong>{t.cuantas}</strong> · {t.queHace}</li>
      {/each}
    </ul>
  {/if}

  {#if !cargando && !lineas.length && !error}
    <p class="v2-muted">
      No queda ninguna acción pendiente sin conversación. Nada que revisar.
    </p>
  {/if}

  <ul class="lista">
    {#each lineas as linea (linea.id)}
      <li class="accion">
        <div class="cabecera">
          <span class="que-hace">{linea.queHace}</span>
          {#if linea.antiguedad}
            <span class="v2-sub">se propuso {linea.antiguedad}</span>
          {/if}
        </div>

        {#if linea.resumen}
          <p class="resumen">{linea.resumen}</p>
        {/if}

        <p class="v2-sub por-que">{linea.porQueNo}</p>

        {#if linea.puedeCancelarse}
          <div class="cancelar">
            <label class="v2-sub" for={`motivo-${linea.id}`}>
              Por qué se cancela (queda en el registro)
            </label>
            <input
              id={`motivo-${linea.id}`}
              class="v2-input"
              bind:value={motivos[linea.id]}
              placeholder="Obsoleta: el cliente ya reportó de nuevo"
            />
            <button
              type="button"
              class="v2-btn"
              disabled={!((motivos[linea.id] ?? '').trim()) || cancelando === linea.id}
              onclick={() => cancelar(linea.id)}
            >
              {cancelando === linea.id ? 'Cancelando…' : 'Cancelar esta acción'}
            </button>
          </div>
        {/if}
      </li>
    {/each}
  </ul>
</div>

<style>
  .legado {
    max-width: 52rem;
    margin: 0 auto;
    padding: 1.5rem 1rem;
  }
  h1 {
    font-size: 1.25rem;
    margin: 0 0 0.75rem;
  }
  .explicacion {
    margin: 0 0 0.75rem;
    line-height: 1.5;
  }
  .por-tipo {
    list-style: none;
    margin: 1rem 0;
    padding: 0.75rem 1rem;
    border: 1px solid var(--v2-borde, #e2e2e2);
    border-radius: 6px;
  }
  .por-tipo li {
    padding: 0.15rem 0;
  }
  .lista {
    list-style: none;
    margin: 1rem 0 0;
    padding: 0;
  }
  .accion {
    border: 1px solid var(--v2-borde, #e2e2e2);
    border-radius: 6px;
    padding: 0.85rem 1rem;
    margin-bottom: 0.75rem;
  }
  .cabecera {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    align-items: baseline;
    justify-content: space-between;
  }
  .que-hace {
    font-weight: 600;
  }
  .resumen {
    margin: 0.4rem 0 0;
    line-height: 1.45;
  }
  .por-que {
    margin: 0.4rem 0 0;
  }
  .cancelar {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    align-items: center;
    margin-top: 0.75rem;
  }
  .cancelar label {
    flex: 1 0 100%;
  }
  .cancelar :global(input) {
    flex: 1 1 18rem;
  }
</style>
