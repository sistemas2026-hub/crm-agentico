<script>
  /**
   * Un sistema externo con lo que se le pidio hoy. Hoy se dibuja como chip en
   * una fila; en la Fase 2 el mismo componente puede recibir `posicion` y
   * quedar anclado al borde del mapa, unido por una FlowLine al agente que lo
   * usa. Lo que no cambia es de donde sale: el motor cuenta tool_calls, no se
   * declara una lista de sistemas a mano.
   */
  /** @type {{ servicio: any, ms: (v: any) => string }} */
  let { servicio, ms } = $props();
</script>

<span class="nodo" class:fallando={servicio.fallos > 0}>
  <b>{servicio.herramienta}</b>
  {servicio.usos} usos · {ms(servicio.duracion_media_ms)}{servicio.fallos ? ` · ${servicio.fallos} fallos` : ''}
</span>

<style>
  .nodo {
    font-family: ui-monospace, monospace; font-size: 10px; color: #8aa2c0;
    border: 1px solid rgba(0,229,255,.28); border-radius: 8px; padding: 4px 9px;
    background: rgba(4,21,37,.6); white-space: nowrap;
  }
  b { color: #00e5ff; font-weight: 700; margin-right: 6px; }
  .fallando { border-color: rgba(239,68,68,.5); }
  .fallando b { color: #ef4444; }
</style>
