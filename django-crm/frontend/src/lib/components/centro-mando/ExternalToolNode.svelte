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
    font-family: ui-monospace, monospace; font-size: 10px; color: #475569;
    border: 1px solid #cbd5e1; border-radius: 8px; padding: 4px 9px;
    background: #f8fafc; white-space: nowrap;
  }
  b { color: #0e7490; font-weight: 700; margin-right: 6px; }
  .fallando { border-color: rgba(239,68,68,.5); }
  .fallando b { color: #b91c1c; }
</style>
