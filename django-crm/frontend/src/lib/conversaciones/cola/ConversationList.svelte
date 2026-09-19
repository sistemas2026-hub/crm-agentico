<script>
  /**
   * La lista de la cola: o las filas, o el hueco que corresponda.
   *
   * NO FILTRA NI ORDENA. `visibles` llega ya resuelta desde `+layout.svelte`,
   * que es donde vive la cadena entera --canal → pestaña → solo escaladas →
   * motivo → búsqueda → ordenar()-- y la autoridad del orden (B3.5/D18). Acá
   * no hay un `.sort()` ni puede haberlo: si esta lista volviera a ordenar,
   * las guardas de `ordenamiento.js` dejarían de proteger lo que se ve.
   *
   * Las tres condiciones de estado vacío viajaron con el `<div class="lista">`
   * porque son la decisión de QUÉ DIBUJAR ADENTRO, y operan sólo sobre props
   * ya resueltas: no recalculan nada ni saben cómo se generó `visibles`.
   *
   * La cáscara de la columna --`.mesa`, `.columna`, `.columna.hay-abierta` y
   * el media query del master-detail-- se queda en el layout. Que la lista
   * desaparezca en pantallas angostas cuando hay una conversación abierta es
   * responsabilidad de la cáscara, no de la lista.
   */
  import QueueEmptyState from '$lib/conversaciones/cola/QueueEmptyState.svelte';
  import ConversationRow from '$lib/conversaciones/cola/ConversationRow.svelte';

  let {
    // Ya filtrada y ordenada por el layout.
    visibles = [],
    // La colección completa, sólo para distinguir "vacía" de "sin coincidencias".
    conversaciones = [],
    error = '',
    busqueda = '',
    // La conversación abierta, para marcar su fila.
    abierta = null,
    // El reloj de 20 s del layout; se propaga tal cual a cada fila.
    ahora = 0,
    // Helpers que se quedan en el layout porque los usa alguien más.
    tramoEspera,
    motivoLabel
  } = $props();
</script>

<div class="lista">
  {#if error}
    <QueueEmptyState variante="error" {error} />
  {:else if conversaciones.length === 0}
    <QueueEmptyState variante="sin-datos" />
  {:else if visibles.length === 0}
    <QueueEmptyState variante="sin-coincidencias" {busqueda} />
  {:else}
    {#each visibles as c (c.id)}
      <ConversationRow {c} {abierta} {ahora} {tramoEspera} {motivoLabel} />
    {/each}
  {/if}
</div>

<style>
  /* Sin padding lateral y sin aire entre filas: las filas ocupan todo el
     ancho y se separan con una línea, como en el diseño congelado. Así entra
     más cola en la misma altura y el conjunto se lee como una lista en vez de
     como una pila de tarjetas. */
  .lista {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    background: var(--bandeja-superficie);
  }
</style>
