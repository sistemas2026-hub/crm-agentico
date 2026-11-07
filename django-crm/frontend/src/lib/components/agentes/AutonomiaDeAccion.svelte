<script>
  /**
   * LO QUE ESTE AGENTE HACE SOLO CON ESTA ACCION  --  02/11/2026
   *
   * Vivia en /capacidad, para toda la empresa. El usuario: "eso deberia ir en
   * cada agente... con un agente si pueda reiniciar y otro no". Aca, debajo de
   * cada accion que pide aprobacion, se ve si ESTE agente la hace solo y se
   * cambia (PRD §2 y §8.18).
   *
   * El estado sale del motor (`por_agente`, nucleo/seguridad/autonomia_ganada.py)
   * y el permiso vive en asistente.autonomia_ganada, que falla cerrado -- no en
   * la config del agente, que falla abierto. Lo que se ve aca es solo la
   * palanca.
   *
   * Formularios nativos y no `enhance`: sin `$app/*` el componente se puede
   * probar renderizado (`autonomia-de-accion.test.js`), y una accion de
   * SvelteKit funciona igual sin JavaScript.
   */
  import { textoDeFalta, textoDeNoCandidata } from '$lib/capacidad/autonomia.js';

  /**
   * @type {{
   *   accion: any,
   *   agente: string,
   *   esAdmin?: boolean,
   *   resultado?: any
   * }}
   */
  let { accion, agente, esAdmin = false, resultado = null } = $props();

  let enEste = $derived(accion?.por_agente?.[agente] ?? null);
  let propio = $derived(
    !!resultado && resultado.accion === accion?.accion && (resultado.rol || '') === agente
  );
</script>

<div class="autonomia">
  <div class="fila">
    {#if enEste?.autonoma}
      <span class="chip sola">Lo hace solo</span>
    {:else if enEste?.estado === 'degradada'}
      <span class="chip perdio">La perdió sola</span>
    {:else}
      <span class="chip">Pide aprobación</span>
    {/if}
    {#if accion?.no_critica}<span class="nota">No crítica: no espera evidencia</span>{/if}
  </div>

  {#if enEste?.autonoma && !enEste?.rol}
    <!-- Viene de la promocion GENERAL (sin agente): vale para todo agente que
         use la accion, tambien uno que se cree despues. Quitarsela aca la frena
         solo en este agente (auditoria, M2). -->
    <p class="nota">Por una autorización para todos los agentes que usan esta acción.</p>
  {/if}

  {#if enEste?.estado === 'degradada'}
    <p class="nota falta">Un efecto no se confirmó o una ejecución falló, y volvió sola a pedir aprobación.</p>
  {/if}

  {#if !accion?.candidata}
    <p class="nota">Siempre la aprueba una persona: {textoDeNoCandidata(accion?.no_candidata ?? [])}.</p>
  {:else if esAdmin}
    {#if enEste?.autonoma}
      <form method="POST" action="?/retirar" class="form">
        <input type="hidden" name="accion" value={accion.accion} />
        <input type="hidden" name="rol" value={agente} />
        <input name="motivo" class="v2-input" placeholder="Por qué vuelve a pedir aprobación" required maxlength="500" />
        <button class="v2-btn" type="submit">Que pida aprobación</button>
      </form>
    {:else if accion.elegible}
      <form method="POST" action="?/promover" class="form">
        <input type="hidden" name="accion" value={accion.accion} />
        <input type="hidden" name="rol" value={agente} />
        <label class="nota"><input type="checkbox" name="confirmo" value="si" required />
          Entiendo que este agente va a hacer {accion.accion} sin que una persona lo apruebe, siempre
          después de comprobar sus condiciones en código, y que lo puedo cambiar cuando quiera.</label>
        <button class="v2-btn v2-btn-primary" type="submit">Que lo haga solo</button>
      </form>
    {:else}
      {#each accion.faltan ?? [] as f, i (i)}<p class="nota falta">{textoDeFalta(f)}</p>{/each}
    {/if}
  {/if}

  {#if propio && resultado.error}
    <p class="nota falta">{resultado.error}</p>
    {#each resultado.faltan ?? [] as f, i (i)}<p class="nota falta">{textoDeFalta(f)}</p>{/each}
  {:else if propio && resultado.ok}
    <p class="nota">{resultado.ok === 'promovida' ? 'Listo: este agente la hace solo.' : 'Listo: vuelve a pedir aprobación.'}</p>
  {/if}
</div>

<style>
  .autonomia { display: flex; flex-direction: column; gap: 4px; margin: 2px 0 8px; }
  .fila { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .chip {
    font-size: 11px; padding: 1px 8px; border-radius: 999px;
    border: 1px solid var(--v2-line-strong); color: var(--v2-slate);
  }
  .chip.sola { border-color: var(--v2-moss); color: var(--v2-moss); }
  .chip.perdio { border-color: var(--v2-rust); color: var(--v2-rust); }
  .nota { font-size: 11.5px; color: var(--v2-slate); margin: 0; }
  .nota.falta { color: var(--v2-clay); }
  .form { display: flex; flex-direction: column; gap: 6px; align-items: flex-start; }
</style>
