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
  .eventos { flex: 0 0 318px; background: var(--v2-paper); border-left: 1px solid var(--v2-line); display: flex; flex-direction: column; min-height: 0; }
  header { padding: 12px 16px; border-bottom: 1px solid var(--v2-line); display: flex; justify-content: space-between; align-items: center; font-size: 11.5px; letter-spacing: .12em; text-transform: uppercase; color: var(--v2-ink); }
  .sello { font-family: ui-monospace, monospace; font-size: 10px; color: var(--v2-slate); letter-spacing: 0; }
  .lista { flex: 1; overflow-y: auto; padding: 10px 14px; }
  .evento { padding: 8px 0 8px 14px; border-left: 1px solid var(--v2-line); position: relative; }
  .evento::before { content: ''; position: absolute; left: -4px; top: 13px; width: 7px; height: 7px; border-radius: 50%; background: var(--v2-slate); }
  .evento.escalada::before { background: var(--v2-ember); }
  .evento.accion::before { background: var(--v2-clay); }
  .evento.herramienta_fallida::before { background: var(--v2-rust); }
  .h { font-family: ui-monospace, monospace; font-size: 10px; color: var(--v2-slate); }
  .q { font-size: 10.5px; font-weight: 600; letter-spacing: .05em; text-transform: uppercase; margin-top: 1px; color: var(--v2-ink); }
  .d { font-size: 11px; color: var(--v2-slate); margin-top: 2px; overflow-wrap: anywhere; }
  .vacio { font-size: 11.5px; color: var(--v2-slate); padding: 8px 0; }
</style>
