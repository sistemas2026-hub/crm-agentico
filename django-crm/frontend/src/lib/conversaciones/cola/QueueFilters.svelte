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
   *
   * DOS RENGLONES, NO CUATRO  (04/11/2026)
   * Los filtros ocupaban hasta cuatro renglones -- controles envueltos, dos
   * filas de motivos y el «+N más» -- y cada uno se lo quitaba a la lista, que
   * es lo que importa. Ahora son exactamente dos: los controles, y los motivos
   * en una tira que se desplaza de costado. Con el desplazamiento todos los
   * motivos están a la vista de un gesto, así que el «+N más» se fue: era un
   * tercer renglón para esconder lo que la tira ya no necesita esconder.
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
    // --- derivado del layout: se representa, no se recalcula
    motivos = [],
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

  /* Un filtro activo que no se ve es la forma más rápida de creer que la
     bandeja está vacía. Los motivos se reordenan por cantidad con cada
     sondeo, así que el elegido puede quedar fuera de la tira: se lo trae a
     la vista cada vez que cambia el motivo o la lista. */
  let tira = $state(/** @type {HTMLElement|null} */ (null));
  $effect(() => {
    void motivos;
    if (!tira || !motivo) return;
    const elegido = /** @type {HTMLElement|null} */ (
      tira.querySelector('[data-motivo][aria-pressed="true"]'));
    if (!elegido) return;
    // Con rectángulos y no con offsetLeft: la tira no está posicionada, así
    // que el offsetParent del chip no es ella.
    const r = elegido.getBoundingClientRect();
    const t = tira.getBoundingClientRect();
    if (r.left < t.left) tira.scrollLeft -= t.left - r.left + 12;
    else if (r.right > t.right) tira.scrollLeft += r.right - t.right + 12;
  });
</script>

  <!-- Una sola fila: QUÉ se ve, EN QUÉ ORDEN, y la excepción que se cruza
       con la pestaña. No envuelve: si la columna se angosta, los selectores
       ceden ancho antes que partir la fila en dos. -->
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

    <button
      type="button"
      class="motivo escaladas"
      aria-pressed={soloEscaladas}
      onclick={() => (soloEscaladas = !soloEscaladas)}
      title="Escalada no es un estado aparte: se cruza con la pestaña que estés viendo"
    >
      Solo escaladas
    </button>
  </div>

  <!-- Por que escalo. Veinte casos del mismo tipo se resuelven mas rapido
       seguidos que mezclados con otros veinte de otra cosa: quien atiende
       ya tiene el contexto cargado.

       Se dibuja solo si hay mas de un motivo en la pestaña: con uno solo, el
       filtro no separa nada y es una fila de ruido. -->
  {#if motivos.length > 1}
    <div class="motivos" role="group" aria-label="Filtrar por motivo de escalada" bind:this={tira}>
      <button
        type="button"
        class="motivo"
        aria-pressed={motivo === ''}
        onclick={() => (motivo = '')}>Todos</button
      >
      {#each motivos as [m, n] (m)}
        <button
          type="button"
          class="motivo"
          data-motivo
          aria-pressed={motivo === m}
          onclick={() => (motivo = motivo === m ? '' : m)}
        >
          {motivoLabel(m)}
          <span class="b-cifra">{n}</span>
        </button>
      {/each}
    </div>
  {/if}

<style>
  /* ── canal, orden y filtro de escalada ───────────────────────────────── */
  /* Una fila, sin envolver. Antes envolvía porque los tres controles medían
     459px en 329 (21/09/2026: el chip «Solo escaladas» se salía de la columna
     y se dibujaba ENCIMA del panel de la conversación). Lo que lo hace entrar
     ahora es el ancho, no el envoltorio: rótulos de 12px escritos normal en
     vez de versalita espaciada, y selectores que pueden ceder ancho
     (`min-width: 0`) antes que empujar el interruptor fuera de la columna. */
  /* MEDIDO el 04/11/2026 con las fuentes cargadas, a 360px: con la flecha
     nativa del selector la fila pedía 366px y recortaba «Operativ…»; con la
     flecha dibujada acá (12px en vez de ~20) y 6px entre controles, pide 346
     y el interruptor termina en 348. Entra con 2px de margen: si se agrega
     algo a esta fila, deja de entrar. */
  .controles {
    display: flex;
    flex-wrap: nowrap;
    align-items: center;
    gap: 6px;
    padding: 0 12px 8px;
    min-width: 0;
  }

  .orden {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    min-width: 0;
    flex: 0 1 auto;
  }

  /* Los mismos valores que `.b-rotulo`: texto chico gris, escrito normal. */
  .orden-rotulo {
    flex: none;
    white-space: nowrap;
    font-family: var(--bandeja-sans);
    font-size: var(--bandeja-rotulo-tam);
    color: var(--bandeja-texto-2);
  }

  .orden select {
    min-width: 0;
    appearance: none;
    -webkit-appearance: none;
    font-family: var(--bandeja-sans);
    font-size: 12px;
    color: var(--bandeja-texto);
    border: 1px solid var(--bandeja-borde);
    border-radius: var(--bandeja-radio-sm);
    /* 26px de alto: el mínimo que sigue siendo cómodo de apuntar. Esta
       pantalla se usa con prisa, así que por debajo de esto no se baja. */
    min-height: 26px;
    padding: 1px 12px 1px 4px;
    /* La flecha: dos triángulos de 4px, del gris de los rótulos. */
    background-color: var(--bandeja-superficie);
    background-image: linear-gradient(45deg, transparent 50%, var(--bandeja-texto-2) 50%),
      linear-gradient(135deg, var(--bandeja-texto-2) 50%, transparent 50%);
    background-position: calc(100% - 8px) 55%, calc(100% - 4px) 55%;
    background-size: 4px 4px;
    background-repeat: no-repeat;
    cursor: pointer;
  }

  .orden select:hover {
    border-color: var(--bandeja-texto-2);
  }

  /* El interruptor va al final de la fila, pegado al borde derecho. Con las
     dos clases: `.motivo` se declara más abajo y, con una sola, su padding
     ganaba y la fila volvía a no entrar. */
  .motivo.escaladas {
    margin-left: auto;
    flex: none;
    min-height: 26px;
    padding: 2px 4px;
  }

  /* ── filtro por motivo ───────────────────────────────────────────────── */
  /* Una tira que se desplaza de costado, sin envolver. La barra de
     desplazamiento fina y no la del sistema: en Windows la de serie mide 17px
     y sería la cosa más gruesa de la columna. */
  .motivos {
    display: flex;
    flex-wrap: nowrap;
    gap: 4px;
    padding: 0 12px 8px;
    min-width: 0;
    overflow-x: auto;
  }

  /* La regla estándar SOLO donde no hay pseudo-elementos: Chrome, al ver
     `scrollbar-width`, ignora los ::-webkit-scrollbar de abajo y en Windows
     dibujaba la barra «fina» con sus dos flechas (visto en producción el
     04/11/2026). Firefox no tiene los pseudo-elementos y usa esta. */
  @supports not selector(::-webkit-scrollbar) {
    .motivos {
      scrollbar-width: thin;
      scrollbar-color: var(--bandeja-borde-fuerte) transparent;
    }
  }

  .motivos::-webkit-scrollbar {
    height: 4px;
  }

  .motivos::-webkit-scrollbar-thumb {
    background: var(--bandeja-borde-fuerte);
    border-radius: 2px;
  }

  .motivo {
    flex: none;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    border: 1px solid var(--bandeja-borde);
    background: var(--bandeja-superficie);
    /* Radio chico, no píldora: el lenguaje del diseño separa con borde y
       superficie, no con esquinas redondas. */
    border-radius: var(--bandeja-radio-sm);
    padding: 2px 8px;
    font-family: var(--bandeja-sans);
    font-size: 12px;
    color: var(--bandeja-texto-2);
    cursor: pointer;
    white-space: nowrap;
  }

  .motivo:hover {
    color: var(--bandeja-texto);
    border-color: var(--bandeja-texto-2);
  }

  /* El filtro puesto se marca en azul, igual que la pestaña activa: las dos
     dicen "esto lo elegiste vos". Sin cambiar el peso, para que la tira no
     salte de ancho al elegir. */
  .motivo[aria-pressed='true'] {
    color: var(--bandeja-humano);
    background: var(--bandeja-humano-fondo);
    border-color: var(--bandeja-humano-borde);
  }
</style>
