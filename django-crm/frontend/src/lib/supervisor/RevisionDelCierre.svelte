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

    <!-- LO QUE SE PIDIO, Y LO QUE LLEGO (06/11/2026). El usuario: «el
         supervisor debe revisar si las fotos coinciden con lo pedido; si
         piden foto del router y manda el TV no debe pasar, y si pide la
         potencia y no manda la potencia no debería pasar».

         El hueco era de INFORMACIÓN, no de poder: «Devolver al técnico» ya
         existía, pero acá solo se veía «El checklist está completo: datos y
         fotos» -- que es contar fotos, no mirarlas-- y los títulos aparecían
         recién dentro del formulario de devolver, sin la imagen y sin lo que
         cada una tenía que mostrar.

         LAS QUE FALTAN TAMBIÉN SALEN, y es la mitad del valor: una foto que
         no llegó es justo la que hay que mirar. Si desapareciera de la lista
         se verían menos filas sin notar cuál falta. -->
    {#if (r.evidencias ?? []).some((e) => e.instrucciones || e.evidencia_id || e.analisis)}
      <details class="rc-fotos" open>
        <summary class="snoc-label">Las fotos que se pidieron</summary>
        <ul>
          {#each r.evidencias as e (e.id)}
            <li class="rc-foto" class:rc-falta={!e.evidencia_id}>
              {#if e.evidencia_id}
                <a href={`/api/supervisor-noc/evidencias/${e.evidencia_id}/archivo`}
                   target="_blank" rel="noopener" title="Abrir la foto">
                  <img src={`/api/supervisor-noc/evidencias/${e.evidencia_id}/archivo`}
                       alt={e.titulo} loading="lazy" />
                </a>
              {:else}
                <span class="rc-sin-foto" aria-hidden="true">—</span>
              {/if}
              <div class="rc-foto-dice">
                <strong>{e.titulo}</strong>{#if e.obligatoria}<span class="rc-obl"> · obligatoria</span>{/if}
                <!-- QUÉ TENÍA QUE MOSTRAR: la mitad de la comparación. Sin
                     esto se compara contra un título de tres palabras. -->
                {#if e.instrucciones}
                  <span class="rc-pedia">Tenía que mostrar: {e.instrucciones}</span>
                {/if}
                {#if !e.evidencia_id}
                  <span class="rc-no-llego">No llegó.</span>
                {/if}
                <!-- LO QUE LA IA VIO, como dato y nunca como veredicto: puede
                     pedir atención, nunca negar un cierre. Quien decide sigue
                     siendo quien mira. -->
                {#if e.analisis}
                  <span class="rc-ia" class:rc-ia-ojo={e.pide_atencion}>
                    {e.pide_atencion ? '⚠' : '·'} {e.analisis}
                  </span>
                {/if}
              </div>
            </li>
          {/each}
        </ul>
      </details>
    {/if}

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
  .rc-fotos summary { cursor: pointer; }
  .rc-fotos ul { list-style: none; margin: var(--snoc-xs) 0 0; padding: 0; display: grid; gap: var(--snoc-xs); }
  .rc-foto {
    display: grid;
    grid-template-columns: 72px minmax(0, 1fr);
    gap: var(--snoc-sm);
    align-items: start;
    padding: 6px;
    border-radius: 6px;
    background: rgba(0, 0, 0, 0.02);
  }
  /*  La que falta se ve distinta SIN depender solo del color: el borde y el
      guion la separan aunque alguien no distinga el rojo. */
  .rc-foto.rc-falta { background: rgba(185, 28, 28, 0.06); border: 1px dashed #b91c1c; }
  .rc-foto img { width: 72px; height: 72px; object-fit: cover; border-radius: 6px; display: block; }
  .rc-sin-foto { display: grid; place-items: center; width: 72px; height: 72px; color: #b91c1c; font-size: 20px; }
  .rc-foto-dice { display: grid; gap: 2px; font-size: 12px; min-width: 0; }
  .rc-obl { color: var(--snoc-on-surface-variant, #666); font-weight: 400; }
  .rc-pedia { color: var(--snoc-on-surface-variant, #666); }
  .rc-no-llego { color: #b91c1c; font-weight: 600; }
  .rc-ia { color: var(--snoc-on-surface-variant, #666); }
  .rc-ia-ojo { color: #8a5300; }
  .rc-punto-false { color: var(--snoc-error); font-weight: 600; }
  .rc-punto-null { color: #8a5300; }
  .rc-acciones { display: flex; flex-wrap: wrap; gap: 8px; }
  .rc-devolver { display: grid; gap: 6px; }
  .rc-devolver fieldset { margin: 0; padding: 4px 0; border: 0; display: grid; gap: 2px; }
  .rc-devolver legend { font-weight: 600; }
  .rc-porque { display: grid; gap: 2px; }
  .rc-porque textarea { font: inherit; width: 100%; box-sizing: border-box; }
</style>
