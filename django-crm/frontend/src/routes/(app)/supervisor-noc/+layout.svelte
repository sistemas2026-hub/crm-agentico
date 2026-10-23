<script>
  /**
   * Las pestañas del Supervisor NOC comparten el chat (21/10/2026).
   *
   * Pedido del usuario: «el chat de Supervisor ¿no debe salir en todas las
   * pestañas de Supervisor?». Hasta hoy la burbuja se montaba solo en
   * Pendientes, y en Cuadrillas, Despacho o Plantillas no había forma de
   * hablarle al Supervisor — justo donde se arma la jornada y se le delegan
   * tareas. Montada acá, una sola vez, aparece en todas, y como el layout no se
   * desmonta al cambiar de pestaña, la conversación tampoco se corta.
   */
  import ChatBurbuja from '$lib/supervisor/ChatBurbuja.svelte';

  /** @type {{ children: import('svelte').Snippet }} */
  let { children } = $props();
</script>

{@render children()}

<!-- La burbuja es fija y de la pantalla, no de una sección. Ver
     ChatBurbuja.svelte: recupera el hilo al montarse. -->
<ChatBurbuja />
