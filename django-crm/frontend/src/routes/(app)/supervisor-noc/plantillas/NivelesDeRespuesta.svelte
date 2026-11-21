<script>
  /**
   * NIVELES DE RESPUESTA — plazo y prioridad por asunto (24/10/2026).
   *
   * Los tres niveles se definen una vez; cada asunto queda en uno, con quién
   * lo decidió. Lo pone el Supervisor (habilidad H-21) por lo que mide en los
   * tickets; si una persona lo cambia, gana la persona y el Supervisor ya no
   * lo toca. La regla vive en el backend (`campo/niveles.py`): acá solo se
   * muestra y se manda.
   *
   * REDISEÑO DEL 21/11/2026: ahora es una pestaña de Plantillas, con los
   * asuntos en una tabla que se busca y se filtra por nivel (eran ~50
   * tarjetas sueltas), y el resultado de guardar se ve junto a la acción.
   */
  import { enhance } from '$app/forms';
  import ComoFunciona from '$lib/supervisor/ui/ComoFunciona.svelte';
  import { avisar } from '$lib/supervisor/ui/avisos.svelte.js';
  import { quienLoDecidio, textoDelPlazo } from '$lib/supervisor/niveles-de-respuesta.js';

  /** @type {{ niveles: any[], asuntos: any[], ubica_el_supervisor?: boolean, error?: boolean }} */
  let { niveles = [], asuntos = [], ubica_el_supervisor = false, error = false } = $props();

  const PRIORIDADES = [
    { id: 'alta', texto: 'Alta' },
    { id: 'media', texto: 'Media' },
    { id: 'baja', texto: 'Baja' }
  ];
  const TONO = /** @type {Record<string, string>} */ ({ alta: 'snoc-recuadro-error', media: 'snoc-recuadro-alerta', baja: '' });
  const nombreDelNivel = (/** @type {string} */ codigo) =>
    niveles.find((n) => n.codigo === codigo)?.nombre ?? codigo;
  const fecha = (/** @type {string} */ iso) =>
    new Date(iso).toLocaleDateString('es-CO', { day: 'numeric', month: 'short', timeZone: 'America/Bogota' });

  let busqueda = $state('');
  /** '' = todos, '__sin' = sin nivel, o el código de un nivel */
  let filtro = $state('');
  const sinAcentos = (/** @type {string} */ s) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  const visibles = $derived(
    asuntos.filter((a) => {
      if (filtro === '__sin' ? a.nivel : filtro && a.nivel !== filtro) return false;
      return !busqueda.trim() || sinAcentos(a.asunto).includes(sinAcentos(busqueda.trim()));
    })
  );
  const cuantos = (/** @type {string} */ f) =>
    f === '' ? asuntos.length : f === '__sin' ? asuntos.filter((a) => !a.nivel).length : asuntos.filter((a) => a.nivel === f).length;

  /** @param {string} exito */
  const conAviso = (exito) => () => async (/** @type {any} */ { result, update }) => {
    await update({ reset: false });
    if (result?.type === 'success') avisar(result.data?.hecho ?? exito);
    else if (result?.type === 'failure') avisar(result.data?.error ?? 'No se pudo guardar.', { tono: 'error' });
  };
</script>

<ComoFunciona>
  <p style="margin:0;">
    Cuánto se tarda y con qué prioridad arranca cada asunto. Los tres niveles se definen una vez:
    cambiar un número cambia todos los asuntos de ese nivel. Cada asunto lo ubica el Supervisor por
    lo que mide en sus tickets; si lo cambiás vos, ya no lo vuelve a tocar.
  </p>
  <p style="margin:0;">Por ahora ninguna orden los usa: los va a usar el Supervisor cuando cree las órdenes.</p>
</ComoFunciona>

{#if !ubica_el_supervisor}
  <p class="snoc-recuadro snoc-recuadro-alerta" role="status">
    El Supervisor todavía no ubica los asuntos solo: se le pide desde su chat («ubicá cada asunto en
    su nivel»), y además la empresa tiene que tener autorizado el nivel 3. Mientras tanto, los ubicás vos.
  </p>
{/if}

{#if error}
  <p class="snoc-recuadro snoc-recuadro-error">No se pudieron leer los niveles.</p>
{:else}
  <form method="POST" action="?/guardarNiveles" use:enhance={conAviso('Niveles guardados.')} class="snoc-panel">
    <div class="snoc-tarjeta-cabeza">
      <h2 class="snoc-h2">Los tres niveles</h2>
      <button class="snoc-btn snoc-btn-primario" type="submit">Guardar los niveles</button>
    </div>
    <div class="nr-niveles">
      {#each niveles as n (n.codigo)}
        <div class="snoc-recuadro {TONO[n.prioridad] ?? ''} nr-nivel">
          <label class="snoc-campo-grupo">
            <span class="snoc-label">Nivel</span>
            <input class="snoc-campo" name="nombre_{n.codigo}" value={n.nombre} required maxlength="40" />
          </label>
          <div class="nr-par">
            <label class="snoc-campo-grupo">
              <span class="snoc-label">Plazo (días)</span>
              <input class="snoc-campo" type="number" name="plazo_{n.codigo}" value={n.plazo_dias} min="0" max="60" required />
            </label>
            <label class="snoc-campo-grupo">
              <span class="snoc-label">Prioridad inicial</span>
              <select class="snoc-select" name="prioridad_{n.codigo}">
                {#each PRIORIDADES as p (p.id)}
                  <option value={p.id} selected={p.id === n.prioridad}>{p.texto}</option>
                {/each}
              </select>
            </label>
          </div>
          <span class="snoc-body-sm snoc-secundario">{textoDelPlazo(n.plazo_dias)} · {cuantos(n.codigo)} asuntos</span>
        </div>
      {/each}
    </div>
  </form>

  <section class="snoc-panel" style="padding:0; gap:0;" aria-labelledby="nr-asuntos">
    <div class="snoc-tarjeta-cabeza nr-cabeza">
      <div class="snoc-fila">
        <h2 class="snoc-h2" id="nr-asuntos">Asuntos</h2>
        <span class="snoc-cuenta">{asuntos.length}</span>
      </div>
      <div class="snoc-fila" style="flex-wrap:wrap;">
        <input class="snoc-campo" type="search" bind:value={busqueda} placeholder="Buscar asunto…" aria-label="Buscar asunto" style="width:220px;" />
        <div class="snoc-segmentado" role="group" aria-label="Filtrar por nivel">
          <button type="button" aria-pressed={filtro === ''} onclick={() => (filtro = '')}>Todos</button>
          <button type="button" aria-pressed={filtro === '__sin'} onclick={() => (filtro = '__sin')}>
            Sin nivel <span class="snoc-cuenta">{cuantos('__sin')}</span>
          </button>
          {#each niveles as n (n.codigo)}
            <button type="button" aria-pressed={filtro === n.codigo} onclick={() => (filtro = n.codigo)}>{n.nombre}</button>
          {/each}
        </div>
      </div>
    </div>
    {#if !asuntos.length}
      <p class="snoc-body-sm snoc-secundario" style="margin:0; padding:16px 18px;">
        Todavía no hay asuntos. Aparecen acá los de cada plantilla y, si el Supervisor los ubica,
        también los que lleguen en los tickets.
      </p>
    {:else if !visibles.length}
      <p class="snoc-body-sm snoc-secundario" style="margin:0; padding:16px 18px;">Ningún asunto coincide.</p>
    {:else}
      <div class="snoc-tabla-caja">
        <table class="snoc-tabla">
          <thead><tr><th>Asunto</th><th>Quién lo decidió</th><th>Nivel</th></tr></thead>
          <tbody>
            {#each visibles as a (a.asunto)}
              <tr>
                <td><strong>{a.asunto}</strong></td>
                <td class="snoc-body-sm snoc-secundario">
                  {#if !a.nivel}<span class="snoc-insignia snoc-insignia-alerta">{quienLoDecidio(a, fecha)}</span>
                  {:else}{quienLoDecidio(a, fecha)}{a.provisional ? ' · provisional' : ''}{/if}
                </td>
                <td>
                  <form method="POST" action="?/nivelDeAsunto" use:enhance={conAviso('Asunto ubicado.')} class="snoc-fila">
                    <input type="hidden" name="asunto" value={a.asunto} />
                    <select class="snoc-select" name="nivel" aria-label="Nivel de {a.asunto}" required>
                      {#if !a.nivel}<option value="" selected disabled>Elegí un nivel</option>{/if}
                      {#each niveles as n (n.codigo)}
                        <option value={n.codigo} selected={n.codigo === a.nivel}>{nombreDelNivel(n.codigo)}</option>
                      {/each}
                    </select>
                    <button class="snoc-btn {a.nivel ? '' : 'snoc-btn-primario'}" type="submit">{a.nivel ? 'Cambiar' : 'Ubicar'}</button>
                  </form>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  </section>
{/if}

<style>
  .nr-niveles { display: grid; gap: 14px; grid-template-columns: repeat(auto-fit, minmax(min(100%, 240px), 1fr)); }
  .nr-nivel { display: flex; flex-direction: column; gap: 10px; }
  .nr-par { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .nr-cabeza { padding: 14px 18px; border-bottom: 1px solid var(--v2-line-soft); }
</style>
