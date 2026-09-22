<script>
  /**
   * Lo que dice la documentación interna sobre lo último que preguntó el
   * cliente. Recupera, no genera: son fragmentos reales con su procedencia, y
   * quien atiende decide qué hacer con ellos.
   */
  import { ChevronDown, Search, X } from '@lucide/svelte';

  let {
    sugerencias = [], buscandoDocs = false, errorDocs = '', mejorSimilitud,
    consultaDocs = $bindable(''),
    expandido = $bindable(null),
    copiado = null,
    onAbrir, onBuscar, onCopiar
  } = $props();
</script>

<!-- ══════════════════════════════════════════════════════════════════════════
     «DOCUMENTATION», con los fragmentos reales

     Referencia: la pestaña Tools. Tarjeta con cabecera, buscador arriba y
     cada resultado como una ficha: la cita, y debajo su procedencia
     --código · versión · puntaje-- más «Copiar fragmento».

     El puntaje de la referencia (0.87) NO es decorativo y acá tampoco es
     inventado: cada sugerencia viaja con su `similitud`, calculada por el
     motor. Es el dato que dice si el fragmento contesta la pregunta o si el
     buscador se estiró para devolver algo -- y sin él, tres citas parecidas
     se leen como si valieran lo mismo.

     RECUPERA, NO GENERA: son fragmentos textuales con su procedencia, y quien
     atiende decide qué hacer con ellos. Por eso la cita va entre comillas y
     con el código al pie, no reescrita.
     ══════════════════════════════════════════════════════════════════════════ -->

<details class="panel-tarjeta docs" ontoggle={(e) => onAbrir?.(e)}>
  <summary class="panel-tarjeta-cabeza docs-cabeza">
    <span class="panel-titulo">Documentación</span>
    <span class="docs-cabeza-fin">
      {#if sugerencias.length}
        <span class="panel-marca">{sugerencias.length}</span>
      {/if}
      <ChevronDown size={14} class="docs-flecha" />
    </span>
  </summary>

  <form class="docs-buscar" onsubmit={(e) => onBuscar?.(e)}>
    <span class="docs-lupa" aria-hidden="true"><Search size={13} /></span>
    <input
      class="docs-campo"
      type="text"
      bind:value={consultaDocs}
      placeholder="Buscar en las guías"
      aria-label="Buscar en la documentación interna"
    />
    {#if consultaDocs}
      <!-- La × de la referencia. Borrar a mano una consulta larga en una
           columna de 350px son varios segundos de backspace. -->
      <button
        type="button"
        class="docs-limpiar"
        title="Borrar la búsqueda"
        onclick={() => (consultaDocs = '')}
      >
        <X size={12} />
      </button>
    {/if}
    <button class="docs-ir" type="submit" disabled={buscandoDocs}>
      {buscandoDocs ? '…' : 'Buscar'}
    </button>
  </form>

  {#if buscandoDocs}
    <p class="panel-nota">Buscando…</p>
  {:else if errorDocs}
    <p class="panel-nota docs-malo">{errorDocs}</p>
  {:else if sugerencias.length === 0}
    <!-- NO ES LO MISMO «no hay nada» que «hay algo pero no alcanza». Cuando
         el mejor resultado quedó por debajo del umbral se dice con su número:
         quien busca sabe entonces si vale la pena reformular la consulta o si
         la documentación simplemente no cubre el tema. -->
    <p class="panel-nota">
      La documentación no cubre esta consulta.
      {#if mejorSimilitud !== null}
        Lo más parecido quedó en <span class="v2-num">{mejorSimilitud}</span>,
        por debajo del umbral.
      {/if}
    </p>
  {:else}
    {#each sugerencias as s, i}
      <article class="doc" class:abierto={expandido === i}>
        <!-- La cita entera al abrir; recortada al cerrar. Un fragmento de
             guía suele medir cuatro renglones y tres de esos apilados dejan
             el buscador fuera de la pantalla. -->
        <button
          type="button"
          class="doc-cita"
          onclick={() => (expandido = expandido === i ? null : i)}
          aria-expanded={expandido === i}
        >
          <span class="doc-texto">{s.contenido}</span>
        </button>
        <div class="doc-pie">
          <span class="doc-origen v2-num">
            {s.codigo || 'sin código'}{#if s.version} · v{s.version}{/if}{#if s.similitud !== null && s.similitud !== undefined} · {s.similitud}{/if}
          </span>
          <button
            class="doc-copiar"
            type="button"
            onclick={() => onCopiar?.(s.contenido, i)}
          >
            {copiado === i ? 'Copiado' : 'Copiar fragmento'}
          </button>
        </div>
      </article>
    {/each}
  {/if}
</details>

<style>
  .docs {
    margin-bottom: 10px;
  }

  .docs-cabeza {
    cursor: pointer;
    list-style: none;
    user-select: none;
  }
  .docs-cabeza::-webkit-details-marker {
    display: none;
  }

  .docs-cabeza-fin {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    flex: none;
    color: var(--bandeja-texto-3);
  }

  .docs :global(.docs-flecha) {
    transition: transform 0.15s ease;
  }
  .docs[open] :global(.docs-flecha) {
    transform: rotate(180deg);
  }

  /* ── el buscador ───────────────────────────────────────────────────────
     Un solo recuadro con la lupa adentro, como la referencia. Antes eran un
     `input` del CRM y un botón al lado, y los dos juntos no entraban en 350px
     sin que el campo quedara en la mitad del ancho. */
  .docs-buscar {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px 8px;
    border: 1px solid var(--bandeja-borde);
    border-radius: 3px;
    background: var(--bandeja-superficie-suave);
  }
  .docs-buscar:focus-within {
    border-color: var(--bandeja-humano);
    background: var(--bandeja-superficie);
  }

  .docs-lupa {
    display: inline-flex;
    flex: none;
    color: var(--bandeja-texto-3);
  }

  .docs-campo {
    flex: 1 1 auto;
    min-width: 0;
    border: 0;
    background: none;
    font: inherit;
    font-size: 12px;
    color: var(--bandeja-texto);
  }
  .docs-campo:focus {
    outline: none;
  }
  .docs-campo::placeholder {
    color: var(--bandeja-texto-3);
  }

  .docs-limpiar {
    display: inline-flex;
    flex: none;
    padding: 2px;
    border: 0;
    border-radius: 2px;
    background: none;
    color: var(--bandeja-texto-3);
    cursor: pointer;
  }
  .docs-limpiar:hover {
    color: var(--bandeja-texto);
  }

  .docs-ir {
    flex: none;
    padding: 1px 7px;
    border: 1px solid var(--bandeja-borde);
    border-radius: 3px;
    background: var(--bandeja-superficie);
    font-family: var(--bandeja-mono);
    font-size: 9.5px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--bandeja-texto-2);
    cursor: pointer;
  }
  .docs-ir:hover:not(:disabled) {
    color: var(--bandeja-texto);
    border-color: var(--bandeja-borde-fuerte);
  }
  .docs-ir:disabled {
    opacity: 0.6;
    cursor: default;
  }

  /* ── cada fragmento ───────────────────────────────────────────────────── */
  .doc {
    border: 1px solid var(--bandeja-borde);
    border-radius: 3px;
    background: var(--bandeja-superficie);
    padding: 8px 9px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .doc-cita {
    display: block;
    width: 100%;
    padding: 0;
    border: 0;
    background: none;
    font: inherit;
    text-align: left;
    cursor: pointer;
    color: var(--bandeja-texto);
  }

  /* Entre comillas y en cursiva: es una CITA de una guía, no una respuesta
     redactada acá. La diferencia importa -- lo de adentro se puede pegar tal
     cual en una respuesta y sigue siendo lo que dice el procedimiento. */
  .doc-texto {
    display: -webkit-box;
    -webkit-line-clamp: 3;
    line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
    font-size: 11.5px;
    font-style: italic;
    line-height: 1.5;
  }
  .doc-texto::before {
    content: '\201C';
  }
  .doc-texto::after {
    content: '\201D';
  }
  .doc.abierto .doc-texto {
    -webkit-line-clamp: unset;
    line-clamp: unset;
    overflow: visible;
  }

  .doc-pie {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    padding-top: 6px;
    border-top: 1px solid var(--bandeja-borde);
  }

  /* De dónde salió y cuánto se parece. En mono porque son datos que se
     comparan: el código se busca en el gestor de documentos, y el puntaje se
     compara contra el de la ficha de al lado. */
  .doc-origen {
    min-width: 0;
    font-family: var(--bandeja-mono);
    font-size: 10px;
    font-variant-numeric: tabular-nums;
    color: var(--bandeja-texto-3);
    overflow-wrap: anywhere;
  }

  .doc-copiar {
    flex: none;
    padding: 0;
    border: 0;
    background: none;
    font: inherit;
    font-size: 10.5px;
    font-weight: 600;
    color: var(--bandeja-humano);
    cursor: pointer;
  }
  .doc-copiar:hover {
    text-decoration: underline;
  }

  .docs-malo {
    color: var(--bandeja-error);
  }
</style>
