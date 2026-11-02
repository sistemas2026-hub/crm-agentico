<script>
  /**
   * "✎ Corregir" — el otro lado de MarcarEjemplo  --  02/11/2026
   * ===========================================================
   *
   * Hasta hoy, desde una burbuja solo se podía decir que una respuesta
   * estuvo BUENA («☆ Buen ejemplo»). Decirlo al revés —esto estuvo mal, y
   * así se hace— no existía: la propia migración de `ejemplos_validados` lo
   * declara como decisión («solo se marcan respuestas BUENAS, no hay
   * contraparte inválida ni flujo de corrección en el momento»).
   *
   * POR QUÉ ESTO NO CREA UN «EJEMPLO MALO»
   * ---------------------------------------
   * Porque un ejemplo marcado hoy NO LLEGA AL AGENTE. Es material crudo
   * para que una persona después escriba algo a mano: el único lector de
   * `ejemplos_validados` es la consulta que pinta /manual, y no hay un solo
   * llamador en `nucleo/modelo/`. Agregarle un estado «malo» habría sumado
   * una segunda marca sin efecto.
   *
   * Lo que SÍ llega al agente es una HABILIDAD: está por rol, la aprueba
   * una persona y el motor le inyecta su índice en cada turno. Entonces
   * corregir es escribir el procedimiento que faltaba, para ESE agente.
   *
   * QUEDA COMO PROPUESTA, SIEMPRE
   * ------------------------------
   * No aprueba nada. Nace `propuesta`, igual que las que escribe una
   * persona desde /habilidades y que las que propone el analista: que la
   * haya escrito alguien mirando una respuesta mala no la pone a operar.
   * Quien la aprueba lo hace en /habilidades, viendo a qué roles se la da.
   *
   * @type {{
   *   rol?: string | null,
   *   textoDeLaRespuesta?: string,
   *   conversacionId?: string | null
   * }}
   */
  let { rol = null, textoDeLaRespuesta = '', conversacionId = null } = $props();

  import { codigoDesde } from './entrenar.js';

  let abierto = $state(false);
  let guardando = $state(false);
  let guardada = $state(false);
  let error = $state('');
  let nombre = $state('');
  let cuandoUsarla = $state('');
  let pasos = $state('');


  function abrir() {
    if (!abierto) {
      error = '';
      guardada = false;
      //  Lo que el agente contestó se precarga como contexto del «cuándo»,
      //  recortado: sirve para recordar de qué se trataba, no para copiarlo
      //  entero a un procedimiento.
      const recorte = (textoDeLaRespuesta || '').trim().slice(0, 180);
      cuandoUsarla = recorte ? `Cuando pase algo como esto: «${recorte}»` : '';
      nombre = '';
      pasos = '';
    }
    abierto = !abierto;
  }

  async function guardar() {
    if (!nombre.trim() || !pasos.trim()) {
      error = 'Falta el nombre y los pasos.';
      return;
    }
    if (!rol) {
      //  Sin rol no se guarda: una habilidad sin roles no la ve ningún
      //  agente, y guardarla igual sería dejar una propuesta muerta que
      //  parece una corrección hecha.
      error = 'No se sabe qué agente atendió esto, así que no se puede corregirlo.';
      return;
    }
    guardando = true;
    error = '';
    try {
      const resp = await fetch('/api/habilidades', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          accion: 'crear',
          codigo: codigoDesde(nombre),
          nombre: nombre.trim(),
          cuando_usarla: cuandoUsarla.trim() || nombre.trim(),
          pasos: pasos.trim(),
          //  EL ROL DE ESTA CONVERSACION, y es toda la diferencia con
          //  marcar un ejemplo: esto le llega al agente que se equivocó.
          roles_permitidos: [rol]
        })
      });
      const datos = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        error = datos?.error || 'No se pudo guardar.';
        return;
      }
      guardada = true;
      abierto = false;
    } catch {
      error = 'No se pudo guardar. Probá de nuevo.';
    } finally {
      guardando = false;
    }
  }
</script>

<div class="corregir">
  <button
    type="button"
    class="corregir-trigger"
    class:hecho={guardada}
    disabled={guardando}
    title={rol
      ? `Escribir el procedimiento que le faltó a «${rol}». Queda como propuesta hasta que alguien la apruebe en Habilidades.`
      : 'No se sabe qué agente atendió esta conversación'}
    onclick={abrir}
  >
    {#if guardada}✓ Corregido{:else}✎ Corregir{/if}
  </button>

  {#if abierto}
    <button
      type="button"
      class="corregir-fondo"
      aria-label="Cerrar"
      onclick={() => (abierto = false)}
    ></button>
    <div class="corregir-panel">
      <p class="corregir-titulo">
        Enseñarle a <strong>{rol ?? '—'}</strong>
      </p>
      <p class="corregir-nota">
        Se guarda como <strong>propuesta</strong>. No cambia nada hasta que la apruebes en
        <a href="/habilidades">Habilidades</a>.
      </p>

      <label class="corregir-campo">
        Qué tiene que saber hacer
        <input
          class="v2-input"
          type="text"
          bind:value={nombre}
          placeholder="Ej: Cambiar la contraseña del wifi"
        />
      </label>

      <label class="corregir-campo">
        Cuándo usarlo
        <textarea class="v2-input" rows="2" bind:value={cuandoUsarla}></textarea>
      </label>

      <label class="corregir-campo">
        Los pasos
        <textarea
          class="v2-input"
          rows="4"
          bind:value={pasos}
          placeholder={'1. ...\n2. ...'}
        ></textarea>
      </label>

      {#if error}<p class="corregir-error">{error}</p>{/if}

      <div class="corregir-acciones">
        <button type="button" class="v2-btn" onclick={() => (abierto = false)}>Cancelar</button>
        <button type="button" class="v2-btn v2-btn-primary" disabled={guardando} onclick={guardar}>
          {guardando ? 'Guardando…' : 'Guardar como propuesta'}
        </button>
      </div>
    </div>
  {/if}
</div>

<style>
  .corregir {
    position: relative;
    display: inline-block;
    margin-top: 6px;
    margin-left: 6px;
  }
  .corregir-trigger {
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 999px;
    border: 1px solid var(--v2-line);
    background: transparent;
    cursor: pointer;
    color: inherit;
    opacity: 0.65;
  }
  .corregir-trigger:hover {
    opacity: 1;
  }
  .corregir-trigger:disabled {
    cursor: default;
    opacity: 0.35;
  }
  .corregir-trigger.hecho {
    opacity: 1;
    border-color: var(--v2-moss);
    color: var(--v2-moss);
    background: color-mix(in srgb, var(--v2-moss) 8%, transparent);
  }
  .corregir-fondo {
    position: fixed;
    inset: 0;
    z-index: 40;
    background: transparent;
    border: none;
    cursor: default;
  }
  .corregir-panel {
    position: absolute;
    z-index: 41;
    top: calc(100% + 4px);
    left: 0;
    width: min(360px, 90vw);
    display: grid;
    gap: 8px;
    padding: 12px;
    border-radius: 10px;
    border: 1px solid var(--v2-line-strong);
    background: var(--v2-surface, #fff);
    box-shadow: 0 8px 24px rgb(0 0 0 / 12%);
    text-align: left;
  }
  .corregir-titulo {
    margin: 0;
    font-size: 13px;
  }
  .corregir-nota {
    margin: 0;
    font-size: 11px;
    color: var(--v2-slate);
  }
  .corregir-campo {
    display: grid;
    gap: 3px;
    font-size: 11px;
    color: var(--v2-slate);
  }
  .corregir-campo :global(input),
  .corregir-campo :global(textarea) {
    font-size: 12px;
  }
  .corregir-error {
    margin: 0;
    font-size: 11px;
    color: var(--v2-error, #b00020);
  }
  .corregir-acciones {
    display: flex;
    justify-content: flex-end;
    gap: 6px;
  }
</style>
