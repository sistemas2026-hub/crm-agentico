<script>
  /**
   * El resumen de por qué esto llegó a una persona: qué quiere el cliente, qué
   * hizo la IA, qué se le prometió y qué falta.
   *
   * Es presentación pura. Los textos los escribe el modelo al evaluar la
   * escalada y llegan ya armados en `resumenEscalada`; `hizoLaIA` sale de la
   * traza. Acá no se resume nada ni se vuelve a derivar: solo se dibuja.
   */
  import { TriangleAlert, CircleCheck, CircleX, ShieldCheck,
           ChevronDown, ChevronRight } from '@lucide/svelte';
  import { resumenRecogido } from '$lib/conversaciones/barra-lateral.svelte.js';

  let { resumenEscalada, hizoLaIA } = $props();

  /* SE PUEDE RECOGER, y el estado dura entre conversaciones.
     Estos cuatro renglones ocupan un tercio de la altura util del hilo, y no
     hacen falta las dos veces: al abrir una conversacion se leen una vez para
     entender por que llego, y despues estorban a lo que se esta haciendo, que
     es la conversacion.

     Por que la preferencia se guarda y no arranca abierta siempre: quien
     trabaja un turno entero abre decenas de conversaciones, y volver a
     cerrarlo en cada una es la clase de friccion que hace que la pantalla se
     sienta en contra. Mismo criterio que la barra lateral, y por eso comparte
     su modulo.

     La linea de arriba sigue visible con el resumen recogido: dice CUANTOS
     datos hay debajo, asi que recoger no esconde que exista algo. */
  const recogido = $derived(resumenRecogido.valor);
  const conDato = $derived(resumenEscalada.filter((f) => f.texto).length);
</script>

  <button
    type="button"
    class="brief-toggle"
    onclick={() => resumenRecogido.alternar()}
    aria-expanded={!recogido}
    title={recogido ? 'Mostrar el resumen de la escalada' : 'Recoger el resumen'}
  >
    {#if recogido}<ChevronRight size={13} />{:else}<ChevronDown size={13} />{/if}
    <span>Por qué llegó acá</span>
    <span class="brief-cuenta">{conDato} de {resumenEscalada.length}</span>
  </button>

  <dl class="brief" class:brief-recogido={recogido}>
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
  .brief-toggle {
    display: flex;
    align-items: center;
    gap: 6px;
    width: 100%;
    padding: 5px 14px;
    border: 0;
    background: none;
    font-family: var(--bandeja-mono);
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--bandeja-texto-2);
    cursor: pointer;
    text-align: left;
  }
  .brief-toggle:hover {
    color: var(--bandeja-texto);
  }
  .brief-toggle :global(svg) {
    flex: none;
  }
  /* A la derecha y en cifras: es el dato que dice si vale la pena abrirlo. */
  .brief-cuenta {
    margin-left: auto;
    font-variant-numeric: tabular-nums;
    color: var(--bandeja-texto-3);
    letter-spacing: 0;
  }


  /* ── qué pasó acá ───────────────────────────────────────────────────────
     Rótulo a la izquierda, texto a la derecha: se leen los cuatro rótulos en
     vertical de un vistazo y se entra al que interesa. Con el texto debajo
     del rótulo habría que recorrer ocho renglones para lo mismo. */
  /* RECOGIDO. La regla va DESPUES de '.brief' y repite la clase
     ('.brief.brief-recogido') por dos motivos, y el segundo es el que
     importa: en un <style> de Svelte el orden ES especificidad entre
     selectores de la misma fuerza. La primera version puso
     '.brief-recogido { display: none }' ANTES de '.brief { display: flex }'
     y perdia siempre -- el panel nunca se recogia, aunque la flecha cambiara.
     Visto en produccion el 22/09/2026.

     Repetir la clase lo vuelve inmune a que alguien reordene el archivo
     despues; depender del orden es dejar una trampa para el proximo.

     'display:none' y no altura cero: con altura cero los cuatro renglones
     siguen en el arbol de accesibilidad y un lector de pantalla los lee
     igual, que es justo lo contrario de recoger. */
  .brief.brief-recogido {
    display: none;
  }

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
  /* LOS RÓTULOS SON RÓTULOS, NO TEXTO.
     Estaban a 11px con peso 650 en la misma familia que la respuesta, así que
     las cuatro preguntas pesaban casi tanto como sus cuatro respuestas y el
     bloque se leía como ocho cosas en vez de cuatro. La referencia usa mono
     de 9,5-10px en versalita para todo lo que rotula, y es la misma forma que
     ya tienen `.panel-titulo` en la columna de contexto y `.autor` en el hilo.
     Acá era el único rótulo de la Bandeja que no la usaba. */
  .brief dt {
    color: var(--bandeja-texto-2);
    font-family: var(--bandeja-mono);
    font-size: 9.5px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
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

  /* EL RESUMEN CEDE ALTURA ANTES QUE EL HILO.
     'Qué quiere' imprime el mensaje del cliente entero y sin resumir (es el
     punto: "lo que escribió, sin resumir"), así que este bloque crece sin
     techo. Medido el 21/09/2026 a 390x844: el resumen se llevaba 224px y al
     hilo le quedaban 28 -- ni un mensaje completo en pantalla. A 1024x768,
     175px contra 121.
     La causa es de flex, no de contenido: el resumen no podía encogerse
     (`min-height: auto` = min-content) y el hilo tiene `flex-basis: 0`, así que
     toda la falta de espacio caía del lado del hilo. Con `min-height: 0` el
     resumen sí encoge, y con su propio scroll no se pierde nada: sigue entero,
     se lee bajando. El piso del hilo lo pone `.hilo { min-height }`. */
  .brief {
    min-height: 0;
    overflow-y: auto;
  }

  /* DENSIDAD.
     Medido el 21/09/2026: 157px a 1440 y 224 a 390, contra los 38px que ocupa
     la franja equivalente en la referencia. No se saca información --las
     cuatro preguntas siguen enteras-- se saca AIRE: el separador por fila deja
     de ser una línea con 7px de padding y pasa a ser 5px de espacio, el
     interlineado baja de 1,45 a 1,35 y el texto a 11,5px, que es el tamaño con
     el que la referencia escribe el motivo de la escalada.

     La grilla de 8,5rem se queda: es lo que alinea las cuatro respuestas en
     una columna y deja leer los cuatro rótulos en vertical de un vistazo, que
     era el motivo de usar grilla. */
  .brief {
    gap: 5px;
    padding: 8px 14px;
    font-size: 11.5px;
    line-height: 1.35;
  }

  .brief-fila:not(.brief-primero) {
    padding-top: 5px;
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
