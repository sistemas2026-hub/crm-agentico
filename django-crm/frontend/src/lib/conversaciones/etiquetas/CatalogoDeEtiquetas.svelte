<script>
  /**
   * El catálogo de etiquetas del equipo, en /settings/bandeja (11/11/2026):
   * crear, renombrar, cambiar el color y borrar.
   *
   * POR QUÉ UNA LISTA ENTERA Y NO UN BOTÓN POR ETIQUETA
   * ---------------------------------------------------
   * Se guarda junto, como los rótulos: el motor reemplaza el catálogo entero
   * (PUT /configuracion/bandeja/etiquetas) y valida todo de una -- dos con el
   * mismo nombre se ven recién al mirarlas juntas. La lista viaja en un campo
   * oculto (`etiquetas`, JSON) y la acción `?/etiquetas` la reenvía.
   *
   * RENOMBRAR NO DESETIQUETA. Cada fila lleva su `clave` escondida: es lo que
   * guardan los chats. Una fila nueva va sin clave y el motor la arma del
   * nombre. Borrar una etiqueta la saca de la cola, pero no de los chats: si
   * se vuelve a crear con la misma clave, reaparece donde estaba.
   *
   * El color se elige de la paleta CERRADA (la misma del esquema): ocho
   * muestras, cada una con su nombre para el lector de pantalla.
   */
  import { untrack } from 'svelte';
  import { Tags, Plus, Trash2 } from '@lucide/svelte';
  import EtiquetaChip from './EtiquetaChip.svelte';
  import { COLORES, COLOR_LEGIBLE, NOMBRES_DE_COLOR } from '$lib/conversaciones/etiquetas.js';

  let {
    /** [{ clave, nombre, color }] guardado. */
    catalogo = [],
    /** La paleta que manda el motor; si no llega, la del frontend. */
    colores = NOMBRES_DE_COLOR,
    puedeEditar = false,
    error = '',
    guardadas = false
  } = $props();

  const MAXIMO = 30;
  const NOMBRE_MAXIMO = 30;

  let editando = $state(false);
  /** @type {{ clave: string, nombre: string, color: string, id: string }[]} */
  let filas = $state([]);
  let n = 0;
  const nuevaId = () => `f${++n}`;

  function empezar() {
    filas = untrack(() => catalogo).map((/** @type {any} */ e) => ({ ...e, id: nuevaId() }));
    editando = true;
  }

  function agregar() {
    // El color de la nueva va rotando, para que dos seguidas no se confundan.
    const color = colores[filas.length % colores.length] ?? 'gris';
    filas.push({ clave: '', nombre: '', color, id: nuevaId() });
  }

  /** @param {string} id */
  function borrar(id) {
    filas = filas.filter((f) => f.id !== id);
  }

  const lista = $derived(
    JSON.stringify(filas.map(({ clave, nombre, color }) => ({ clave, nombre, color })))
  );
  const paleta = $derived(colores.filter((c) => c in COLORES));
</script>

<section class="v2-card catalogo" aria-labelledby="etq-titulo">
  <p class="titulo" id="etq-titulo"><Tags size={14} /> Etiquetas del equipo</p>
  <p class="cuerpo">
    Las que una persona le pone a un chat desde la conversación: «Cliente VIP», «Moroso». Se
    ven en la cola y se filtran. Son del chat: un cliente que vuelve las conserva. No son los
    motivos de escalamiento, que elige el asistente.
  </p>

  {#if !editando}
    {#if catalogo.length}
      <div class="chips">
        {#each catalogo as e (e.clave)}
          <EtiquetaChip nombre={e.nombre} color={e.color} />
        {/each}
      </div>
    {:else}
      <p class="cuerpo apagado">Todavía no hay ninguna: la Bandeja no ofrece etiquetar.</p>
    {/if}
    {#if guardadas}<p class="v2-hint">Guardado.</p>{/if}
    {#if error}<p class="v2-error">{error}</p>{/if}
    {#if puedeEditar}
      <button type="button" class="v2-btn v2-btn-sm" onclick={empezar}>Editar etiquetas</button>
    {/if}
  {:else}
    <form method="POST" action="?/etiquetas">
      <input type="hidden" name="etiquetas" value={lista} />
      <ul class="filas">
        {#each filas as f, i (f.id)}
          <li class="fila">
            <label class="oculto" for="etq-nombre-{f.id}">Nombre de la etiqueta {i + 1}</label>
            <input
              id="etq-nombre-{f.id}"
              class="v2-input nombre"
              bind:value={f.nombre}
              maxlength={NOMBRE_MAXIMO}
              placeholder="Nombre"
              required
            />
            <fieldset class="paleta">
              <legend class="oculto">Color de {f.nombre || `la etiqueta ${i + 1}`}</legend>
              {#each paleta as c (c)}
                <label class="muestra" title={COLOR_LEGIBLE[c] ?? c}>
                  <input type="radio" name="color-{f.id}" value={c} bind:group={f.color} />
                  <span class="punto" style="background:{COLORES[c].texto}" aria-hidden="true"></span>
                  <span class="oculto">{COLOR_LEGIBLE[c] ?? c}</span>
                </label>
              {/each}
            </fieldset>
            <span class="vista"><EtiquetaChip nombre={f.nombre || 'Sin nombre'} color={f.color} /></span>
            <button
              type="button"
              class="v2-btn v2-btn-sm quitar"
              onclick={() => borrar(f.id)}
              aria-label="Borrar {f.nombre || `la etiqueta ${i + 1}`}"
              title="Borrar"
            >
              <Trash2 size={14} aria-hidden="true" />
            </button>
          </li>
        {/each}
      </ul>
      {#if filas.length < MAXIMO}
        <button type="button" class="v2-btn v2-btn-sm" onclick={agregar}>
          <Plus size={14} aria-hidden="true" /> Agregar etiqueta
        </button>
      {/if}
      <p class="v2-hint">
        Renombrar una etiqueta no la saca de los chats que la tienen. Borrarla la deja de mostrar.
      </p>
      {#if error}<p class="v2-error">{error}</p>{/if}
      <div class="acciones">
        <button type="submit" class="v2-btn v2-btn-primary v2-btn-sm">Guardar etiquetas</button>
        <button type="button" class="v2-btn v2-btn-sm" onclick={() => (editando = false)}>Cancelar</button>
      </div>
    </form>
  {/if}
</section>

<style>
  .catalogo {
    padding: 16px;
    margin-top: 16px;
  }
  .titulo {
    display: flex;
    align-items: center;
    gap: 6px;
    margin: 0 0 6px;
    font-size: 13px;
    font-weight: 600;
    color: var(--v2-ink);
  }
  .cuerpo {
    margin: 0 0 10px;
    font-size: 12.5px;
    line-height: 1.55;
    color: var(--v2-ink);
  }
  .apagado {
    color: var(--v2-slate);
  }
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-bottom: 10px;
  }
  .filas {
    list-style: none;
    margin: 0 0 10px;
    padding: 0;
  }
  .fila {
    display: grid;
    grid-template-columns: minmax(8rem, 14rem) auto minmax(0, 1fr) auto;
    align-items: center;
    gap: 10px;
    padding: 6px 0;
    border-top: 1px solid var(--v2-line-soft);
  }
  .fila:first-child {
    border-top: 0;
  }
  .paleta {
    display: flex;
    gap: 4px;
    margin: 0;
    padding: 0;
    border: 0;
  }
  .muestra {
    position: relative;
    display: grid;
    place-items: center;
    width: 22px;
    height: 22px;
    border: 1px solid transparent;
    border-radius: 4px;
    cursor: pointer;
  }
  .muestra input {
    position: absolute;
    opacity: 0;
    inset: 0;
    margin: 0;
    cursor: pointer;
  }
  .muestra:has(input:checked) {
    border-color: var(--v2-ink);
  }
  .muestra:has(input:focus-visible) {
    outline: 2px solid var(--v2-ink);
    outline-offset: 1px;
  }
  .punto {
    width: 12px;
    height: 12px;
    border-radius: 3px;
  }
  .vista {
    min-width: 0;
  }
  .acciones {
    display: flex;
    gap: 8px;
    margin-top: 10px;
  }
  .oculto {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
  }
  @media (max-width: 640px) {
    .fila {
      grid-template-columns: 1fr auto;
    }
    .paleta {
      grid-column: 1 / -1;
    }
    .vista {
      display: none;
    }
  }
</style>
