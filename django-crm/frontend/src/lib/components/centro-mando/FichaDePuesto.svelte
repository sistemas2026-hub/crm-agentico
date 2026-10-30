<script>
  /**
   * LA FICHA DE UN PUESTO.
   *
   * Lo que se abre al pulsar un puesto de la sala. Muestra quién lo ocupa, qué
   * está haciendo, con qué, y el historial de lo que pasó — y, arriba de todo,
   * **si se puede confiar en lo que dice**.
   *
   * TRES DECISIONES QUE ESTÁN EN EL ORDEN DE LOS BLOQUES
   *
   * 1 · La calidad de la información va PRIMERO, no en un pie de página. Si el
   *     flujo está caído, lo que viene abajo es historia, no presente, y leerlo
   *     como presente es el error que esta pantalla existe para evitar.
   *
   * 2 · Un puesto vacío lo dice y no se disfraza. «Sin agente asignado» es un
   *     dato, no un hueco que haya que rellenar con algo.
   *
   * 3 · El historial real y el simulado NO se concatenan nunca. Llegan en dos
   *     arreglos separados desde `bitacora.js` y la ficha muestra uno o el otro,
   *     con su rótulo. Juntarlos «para verlo todo» es la mezcla que toda esta
   *     cadena está construida para impedir.
   *
   * NO IMPORTA `$app/*` A PROPÓSITO
   * Así se puede renderizar fuera de SvelteKit —en el banco de pruebas del
   * navegador y con `render()` de 'svelte/server'—, que en este repositorio es
   * la única forma de probar un componente: jsdom no arranca acá.
   */

  /**
   * @typedef {{ id: string, agente: string, tipo: string, etiqueta: string|null,
   *             procedencia: string, en: string|null, visto: number }} Anotacion
   */

  let {
    /** El puesto seleccionado, o `null` si no hay ninguno. */
    puesto = null,
    /** Lo que el adaptador decidió para su agente, o `null`. */
    estado = null,
    /** El veredicto de `frescura()`. */
    veredicto = null,
    /** @type {Anotacion[]} */
    historial = [],
    /** `true` cuando lo que se muestra viene de la demostración. */
    simulado = false,
    /** Diagnóstico del flujo: cursor, consultas, saltos. */
    diagnostico = null,
    alCerrar = () => {}
  } = $props();

  /** Las palabras de cada motivo. La clave la pone el código; la redacción,
   *  acá: un motivo es un dato y una frase es presentación. */
  const PALABRAS = {
    sin_lectura: ['Sin información', 'Todavía no llegó ninguna respuesta del motor.'],
    silencio: ['Sin información', 'El motor dejó de responder. Lo que se ve abajo es historia.'],
    pausado: ['Sin información', 'La pestaña estuvo oculta y el sondeo se detuvo. Reanudando.'],
    error: ['Sin información', 'La última lectura falló.'],
    retraso: ['Sin información', 'El flujo viene atrasado: hay eventos que todavía no llegaron.'],
    al_dia: ['Actualizado', 'El flujo de eventos está al día.'],
    sin_actividad_vigente: ['En reposo', 'Ningún evento vigente respalda una actividad.'],
    sin_representacion: ['Sin representar', 'Hay un hecho registrado que la escena no sabe dibujar.']
  };

  const TIPOS = {
    consulta: 'Consulta',
    accion: 'Acción',
    falla: 'Fallo',
    expediente: 'Derivación',
    escalada: 'Escalada a una persona'
  };

  let confiable = $derived(veredicto?.confiable === true);
  let cabecera = $derived(PALABRAS[veredicto?.motivo] ?? ['Sin información', 'No se pudo evaluar la frescura de los datos.']);

  /** Hace cuánto, en palabras. Sin librería: son cuatro casos. */
  function hace(ms) {
    if (ms == null) return '—';
    const s = Math.max(0, Math.round((Date.now() - ms) / 1000));
    if (s < 60) return `hace ${s} s`;
    const m = Math.round(s / 60);
    if (m < 60) return `hace ${m} min`;
    return `hace ${Math.round(m / 60)} h`;
  }

  /** La hora del hecho, en la zona de quien mira. */
  function hora(iso) {
    if (!iso) return null;
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return null;
    return d.toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }

  /** El identificador del hecho que respalda una línea. Se muestra recortado:
   *  entero no cabe, y sin nada no habría forma de rastrearlo. */
  function rastro(procedencia) {
    if (typeof procedencia !== 'string') return null;
    if (procedencia === 'simulado') return 'simulado';
    if (procedencia === 'ambiente') return 'ambiente';
    const uuid = procedencia.slice('evento:'.length);
    return uuid.slice(0, 8);
  }
</script>

{#if puesto}
  <aside class="ficha" aria-label="Ficha del puesto">
    <header>
      <div class="titulo">
        <h2>{puesto.nombre}</h2>
        <p class="rol">
          {#if puesto.agente}
            Agente IA · {puesto.area}
          {:else}
            Puesto sin agente asignado
          {/if}
        </p>
      </div>
      <button type="button" class="cerrar" onclick={alCerrar} aria-label="Cerrar la ficha">×</button>
    </header>

    {#if simulado}
      <!-- Primero y sin disimulo. Si alguien mira esta ficha durante una
           demostración tiene que saberlo antes de leer un solo dato. -->
      <p class="aviso-simulado">
        <strong>Demostración.</strong> Lo que se ve es un guion de prueba, no la
        operación. No entra en el historial real.
      </p>
    {/if}

    <section class="frescura" class:mal={!confiable}>
      <span class="punto" aria-hidden="true"></span>
      <div>
        <p class="estado">{cabecera[0]}</p>
        <p class="detalle">{veredicto?.detalle || cabecera[1]}</p>
      </div>
    </section>

    {#if puesto.agente}
      <section>
        <h3>Actividad</h3>
        {#if !confiable}
          <p class="vacio">
            No se puede afirmar qué está haciendo ahora. El último estado conocido
            no se muestra como actual a propósito.
          </p>
        {:else if estado?.rotulo}
          <p class="actividad">{estado.rotulo}</p>
          <p class="meta">
            {TIPOS[estado.animacion] ?? ''}
            {#if estado.hasta}
              · vigente hasta {hora(new Date(estado.hasta).toISOString())}
            {/if}
          </p>
        {:else}
          <p class="vacio">En reposo: ningún evento vigente respalda una actividad.</p>
        {/if}
      </section>

      <section>
        <h3>
          {#if simulado}Historial de la demostración{:else}Historial de eventos{/if}
          <span class="cuenta">{historial.length}</span>
        </h3>
        {#if historial.length === 0}
          <p class="vacio">
            Todavía no llegó ningún evento de este puesto por el flujo
            incremental.
          </p>
        {:else}
          <ol class="historial">
            {#each historial as a (a.procedencia + a.id)}
              <li>
                <span class="tipo tipo-{a.tipo}">{TIPOS[a.tipo] ?? a.tipo}</span>
                <span class="que">{a.etiqueta ?? '—'}</span>
                <span class="cuando">{hora(a.en) ?? hace(a.visto)}</span>
                <!-- El rastro es lo que hace auditable la animación: de la
                     figura que se movió al hecho que la causó. -->
                <code class="rastro" title={a.procedencia}>{rastro(a.procedencia)}</code>
              </li>
            {/each}
          </ol>
        {/if}
      </section>
    {:else}
      <section>
        <p class="vacio">
          Esta estación existe en la sala y no tiene agente. No hay actividad que
          mostrar, y no es un fallo del flujo.
        </p>
      </section>
    {/if}

    {#if diagnostico}
      <section class="diagnostico">
        <h3>Flujo de eventos</h3>
        <dl>
          <dt>Consultas</dt>
          <dd>{diagnostico.consultas ?? 0}</dd>
          <dt>Retraso declarado</dt>
          <dd>{diagnostico.retraso_s == null ? 'sin medir' : `${diagnostico.retraso_s.toFixed(2)} s`}</dd>
          <dt>Cursor</dt>
          <dd><code>{diagnostico.cursor ? String(diagnostico.cursor).slice(0, 18) + '…' : 'sin cursor'}</code></dd>
          {#if diagnostico.saltos > 0}
            <dt>Saltos</dt>
            <dd class="alarma">{diagnostico.saltos}</dd>
          {/if}
        </dl>
        {#if diagnostico.ultimoError}
          <p class="error">{diagnostico.ultimoError}</p>
        {/if}
      </section>
    {/if}
  </aside>
{/if}

<style>
  .ficha {
    display: flex;
    flex-direction: column;
    gap: 14px;
    width: 320px;
    max-height: 100%;
    overflow-y: auto;
    padding: 16px;
    background: #15142c;
    border-left: 1px solid rgba(255, 255, 255, 0.08);
    color: #e8e7f5;
    font-size: 13px;
    line-height: 1.45;
  }

  header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 8px;
  }

  h2 {
    margin: 0;
    font-size: 15px;
    font-weight: 600;
    letter-spacing: 0.01em;
  }

  .rol {
    margin: 2px 0 0;
    color: #9a98bd;
    font-size: 11.5px;
  }

  .cerrar {
    flex: none;
    width: 26px;
    height: 26px;
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 6px;
    background: transparent;
    color: #9a98bd;
    font-size: 16px;
    line-height: 1;
    cursor: pointer;
  }
  .cerrar:hover {
    color: #e8e7f5;
    border-color: rgba(255, 255, 255, 0.3);
  }

  .aviso-simulado {
    margin: 0;
    padding: 8px 10px;
    border-radius: 6px;
    background: rgba(224, 166, 83, 0.14);
    border: 1px solid rgba(224, 166, 83, 0.4);
    color: #e0a653;
    font-size: 11.5px;
  }

  .frescura {
    display: flex;
    gap: 10px;
    align-items: flex-start;
    padding: 10px;
    border-radius: 6px;
    background: rgba(123, 203, 138, 0.1);
    border: 1px solid rgba(123, 203, 138, 0.32);
  }
  .frescura.mal {
    background: rgba(107, 106, 133, 0.16);
    border-color: rgba(154, 152, 189, 0.45);
  }
  .punto {
    flex: none;
    width: 8px;
    height: 8px;
    margin-top: 5px;
    border-radius: 50%;
    background: #7bcb8a;
  }
  .frescura.mal .punto {
    background: #9a98bd;
  }
  .estado {
    margin: 0;
    font-weight: 600;
    font-size: 12.5px;
  }
  .detalle {
    margin: 2px 0 0;
    color: #9a98bd;
    font-size: 11.5px;
  }

  h3 {
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 0 0 6px;
    color: #9a98bd;
    font-size: 10.5px;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  .cuenta {
    padding: 1px 6px;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.08);
    font-size: 10px;
    letter-spacing: 0;
  }

  .actividad {
    margin: 0;
    font-family: ui-monospace, SFMono-Regular, monospace;
    font-size: 12.5px;
  }
  .meta,
  .vacio {
    margin: 3px 0 0;
    color: #9a98bd;
    font-size: 11.5px;
  }

  .historial {
    margin: 0;
    padding: 0;
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 1px;
  }
  .historial li {
    display: grid;
    grid-template-columns: auto 1fr auto;
    grid-template-areas: 'tipo que cuando' 'rastro rastro rastro';
    gap: 2px 8px;
    padding: 6px 0;
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  }
  .tipo {
    grid-area: tipo;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: #8b84f5;
  }
  .tipo-falla {
    color: #ff7b6b;
  }
  .tipo-expediente,
  .tipo-escalada {
    color: #e0a653;
  }
  .que {
    grid-area: que;
    font-family: ui-monospace, SFMono-Regular, monospace;
    font-size: 11.5px;
    overflow-wrap: anywhere;
  }
  .cuando {
    grid-area: cuando;
    color: #9a98bd;
    font-size: 10.5px;
    font-variant-numeric: tabular-nums;
  }
  .rastro {
    grid-area: rastro;
    color: #6b6a85;
    font-size: 10px;
  }

  .diagnostico dl {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 3px 10px;
    margin: 0;
    font-size: 11.5px;
  }
  .diagnostico dt {
    color: #9a98bd;
  }
  .diagnostico dd {
    margin: 0;
    text-align: right;
    font-variant-numeric: tabular-nums;
  }
  .diagnostico code {
    font-size: 10.5px;
    color: #9a98bd;
  }
  .alarma {
    color: #e0a653;
  }
  .error {
    margin: 6px 0 0;
    color: #ff7b6b;
    font-size: 11.5px;
  }
</style>
