<script>
  /**
   * El centro de mando entero. Recibe un panorama y lo pinta; no sabe de
   * donde vino -- eso es cosa del AgentEventService -- ni calcula nada que el
   * motor no haya contado.
   *
   * COMO SE LEE ESTE TABLERO
   * Un nodo central (el orquestador) y un anillo de agentes. Cada via dice
   * tres cosas a la vez: el GROSOR es cuanta carga pasa por ahi, el COLOR es
   * el estado del agente, y PUNTEADA significa que ese agente no tiene
   * trafico ahora. Nada de eso esta escrito a mano: sale de las cifras del
   * motor.
   *
   * DONDE VA CADA NODO
   * Lo decide lib/centro-mando/disposicion.js, y cada pieza de ese calculo
   * viene de un fallo medido el 24/09/2026, no de una preferencia:
   *  - el radio sale del espacio que HAY, no de un porcentaje del lienzo;
   *  - los angulos se reparten por longitud de arco, no en partes iguales:
   *    en una elipse achatada, partes iguales agolpaba a los vecinos
   *    diagonales y cuatro pares se solapaban;
   *  - lo que se coloca sobre el anillo es el DISCO, no la caja entera: el
   *    nombre y la tarea cuelgan a un lado y corren su centro;
   *  - que quepa el anillo no es que quepan las piezas. Con ocho agentes este
   *    lienzo va sobrado y con once los vecinos se montan, asi que se
   *    comprueban los solapes antes de pintar.
   * Las piezas se MIDEN despues de pintarlas: cuanto ocupa un nodo depende de
   * los nombres que cada empresa le ponga a sus agentes. Si no caben, el nodo
   * se encoge y suelta la linea de tarea antes de rendirse; solo si tampoco
   * asi, el mapa cede a una rejilla. Se probo al reves -- rejilla directa -- y
   * en produccion, con 514 px de alto, el tablero perdia el mapa teniendo
   * sitio de sobra a los lados.
   */
  import { untrack } from 'svelte';
  import AgentStation from './AgentStation.svelte';
  import AgentDetail from './AgentDetail.svelte';
  import MetricsPanel from './MetricsPanel.svelte';
  import PlantaOficina from './PlantaOficina.svelte';
  import EventTimeline from './EventTimeline.svelte';
  import ExternalToolNode from './ExternalToolNode.svelte';
  import OrchestratorNode from './OrchestratorNode.svelte';
  import { ordenar, colorDe } from '$lib/centro-mando/estados.js';
  import {
    angulosPorArco,
    radiosDelAnillo,
    dentroDelLienzo,
    seSolapanEnElAnillo
  } from '$lib/centro-mando/disposicion.js';
  import { cargaMaxima } from '$lib/centro-mando/telemetria.js';

  /** @type {{ panorama: any, sello?: string|null }} */
  let { panorama, sello = null } = $props();

  let seleccionado = $state(/** @type {any} */ (null));
  /** Cual de las dos vistas se muestra. El anillo manda por omisión: es el
      que esta medido en produccion. */
  let vista = $state(/** @type {'anillo'|'planta'} */ ('anillo'));

  const totales = $derived(panorama?.totales || {});
  const servicios = $derived(panorama?.servicios || []);
  const eventos = $derived(panorama?.eventos || []);
  const agentes = $derived(ordenar(panorama?.agentes || []));
  const referencia = $derived(cargaMaxima(panorama?.agentes || []));

  /** El radio del nodo central, en pixeles: la via nace en su borde. */
  const R_NUCLEO = 62;

  let lienzo = $state(/** @type {HTMLElement|null} */ (null));
  let caja = $state({ ancho: 0, alto: 0 });
  let puestos = $state(/** @type {{x:number,y:number,haciaArriba:boolean}[]} */ ([]));
  let vias = $state(/** @type {any[]} */ ([]));
  /* Si el anillo cabe no lo decide un umbral inventado: lo dice la geometria
     con las piezas ya medidas. Arranca en true para que la primera pasada
     pinte los nodos y haya algo que medir. */
  let cabeElAnillo = $state(true);
  let compacto = $state(false);
  /* Lo ultimo que se coloco. Variable normal, no $state: es una guarda contra
     recolocar dos veces por lo mismo -- recolocar reescribe los nodos, eso
     vuelve a disparar al observador, y sin esta comparacion el ciclo no para. */
  let ultimo = { ancho: 0, alto: 0, n: 0 };

  const hayMapa = $derived(cabeElAnillo && agentes.length > 0);

  const hora = (/** @type {string|null} */ iso) =>
    iso
      ? new Date(iso).toLocaleTimeString('es-CO', {
          hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: 'America/Bogota'
        })
      : '—';

  const ms = (/** @type {number|null} */ v) =>
    v == null ? '—' : v >= 1000 ? `${(v / 1000).toFixed(1)} s` : `${v} ms`;

  // El agente abierto se refresca solo cuando llega un panorama nuevo: si no,
  // la ficha se queda con las cifras del momento en que se abrio.
  //
  // La dependencia es el panorama, y SOLO el panorama: este efecto escribe
  // `seleccionado`, asi que leerlo fuera de untrack lo vuelve dependiente de su
  // propia escritura. Eso reventaba con effect_update_depth_exceeded al abrir
  // la ficha, y a partir de ahi Svelte deja de re-ejecutar efectos -- el
  // tablero se quedaba sin recolocar aunque cambiara el tamano de la ventana.
  $effect(() => {
    const lista = panorama?.agentes || [];
    untrack(() => {
      if (!seleccionado) return;
      const fresco = lista.find((a) => a.nombre === seleccionado.nombre);
      if (fresco && fresco !== seleccionado) seleccionado = fresco;
    });
  });

  /**
   * El alto de la sala: lo que queda de ventana desde donde empieza. Medido,
   * no una constante restada a 100vh -- el encabezado de la pagina cambia de
   * alto con el ancho, y un numero fijo deja franja blanca en unas ventanas y
   * scroll en otras.
   */
  function estirar(/** @type {HTMLElement} */ nodo) {
    const ajustar = () => {
      const arriba = nodo.getBoundingClientRect().top + window.scrollY;
      nodo.style.height = `${Math.max(560, window.innerHeight - arriba - 14)}px`;
    };
    ajustar();
    window.addEventListener('resize', ajustar);
    return { destroy: () => window.removeEventListener('resize', ajustar) };
  }

  /**
   * Mide el lienzo y recoloca cuando cambia de tamano.
   *
   * Dos cosas que parecen de mas y no lo son (medidas el 24/09/2026):
   *  - La medida se aplaza con setTimeout, para no recolocar dentro del propio
   *    ciclo de entrega del ResizeObserver: lo que se recoloca vive DENTRO del
   *    elemento observado. Con requestAnimationFrame no sirve -- rAF no corre
   *    en una pestana que no pinta (un navegador sin cabeza, una pestana de
   *    fondo) y ahi la medida no llegaba nunca: el observer disparaba, el
   *    frame no venia, y un nodo acabo 35 px fuera del lienzo.
   *  - Se observa tambien al padre, cuyo tamano no depende de lo que pase
   *    dentro del mapa, y ademas se escucha el resize de la ventana: tres
   *    fuentes para el dato del que depende todo el trazado.
   */
  function observar(/** @type {HTMLElement} */ nodo) {
    lienzo = nodo;
    let pendiente = false;
    const medir = () => {
      pendiente = false;
      recolocar();
      // Segunda pasada, una sola: colocar los nodos cambia el alto de alguno
      // (el texto envuelve distinto al moverse), y la primera pasada trabajo
      // con el alto de antes. Sin ella, tras redimensionar quedaba un nodo
      // pegado al borde y otro con el disco 5 px dentro del nucleo -- solo
      // hasta el siguiente cambio de tamano, que es lo que hacia dificil de
      // ver el problema.
      setTimeout(() => recolocar(true), 50);
    };
    const programar = () => {
      if (pendiente) return;
      pendiente = true;
      setTimeout(medir, 0);
    };
    medir();
    recolocar();
    const obs = new ResizeObserver(programar);
    obs.observe(nodo);
    if (nodo.parentElement) obs.observe(nodo.parentElement);
    window.addEventListener('resize', programar);
    // Un repaso periodico, porque el ResizeObserver pierde avisos: medido con
    // un observador propio el 24/09/2026, de cuatro cambios de tamano entrego
    // dos, y el tablero se quedaba colocado para el ancho anterior. Cuesta dos
    // lecturas de clientWidth cada medio segundo, y `recolocar` sale en la
    // primera linea si nada cambio.
    const repaso = setInterval(programar, 500);
    return {
      destroy: () => {
        obs.disconnect();
        clearInterval(repaso);
        window.removeEventListener('resize', programar);
      }
    };
  }

  /**
   * Coloca el anillo y traza las vias.
   *
   * Es una funcion que se LLAMA, no un $effect: el calculo lee el tamano del
   * lienzo y escribe la colocacion, y ese ida y vuelta por el sistema reactivo
   * no volvia a correr de forma fiable -- con la medida ya nueva, los nodos
   * seguian colocados para el tamano anterior.
   *
   * Necesita el DOM ya pintado porque mide el alto real de cada nodo: cuanto
   * ocupa depende de los nombres que cada empresa le ponga a sus agentes, y
   * estimarlo es justo lo que descuadraba el mapa anterior.
   */
  function recolocar(forzar = false) {
    const n = agentes.length;
    if (!lienzo) return;
    // Se mide aqui y no se confia en `caja`: el tamano es un dato del DOM, y
    // hacerlo pasar por el estado reactivo antes de usarlo fue lo que dejaba
    // el trazado calculado para un tamano que ya no era el de la pantalla.
    const ancho = lienzo.clientWidth;
    const alto = lienzo.clientHeight;
    if (!forzar && ancho === ultimo.ancho && alto === ultimo.alto && n === ultimo.n) return;
    ultimo = { ancho, alto, n };
    caja = { ancho, alto };
    if (!n || !ancho || !alto) {
      puestos = [];
      vias = [];
      return;
    }

    const nodos = /** @type {HTMLElement[]} */ ([...lienzo.querySelectorAll('.nodo-agente')]);
    if (nodos.length !== n) return;

    /**
     * Mide las piezas tal como estan ahora y dice si el anillo sale.
     * Que quepa el anillo no es que quepan las piezas: con ocho agentes este
     * mismo lienzo va sobrado y con once los vecinos se montan.
     */
    const intentar = () => {
      const anchoPieza = Math.max(...nodos.map((e) => e.offsetWidth));
      const altoPieza = Math.max(...nodos.map((e) => e.offsetHeight));
      const aro0 = nodos[0].querySelector('.aro');
      const radioPieza = (aro0 ? aro0.getBoundingClientRect().width : 88) / 2;
      // Cuanto se corre el centro del disco respecto al centro de la caja: el
      // nombre y la tarea cuelgan de un lado.
      const desfase = altoPieza / 2 - radioPieza;
      // Margenes anchos a proposito. Con los de antes, a 514 px de alto el
      // anillo "cabia" por 3 px: los nodos de arriba y abajo quedaban rozando
      // el borde y dos se salian. Que quepa raspando no es que quepa -- si no
      // hay sitio holgado, es mejor el nodo compacto.
      const { rx, ry, cabe } = radiosDelAnillo({
        ancho, alto, anchoPieza, altoPieza, desfase, radioPieza,
        radioCentro: R_NUCLEO, margen: 20, holguraCentro: 24
      });
      const angulos = angulosPorArco(n, rx, ry);
      const sale = cabe && !seSolapanEnElAnillo({ angulos, rx, ry, anchoPieza, altoPieza });
      return { sale, rx, ry, angulos, radioPieza };
    };

    // Primero el nodo entero; si no da el alto, el compacto -- que suelta la
    // linea de tarea y encoge el disco. Perder esa linea es mejor que perder
    // el mapa: en produccion quedaban 514 px de alto y el tablero caia a
    // rejilla teniendo sitio de sobra a los lados.
    // La clase se pone en el DOM ANTES de medir, no despues: cada intento tiene
    // que medir el nodo tal como quedaria, y el prop de Svelte llega un
    // re-render tarde.
    const vestir = (/** @type {boolean} */ c) => nodos.forEach((e) => e.classList.toggle('compacto', c));

    vestir(false);
    let intento = intentar();
    let vaCompacto = false;
    if (!intento.sale) {
      vestir(true);
      intento = intentar();
      vaCompacto = intento.sale;
      if (!intento.sale) vestir(false);
    }
    compacto = vaCompacto;

    cabeElAnillo = intento.sale;
    if (!cabeElAnillo) {
      puestos = [];
      vias = [];
      return;
    }
    const { rx, ry, angulos, radioPieza } = intento;
    const cx = ancho / 2;
    const cy = alto / 2;

    const discos = [];
    puestos = angulos.map((ang, i) => {
      const haciaArriba = Math.sin(ang) < -0.25;
      const medida = { ancho: nodos[i].offsetWidth, alto: nodos[i].offsetHeight };
      // El anillo coloca el DISCO; la caja se corre para que su disco caiga ahi.
      const corrimiento = (medida.alto / 2 - radioPieza) * (haciaArriba ? 1 : -1);
      const puntoDisco = { x: cx + rx * Math.cos(ang), y: cy + ry * Math.sin(ang) };
      const p = dentroDelLienzo({ x: puntoDisco.x, y: puntoDisco.y - corrimiento }, medida, { ancho, alto });
      // Si acotar movio la caja, el disco se movio con ella.
      discos.push({ x: p.x, y: p.y + corrimiento });
      return { ...p, haciaArriba };
    });

    // Ultima comprobacion, sobre lo ya colocado: si alguna pieza quedo fuera
    // del lienzo, el anillo no servia y es mejor la rejilla. Sin esto, un
    // error de calculo se ve como un nodo cortado por el borde y nadie sabe
    // por que -- paso el 24/09/2026 con dos nodos a -5 y -1 px.
    const seSale = puestos.some((p, i) => {
      const w = nodos[i].offsetWidth;
      const h = nodos[i].offsetHeight;
      return p.x - w / 2 < -1 || p.y - h / 2 < -1 || p.x + w / 2 > ancho + 1 || p.y + h / 2 > alto + 1;
    });
    if (seSale) {
      cabeElAnillo = false;
      compacto = false;
      vestir(false);
      puestos = [];
      vias = [];
      return;
    }

    // Las vias salen de la geometria, no del DOM: el centro del disco es el
    // punto que acabamos de calcular. Releerlo con getBoundingClientRect
    // devolvia la posicion ANTERIOR, porque el DOM todavia no se actualizo.
    vias = agentes.map((a, i) => {
      const { x: dx, y: dy } = discos[i];
      const ang = Math.atan2(dy - cy, dx - cx);
      const carga = a.conversaciones || 0;
      return {
        nombre: a.nombre,
        x1: cx + Math.cos(ang) * R_NUCLEO,
        y1: cy + Math.sin(ang) * R_NUCLEO,
        x2: dx - Math.cos(ang) * (radioPieza + 3),
        y2: dy - Math.sin(ang) * (radioPieza + 3),
        // el grosor DICE la carga, comparada con el agente mas cargado
        grosor: carga > 0 ? 2 + (carga / Math.max(referencia, 1)) * 7 : 1.5,
        color: carga > 0 ? colorDe(a.estado) : '#94a3b8',
        punteada: carga === 0
      };
    });
  }

  // Un panorama nuevo puede traer otro conjunto de agentes (una empresa da de
  // alta uno, o el motor deja de emitir otro): hay que recolocar. `untrack`
  // para que el calculo no se suscriba a todo lo que toca.
  $effect(() => {
    agentes.length;
    untrack(() => {
      ultimo = { ancho: 0, alto: 0, n: 0 };
      recolocar();
    });
  });

</script>

<div class="sala" use:estirar>
  <div class="identidad">
    <span class="marca"><i></i>DEXTER <b>· CENTRO DE MANDO</b></span>
    <span class="tenant">{panorama.tenant}</span>
    <span class="sep"></span>
    <span class="dato">{agentes.length} agentes configurados</span>
    {#if totales.abiertas_total}
      <span class="dato">{totales.abiertas_total} abiertas sin cerrar</span>
    {/if}
    {#if totales.fallos_hoy}
      <span class="dato rojo">{totales.fallos_hoy} fallos hoy</span>
    {/if}
    <span class="reloj">{hora(sello || panorama.generado_en)} <em>(Bogotá)</em></span>
    <!-- Dos vistas de lo mismo, y el anillo sigue siendo la de por defecto:
         esta medido en produccion desde el 24/09/2026, y estrenar la planta
         como unica vista seria cambiar algo que funciona por algo que nadie
         miro todavia en la operacion real. La planta aporta lo que el anillo
         no muestra -- la estructura del tenant: quien atiende al cliente,
         quien trabaja para adentro y por donde entran las conversaciones. -->
    <div class="vistas" role="group" aria-label="Forma de ver la operación">
      <button class:activa={vista === 'anillo'} onclick={() => (vista = 'anillo')}>Anillo</button>
      <button class:activa={vista === 'planta'} onclick={() => (vista = 'planta')}>Planta</button>
    </div>
  </div>

  <MetricsPanel {totales} {ms} />

  <div class="cuerpo">
    {#if vista === 'planta'}
      <div class="mapa planta">
        <PlantaOficina {panorama} alSeleccionar={(x) => (seleccionado = x)} />
      </div>
    {:else}
    <div class="mapa" class:rejilla={!hayMapa} use:observar>
      {#if hayMapa}
        <svg class="vias" viewBox="0 0 {caja.ancho} {caja.alto}" aria-hidden="true">
          {#each vias as v (v.nombre)}
            <line
              x1={v.x1} y1={v.y1} x2={v.x2} y2={v.y2}
              stroke={v.color} stroke-width={v.grosor} stroke-linecap="round"
              stroke-dasharray={v.punteada ? '5 7' : null}
              opacity={v.punteada ? 0.45 : 0.8}
            />
          {/each}
        </svg>
        <OrchestratorNode {totales} />
      {/if}

      {#each agentes as a, i (a.nombre)}
        <AgentStation
          agente={a}
          x={puestos[i]?.x ?? null}
          y={puestos[i]?.y ?? null}
          haciaArriba={puestos[i]?.haciaArriba ?? false}
          {compacto}
          alSeleccionar={(x) => (seleccionado = x)}
        />
      {/each}
    </div>
    {/if}

    <div class="lateral">
      <EventTimeline {eventos} {hora} {ms} sello={hora(sello || panorama.generado_en)} />
      {#if servicios.length}
        <div class="servicios">
          <span class="et">Servicios usados hoy</span>
          {#each servicios as s (s.herramienta)}
            <ExternalToolNode servicio={s} {ms} />
          {/each}
        </div>
      {/if}
    </div>
  </div>

  <!-- La leyenda explica LAS VIAS, que solo existen en el anillo. Mostrarla
       en la planta describia un dibujo que no estaba: «el grosor es la carga
       que pasa por esa via» y «punteada: sin trafico ahora» sobre una
       pantalla sin una sola via. La planta trae la suya propia (las zonas),
       dentro de su componente. -->
  {#if vista === 'anillo'}
    <div class="leyenda">
      <span><i style="background:#0e7490"></i> el grosor es la carga que pasa por esa vía</span>
      <span><i style="background:#a15c07"></i> el color es el estado del agente</span>
      <span><i class="rayas"></i> punteada: sin tráfico ahora</span>
    </div>
  {/if}
</div>

{#if seleccionado}
  <AgentDetail
    agente={seleccionado}
    ventana={panorama.ventana_min}
    {referencia}
    {hora}
    {ms}
    alCerrar={() => (seleccionado = null)}
  />
{/if}

<style>
  .sala {
    background: #fff;
    background-image: radial-gradient(ellipse at 50% 40%, rgba(14,116,144,.06), transparent 62%);
    color: #0f172a; border: 1px solid #e2e8f0; border-radius: 14px;
    overflow: hidden; display: flex; flex-direction: column;
    min-height: 560px;
  }

  .identidad {
    display: flex; align-items: center; gap: 14px; padding: 9px 16px;
    border-bottom: 1px solid #e2e8f0; font-size: 11px; color: #475569;
  }
  .marca { font-weight: 700; letter-spacing: .16em; color: #0f172a; display: flex; align-items: center; gap: 8px; }
  .marca b { font-weight: 500; letter-spacing: .18em; color: #475569; }
  .marca i { width: 7px; height: 7px; border-radius: 50%; background: #0e7490; }
  .tenant { font-family: ui-monospace, monospace; letter-spacing: .08em; padding: 3px 9px; border: 1px solid #e2e8f0; border-radius: 6px; text-transform: uppercase; }
  .sep { flex: 1; }
  .dato { font-family: ui-monospace, monospace; font-size: 10.5px; }
  .dato.rojo { color: #b91c1c; }
  .reloj { font-family: ui-monospace, monospace; font-size: 11px; color: #0f172a; }
  .reloj em { color: #64748b; font-style: normal; }

  .vistas { display: inline-flex; gap: 2px; padding: 2px; border-radius: 6px; background: #f1f5f9; }
  .vistas button {
    font: inherit; font-size: 10.5px; font-weight: 700; letter-spacing: .04em;
    padding: 3px 10px; border: 0; border-radius: 4px;
    background: transparent; color: #475569; cursor: pointer;
  }
  .vistas button:hover { color: #0f172a; }
  .vistas button.activa { background: #fff; color: #0f172a; box-shadow: 0 1px 2px rgb(15 23 42 / 12%); }

  /* La planta trae su propio lienzo y su propio encaje: aqui solo se le da
     el sitio. */
  .mapa.planta { display: flex; }

  .cuerpo { flex: 1; display: flex; min-height: 0; }
  .mapa { flex: 1; position: relative; min-width: 0; min-height: 0; }
  .vias { position: absolute; inset: 0; width: 100%; height: 100%; }

  /* Sin sitio para el anillo, los nodos se acomodan en rejilla. */
  .mapa.rejilla {
    position: static; display: grid; grid-template-columns: repeat(auto-fill, minmax(156px, 1fr));
    gap: 18px; padding: 16px; align-content: start; overflow-y: auto;
  }

  .lateral { flex: 0 0 319px; display: flex; flex-direction: column; min-height: 0; border-left: 1px solid #e2e8f0; }
  .lateral :global(.eventos) { flex: 1; min-height: 0; border-left: 0; }
  .servicios { display: flex; flex-wrap: wrap; align-content: start; gap: 8px; padding: 10px 14px; border-top: 1px solid #e2e8f0; background: #f8fafc; max-height: 132px; overflow-y: auto; }
  .servicios .et { font-size: 10px; letter-spacing: .12em; text-transform: uppercase; color: #475569; margin-right: 4px; }

  .leyenda { display: flex; gap: 18px; flex-wrap: wrap; padding: 10px 16px; border-top: 1px solid #e2e8f0; font-family: ui-monospace, monospace; font-size: 9.5px; color: #64748b; }
  .leyenda span { display: flex; align-items: center; gap: 6px; }
  .leyenda i { width: 16px; height: 2px; display: inline-block; }
  .leyenda i.rayas { border-top: 2px dashed #94a3b8; }
</style>
