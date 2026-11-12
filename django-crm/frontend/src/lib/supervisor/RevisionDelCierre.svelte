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
  import {
    MAX_INSTRUCCION,
    cuerpoDePrueba,
    queSignifica,
    sePuedeProbar,
    veredicto
  } from './afinar_instruccion.js';
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

  //  ===================================================================
  //   AFINAR LA INSTRUCCION DE UNA FOTO  --  06/11/2026
  //  ===================================================================
  //  El usuario, viendo cuatro fotos marcadas «no es lo que se pidio»:
  //  «hagamoslo mas facil, que uno le indique por texto y guarde eso».
  //
  //  Se mide primero: una foto marcada mal puede ser la FOTO o puede ser
  //  la INSTRUCCION. El 06/11 se comprobo que era la instruccion -- pedia
  //  «Velocidad contratada» y un speedtest no la muestra--. Desde aca se
  //  prueba el texto contra esa misma foto y recien despues se guarda.
  //
  //  EL ESTADO ES POR FOTO Y VIVE ACA, no en la revision: Programacion se
  //  refresca sola cada pocos segundos y lo que alguien esta escribiendo
  //  no se puede pisar. Misma razon que `porque` y `marcadas`.
  /** @type {Record<string, any>} */
  let afinando = $state({});

  function abrirAfinar(/** @type {any} */ e) {
    const id = e.id;
    if (afinando[id]) {
      afinando = { ...afinando, [id]: null };
      return;
    }
    afinando = {
      ...afinando,
      [id]: {
        texto: e.instrucciones ?? '',
        guardado: e.instrucciones ?? '',
        //  LA PERSONA SABE ALGO QUE EL MODELO NO: si esa foto estaba bien.
        //  Sin ese dato, un «SI muestra» puede ser un acierto o una
        //  redaccion laxa que aprueba cualquier cosa.
        fotoEstaBien: true,
        cargando: false,
        error: '',
        resultado: null,
        guardadoOk: ''
      }
    };
  }

  function cambiar(/** @type {string} */ id, /** @type {any} */ parche) {
    afinando = { ...afinando, [id]: { ...afinando[id], ...parche } };
  }

  async function probar(/** @type {any} */ e) {
    const id = e.id;
    const a = afinando[id];
    const { puede, motivo } = sePuedeProbar(a.texto, a.guardado);
    if (!puede) {
      cambiar(id, { error: motivo, resultado: null });
      return;
    }
    cambiar(id, { cargando: true, error: '', resultado: null, guardadoOk: '' });
    try {
      const resp = await fetch(
        `/api/supervisor-noc/evidencias/${e.evidencia_id}/probar-instruccion`,
        {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify(cuerpoDePrueba(a.texto))
        }
      );
      const datos = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        cambiar(id, { cargando: false, error: datos?.detalle || `No se pudo probar (HTTP ${resp.status}).` });
        return;
      }
      cambiar(id, { cargando: false, resultado: datos });
    } catch {
      cambiar(id, { cargando: false, error: 'No se pudo probar: revisá la conexión.' });
    }
  }

  async function guardar(/** @type {any} */ e) {
    const id = e.id;
    const a = afinando[id];
    cambiar(id, { cargando: true, error: '', guardadoOk: '' });
    try {
      const resp = await fetch(
        `/api/supervisor-noc/evidencias/${e.evidencia_id}/guardar-instruccion`,
        {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify(cuerpoDePrueba(a.texto))
        }
      );
      const datos = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        cambiar(id, { cargando: false, error: datos?.detalle || `No se pudo guardar (HTTP ${resp.status}).` });
        return;
      }
      //  SE DICE QUE ESTA ORDEN NO CAMBIA. Sin esto alguien guarda, mira
      //  la tarjeta que tiene delante, no ve nada y cree que fallo.
      const vivas = datos.ordenes_vivas ?? 0;
      cambiar(id, {
        cargando: false,
        guardado: a.texto,
        guardadoOk:
          (datos.cambio ? `Guardado (versión ${datos.version}).` : 'Ya estaba guardado así.') +
          ' Vale para las órdenes NUEVAS; esta y las que están en curso' +
          (vivas ? ` (${vivas})` : '') +
          ' conservan la instrucción con la que nacieron.'
      });
    } catch {
      cambiar(id, { cargando: false, error: 'No se pudo guardar: revisá la conexión.' });
    }
  }
</script>

{#if r}
  <section class="rc rc-{r.veredicto}" aria-label="Revisión del cierre">
    <p class="rc-titulo"><strong>El Supervisor revisó el cierre:</strong> {r.texto}</p>
    <!-- LOS DOS LADOS, UNO AL LADO DEL OTRO (12/11/2026). El usuario:
         «debe haber relación entre el asunto, la descripción del ticket y la
         respuesta del técnico. No puede haber una respuesta correcta en un
         asunto que ni por ahí iba al caso». Hasta hoy esta tarjeta mostraba
         «Qué hizo» y nada de lo que se le pidió: para cruzarlos había que
         abrir la orden en otra pantalla, y nadie lo hacía. Es el mismo hueco
         del 06/11 con las fotos --«no había con qué comparar»--, con texto. -->
    {#if r.el_ticket?.caso || r.el_ticket?.diagnostico_previo}
      <div class="rc-cotejo">
        <p class="rc-pedido">
          <span class="rc-rotulo">Se pidió</span>
          {#if r.el_ticket.asunto}<span class="rc-asunto">{r.el_ticket.asunto}</span>{/if}
          {#if r.el_ticket.caso}<span class="rc-caso">{r.el_ticket.caso}</span>{/if}
        </p>
        {#if r.el_ticket.diagnostico_previo}
          <p class="rc-previo">
            <span class="rc-rotulo">Ya se había diagnosticado</span>
            {r.el_ticket.diagnostico_previo}
          </p>
        {/if}
        {#if r.solucion}
          <p class="rc-solucion">
            <span class="rc-rotulo">Qué hizo</span>«{r.solucion}»
          </p>
        {:else}
          <p class="rc-solucion rc-sin-solucion">
            <span class="rc-rotulo">Qué hizo</span>no lo escribió
          </p>
        {/if}
      </div>
    {:else if r.solucion}
      <p class="rc-solucion"><span class="rc-rotulo">Qué hizo</span>«{r.solucion}»</p>
    {/if}
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
                <!-- NO ES LO QUE SE PIDIO: va primero y aparte del resto
                     del analisis. «Se ve un cable suelto» dice que el TRABAJO
                     tiene un problema; «hay un televisor donde pedian el
                     router» dice que la FOTO esta mal. Una se arregla
                     volviendo a la casa, la otra sacando otra foto. -->
                {#if e.muestra_lo_pedido === false}
                  <span class="rc-no-es">✗ No es lo que se pidió.</span>
                {/if}
                {#if e.analisis}
                  <span class="rc-ia" class:rc-ia-ojo={e.pide_atencion}>
                    {e.pide_atencion ? '⚠' : '·'} {e.analisis}
                  </span>
                {/if}

                <!-- AFINAR LA INSTRUCCIÓN, desde donde se descubre que está
                     mal. Solo con la foto presente: sin foto no hay contra qué
                     probar, y guardar a ciegas es lo que ya se podía hacer en
                     el editor de plantillas. -->
                {#if e.evidencia_id}
                  <button type="button" class="rc-afinar-abrir" onclick={() => abrirAfinar(e)}>
                    {afinando[e.id] ? 'Cerrar' : '✎ Afinar lo que se le pide'}
                  </button>
                {/if}

                {#if afinando[e.id]}
                  {@const a = afinando[e.id]}
                  <div class="rc-afinar">
                    <label class="rc-afinar-lbl" for={`instr-${e.id}`}>
                      Qué tenía que mostrar esta foto
                    </label>
                    <textarea
                      id={`instr-${e.id}`}
                      class="rc-afinar-txt"
                      rows="3"
                      maxlength={MAX_INSTRUCCION}
                      bind:value={a.texto}
                      oninput={(ev) => cambiar(e.id, { texto: ev.currentTarget.value })}
                      placeholder="Ej.: Resultado del test con los tres números legibles: descarga, subida y ping."
                    ></textarea>

                    <label class="rc-afinar-chk">
                      <input
                        type="checkbox"
                        checked={a.fotoEstaBien}
                        onchange={(ev) => cambiar(e.id, { fotoEstaBien: ev.currentTarget.checked })}
                      />
                      Esta foto está bien (sirve para leer el resultado)
                    </label>

                    <div class="rc-afinar-btns">
                      <button type="button" disabled={a.cargando} onclick={() => probar(e)}>
                        {a.cargando ? 'Mirando…' : 'Probar con esta foto'}
                      </button>
                      <button
                        type="button"
                        class="rc-afinar-guardar"
                        disabled={a.cargando || !a.texto.trim() || a.texto.trim() === a.guardado.trim()}
                        onclick={() => guardar(e)}
                      >
                        Guardar en la plantilla
                      </button>
                    </div>

                    {#if a.error}<p class="rc-afinar-error">{a.error}</p>{/if}

                    {#if a.resultado}
                      {@const v = veredicto(a.resultado.corresponde)}
                      <p class={`rc-afinar-ver rc-ver-${v.clase}`}>{v.icono} {v.texto}</p>
                      <p class="rc-afinar-que">{queSignifica(a.resultado.corresponde, a.fotoEstaBien)}</p>
                      {#if a.resultado.texto}
                        <p class="rc-afinar-dijo">{a.resultado.texto}</p>
                      {/if}
                      <!-- LO QUE DE VERDAD VIAJÓ. Producción envuelve el texto
                           con «Esta foto tenía que mostrar: <título>.», y ese
                           prefijo dispara las reglas del veredicto. Verlo es la
                           única forma de no tener que confiar. -->
                      <details class="rc-afinar-pie">
                        <summary>Lo que se le preguntó, completo</summary>
                        <code>{a.resultado.se_le_pidio}</code>
                      </details>
                    {/if}

                    {#if a.guardadoOk}<p class="rc-afinar-ok">{a.guardadoOk}</p>{/if}
                  </div>
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
  /*  EL COTEJO (12/11/2026): lo pedido y lo hecho tienen que leerse de un
      vistazo, uno debajo del otro. El borde de la izquierda los agrupa como
      una sola cosa: si se ven como dos parrafos sueltos, el ojo los lee por
      separado y vuelve el problema que esto resuelve.  */
  .rc-cotejo {
    display: flex; flex-direction: column; gap: 2px;
    border-left: 3px solid var(--snoc-outline-variant);
    padding-left: var(--snoc-sm); margin: 0;
  }
  .rc-pedido, .rc-previo { margin: 0; overflow-wrap: anywhere; }
  /*  El rotulo NO es negrita sobre el texto: el texto es lo que se compara y
      tiene que ganar. El rotulo solo dice de cual de los dos lados es.  */
  .rc-rotulo {
    display: inline-block; min-width: 10.5em;
    color: var(--snoc-on-surface-variant);
    font-size: 11px; text-transform: uppercase; letter-spacing: .04em;
  }
  .rc-asunto { font-weight: 600; }
  .rc-asunto + .rc-caso::before { content: ' · '; }
  .rc-sin-solucion { color: var(--snoc-error); font-style: normal; }
  @media (max-width: 640px) {
    /*  En el telefono el rotulo va arriba: con 10.5em al lado, al texto le
        quedan pocas palabras por linea y deja de leerse como una frase.  */
    .rc-rotulo { display: block; min-width: 0; }
  }
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
  /*  Mismo rojo que «No llegó»: las dos dicen que esa foto no sirve como
      evidencia, por motivos distintos. */
  .rc-no-es { color: #b91c1c; font-weight: 600; }
  .rc-punto-false { color: var(--snoc-error); font-weight: 600; }
  .rc-punto-null { color: #8a5300; }
  .rc-acciones { display: flex; flex-wrap: wrap; gap: 8px; }
  .rc-devolver { display: grid; gap: 6px; }
  .rc-devolver fieldset { margin: 0; padding: 4px 0; border: 0; display: grid; gap: 2px; }
  .rc-devolver legend { font-weight: 600; }
  .rc-porque { display: grid; gap: 2px; }
  .rc-porque textarea { font: inherit; width: 100%; box-sizing: border-box; }

  /*  AFINAR LA INSTRUCCIÓN (06/11/2026). Discreto a propósito: el botón se
      ofrece en cada foto pero no compite con el veredicto ni con las dos
      acciones que de verdad mueven la orden (aprobar y devolver). Quien entra
      acá viene a arreglar un texto, no a decidir sobre el trabajo.  */
  .rc-afinar-abrir {
    align-self: start;
    margin-top: 4px;
    padding: 2px 6px;
    font-size: 0.82em;
    color: var(--snoc-on-surface-variant, #666);
    background: none;
    border: 1px solid var(--snoc-outline, #d4d4d8);
    border-radius: 6px;
    cursor: pointer;
  }
  .rc-afinar-abrir:hover { background: var(--snoc-surface-container, #f4f4f5); }
  .rc-afinar {
    display: grid;
    gap: 6px;
    margin-top: 6px;
    padding: 8px;
    border-left: 3px solid var(--snoc-outline, #d4d4d8);
    background: var(--snoc-surface-container-low, #fafafa);
    border-radius: 0 6px 6px 0;
  }
  .rc-afinar-lbl { font-weight: 600; font-size: 0.85em; }
  .rc-afinar-txt {
    width: 100%;
    font: inherit;
    font-size: 0.9em;
    padding: 6px;
    border: 1px solid var(--snoc-outline, #d4d4d8);
    border-radius: 6px;
    resize: vertical;
  }
  .rc-afinar-chk {
    display: flex;
    gap: 6px;
    align-items: center;
    font-size: 0.85em;
    color: var(--snoc-on-surface-variant, #666);
  }
  .rc-afinar-btns { display: flex; flex-wrap: wrap; gap: 8px; }
  .rc-afinar-btns button {
    padding: 4px 10px;
    font-size: 0.85em;
    border: 1px solid var(--snoc-outline, #d4d4d8);
    border-radius: 6px;
    background: var(--snoc-surface, #fff);
    cursor: pointer;
  }
  .rc-afinar-btns button:disabled { opacity: 0.5; cursor: default; }
  .rc-afinar-guardar { font-weight: 600; }
  .rc-afinar-error { color: var(--snoc-error, #b91c1c); font-size: 0.85em; margin: 0; }
  .rc-afinar-ver { margin: 2px 0; font-weight: 600; font-size: 0.9em; }
  /*  LOS TRES, DISTINGUIBLES. «No se sabe» en ámbar y no en rojo: una duda no
      es un rechazo, y pintarla igual mandaría a reescribir un texto que está
      bien. Es el mismo error que un parser binario cometió el 06/11/2026.  */
  .rc-ver-ok { color: #15803d; }
  .rc-ver-no { color: var(--snoc-error, #b91c1c); }
  .rc-ver-duda { color: #8a5300; }
  .rc-afinar-que { margin: 0; font-size: 0.85em; }
  .rc-afinar-dijo {
    margin: 0;
    font-size: 0.85em;
    color: var(--snoc-on-surface-variant, #666);
    white-space: pre-wrap;
  }
  .rc-afinar-pie { font-size: 0.8em; color: var(--snoc-on-surface-variant, #666); }
  .rc-afinar-pie code { white-space: pre-wrap; word-break: break-word; }
  .rc-afinar-ok { margin: 0; font-size: 0.85em; color: #15803d; }
</style>
