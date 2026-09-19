<script>
  /**
   * Los filtros de la cola: qué canales se miran, en qué orden, solo escaladas
   * y por qué motivo escaló.
   *
   * NO FILTRA NADA. Escribe los valores y ya; la cadena entera --canal →
   * pestaña → solo escaladas → motivo → búsqueda → ordenar()-- se deriva en
   * `visibles`, en el layout, que sigue siendo la única autoridad. El catálogo
   * de motivos y sus conteos también se calculan allá, sobre la pestaña
   * actual: acá solo se dibujan.
   *
   * `vista` NO es `filtro`. Son dos cosas con nombres parecidos:
   *
   *   filtro   la pestaña (Por atender / En atención / …) → QueueTabs
   *   vista    qué canales se ven (Operativo / Pruebas / Todos) → acá
   *
   * Y el frontend no decide qué canal es operativo: eso lo marca el motor en
   * `canal_operativo`. Acá no hay ninguna lista de canales, a propósito.
   *
   * `ordenElegido` se escribe al elegir un orden a mano, igual que antes:
   * significa "esto lo eligió una persona" y hace que `irA()` no lo pise al
   * cambiar de pestaña. Esa decisión vive en el layout.
   */
  let {
    // --- qué canales se ven
    vista = $bindable('operativo'),
    // --- el orden, y la marca de que lo eligió una persona
    orden = $bindable('recomendado'),
    ordenElegido = $bindable(false),
    // --- escaladas y motivo
    soloEscaladas = $bindable(false),
    motivo = $bindable(''),
    motivosDesplegados = $bindable(false),
    // --- derivados del layout: se representan, no se recalculan
    motivos = [],
    motivosVisibles = [],
    // --- helper puro, compartido con la fila de la lista
    motivoLabel,
    // ORDENES llega como prop y NO se declara acá, aunque sólo se dibuje acá:
    // `ORDEN_POR_PESTANA`, en el layout, mapea cada pestaña a uno de ESTOS
    // ids. Si la lista viviera en este archivo, esa correspondencia quedaría
    // repartida en dos lugares sin nada que la mantenga junta, y el día que
    // alguien renombre un id la pestaña abriría con un orden que no existe.
    ORDENES = []
  } = $props();

  // VISTAS sí vive acá: ningún otro lugar la usa. Y no es una lista de
  // canales -- son los tres modos de mirar. Qué canal es operativo lo decide
  // el motor con `canal_operativo`.
  const VISTAS = [
    { id: 'operativo', label: 'Operativo' },
    { id: 'pruebas', label: 'Pruebas' },
    { id: 'todos', label: 'Todos' }
  ];
</script>

  <!-- Por que escalo. Veinte casos del mismo tipo se resuelven mas rapido
       seguidos que mezclados con otros veinte de otra cosa: quien atiende
       ya tiene el contexto cargado. El dato estaba guardado desde
       siempre y no habia forma de filtrarlo.

       Se dibuja solo si hay mas de un motivo entre las que esperan: con
       uno solo, el filtro no separa nada y es una fila de ruido. -->
  <div class="controles">
    <!-- Que canales se miran. Operativo (los reales) es el default: una
         prueba del simulador no puede competir con un cliente. -->
    <label class="orden">
      <span class="orden-rotulo">Canales</span>
      <select bind:value={vista} aria-label="Qué canales se ven">
        {#each VISTAS as v (v.id)}
          <option value={v.id}>{v.label}</option>
        {/each}
      </select>
    </label>

    <label class="orden">
      <span class="orden-rotulo">Ordenar por</span>
      <select
        bind:value={orden}
        onchange={() => (ordenElegido = true)}
        aria-label="Ordenar la lista"
      >
        {#each ORDENES as o (o.id)}
          <option value={o.id}>{o.label}</option>
        {/each}
      </select>
    </label>

    <button
      type="button"
      class="motivo"
      aria-pressed={soloEscaladas}
      onclick={() => (soloEscaladas = !soloEscaladas)}
      title="Escalada no es un estado aparte: se cruza con la pestaña que estés viendo"
    >
      Solo escaladas
    </button>
  </div>

  {#if motivos.length > 1}
    <div class="motivos" role="group" aria-label="Filtrar por motivo de escalada">
      <button
        type="button"
        class="motivo"
        aria-pressed={motivo === ''}
        onclick={() => (motivo = '')}>Todos</button
      >
      {#each motivosVisibles as [m, n] (m)}
        <button
          type="button"
          class="motivo"
          aria-pressed={motivo === m}
          onclick={() => (motivo = motivo === m ? '' : m)}
        >
          {motivoLabel(m)}
          <span class="v2-num">{n}</span>
        </button>
      {/each}
      {#if motivos.length > motivosVisibles.length}
        <button
          type="button"
          class="motivo motivo-mas"
          onclick={() => (motivosDesplegados = true)}
        >
          +{motivos.length - motivosVisibles.length} más
        </button>
      {/if}
    </div>
  {/if}

<style>


  /* ── orden y filtro de escalada ──────────────────────────────────────── */
  .controles {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 0 12px 8px;
  }

  .orden {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 11px;
    color: var(--v2-slate);
  }

  .orden-rotulo {
    white-space: nowrap;
  }

  .orden select {
    font: inherit;
    font-size: 11.5px;
    color: var(--v2-ink);
    background: none;
    border: 1px solid var(--v2-line);
    border-radius: 6px;
    /* 28px de alto: por debajo de eso un select deja de ser comodo de
       apuntar, y esta pantalla se usa con prisa. */
    min-height: 28px;
    padding: 2px 6px;
    cursor: pointer;
  }

  .orden select:hover {
    border-color: var(--v2-slate);
  }

  .motivo-mas {
    border-style: dashed;
  }


  /* ── filtro por motivo ───────────────────────────────────────────────── */
  .motivos {
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
    padding: 0 12px 8px;
  }

  .motivo {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    border: 1px solid var(--v2-line);
    background: none;
    border-radius: 999px;
    padding: 2px 9px;
    font: inherit;
    font-size: 11px;
    color: var(--v2-slate);
    cursor: pointer;
    white-space: nowrap;
  }

  .motivo:hover {
    color: var(--v2-ink);
    border-color: var(--v2-slate);
  }

  .motivo[aria-pressed='true'] {
    color: var(--v2-ink);
    border-color: var(--v2-ink);
    font-weight: 650;
  }
</style>
