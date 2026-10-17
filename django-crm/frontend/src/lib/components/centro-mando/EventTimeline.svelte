<script>
  /**
   * El ticker de actividad. Cada evento trae metadatos -- herramienta, rol,
   * exito, duracion, motivo de escalamiento -- y nunca contenido de la
   * conversacion: esta pantalla se mira de lejos y en grupo, y lo que
   * escribio el cliente tiene su lugar en la bandeja, que exige entrar.
   */
  /** @type {{ eventos: any[], hora: (iso: any) => string, ms: (v: any) => string, sello: string }} */
  let { eventos, hora, ms, sello } = $props();

  function texto(/** @type {any} */ e) {
    if (e.tipo === 'escalada') return `Conversación escalada${e.motivo ? `: ${e.motivo}` : ''}`;
    if (e.tipo === 'herramienta_fallida') return `${e.herramienta} falló`;
    if (e.tipo === 'accion') return `${e.herramienta} ejecutada`;
    return `${e.herramienta} · ${ms(e.duracion_ms)}`;
  }
</script>

<aside class="eventos">
  <header>
    <span>Actividad reciente</span>
    <span class="sello">{sello}</span>
  </header>
  <div class="lista">
    {#each eventos as e}
      <div class="evento {e.tipo}">
        <div class="h">{hora(e.en)}</div>
        <div class="q">{e.agente.replaceAll('_', ' ')}</div>
        <div class="d">{texto(e)}</div>
      </div>
    {:else}
      <p class="vacio">Sin actividad registrada en las últimas 6 horas.</p>
    {/each}
  </div>
</aside>

<style>
  .eventos { flex: 0 0 318px; background: #f8fafc; border-left: 1px solid #e2e8f0; display: flex; flex-direction: column; min-height: 0; }
  header { padding: 12px 16px; border-bottom: 1px solid #e2e8f0; display: flex; justify-content: space-between; align-items: center; font-size: 11.5px; letter-spacing: .12em; text-transform: uppercase; color: #0f172a; }
  .sello { font-family: ui-monospace, monospace; font-size: 10px; color: #64748b; letter-spacing: 0; }
  .lista { flex: 1; overflow-y: auto; padding: 10px 14px; }
  .evento { padding: 8px 0 8px 14px; border-left: 1px solid #e2e8f0; position: relative; }
  .evento::before { content: ''; position: absolute; left: -4px; top: 13px; width: 7px; height: 7px; border-radius: 50%; background: #0e7490; }
  .evento.escalada::before { background: #6d28d9; }
  .evento.accion::before { background: #a15c07; }
  .evento.herramienta_fallida::before { background: #b91c1c; }
  .h { font-family: ui-monospace, monospace; font-size: 10px; color: #475569; }
  .q { font-size: 10.5px; font-weight: 600; letter-spacing: .05em; text-transform: uppercase; margin-top: 1px; color: #0f172a; }
  .d { font-size: 11px; color: #475569; margin-top: 2px; overflow-wrap: anywhere; }
  .vacio { font-size: 11.5px; color: #64748b; padding: 8px 0; }
</style>
