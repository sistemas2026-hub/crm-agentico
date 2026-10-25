<script>
  /**
   * NIVELES DE RESPUESTA — plazo y prioridad por asunto (24/10/2026).
   *
   * Los tres niveles se definen una vez; cada asunto queda en uno, con quién
   * lo decidió. Lo pone el Supervisor (habilidad H-21) por lo que mide en los
   * tickets; si una persona lo cambia, gana la persona y el Supervisor ya no
   * lo toca. La regla vive en el backend (`campo/niveles.py`): acá solo se
   * muestra y se manda.
   */
  import { enhance } from '$app/forms';
  import { quienLoDecidio, textoDelPlazo } from '$lib/supervisor/niveles-de-respuesta.js';

  /** @type {{ niveles: any[], asuntos: any[], ubica_el_supervisor?: boolean, error?: boolean }} */
  let { niveles = [], asuntos = [], ubica_el_supervisor = false, error = false } = $props();

  const PRIORIDADES = [
    { id: 'alta', texto: 'Alta' },
    { id: 'media', texto: 'Media' },
    { id: 'baja', texto: 'Baja' }
  ];
  const nombreDelNivel = (/** @type {string} */ codigo) =>
    niveles.find((n) => n.codigo === codigo)?.nombre ?? codigo;
  const fecha = (/** @type {string} */ iso) =>
    new Date(iso).toLocaleDateString('es-CO', { day: 'numeric', month: 'short',
                                                 timeZone: 'America/Bogota' });
</script>

<section class="snoc-panel" style="gap:var(--snoc-sm);">
  <div class="snoc-pila-xs">
    <h2 class="snoc-h2">Niveles de respuesta</h2>
    <p class="snoc-body-sm snoc-secundario">
      Cuánto se tarda y con qué prioridad arranca cada asunto. Los tres niveles se definen
      una vez: cambiar un número cambia todos los asuntos de ese nivel. Cada asunto lo ubica
      el Supervisor por lo que mide en sus tickets; si lo cambiás vos, ya no lo vuelve a tocar.
      Por ahora ninguna orden los usa: los va a usar el Supervisor cuando cree las órdenes.
    </p>
    {#if !ubica_el_supervisor}
      <p class="snoc-aviso" role="status">
        El Supervisor todavía no ubica los asuntos solo: se le pide desde su chat («ubicá cada
        asunto en su nivel»), y además la empresa tiene que tener autorizado el nivel 3.
        Mientras tanto, los ubicás vos.
      </p>
    {/if}
  </div>

  {#if error}
    <p class="snoc-aviso snoc-error-txt">No se pudieron leer los niveles.</p>
  {:else}
    <form method="POST" action="?/guardarNiveles" use:enhance class="snoc-pila" style="gap:var(--snoc-xs);">
      {#each niveles as n (n.codigo)}
        <div class="snoc-tarjeta snoc-fila" style="flex-wrap:wrap; gap:var(--snoc-sm); align-items:flex-end;">
          <label class="snoc-campo-grupo">
            <span class="snoc-label">Nivel</span>
            <input class="snoc-campo" name="nombre_{n.codigo}" value={n.nombre} required maxlength="40" />
          </label>
          <label class="snoc-campo-grupo">
            <span class="snoc-label">Plazo (días)</span>
            <input class="snoc-campo" type="number" name="plazo_{n.codigo}" value={n.plazo_dias}
                   min="0" max="60" required />
          </label>
          <label class="snoc-campo-grupo">
            <span class="snoc-label">Prioridad inicial</span>
            <select class="snoc-select" name="prioridad_{n.codigo}">
              {#each PRIORIDADES as p (p.id)}
                <option value={p.id} selected={p.id === n.prioridad}>{p.texto}</option>
              {/each}
            </select>
          </label>
          <span class="snoc-body-sm snoc-secundario">{textoDelPlazo(n.plazo_dias)}</span>
        </div>
      {/each}
      <div>
        <button class="snoc-btn snoc-btn-primario" type="submit">Guardar los niveles</button>
      </div>
    </form>

    <div class="snoc-pila-xs" style="margin-top:var(--snoc-sm);">
      <h3 class="snoc-h3">Asuntos</h3>
      {#if !asuntos.length}
        <p class="snoc-body-sm snoc-secundario">
          Todavía no hay asuntos. Aparecen acá los de cada plantilla y, si el Supervisor los
          ubica, también los que lleguen en los tickets.
        </p>
      {/if}
    </div>
    <div class="snoc-pila" style="gap:var(--snoc-xs);">
      {#each asuntos as a (a.asunto)}
        <form method="POST" action="?/nivelDeAsunto" use:enhance
              class="snoc-tarjeta snoc-fila-sep" style="flex-wrap:wrap; gap:var(--snoc-sm);">
          <input type="hidden" name="asunto" value={a.asunto} />
          <div class="snoc-pila-xs" style="min-width:0;">
            <span class="snoc-body"><strong>{a.asunto}</strong></span>
            <span class="snoc-body-sm snoc-secundario">
              {quienLoDecidio(a, fecha)}{a.provisional ? ' · provisional' : ''}
            </span>
          </div>
          <div class="snoc-fila" style="gap:var(--snoc-xs);">
            <select class="snoc-select" name="nivel" aria-label="Nivel de {a.asunto}" required>
              {#if !a.nivel}
                <option value="" selected disabled>Elegí un nivel</option>
              {/if}
              {#each niveles as n (n.codigo)}
                <option value={n.codigo} selected={n.codigo === a.nivel}>{nombreDelNivel(n.codigo)}</option>
              {/each}
            </select>
            <button class="snoc-btn" type="submit">{a.nivel ? 'Cambiar' : 'Ubicar'}</button>
          </div>
        </form>
      {/each}
    </div>
  {/if}
</section>
