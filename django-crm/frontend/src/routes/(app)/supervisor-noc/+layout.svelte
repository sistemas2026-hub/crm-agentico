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
  import PulsoDelNoc from '$lib/supervisor/ui/PulsoDelNoc.svelte';
  import Avisos from '$lib/supervisor/ui/Avisos.svelte';

  /** @type {{ children: import('svelte').Snippet }} */
  let { children } = $props();
</script>

<!-- EL PULSO DEL NOC (21/11/2026): la misma franja en las siete pantallas.
     Va acá, fuera del contenedor que se desplaza de cada página, así queda
     siempre a la vista. Ver PulsoDelNoc.svelte. -->
<PulsoDelNoc />

{@render children()}

<!-- La burbuja es fija y de la pantalla, no de una sección. Ver
     ChatBurbuja.svelte: recupera el hilo al montarse. -->
<ChatBurbuja />

<!-- El resultado de cada acción, a la vista (ver avisos.svelte.js). -->
<Avisos />
