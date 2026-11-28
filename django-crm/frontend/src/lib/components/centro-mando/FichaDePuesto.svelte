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
  import { enlacesDelPuesto } from '$lib/centro-mando/enlaces.js';

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
    /** Roles del área que existen y no ocupan un puesto. */
    capacidades = [],
    /**
     * La sala a la que pertenece el puesto, tal como la declara la
     * organización de la empresa: su rótulo, su piso, si es un departamento o
     * un espacio, y qué plantilla pidió.
     *
     * Viaja entera y no sólo el rótulo porque la ficha tiene que poder decir
     * DÓNDE está el puesto —un edificio tiene pisos— y porque las
     * incoherencias de la configuración se ven desde acá: una plantilla que el
     * catálogo no tiene, un puesto declarado que la plantilla no trae.
     */
    sala = null,
    /**
     * QUE PUEDE HACER HOY ESTE AGENTE. No es la lista blanca de su rol.
     *
     * El motor la cruza con el interruptor de autonomía y el techo vigentes
     * —los dos leídos de la base, sin caché— y manda `disponible` con su
     * motivo. La lista blanca cruda diría que este agente puede reiniciar una
     * ONU con la empresa detenida; esta no.
     *
     * `null` significa «no se pudo leer», que NO es lo mismo que una lista
     * vacía: una lista vacía dice «no puede hacer nada» y eso sería una
     * afirmación. Los dos casos se muestran distinto.
     *
     * @type {{nombre: string, descripcion: string, clase: string,
     *         nivel_requerido: number, requiere_aprobacion: boolean,
     *         disponible: boolean, motivo: string|null}[]|null}
     */
    acciones = null,
    /** Techo e interruptor de la empresa, para explicar un bloqueo. */
    autonomia = null,
    /** El rol de quien mira (del servidor): decide qué enlaces se ofrecen. */
    rol = null,
    alCerrar = () => {}
  } = $props();

  /** A dónde se va desde este puesto (12/11/2026): configurarlo, lo que
   *  atiende, y el tablero si es el Supervisor. Ver lib/centro-mando/enlaces.js. */
  let enlaces = $derived(enlacesDelPuesto(puesto, rol));

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
    sin_representacion: ['Sin representar', 'Hay un hecho registrado que la escena no sabe dibujar.'],
    ejecucion_sin_noticias: ['Sin información', 'Hay un turno abierto desde hace más de lo que un turno puede durar: no se sabe si sigue o si el proceso murió.']
  };

  const TIPOS = {
    consulta: 'Consulta',
    accion: 'Acción',
    falla: 'Fallo',
    expediente: 'Derivación',
    escalada: 'Escalada a una persona'
  };

  /**
   * QUÉ es quien ocupa este puesto. Cuatro cosas distintas, y confundirlas es
   * lo que hacía que la oficina dibujara nueve empleados donde hay seis.
   *
   *   agente        un agente IA ejecutable: tiene instancia en el motor
   *   persona       alguien del equipo, de carne y hueso
   *   ausente       la configuración lo declara y el inventario no lo trae
   *   libre         el puesto existe y nadie lo ocupa
   *
   * `persona` va ANTES que `ausente` y que `libre` por lo mismo que existe:
   * hasta el 31/10/2026 un escritorio con alguien trabajando se veía idéntico
   * a uno vacío, así que la oficina decía que media empresa no existe.
   *
   * Las CAPACIDADES no aparecen acá y es a propósito: no ocupan un puesto, así
   * que no pueden ser el tipo de miembro de uno. Van en su propio bloque.
   */
  let tipo = $derived(
    puesto?.agente ? 'agente'
      : puesto?.persona ? 'persona'
      : puesto?.motivo && puesto.motivo !== 'sin agente asignado' ? 'ausente'
      : 'libre'
  );
  const MIEMBRO = {
    agente: 'Agente IA ejecutable',
    persona: 'Persona del equipo',
    ausente: 'Agente declarado, ausente del inventario',
    libre: 'Puesto libre'
  };

  /**
   * Lo que la configuración de la empresa declaró y la pantalla no pudo
   * cumplir.
   *
   * No es un error del flujo ni del motor: es una incoherencia entre lo que la
   * organización dice y lo que el producto sabe dibujar. Se muestra acá porque
   * es el único sitio donde alguien que mira ese puesto puede entenderla.
   */
  let advertencias = $derived.by(() => {
    const avisos = [];
    if (sala?.plantillaFaltante) {
      avisos.push(`La organización pide la plantilla «${sala.plantillaFaltante}» y el ` +
                  'catálogo no la tiene: esta sala se dibuja con una genérica.');
    }
    for (const p of sala?.puestosDesconocidos ?? []) {
      avisos.push(`La organización declara el puesto «${p}» y la plantilla de esta ` +
                  'sala no lo tiene: lo que se declaró ahí no se dibuja.');
    }
    if (tipo === 'ausente' && puesto?.motivo) avisos.push(puesto.motivo);
    return avisos;
  });

  /**
   * Las acciones partidas en MIRAR y HACER.
   *
   * Se separan porque no son lo mismo y la diferencia es la que importa:
   * `consultar_cliente` lee, `reiniciar_ont` corta el servicio de una casa. En
   * una lista plana se ven iguales, que es justo lo que hacía falta separar.
   *
   * Y las consultas NO las gobierna ni el interruptor ni el techo —una
   * consulta no es una acción autónoma, lo dice el propio interruptor—, así
   * que mezclarlas haría que un bloqueo pareciera alcanzar a todo.
   */
  let consultas = $derived((acciones ?? []).filter((a) => a.clase === 'consulta'));
  let conEfecto = $derived((acciones ?? []).filter((a) => a.clase !== 'consulta'));
  let bloqueadas = $derived(conEfecto.filter((a) => !a.disponible));

  let confiable = $derived(veredicto?.confiable === true);
  /** Hay un turno abierto AHORA, no un eco de uno que terminó. */
  let enCurso = $derived(
    typeof estado?.procedencia === 'string' && estado.procedencia.startsWith('ejecucion:')
  );
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
          {MIEMBRO[tipo]}
          {#if sala}
            · {sala.rotulo}{#if sala.tipo === 'espacio'} (espacio){/if}
          {:else if puesto.agente}
            · {puesto.area}
          {/if}
        </p>
      </div>
      <button type="button" class="cerrar" onclick={alCerrar} aria-label="Cerrar la ficha">×</button>
    </header>

    {#if enlaces.length}
      <nav class="enlaces" aria-label="Ir a" data-prueba="enlaces-del-puesto">
        {#each enlaces as e (e.href)}
          <a href={e.href}>{e.texto} →</a>
        {/each}
      </nav>
    {/if}

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
        {:else if enCurso}
          <!-- Lo que `tool_calls` nunca pudo decir. Esa tabla se escribe
               cuando la llamada termina, así que hasta ahora la ficha solo
               podía contar cosas que ya habían pasado. -->
          <p class="actividad en-curso">Un turno en curso</p>
          <p class="meta">
            Empezó hace poco y todavía no terminó. No se puede decir con qué
            está trabajando hasta que cierre.
          </p>
          {#if estado?.acontecimiento}
            <!-- LA SEGUNDA DIMENSIÓN. Un fallo de una llamada no significa que
                 el turno haya terminado: el agente puede estar recuperándose o
                 llamando a otra cosa. Las dos señales conviven; una no
                 reemplaza a la otra. -->
            <p class="suceso">
              <span class="tipo tipo-{estado.acontecimiento.tipo}">
                {TIPOS[estado.acontecimiento.tipo] ?? estado.acontecimiento.tipo}
              </span>
              <span class="que">{estado.acontecimiento.etiqueta ?? '—'}</span>
            </p>
            <p class="meta">Lo último que pasó, mientras el turno sigue abierto.</p>
          {/if}
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

      <section class="identidad">
        <h3>Identificación</h3>
        <!-- LO QUE PERMITE VERIFICAR, no lo que queda bonito. Cada línea es un
             identificador con el que alguien puede ir a buscar: el nombre
             técnico del rol en la configuración, el identificador del puesto
             tal como lo conoce la escena, y dónde está en el edificio.

             El nombre que se lee arriba es el CARGO, que una empresa puede
             cambiar cuando quiera; esto es lo que no cambia. -->
        <dl>
          <dt>Agente</dt>
          <dd><code>{puesto.agente}</code></dd>
          <dt>Puesto</dt>
          <dd><code>{puesto.id}</code></dd>
          {#if sala}
            <dt>Departamento</dt>
            <dd>{sala.rotulo}{#if sala.direccion} · {sala.direccion}{/if}</dd>
            <dt>Piso</dt>
            <dd>{sala.piso}</dd>
          {/if}
          {#if puesto.orientado_a}
            <dt>Atiende a</dt>
            <dd>{puesto.orientado_a}</dd>
          {/if}
        </dl>
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
        {#if puesto.motivo && puesto.motivo !== 'sin agente asignado'}
          <!-- UN AGENTE DECLARADO QUE EL INVENTARIO NO TRAE no es lo mismo que
               un puesto libre, y decir «no es un fallo del flujo» en ese caso
               sería afirmar que todo está bien cuando algo falta. -->
          <p class="vacio alarma">{puesto.motivo}</p>
          <p class="vacio">
            El puesto se dibuja vacío a propósito: dibujarlo ocupado sería
            inventar un empleado.
          </p>
        {:else}
          {#if tipo === 'persona'}
            <!-- Una persona NO es un puesto vacío, y decirle lo mismo sería
                 borrarla. Lo que es cierto es que el motor no la representa:
                 no hay flujo de eventos de una persona, y dibujar actividad
                 por ella sería inventarla. -->
            <p class="vacio">
              Lo que hace una persona del equipo no lo registra el motor. No es
              que no esté pasando nada: es que esta pantalla no lo ve.
            </p>
          {:else}
            <p class="vacio">
              Esta estación existe en la sala y no tiene agente. No hay actividad
              que mostrar, y no es un fallo del flujo.
            </p>
          {/if}
        {/if}
      </section>
    {/if}

    {#if tipo === 'persona'}
      <section class="acciones">
        <h3>Qué puede hacer</h3>
        <!-- Una persona no tiene lista blanca, ni techo, ni interruptor: lo
             que hace no pasa por el motor. Decir «sin acciones» sería
             describirla con el vocabulario de un agente. -->
        <p class="vacio" data-prueba="persona-sin-acciones">
          Lo que hace una persona del equipo no pasa por el motor: no tiene
          herramientas habilitadas ni techo de autonomía.
        </p>
      </section>
    {/if}

    {#if tipo === 'agente'}
      <section class="acciones">
        <h3>Qué puede hacer</h3>
        {#if acciones === null}
          <!-- No se pudo leer. Una lista vacía diría «no puede hacer nada», que
               es una afirmación distinta y podría ser falsa. -->
          <p class="vacio" data-prueba="acciones-sin-leer">
            No se pudo leer qué acciones tiene habilitadas este agente. No es
            que no tenga: es que no se pudo consultar.
          </p>
        {:else}
          <p class="nota-acciones">
            Lo que la empresa le habilitó, cruzado con su autonomía de hoy.
            {#if autonomia}
              {#if autonomia.detenido}
                <strong>La autonomía de la empresa está detenida.</strong>
              {:else if autonomia.techo_nombre}
                Techo: <strong>{autonomia.techo_nombre}</strong>.
              {/if}
            {/if}
          </p>

          {#if conEfecto.length > 0}
            <ul class="lista-acciones" data-prueba="acciones-con-efecto">
              {#each conEfecto as a (a.nombre)}
                <li class:bloqueada={!a.disponible}>
                  <code>{a.nombre}</code>
                  <span class="etiqueta {a.clase}">
                    {a.clase === 'irreversible' ? 'no se puede deshacer' : 'con efecto'}
                  </span>
                  {#if a.disponible}
                    {#if a.requiere_aprobacion}
                      <!-- Por separado y no dentro de «disponible»: una
                           irreversible habilitada sigue necesitando que una
                           persona la apruebe, y esconderlo en un booleano la
                           haría parecer automática. -->
                      <span class="aprobacion">solo con aprobación de una persona</span>
                    {/if}
                  {:else}
                    <span class="motivo">{a.motivo}</span>
                  {/if}
                </li>
              {/each}
            </ul>
          {:else}
            <p class="vacio">
              Ninguna acción con efecto: este agente solo consulta.
            </p>
          {/if}

          {#if consultas.length > 0}
            <details>
              <summary>{consultas.length} consulta(s)</summary>
              <ul class="lista-acciones consultas" data-prueba="acciones-consulta">
                {#each consultas as a (a.nombre)}
                  <li><code>{a.nombre}</code></li>
                {/each}
              </ul>
              <p class="vacio">
                Una consulta no es una acción autónoma: ni el interruptor ni el
                techo la gobiernan.
              </p>
            </details>
          {/if}
        {/if}
      </section>
    {/if}

    {#if capacidades.length > 0}
      <section>
        <h3>Capacidades del área <span class="cuenta">{capacidades.length}</span></h3>
        <!-- No tienen escritorio y NO es un olvido: son capacidades que se le
             asignan a una persona real del CRM, no empleados virtuales.
             Dibujarles un puesto sería inventar gente. -->
        <ul class="capacidades">
          {#each capacidades as c (c.nombre)}
            <li><code>{c.nombre}</code> {c.cargo ?? ''}</li>
          {/each}
        </ul>
        <p class="vacio">
          Se le asignan a una persona del CRM; no ocupan un puesto propio.
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
          {#if diagnostico.enCurso != null}
            <dt>Turnos en curso</dt>
            <dd>{diagnostico.enCurso}</dd>
          {/if}
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
  {#if advertencias.length}
      <section class="advertencias">
        <h3>Advertencias</h3>
        <!-- No son fallos del flujo ni del motor: son incoherencias entre lo
             que la organización declara y lo que el producto sabe dibujar.
             Callarlas dejaría un hueco que nadie puede explicar. -->
        <ul>
          {#each advertencias as a (a)}
            <li>{a}</li>
          {/each}
        </ul>
      </section>
    {/if}
  </aside>
{/if}

<style>
  .acciones .nota-acciones { font-size: 0.74rem; color: #94a3b8; margin: 0 0 0.5rem; }
  .lista-acciones { list-style: none; padding: 0; margin: 0; display: grid; gap: 0.3rem; }
  .lista-acciones li { font-size: 0.74rem; display: flex; gap: 0.4rem; align-items: baseline;
                       flex-wrap: wrap; }
  .lista-acciones li.bloqueada code { opacity: 0.55; text-decoration: line-through; }
  .lista-acciones.consultas { margin-top: 0.4rem; opacity: 0.85; }
  .etiqueta { font-size: 0.64rem; padding: 0.05rem 0.35rem; border-radius: 999px;
              border: 1px solid currentColor; }
  .etiqueta.efecto { color: #fbbf24; }
  .etiqueta.irreversible { color: #fb7185; }
  .aprobacion { font-size: 0.68rem; color: #fbbf24; }
  .motivo { font-size: 0.68rem; color: #94a3b8; }
  .acciones details summary { font-size: 0.72rem; color: #94a3b8; cursor: pointer; }
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

  .en-curso {
    color: #8b84f5;
  }
  .suceso {
    display: flex;
    align-items: baseline;
    gap: 8px;
    margin: 8px 0 0;
    padding-top: 8px;
    border-top: 1px solid rgba(255, 255, 255, 0.07);
  }
  .actividad {
    margin: 0;
    font-family: ui-monospace, SFMono-Regular, monospace;
    font-size: 12.5px;
  }
  .meta,
  .identidad dl {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 0.25rem 0.75rem;
    margin: 0;
    font-size: 0.82rem;
  }
  .identidad dt {
    color: #9a98c4;
  }
  .identidad dd {
    margin: 0;
    overflow-wrap: anywhere;
  }
  .identidad code {
    font-size: 0.78rem;
  }
  .advertencias ul {
    margin: 0;
    padding-left: 1.1rem;
    font-size: 0.82rem;
    color: #ffd79a;
  }
  .advertencias li + li {
    margin-top: 0.35rem;
  }

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

  .capacidades {
    margin: 0;
    padding: 0;
    list-style: none;
    font-size: 11.5px;
  }
  .capacidades li {
    padding: 2px 0;
  }
  .capacidades code {
    color: #8b84f5;
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
  .vacio.alarma {
    color: #e0a653;
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
  .enlaces {
    display: flex;
    flex-wrap: wrap;
    gap: 6px 14px;
    margin: 0 0 12px;
  }
  .enlaces a {
    font-size: 12.5px;
    font-weight: 600;
    color: var(--v2-ember-text, #9a3412);
    text-decoration: none;
  }
  .enlaces a:hover {
    text-decoration: underline;
    text-underline-offset: 3px;
  }
</style>
