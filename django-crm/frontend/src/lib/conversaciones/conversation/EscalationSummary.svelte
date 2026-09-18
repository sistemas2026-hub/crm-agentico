<script>
  /**
   * El resumen de por qué esto llegó a una persona: qué quiere el cliente, qué
   * hizo la IA, qué se le prometió y qué falta.
   *
   * Es presentación pura. Los textos los escribe el modelo al evaluar la
   * escalada y llegan ya armados en `resumenEscalada`; `hizoLaIA` sale de la
   * traza. Acá no se resume nada ni se vuelve a derivar: solo se dibuja.
   */
  import { TriangleAlert, CircleCheck, CircleX, ShieldCheck } from '@lucide/svelte';

  let { resumenEscalada, hizoLaIA } = $props();
</script>

  <dl class="brief">
    {#each resumenEscalada as fila (fila.rotulo)}
      <div
        class="brief-fila"
        class:brief-sin-dato={!fila.texto}
        class:brief-primero={fila.orden === 0}
        style="order:{fila.orden}"
      >
        <dt>{fila.rotulo}</dt>
        <dd>
          {#if fila.texto}
            {fila.texto}
            {#if fila.nota}<span class="brief-nota">— {fila.nota}</span>{/if}
          {:else if fila.alerta}
            <span class="brief-alerta"><TriangleAlert size={12} /> {fila.vacio}</span>
          {:else}
            <span class="brief-nada">{fila.vacio}</span>
          {/if}
        </dd>
      </div>
    {/each}

    <!-- Qué hizo la IA. Va después de "qué quiere" porque el orden en que
         alguien entiende un caso es ese: primero qué pedían, después qué se
         intentó. Y antes de "qué falta", que es lo que hay que hacer. -->
    <div class="brief-fila" style="order:1" class:brief-sin-dato={!hizoLaIA.length}>
      <dt>Qué hizo la IA</dt>
      <dd>
        {#if hizoLaIA.length === 0}
          <!-- No es lo mismo "no sabemos" que "no hizo nada". Esto ultimo se
               sabe con certeza --la traza esta vacia-- y le dice a quien
               toma el caso que arranca desde cero, sin ninguna medicion
               hecha. Ocultarlo perderia esa informacion. -->
          <span class="brief-nada">No consultó ningún sistema antes de derivar.</span>
        {:else}
          <ul class="hizo">
            {#each hizoLaIA as h (h.texto)}
              <li class="hizo-{h.estado}">
                {#if h.estado === 'ok'}
                  <CircleCheck size={13} style="color:var(--v2-moss);flex:none" />
                {:else if h.estado === 'bloqueo'}
                  <ShieldCheck size={13} style="color:var(--v2-clay);flex:none" />
                {:else}
                  <CircleX size={13} style="color:var(--v2-rust);flex:none" />
                {/if}
                <span>{h.texto}</span>
                {#if h.detalle}<span class="v2-muted">— {h.detalle}</span>{/if}
              </li>
            {/each}
          </ul>
        {/if}
      </dd>
    </div>
  </dl>

<style>
  /* ── qué pasó acá ───────────────────────────────────────────────────────
     Rótulo a la izquierda, texto a la derecha: se leen los cuatro rótulos en
     vertical de un vistazo y se entra al que interesa. Con el texto debajo
     del rótulo habría que recorrer ocho renglones para lo mismo. */
  .brief {
    margin: 0 0 4px;
    padding: 10px 14px;
    display: flex;
    flex-direction: column;
    gap: 6px;
    background: var(--v2-ember-soft);
    border-radius: 7px;
    font-size: 12.5px;
    line-height: 1.45;
  }
  .brief-fila {
    display: grid;
    grid-template-columns: 8.5rem 1fr;
    gap: 10px;
    align-items: baseline;
  }
  .brief dt {
    color: var(--v2-slate);
    font-size: 11px;
    font-weight: 650;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .brief dd {
    margin: 0;
    color: var(--v2-ink);
  }
  /* El bloque era una sola masa rosa donde promesa, acciones y estado se
     fundian. El fondo de alerta se queda arriba, en el aviso de escalada, que
     es lo unico que de verdad alerta; el resumen pasa a tarjeta neutra con los
     renglones separados por una linea, para que el ojo encuentre cada
     pregunta sin leerlas todas. */
  .brief {
    background: var(--v2-card);
    border: 1px solid var(--v2-line);
  }
  /* El orden en que alguien entiende un caso: que pide, que se intento, que
     se le dijo, que queda. 'Que hizo la IA' sale de un bloque aparte --viene
     de la traza, no de los textos del modelo-- asi que cada renglon lleva su
     posicion como dato y no por el lugar que ocupa en el marcado. */
  .brief {
    display: flex;
    flex-direction: column;
  }

  /* Con 'order' el orden visual no es el del DOM, asi que un selector de
     hermano adyacente pondria la linea entre los renglones equivocados. Se
     usa gap y un borde en todos menos el primero VISUAL, marcado por dato. */
  .brief {
    gap: 7px;
  }
  .brief-fila:not(.brief-primero) {
    border-top: 1px solid var(--v2-line-soft);
    padding-top: 7px;
  }
  /* Un renglon sin dato no puede pesar lo mismo que uno con dato: se ve, para
     que las cuatro preguntas esten siempre, pero no compite. */
  .brief-nada {
    color: var(--v2-slate);
    font-style: italic;
  }
  .brief-alerta {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    color: var(--v2-clay);
    font-weight: 600;
  }
  .brief-nota {
    color: var(--v2-slate);
    font-size: 11px;
  }

  .hizo {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 3px;
  }
  .hizo li {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  /* Lo que se freno o fallo se lee distinto de lo que corrio bien, y no solo
     por el color: tambien por el peso y por el icono. */
  .hizo-bloqueo span:first-of-type {
    color: var(--v2-clay);
    font-weight: 600;
  }
  .hizo-error span:first-of-type {
    color: var(--v2-rust);
    font-weight: 600;
  }
  @media (max-width: 640px) {
    /* En pantalla chica el rótulo de 8.5rem deja al texto en una columna
       inservible: pasan a apilarse. */
    .brief-fila {
      grid-template-columns: 1fr;
      gap: 1px;
    }
  }
</style>
