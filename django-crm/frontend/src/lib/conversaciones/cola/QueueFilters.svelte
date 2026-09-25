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
      <span class="orden-rotulo">Canal</span>
      <select bind:value={vista} aria-label="Qué canales se ven">
        {#each VISTAS as v (v.id)}
          <option value={v.id}>{v.label}</option>
        {/each}
      </select>
    </label>

    <label class="orden">
      <span class="orden-rotulo">Orden</span>
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

    <!-- Los dos selectores juntos y el interruptor después: son QUÉ se ve y
         EN QUÉ ORDEN, contra una excepción que se cruza con la pestaña.
         Con los rótulos acortados ("Canal", "Orden") y las opciones más
         cortas, los dos entran en un renglón (116 + 140 de 304) y el
         interruptor se lleva el segundo. Antes eran tres renglones. -->
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
  /* Envuelve. Los tres controles miden 459px y la columna de la cola son 329px:
     sin `wrap` la fila se salía 130px y, como `.columna` no recorta en X, el
     chip "Solo escaladas" se dibujaba ENCIMA del panel de la conversación
     (medido el 21/09/2026: borde derecho del chip en 681px, borde de la columna
     en 552px). Envolver es lo correcto acá y no achicar los controles: los
     rótulos ya van en `nowrap` porque "Ordenar por" partido en dos no se lee. */
  .controles {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
    row-gap: 4px;
    padding: 6px 10px;
    border-bottom: 1px solid var(--bandeja-borde);
  }

  .orden {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    color: var(--bandeja-texto-2);
  }

  /* El rótulo es un rótulo: mono en versalita, como `.panel-titulo` en la
     columna de contexto, `.autor` en el hilo y `.marca-banda` en la fila. Era
     lo único de la cola que rotulaba con texto normal de 11px, y además es lo
     que hacía que los tres controles midieran 459px en una columna de 329 --
     o sea tres renglones donde la referencia usa uno. Angosto sigue
     envolviendo; lo que cambia es que ahora entra. */
  .orden-rotulo {
    white-space: nowrap;
    font-family: var(--bandeja-mono);
    font-size: 9.5px;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }

  .orden select {
    font-family: var(--bandeja-sans);
    font-size: 11.5px;
    color: var(--bandeja-texto);
    background: none;
    border: 1px solid var(--bandeja-borde);
    border-radius: var(--bandeja-radio-sm);
    /* 26px de alto: el mínimo que sigue siendo cómodo de apuntar. Esta
       pantalla se usa con prisa, así que por debajo de esto no se baja. */
    min-height: 26px;
    padding: 1px 4px;
    cursor: pointer;
  }

  .orden select:hover {
    border-color: var(--bandeja-texto-2);
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
    border: 1px solid var(--bandeja-borde);
    background: var(--bandeja-superficie);
    /* Radio chico, no píldora: el lenguaje del diseño separa con borde y
       superficie, no con esquinas redondas. */
    border-radius: var(--bandeja-radio-sm);
    padding: 2px 8px;
    font: inherit;
    font-size: 11px;
    color: var(--bandeja-texto-2);
    cursor: pointer;
    white-space: nowrap;
  }

  .motivo:hover {
    color: var(--bandeja-texto);
    border-color: var(--bandeja-texto-2);
  }

  /* El filtro puesto se marca en azul, igual que la pestaña activa: las dos
     dicen "esto lo elegiste vos". */
  .motivo[aria-pressed='true'] {
    color: var(--bandeja-humano);
    background: var(--bandeja-humano-fondo);
    border-color: var(--bandeja-humano-borde);
    font-weight: 650;
  }
</style>
