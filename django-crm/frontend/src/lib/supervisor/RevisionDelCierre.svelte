<!--
  LO QUE DICE EL SUPERVISOR DEL CIERRE, en la tarjeta de la orden (30/10/2026,
  SPEC/objetivos/revision-del-cierre.md). El usuario: «al momento que el
  técnico envía el reporte final, el supervisor debe revisar si quedó bien y
  indicar si lo cierra o no y por qué».

  El Supervisor INDICA; la persona confirma con un toque. Aprobar cierra el
  ticket del ISP por la puerta humana del motor, y esa puerta no es de una IA.
  Devolver lleva ya escrito el porqué del Supervisor, y marcadas las fotos que
  el checklist dice que faltan.

  Formularios nativos, sin `enhance`: al confirmar, la página se vuelve a
  cargar con la orden ya movida. Un doble clic no decide dos veces: la clave
  de idempotencia es la orden y su vuelta (`server/v2/revision-del-cierre.js`).
-->
<script>
  import { motivosDeLaRevision } from './dia-publicado.js';

  /** @type {{ orden: any }} */
  let { orden } = $props();

  const r = $derived(orden.revision);
  const marca = /** @type {Record<string, string>} */ ({ true: '✔', false: '✖', null: '?' });
  let devolviendo = $state(false);
  //  LO QUE SE ESTÁ ESCRIBIENDO NO SE PISA (30/10/2026). Programación se
  //  actualiza sola cada pocos segundos; si el porqué y las casillas salieran
  //  de la revisión en vivo, cada vuelta borraría lo que la persona escribió.
  //  Se toman UNA vez, al abrir «Devolver».
  let porque = $state('');
  /** @type {string[]} */
  let marcadas = $state([]);

  function abrirDevolver() {
    if (!devolviendo) {
      porque = motivosDeLaRevision(r);
      marcadas = [...(r?.sugeridas ?? [])];
    }
    devolviendo = !devolviendo;
  }
</script>

{#if r}
  <section class="rc rc-{r.veredicto}" aria-label="Revisión del cierre">
    <p class="rc-titulo"><strong>El Supervisor revisó el cierre:</strong> {r.texto}</p>
    {#if r.solucion}<p class="rc-solucion">Qué hizo: «{r.solucion}»</p>{/if}
    {#if r.supervisor_no_pudo}
      <!-- La quiso cerrar solo y no quedó cerrada: cuándo, y si el motor no lo
           dejó o no se sabe si el ISP la cerró (no es lo mismo). -->
      {#if r.supervisor_no_pudo.detalle.includes('ESTADO_INCIERTO')}
        <p class="rc-no-pudo">El Supervisor la quiso cerrar solo a las {r.supervisor_no_pudo.hora} y no se sabe si el ISP la cerró: revisalo en su sistema antes de aprobar.</p>
      {:else}
        <p class="rc-no-pudo">El Supervisor la quiso cerrar solo a las {r.supervisor_no_pudo.hora} y el motor no lo dejó: {r.supervisor_no_pudo.detalle}</p>
      {/if}
    {/if}
    <ul class="rc-puntos">
      {#each r.puntos as p (p.clave)}
        <li class="rc-punto-{String(p.ok)}"><span aria-hidden="true">{marca[String(p.ok)]}</span> {p.texto}</li>
      {/each}
    </ul>

    <div class="rc-acciones">
      <form method="POST" action="?/aprobar">
        <input type="hidden" name="orden" value={orden.id} />
        <input type="hidden" name="vuelta" value={orden.vuelta ?? 1} />
        <input type="hidden" name="veredicto" value={r.texto} />
        <button type="submit" class="snoc-btn snoc-btn-primario" >Aprobar y cerrar</button>
      </form>
      <button type="button" class="snoc-btn" onclick={abrirDevolver} aria-expanded={devolviendo}>
        Devolver al técnico
      </button>
    </div>

    {#if devolviendo}
      <form method="POST" action="?/devolver" class="rc-devolver">
        <input type="hidden" name="orden" value={orden.id} />
        <input type="hidden" name="vuelta" value={orden.vuelta ?? 1} />
        <fieldset>
          <legend>Qué tiene que rehacer</legend>
          {#each r.evidencias as e (e.id)}
            <label><input type="checkbox" name="requisito" value={e.id} bind:group={marcadas} /> {e.titulo}</label>
          {:else}
            <p>Esta plantilla no pide fotos: no hay qué devolver desde acá.</p>
          {/each}
        </fieldset>
        <label class="rc-porque">Por qué
          <textarea name="observacion" rows="3" bind:value={porque}></textarea>
        </label>
        <button type="submit" class="snoc-btn snoc-btn-error" disabled={!r.evidencias.length}>Devolver</button>
      </form>
    {/if}
  </section>
{/if}

<style>
  .rc {
    display: grid;
    gap: 6px;
    padding: 8px 10px;
    border-radius: var(--snoc-r-xl);
    font-size: 13px;
    line-height: 18px;
    border-left: 3px solid var(--snoc-outline-variant);
    background: var(--snoc-surface-container);
  }
  .rc-se_puede_cerrar { border-left-color: var(--snoc-primary); }
  .rc-revisar { border-left-color: #8a5300; }
  .rc-no_cerrar { border-left-color: var(--snoc-error); background: var(--snoc-error-container); }
  .rc-titulo, .rc-solucion { margin: 0; overflow-wrap: anywhere; }
  .rc-solucion { font-style: italic; color: var(--snoc-on-surface-variant); }
  .rc-no-pudo { margin: 0; font-size: 12px; color: #8a5300; overflow-wrap: anywhere; }
  .rc-puntos { list-style: none; margin: 0; padding: 0; display: grid; gap: 2px; font-size: 12px; }
  .rc-punto-false { color: var(--snoc-error); font-weight: 600; }
  .rc-punto-null { color: #8a5300; }
  .rc-acciones { display: flex; flex-wrap: wrap; gap: 8px; }
  .rc-devolver { display: grid; gap: 6px; }
  .rc-devolver fieldset { margin: 0; padding: 4px 0; border: 0; display: grid; gap: 2px; }
  .rc-devolver legend { font-weight: 600; }
  .rc-porque { display: grid; gap: 2px; }
  .rc-porque textarea { font: inherit; width: 100%; box-sizing: border-box; }
</style>
