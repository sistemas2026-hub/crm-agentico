<script>
  /**
   * LA OFICINA VIRTUAL — PROTOTIPO DEL NOC.
   *
   * Ruta aparte, `/centro-mando/v2`. El centro de mando que está en producción
   * no se toca: comparte los módulos de datos (`proyeccion`, `frescura`) y nada
   * más. Si esto se cae, aquello sigue.
   *
   * CÓMO SE COMPONE, DE FUERA HACIA DENTRO
   *
   *   flujo.js        pide eventos con cursor y MIDE si se puede confiar
   *   proyeccion.js   evento -> instrucción visual, con procedencia
   *   frescura.js     las cuatro señales -> un veredicto
   *   adaptador.ts    instrucción + veredicto -> animación
   *   montar.ts       la única puerta de la escena
   *
   * Esta pantalla no sabe qué es un sprite ni cómo se dibuja un suelo
   * isométrico, y la escena no sabe qué es un evento. Ese corte es el
   * entregable de verdad: cuando haya ocho departamentos, lo que se repite es
   * la escena, no esta cadena.
   *
   * EL BUCLE DE AQUÍ NO ES EL DE LA ESCENA
   * La escena tiene su propio reloj a la velocidad de la pantalla (respiración,
   * pantallas, cámara). Acá hay un reloj LENTO, de 150 ms, que hace tres cosas
   * que no necesitan 60 veces por segundo: avanzar el guion de demostración,
   * caducar las instrucciones vencidas y —esto es lo importante— recalcular la
   * frescura. Lo último tiene que pasar SIN respuestas del motor: si el silencio
   * solo se evaluara al recibir algo, un motor caído nunca dispararía el aviso.
   */

  import { onDestroy } from 'svelte';
  import { crearFlujo } from '$lib/centro-mando/flujo.js';
  import { crearBitacora } from '$lib/centro-mando/bitacora.js';
  import { crearDemostracion } from '$lib/centro-mando/demo.js';
  import { proyectar, vigentes } from '$lib/centro-mando/proyeccion.js';
  import { frescura } from '$lib/centro-mando/frescura.js';
  import { DEPARTAMENTOS, plantaDe, plantaDeLaEmpresa } from '$lib/centro-mando/departamentos.js';
  import FichaDePuesto from '$lib/components/centro-mando/FichaDePuesto.svelte';

  let { data } = $props();

  /**
   * El departamento que se está mirando.
   *
   * Cambiarlo DESMONTA y vuelve a montar la escena: la sala entera es otra
   * —otro mundo, otro mobiliario, otros puestos— y reconstruirla en caliente
   * sería mantener dos caminos para el mismo resultado.
   */
  //  `null` significa LA EMPRESA ENTERA: las seis salas a la vez. No es un
  //  departamento más — cambia qué se monta, no cuál se mira.
  let deptoId = $state(DEPARTAMENTOS[0].id);
  let depto = $derived(DEPARTAMENTOS.find((d) => d.id === deptoId) ?? DEPARTAMENTOS[0]);

  /**
   * El inventario se lee UNA vez, al montar. El compilador avisa de que esto
   * captura el valor inicial; ese es exactamente el valor que queremos: si el
   * inventario cambiara habría que remontar, que es lo que pasa al navegar.
   */
  const inventario = data.agentes;
  let planta = $derived(
    deptoId === null ? plantaDeLaEmpresa(inventario) : plantaDe(depto, inventario)
  );
  /** Los puestos de lo que se esté mirando: una sala o las seis. */
  let puestosVisibles = $derived(
    Array.isArray(planta) ? planta.flatMap((p) => p.puestos) : planta.puestos
  );
  let agentesConPuesto = $derived(puestosVisibles.map((p) => p.agente).filter(Boolean));

  /** @type {HTMLElement|null} */
  let lienzo = $state(null);
  /** @type {any} */
  let escena = null;
  let montando = $state(true);
  /** @type {string|null} */
  let errorDeEscena = $state(null);

  /** Instrucciones acumuladas, reales y simuladas por separado. */
  let instruccionesReales = $state([]);
  let instruccionesSimuladas = $state([]);
  const bitacora = crearBitacora();
  /**
   * Copias reactivas de los dos historiales.
   *
   * `bitacora` es un objeto corriente con dos captadores: leerlo dentro de un
   * `$derived` NO crea dependencia, así que la ficha se habría quedado con el
   * historial del instante en que se abrió y nadie lo habría notado —se ve
   * igual que «todavía no llegó nada»—. Es el salto que §6 de CLAUDE.md
   * describe: el dato llega bien y la capa de pantalla lo deja caer.
   *
   * Siguen siendo DOS, nunca uno: la separación entre lo real y lo simulado es
   * estructural y no sobrevive a juntarlos «para la vista».
   */
  let historialReal = $state([]);
  let historialSimulado = $state([]);

  let demostracion = $state(false);
  /** @type {any} */
  let guion = null;

  /** @type {any} */
  let veredicto = $state(frescura({ ultimaRespuestaOk: null }));
  /** @type {any[]} */
  let estados = $state([]);
  /** @type {any} */
  let diagnostico = $state(null);
  /** @type {any} */
  let metricas = $state(null);
  let sinRepresentacion = $state(0);

  /** @type {string|null} */
  let seleccionado = $state(null);

  //  El flujo pide TODOS los agentes de la empresa, no los de la sala que se
  //  está mirando: si filtrara por departamento, cambiar de sala tiraría el
  //  cursor y se perderían los eventos de los demás mientras tanto.
  const flujo = crearFlujo({
    agentes: (data.agentes || []).map((a) => a.nombre).filter(Boolean),
    areas: data.areas || [],
    // Un agente sin puesto no se proyecta, y sin agentes con puesto no se filtra
    // por agente: así el prototipo se puede mirar aunque el inventario venga
    // vacío, en vez de quedarse en una sala muda sin decir por qué.
    limite: 120
  });

  flujo.alLote((lote) => {
    instruccionesReales = [...instruccionesReales, ...lote.instrucciones];
    bitacora.anotar(lote.instrucciones);
    historialReal = bitacora.real;
  });

  /** El puesto que está seleccionado, con su definición. */
  let puestoSeleccionado = $derived(puestosVisibles.find((p) => p.id === seleccionado) ?? null);
  let estadoSeleccionado = $derived(
    puestoSeleccionado?.agente
      ? (estados.find((e) => e.agente === puestoSeleccionado.agente) ?? null)
      : null
  );
  let historialSeleccionado = $derived(
    puestoSeleccionado?.agente
      ? (demostracion ? historialSimulado : historialReal).filter(
          (a) => a.agente === puestoSeleccionado.agente
        )
      : []
  );

  /** La frase del indicador de frescura, arriba del lienzo. */
  const PALABRAS = {
    sin_lectura: 'Esperando la primera lectura',
    silencio: 'Sin información · el motor no responde',
    pausado: 'Sin información · la pestaña estuvo oculta',
    error: 'Sin información · la última lectura falló',
    retraso: 'Sin información · el flujo viene atrasado',
    al_dia: 'Actualizado'
  };
  let frase = $derived(PALABRAS[veredicto?.motivo] ?? 'Sin información');

  /* ── el reloj lento ─────────────────────────────────────────────────────── */
  let ultimoTic = 0;

  function tic() {
    const ahora = Date.now();
    const dt = ultimoTic ? Math.min(0.5, (ahora - ultimoTic) / 1000) : 0;
    ultimoTic = ahora;

    if (demostracion && guion) {
      const eventos = guion.avanzar(dt);
      if (eventos.length) {
        // EL LOTE ENTERO SE MARCA COMO SIMULADO. No evento por evento: si
        // dependiera de cada fila, bastaría con olvidarse de una para que un
        // movimiento de prueba entrara como actividad real.
        const p = proyectar(eventos, {
          agentes: agentesConPuesto,
          areas: data.areas || [],
          ahora,
          simulado: true
        });
        instruccionesSimuladas = [...instruccionesSimuladas, ...p.instrucciones];
        bitacora.anotar(p.instrucciones);
        historialSimulado = bitacora.simulado;
      }
    }

    // Caducar. Sin esto, un agente que consultó una vez se quedaría
    // «consultando» para siempre, que es justo la mentira que esta cadena evita.
    instruccionesReales = vigentes(instruccionesReales, ahora);
    instruccionesSimuladas = vigentes(instruccionesSimuladas, ahora);

    // La frescura se recalcula SIEMPRE, con o sin respuestas. Es el único modo
    // de que el silencio se note: un motor caído no manda un aviso de que está
    // caído.
    veredicto = frescura(flujo.senales());
    diagnostico = flujo.diagnostico();

    // Durante la demostración el veredicto del flujo real no puede apagar la
    // escena: lo que se está mirando no viene de ahí. Se mantiene al día a
    // propósito, y el cartel de «demostración» lo dice en todas las vistas.
    const veredictoDeEscena = demostracion
      ? { confiable: true, motivo: 'al_dia', detalle: null, silencio_s: 0 }
      : veredicto;

    //  Durante la demostración no se mezclan los turnos reales en curso: lo
    //  que se está mirando es un guion, y pintar encima una ejecución de
    //  verdad haría que una parte de la escena fuera real y otra inventada sin
    //  que se pueda distinguir cuál es cuál.
    const visual = visualizarAhora(
      demostracion ? instruccionesSimuladas : instruccionesReales,
      veredictoDeEscena,
      ahora,
      demostracion ? [] : flujo.activas()
    );
    estados = visual.estados;
    sinRepresentacion = visual.sinRepresentacion;
    escena?.aplicar(estados);
    metricas = escena?.metricas() ?? null;
  }

  /** @type {any} */
  let visualizar = null;
  function visualizarAhora(instrucciones, v, ahora, activas) {
    if (!visualizar) return { estados: [], sinRepresentacion: 0 };
    return visualizar(instrucciones, agentesConPuesto, v, ahora, activas);
  }

  /* ── montaje ────────────────────────────────────────────────────────────── */
  $effect(() => {
    if (!lienzo) return;
    //  Leer `planta` acá es lo que hace que cambiar de departamento vuelva a
    //  ejecutar este efecto: la escena se destruye y se monta de nuevo.
    const laPlanta = planta;
    let vivo = true;
    /** @type {any} */
    let reloj = null;

    (async () => {
      try {
        // Carga diferida: el motor gráfico son cientos de kilobytes y no tiene
        // nada que hacer en el servidor. Importarlo arriba lo metería en el
        // paquete de todas las pantallas.
        const [{ montarEscena }, adaptador] = await Promise.all([
          import('$lib/centro-mando/escena/montar'),
          import('$lib/centro-mando/escena/adaptador')
        ]);
        if (!vivo) return;
        visualizar = adaptador.visualizar;
        escena = await montarEscena({ contenedor: lienzo, planta: laPlanta });
        if (!vivo) {
          escena.destruir();
          escena = null;
          return;
        }
        escena.alSeleccionar((id) => {
          seleccionado = id;
        });
        montando = false;
        flujo.arrancar();
        reloj = setInterval(tic, 150);
        tic();
      } catch (/** @type {any} */ e) {
        errorDeEscena = e?.message || 'No se pudo iniciar la escena';
        montando = false;
      }
    })();

    return () => {
      vivo = false;
      if (reloj) clearInterval(reloj);
      escena?.destruir();
      escena = null;
    };
  });

  onDestroy(() => {
    flujo.detener();
  });

  function alternarDemostracion() {
    demostracion = !demostracion;
    if (demostracion) {
      guion = guion || crearDemostracion({ agente: agentesConPuesto[0] || 'sin_agente', areaDerivacion: (data.areas || [])[0] ?? null });
      guion.reiniciar();
    } else {
      // Lo simulado se olvida al apagar. Dejarlo ahí haría que la próxima
      // mirada a la ficha encontrara un historial de demostración sin el cartel
      // que lo explica.
      instruccionesSimuladas = [];
      bitacora.olvidarSimulado();
      historialSimulado = [];
    }
  }
</script>

<svelte:head><title>Oficina virtual · {deptoId === null ? 'La empresa' : depto.rotulo}</title></svelte:head>

<div class="pantalla">
  <header class="barra">
    <div class="donde">
      <h1>{deptoId === null ? 'La empresa' : depto.rotulo}</h1>
      <p>
        {deptoId === null
          ? `${DEPARTAMENTOS.length} departamentos`
          : depto.direccion} · prototipo de oficina virtual
      </p>
    </div>

    <!-- El selector de sala. Cambiarlo remonta la escena entera: es otra
         planta, no el mismo recinto con otros muebles. -->
    <nav class="salas" aria-label="Departamento">
      <button
        type="button"
        class:activa={deptoId === null}
        aria-pressed={deptoId === null}
        onclick={() => { deptoId = null; seleccionado = null; }}
      >La empresa</button>
      {#each DEPARTAMENTOS as d (d.id)}
        <button
          type="button"
          class:activa={d.id === deptoId}
          aria-pressed={d.id === deptoId}
          onclick={() => { deptoId = d.id; seleccionado = null; }}
        >{d.rotulo}</button>
      {/each}
    </nav>

    <!-- El indicador de frescura, siempre a la vista y no escondido en la
         ficha: es la diferencia entre «este agente no tiene trabajo» y «no
         tengo ni idea de lo que hace», y eso no puede depender de que alguien
         abra un panel. -->
    <div class="frescura" class:mal={!veredicto?.confiable} data-prueba="frescura">
      <span class="punto"></span>
      <span>{frase}</span>
      {#if veredicto?.silencio_s != null && !veredicto.confiable}
        <span class="desde">{veredicto.silencio_s} s</span>
      {/if}
    </div>

    <div class="mandos">
      {#if demostracion}
        <span class="sello">DEMOSTRACIÓN</span>
      {/if}
      <button type="button" onclick={alternarDemostracion}>
        {demostracion ? 'Detener demostración' : 'Demostración'}
      </button>
      <button type="button" onclick={() => escena?.encuadrar()}>Encuadrar</button>
      {#if metricas}
        <span class="metricas" data-prueba="metricas">
          {metricas.fps} fps · mín {metricas.fpsMinimo} · {metricas.objetos} obj · {metricas.motor}
        </span>
      {/if}
    </div>
  </header>

  <div class="cuerpo">
    <div class="escenario" bind:this={lienzo} data-prueba="escenario">
      {#if montando}
        <p class="cargando">Montando la oficina…</p>
      {/if}
      {#if errorDeEscena}
        <p class="roto">
          No se pudo iniciar la escena: {errorDeEscena}
          <small>El resto del centro de mando no depende de esta pantalla.</small>
        </p>
      {/if}
    </div>

    {#if puestoSeleccionado}
      <FichaDePuesto
        puesto={puestoSeleccionado}
        estado={estadoSeleccionado}
        veredicto={demostracion ? { confiable: true, motivo: 'al_dia', detalle: 'Guion de demostración en curso.' } : veredicto}
        historial={historialSeleccionado}
        simulado={demostracion}
        {diagnostico}
        alCerrar={() => {
          seleccionado = null;
          escena?.seleccionar(null);
        }}
      />
    {/if}
  </div>

  <footer class="pie">
    {#if data.error}
      <span class="alarma">Inventario de agentes: {data.error}</span>
    {:else if agentesConPuesto.length === 0}
      <span class="alarma">
        El inventario no trae ningún agente del área «{depto.id}»: los puestos se
        dibujan vacíos a propósito.
      </span>
    {:else}
      <span>
        {agentesConPuesto.length} de {puestosVisibles.length} puestos ocupados:
        <code>{agentesConPuesto.join(', ')}</code>
      </span>
    {/if}
    {#if sinRepresentacion > 0}
      <span class="alarma">
        {sinRepresentacion} hecho(s) registrado(s) que la escena no sabe dibujar.
      </span>
    {/if}
    <span class="nota">
      Arrastrar mueve la cámara · la rueda hace zoom · pulsar un puesto abre su ficha
    </span>
  </footer>
</div>

<style>
  .pantalla {
    display: flex;
    flex-direction: column;
    height: calc(100vh - 56px);
    min-height: 520px;
    background: #0b0a1c;
    color: #e8e7f5;
  }

  .barra {
    display: flex;
    align-items: center;
    gap: 18px;
    padding: 10px 16px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    flex-wrap: wrap;
  }
  .donde h1 {
    margin: 0;
    font-size: 15px;
    font-weight: 600;
  }
  .donde p {
    margin: 1px 0 0;
    color: #9a98bd;
    font-size: 11.5px;
  }

  .frescura {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-left: auto;
    padding: 5px 11px;
    border-radius: 999px;
    background: rgba(123, 203, 138, 0.12);
    border: 1px solid rgba(123, 203, 138, 0.35);
    font-size: 11.5px;
  }
  .frescura.mal {
    background: rgba(154, 152, 189, 0.14);
    border-color: rgba(154, 152, 189, 0.45);
  }
  .punto {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: #7bcb8a;
  }
  .frescura.mal .punto {
    background: #9a98bd;
  }
  .desde {
    color: #9a98bd;
    font-variant-numeric: tabular-nums;
  }

  .salas {
    display: flex;
    gap: 6px;
  }
  .salas button {
    padding: 5px 11px;
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 6px;
    background: transparent;
    color: #9a98bd;
    font-size: 11.5px;
    cursor: pointer;
  }
  .salas button.activa {
    border-color: #8b84f5;
    color: #e8e7f5;
    background: rgba(139, 132, 245, 0.12);
  }

  .mandos {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 11.5px;
  }
  .mandos button {
    padding: 5px 11px;
    border: 1px solid rgba(255, 255, 255, 0.16);
    border-radius: 6px;
    background: transparent;
    color: #e8e7f5;
    font-size: 11.5px;
    cursor: pointer;
  }
  .mandos button:hover {
    border-color: rgba(255, 255, 255, 0.4);
  }
  .sello {
    padding: 3px 8px;
    border-radius: 4px;
    background: rgba(224, 166, 83, 0.18);
    border: 1px solid rgba(224, 166, 83, 0.5);
    color: #e0a653;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.08em;
  }
  .metricas {
    color: #6b6a85;
    font-variant-numeric: tabular-nums;
  }

  .cuerpo {
    display: flex;
    flex: 1;
    min-height: 0;
  }
  .escenario {
    position: relative;
    flex: 1;
    min-width: 0;
    overflow: hidden;
  }
  .cargando,
  .roto {
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    gap: 6px;
    align-items: center;
    justify-content: center;
    margin: 0;
    color: #9a98bd;
    font-size: 12.5px;
    text-align: center;
  }
  .roto {
    color: #ff7b6b;
  }
  .roto small {
    color: #9a98bd;
  }

  .pie {
    display: flex;
    gap: 16px;
    align-items: center;
    padding: 7px 16px;
    border-top: 1px solid rgba(255, 255, 255, 0.08);
    color: #9a98bd;
    font-size: 11px;
    flex-wrap: wrap;
  }
  .pie code {
    color: #e8e7f5;
  }
  .alarma {
    color: #e0a653;
  }
  .nota {
    margin-left: auto;
    color: #6b6a85;
  }
</style>
