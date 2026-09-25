<script>
  /**
   * Centro de mando. Esta pantalla solo ensambla: quien trae los datos es el
   * AgentEventService (lib/centro-mando/eventos.js) y quien los pinta es
   * CommandCenter (lib/components/centro-mando/). Aqui no hay ni lógica de
   * dominio ni estilos de la sala, a proposito -- asi la Fase 2 puede
   * cambiar el transporte a push, o agregar una vista de mapa, sin tocar la
   * ruta.
   */
  import { onMount } from 'svelte';
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import { Button } from '$lib/components/ui/button/index.js';
  import { AlertTriangle, RefreshCw } from '@lucide/svelte';
  import CommandCenter from '$lib/components/centro-mando/CommandCenter.svelte';
  import { crearServicioEventos } from '$lib/centro-mando/eventos.js';

  /** @type {{ data: any }} */
  let { data } = $props();

  let panorama = $state(data.panorama);
  let error = $state(data.error || '');
  let sello = $state(/** @type {string|null} */ (null));
  let refrescando = $state(false);

  const servicio = crearServicioEventos({ inicial: data.panorama });

  onMount(() => {
    const soltarPanorama = servicio.alPanorama((p) => {
      panorama = p;
      error = '';
      sello = servicio.ultimoCambio;
      refrescando = false;
    });
    const soltarError = servicio.alError((e) => {
      error = e;
      refrescando = false;
    });
    servicio.arrancar();
    return () => {
      soltarPanorama();
      soltarError();
      servicio.detener();
    };
  });

  function refrescar() {
    refrescando = true;
    servicio.refrescar();
    // Si el transporte no contesta, el boton no se queda girando para siempre.
    setTimeout(() => (refrescando = false), 8000);
  }
</script>

<PageHeader title="Centro de mando" subtitle="Qué está haciendo cada agente ahora mismo">
  {#snippet actions()}
    <Button variant="outline" size="sm" onclick={refrescar} disabled={refrescando}>
      <RefreshCw class="mr-2 size-4 {refrescando ? 'animate-spin' : ''}" />
      Actualizar
    </Button>
  {/snippet}
</PageHeader>

{#if error}
  <div class="mb-4 flex items-start gap-3 rounded-lg border border-amber-500/40 bg-amber-500/10 p-4">
    <AlertTriangle class="mt-0.5 size-5 shrink-0 text-amber-500" />
    <div>
      <p class="font-medium">No se pudo leer la operación</p>
      <p class="text-muted-foreground text-sm">{error}</p>
    </div>
  </div>
{/if}

{#if panorama}
  <CommandCenter {panorama} {sello} />
{/if}
