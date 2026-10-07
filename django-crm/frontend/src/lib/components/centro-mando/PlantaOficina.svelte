<script>
  /**
   * La planta de la oficina: un puesto por agente, en rejilla isometrica.
   *
   * Es la UNICA vista del centro de mando desde el 24/09/2026. Nacio como la
   * segunda --convivia con un anillo de discos-- y ese anillo se retiro el
   * mismo dia, por decision de producto, cuando esta llevaba tres
   * despliegues verificados con datos reales.
   *
   * QUE MUESTRA QUE EL ANILLO NO MOSTRABA
   * La ESTRUCTURA del tenant: quien atiende al cliente, quien trabaja para
   * adentro, y por donde entran las conversaciones (el `rol_de_entrada`).
   * Todo eso ya viajaba en el panorama y no se pintaba en ningun lado.
   *
   * LO QUE NO SE MUESTRA, A PROPOSITO
   * Nada del contenido de una conversacion: ni un mensaje, ni un nombre de
   * cliente, ni un numero (PRD RNF-01, y el docstring de
   * panorama_centro_mando: "tampoco viaja nada del cliente"). Un puesto dice
   * "consultar_olt · 342 ms" o "4 esperan a una persona"; nunca a quien.
   */
  import { untrack } from 'svelte';
  import PuestoAgente from './PuestoAgente.svelte';
  import SistemasExternos from './SistemasExternos.svelte';
  import ActividadViva from './ActividadViva.svelte';
  import { ESTADOS, normalizar } from '$lib/centro-mando/estados.js';
  import { rejillaDeSalas, zonaDe, ZONAS, cambios, colorDeArea, poli, punto, iso, tono } from '$lib/centro-mando/planta.js';

  /** @type {{ panorama: any, ms?: (v:any)=>string, alSeleccionar?: (a:any)=>void }} */
  let {
    panorama,
    ms = (v) => (v == null ? '—' : v >= 1000 ? `${(v / 1000).toFixed(1)} s` : `${v} ms`),
    alSeleccionar = () => {}
  } = $props();

  let caja = $state({ ancho: 0, alto: 0 });
  let envoltura = $state(/** @type {HTMLDivElement|null} */ (null));

  const entrada = $derived(panorama?.rol_de_entrada || null);

  /* Orden de lectura: ZONA, despues AREA, y dentro lo que exige atencion.
     El area entra en el orden para que los agentes que la comparten queden
     CONTIGUOS -- en Rapilink son tres pares-- y con el piso tenido del mismo
     color eso dibuja bloques sin gastar espacio.
     Se probo la alternativa de verdad, salas con paredes por area, y sale
     cara: con 8 agentes en 5 areas --1,6 por sala-- tres salas quedan medio
     vacias y los nombres de los puestos se vuelven ilegibles. Agrupar cuesta
     espacio, y el espacio sale del tamaño de los puestos. Esto agrupa sin
     pagar ese precio. */
  const agentes = $derived(
    [...(panorama?.agentes || [])].sort((a, b) =>
      String(a.area || '').localeCompare(String(b.area || '')) ||
      ZONAS[zonaDe(a, entrada)].orden - ZONAS[zonaDe(b, entrada)].orden ||
      ESTADOS[normalizar(a.estado)].orden - ESTADOS[normalizar(b.estado)].orden ||
      (b.conversaciones || 0) - (a.conversaciones || 0) ||
      String(a.nombre).localeCompare(String(b.nombre))
    )
  );

  /* LAS SALAS. La recepcion va SOLA y primera, no dentro del area que
     comparte: es la puerta de entrada del tenant, no un miembro mas de
     Atencion al Cliente. Que este aparte es justamente lo que se quiere ver
     -- por ahi entra todo. */
  const grupos = $derived.by(() => {
    const recep = agentes.filter((a) => entrada && a.nombre === entrada);
    const resto = agentes.filter((a) => !(entrada && a.nombre === entrada));
    const porArea = new Map();
    for (const a of resto) {
      const k = a.area || '(sin área)';
      if (!porArea.has(k)) porArea.set(k, []);
      porArea.get(k).push(a);
    }
    const salas = [...porArea.entries()]
      .map(([area, miembros]) => ({ area, miembros, n: miembros.length, principal: false }))
      .sort((x, y) => y.n - x.n || x.area.localeCompare(y.area));
    return recep.length
      ? [{ area: 'Recepción', miembros: recep, n: recep.length, principal: true }, ...salas]
      : salas;
  });
  const areasPresentes = $derived(grupos.map((g) => g.area));

  /* QUE CAMBIO ENTRE DOS FOTOS.
     Los datos llegan por sondeo cada 12 s, asi que no hay tiempo real que
     animar: lo unico honesto es la diferencia entre dos lecturas. Se guarda
     la anterior con untrack para que recalcular los cambios no dispare otra
     vuelta del efecto. */
  let anteriores = $state(/** @type {any[]} */ ([]));
  let delta = $state(/** @type {Record<string, any>} */ ({}));
  $effect(() => {
    const ahora = panorama?.agentes || [];
    const previos = untrack(() => anteriores);
    delta = cambios(previos, ahora);
    anteriores = ahora;
  });

  /* El sello de frescura: cuantos segundos hace que se leyo la operacion.
     Es lo menos vistoso de esta pantalla y lo mas importante -- deja dicho
     que lo que se ve es una FOTO cada 12 segundos y no un flujo continuo.
     Sin el, una planta que se mueve sugiere continuidad que no existe. */
  let ahora = $state(new Date());
  $effect(() => {
    const t = setInterval(() => (ahora = new Date()), 1000);
    return () => clearInterval(t);
  });
  const segundosDesdeLaLectura = $derived.by(() => {
    if (!panorama?.generado_en) return null;
    return Math.max(0, Math.round((ahora.getTime() - new Date(panorama.generado_en).getTime()) / 1000));
  });

  const LADO = 100, SEP = 30;
  /* Arriba: el rotulo cuelga de la pared y la chapa de "esperan" sobresale
     otro tanto. Abajo: el halo de foco, 4 unidades por fuera del puesto. Un
     margen corto no se ve con ocho agentes y desborda con diez. */
  const MARGEN_SUP = LADO * 0.88, MARGEN_INF = LADO * 0.18, MARGEN_LAT = 24;

  const rej = $derived(
    rejillaDeSalas(grupos.map((g) => ({ n: g.n, principal: !!g.principal })), {
      ancho: Math.max(160, caja.ancho - MARGEN_LAT * 2),
      alto: Math.max(160, caja.alto),
      lado: LADO, separacion: SEP,
      /* Franja de suelo libre al frente de cada sala, para el nombre pintado
         en el piso. Sin ella el nombre cae bajo los escritorios. */
      rotulo: LADO * 0.34,
      /* EL PASILLO CENTRAL: parte las oficinas en dos bandas con un corredor
         por el medio. Es lo que convierte seis cajas sueltas en una PLANTA
         -- un edificio se recorre, y se recorre por algun sitio. */
      pasilloCentral: LADO * 0.95,
      holguraAlto: (MARGEN_SUP + MARGEN_INF) / LADO
    })
  );

  const encuadre = $derived.by(() => {
    const esc = rej.escala;
    const anchoTotal = rej.ancho * esc;
    const altoTotal = (rej.alto + MARGEN_SUP + MARGEN_INF) * esc;
    return {
      // al centrado se le suma el corrimiento propio de la rejilla, que es
      // lo que lleva el dibujo al origen
      dx: (caja.ancho - anchoTotal) / 2 + (rej.dx || 0) * esc,
      dy: (caja.alto - altoTotal) / 2 + MARGEN_SUP * esc + (rej.dy || 0) * esc,
      esc
    };
  });

  /* En isometrica lo que esta mas adelante se pinta DESPUES, o los tabiques
     del puesto de atras tapan el escritorio del de adelante. */

  /* La tarima de cada area: un suelo continuo bajo sus puestos. Separar no
     agrupa --en una rejilla diagonal dos vecinos de la misma area se ven
     igual que dos de areas distintas-- pero un suelo compartido si. Es la
     mitad util de las salas sin la cara: agrupa sin paredes, y las paredes
     eran las que costaban el tamaño de los puestos. */
  /* Paredes altas. A 34 las salas se leian como bandejas vistas desde
     arriba; a 62 se leen como habitaciones. El techo lo pone lo que tapan:
     mas altas y la pared de una sala empieza a comerse la de atras. */
  const ALTO_PARED = 46;
  /** Para comparar un area con el nombre de un rol: una lleva tildes, el otro no. */
  const sinTildes = (t) => String(t).normalize('NFD').replace(/[̀-ͯ]/g, '')
    .replaceAll('_', ' ').trim().toUpperCase();
  const dibujo = $derived.by(() => {
    const e = rej.ejes, H = ALTO_PARED;
    return (rej.salas || []).map((sala, i) => {
      const g = grupos[i];
      if (!g) return null;
      const c = g.principal ? '#8B5FBF' : colorDeArea(g.area, areasPresentes);
      const { u0, v0, u1, v1, rotulo: FR } = sala;
      return {
        clave: g.area, area: g.area, color: c, principal: !!g.principal,
        profundidad: sala.col + sala.fila,
        suelo: poli(e, [u0,v0,0], [u1,v0,0], [u1,v1,0], [u0,v1,0]),
        fondo: poli(e, [u0,v0,0], [u1,v0,0], [u1,v0,H], [u0,v0,H]),
        izq:   poli(e, [u0,v0,0], [u0,v1,0], [u0,v1,H], [u0,v0,H]),
        cantoFondo: poli(e, [u0,v0,H], [u1,v0,H], [u1,v0-4,H], [u0,v0-4,H]),
        cantoIzq:   poli(e, [u0,v0,H], [u0,v1,H], [u0-4,v1,H], [u0-4,v0,H]),
        /* El rotulo va DENTRO de la sala, sobre su suelo y junto al borde de
           delante. Colgado arriba se tapaba con la sala vecina -- se veia
           "SOPORTE TECNI..." cortado por la de al lado. */
        /* LA PUERTA VA EN LA PARED IZQUIERDA, no en la del fondo. En el fondo
           caia justo al lado del cartel del agente y le comia el ancho: el
           nombre se recortaba a "SOPORTE TECNICO CLIE..." teniendo la pared
           medio vacia al lado. Aqui no compite con nada, y se entra por
           delante, que es de donde viene el pasillo. */
        puerta: poli(e, [u0, v1 - 66, 2], [u0, v1 - 22, 2], [u0, v1 - 22, H - 4], [u0, v1 - 66, H - 4]),
        puertaMarco: poli(e, [u0, v1 - 70, 0], [u0, v1 - 18, 0], [u0, v1 - 18, H], [u0, v1 - 70, H]),
        /* Dos cuadros en la pared izquierda. Decoracion, si -- pero es lo que
           hace que una caja de color se lea como una habitacion. */
        cuadros: [
          poli(e, [u0, v0 + 26, H * 0.66], [u0, v0 + 62, H * 0.66], [u0, v0 + 62, H * 0.26], [u0, v0 + 26, H * 0.26]),
          poli(e, [u0, v0 + 78, H * 0.60], [u0, v0 + 104, H * 0.60], [u0, v0 + 104, H * 0.30], [u0, v0 + 78, H * 0.30])
        ],
        /* En una sala de UN agente cuyo nombre coincide con el del area, el
         suelo y el cartel decian lo mismo: "VENTAS" dos veces, una encima de
         la otra. Se compara sin tildes porque el area las lleva y el nombre
         del rol no. */
      repiteNombre: g.miembros.length === 1 && sinTildes(g.area) === sinTildes(g.miembros[0].nombre),
      /* EL NOMBRE VA PINTADO EN EL SUELO, en la franja libre del frente.
           Las placas flotantes que habia antes no decian de que oficina
           eran: "FACTURACION" aparecia sobre la recepcion y "VENTAS" entre
           dos salas. Pintado dentro no hay confusion posible.
           La matriz es la del plano horizontal: el eje u se proyecta en
           (ex, ey) y el v en (-ex, ey). Su determinante es 2*ex*ey, positivo,
           asi que el texto NO sale espejado -- el mismo cuidado que hubo que
           tener con el cartel de la pared izquierda. */
        suelo_texto: {
          centro: iso(u0 + (u1 - u0) / 2, v1 - FR * 0.45, 0, e),
          matriz: `${e.ex} ${e.ey} ${-e.ex} ${e.ey}`,
          /* El cuerpo sale del ANCHO DE SU SALA, no de un numero fijo. Con 26
             fijo, "ATENCION AL CLIENTE" se desbordaba y cruzaba tres oficinas
             -- y el ancho util no es el mismo para una sala de un puesto que
             para una de dos. Mismo criterio que el nombre de cada agente en
             su cartel: se encoge la letra hasta que entra. */
          cuerpo: Math.max(10, Math.min(FR * 0.62,
            ((u1 - u0) - 30) / Math.max(1, String(g.area).length * 0.68)))
        },
        rotulo: iso((u0 + u1) / 2, v1 - 12, 0, e),
        miembros: g.miembros.map((a, k) => ({
          agente: a,
          numero: k + 1,
          pos: iso(sala.puestos[k].u, sala.puestos[k].v, 0, e),
          p: sala.puestos[k]
        }))
      };
    }).filter(Boolean).sort((a, b) => a.profundidad - b.profundidad);
  });

  /** El suelo del edificio: el rectangulo que abarca todas las salas. */
  /* EL CORREDOR: el suelo del pasillo central, con su eje marcado. Se pinta
     aparte del piso del edificio para que se lea como transito y no como
     hueco -- un pasillo es un sitio por donde se pasa, no la ausencia de
     oficinas. */
  const corredor = $derived.by(() => {
    const c = rej.corredor;
    if (!c) return null;
    const e = rej.ejes, m = (c.u0 + c.u1) / 2;
    return {
      suelo: poli(e, [c.u0, c.v0, 0], [c.u1, c.v0, 0], [c.u1, c.v1, 0], [c.u0, c.v1, 0]),
      eje: `${punto(m, c.v0 + 16, 0, e)} ${punto(m, c.v1 - 16, 0, e)}`
    };
  });

  const piso = $derived.by(() => {
    const ss = rej.salas || [];
    if (!ss.length) return null;
    const m = 58;
    return poli(rej.ejes,
      [Math.min(...ss.map((x) => x.u0)) - m, Math.min(...ss.map((x) => x.v0)) - m, 0],
      [Math.max(...ss.map((x) => x.u1)) + m, Math.min(...ss.map((x) => x.v0)) - m, 0],
      [Math.max(...ss.map((x) => x.u1)) + m, Math.max(...ss.map((x) => x.v1)) + m, 0],
      [Math.min(...ss.map((x) => x.u0)) - m, Math.max(...ss.map((x) => x.v1)) + m, 0]);
  });

  /* Donde esta cada puesto, por nombre. Lo necesita la capa de actividad:
     un puesto se dibuja a si mismo y no sabe donde estan los demas, asi que
     lo que va DE un sitio A otro no lo puede dibujar el. El punto es el
     centro del piso del modulo, no su esquina. */
  const posiciones = $derived.by(() => {
    /** @type {Record<string, {x:number,y:number}>} */
    const m = {};
    for (const sala of dibujo) {
      for (const mi of sala.miembros) {
        m[mi.agente.nombre] = { x: mi.pos[0], y: mi.pos[1] + LADO * rej.ejes.ey };
      }
    }
    return m;
  });

  $effect(() => {
    if (!envoltura) return;
    /* Se mide AL MONTAR y ademas se observa. El ResizeObserver no garantiza
       una primera entrega --y en este repo ya hay medido que pierde avisos:
       de cuatro cambios de tamano entregaba dos-- asi que sin la lectura
       inicial el lienzo se queda en 0x0 y no se dibuja nada, aunque los
       elementos SI esten en el DOM. Paso exactamente eso. */
    const medir = () => {
      const r = envoltura.getBoundingClientRect();
      if (r.width && r.height) caja = { ancho: r.width, alto: r.height };
    };
    medir();
    const ro = new ResizeObserver(medir);
    ro.observe(envoltura);
    const repaso = setInterval(medir, 500);
    return () => { ro.disconnect(); clearInterval(repaso); };
  });

  const zonasPresentes = $derived(
    [...new Set(agentes.map((a) => zonaDe(a, entrada)))].sort((a, b) => ZONAS[a].orden - ZONAS[b].orden)
  );

  /* ------------------------------------------------------------ LA CAMARA
     Rueda para acercar, arrastrar para mover, "Ajustar" para volver.

     Vive APARTE del encuadre automatico, y esa separacion es lo que hace que
     funcione: el encaje se recalcula solo con cada foto --cuantas columnas,
     que escala, donde centrar-- y la camara se aplica ENCIMA. Asi la planta
     se repinta cada 12 segundos con datos nuevos sin devolverle la vista a su
     sitio: quien se acerco a un puesto sigue mirando ese puesto. */
  let vista = $state({ k: 1, x: 0, y: 0 });
  const MIN_K = 0.6, MAX_K = 5;
  const enSuSitio = $derived(vista.k === 1 && vista.x === 0 && vista.y === 0);

  function acercar(factor, cx, cy) {
    const k = Math.max(MIN_K, Math.min(MAX_K, vista.k * factor));
    if (k === vista.k) return;
    /* El punto bajo el cursor se queda quieto: es lo que hace que acercar se
       sienta como acercarse a un sitio y no como que la escena se escape. */
    const r = k / vista.k;
    vista = { k, x: cx - (cx - vista.x) * r, y: cy - (cy - vista.y) * r };
  }

  function alaRueda(ev) {
    ev.preventDefault();
    const c = envoltura.getBoundingClientRect();
    acercar(ev.deltaY < 0 ? 1.12 : 1 / 1.12, ev.clientX - c.x, ev.clientY - c.y);
  }

  let arrastre = $state(/** @type {any} */ (null));
  const UMBRAL = 4;

  function alBajar(ev) {
    if (ev.button !== 0) return;
    /* NO se captura el puntero aqui, y ese detalle es el que rompio abrir la
       ficha de un agente (24/09/2026, visto en produccion).
       Con `setPointerCapture` activa, el elemento capturador se queda con
       todos los eventos de puntero Y con el `click` que sale del par
       pointerdown/pointerup: el evento se dispara en el DIV del lienzo y no
       en el <g> del puesto, asi que el `onclick` del puesto no corria nunca.
       Pulsar un agente dejaba de mostrar su ficha, sin ningun error.
       Se captura mas abajo, solo cuando el gesto resulta ser un arrastre de
       verdad. Un clic limpio no captura nada y llega a su destino. */
    arrastre = { x: ev.clientX, y: ev.clientY, vx: vista.x, vy: vista.y, movido: 0, capturado: false };
  }

  function alMover(ev) {
    if (!arrastre) return;
    const dx = ev.clientX - arrastre.x, dy = ev.clientY - arrastre.y;
    arrastre.movido = Math.max(arrastre.movido, Math.abs(dx) + Math.abs(dy));
    if (arrastre.movido < UMBRAL) return;   // todavia puede ser un clic
    /* Ya es un arrastre: ahora si conviene capturar, para que siga
       funcionando aunque el cursor se salga del lienzo. */
    if (!arrastre.capturado) {
      arrastre.capturado = true;
      try { ev.currentTarget.setPointerCapture(ev.pointerId); } catch { /* sin captura */ }
    }
    vista = { ...vista, x: arrastre.vx + dx, y: arrastre.vy + dy };
  }

  /* Un gesto de menos de 4 px cuenta como clic. Sin este umbral, abrir la
     ficha de un puesto se vuelve imposible: el dedo siempre mueve algo.
     Se mira `ultimoGesto` y no `arrastre`, porque para cuando llega el
     `click` el `pointerup` ya limpio el arrastre -- leerlo ahi daba siempre
     null y el umbral no filtraba nada. */
  let ultimoGesto = $state(0);
  function alSoltarGesto() {
    ultimoGesto = arrastre ? arrastre.movido : 0;
    arrastre = null;
  }

  function seleccionar(a) {
    if (ultimoGesto >= UMBRAL) return;
    alSeleccionar(a);
  }

  function ajustar() { vista = { k: 1, x: 0, y: 0 }; }
  function botonZoom(f) {
    const c = envoltura?.getBoundingClientRect();
    if (c) acercar(f, c.width / 2, c.height / 2);
  }

  /* ----------------------------------------------------------- LOS FILTROS
     Lo primero que se pide en una operacion real: "mostrame solo los que
     tienen errores". Atenua en vez de esconder -- la planta no cambia de
     forma al filtrar, asi que no hay que volver a ubicarse cada vez. */
  let filtro = $state('todos');
  const FILTROS = {
    todos: { rotulo: 'Todos', test: () => true },
    llaman: {
      rotulo: 'Esperan a alguien',
      test: (a) => (a.esperando_humano || 0) + (a.esperando_aprobacion || 0) > 0
    },
    error: { rotulo: 'Con errores', test: (a) => normalizar(a.estado) === 'error' },
    trabajan: { rotulo: 'Trabajando', test: (a) => normalizar(a.estado) === 'working' },
    libres: { rotulo: 'Disponibles', test: (a) => normalizar(a.estado) === 'idle' }
  };
  const cuentas = $derived(
    Object.fromEntries(Object.entries(FILTROS).map(([k, f]) => [k, agentes.filter(f.test).length]))
  );
  const pasa = (a) => (FILTROS[filtro] || FILTROS.todos).test(a);
</script>

<div class="planta">
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    class="lienzo"
    class:arrastrando={!!arrastre}
    bind:this={envoltura}
    onwheel={alaRueda}
    onpointerdown={alBajar}
    onpointermove={alMover}
    onpointerup={alSoltarGesto}
    onpointercancel={alSoltarGesto}
    ondblclick={ajustar}
  >
    <svg role="img" aria-label="Planta de la oficina: un puesto por cada agente"
      viewBox="0 0 {Math.max(1, caja.ancho)} {Math.max(1, caja.alto)}">
      <!-- Dos transformaciones compuestas: primero la de la camara, despues
           la del encaje automatico. El orden importa -- al reves, mover la
           vista escalaria tambien el desplazamiento. -->
      <g transform="translate({vista.x}, {vista.y}) scale({vista.k}) translate({encuadre.dx}, {encuadre.dy}) scale({encuadre.esc})">
        <!-- El suelo del edificio. Lo que queda entre salas pasa a leerse
             como PASILLO en vez de como fondo vacio: el hueco entre dos
             oficinas solo es un pasillo si hay piso debajo. -->
        {#if piso}
          <polygon points={piso} fill="#EDF1F6" stroke="#D8DFE8" stroke-width="1.5" />
        {/if}
        {#if corredor}
          <polygon points={corredor.suelo} fill="#FFFFFF" fill-opacity=".72"
            stroke="#C7D1DE" stroke-width="1.4" />
          <polyline points={corredor.eje} fill="none" stroke="#C7D1DE"
            stroke-width="2" stroke-dasharray="9 11" opacity=".75" />
        {/if}

        <!-- Cada sala con sus escritorios dentro. Se pinta de atras hacia
             adelante: en isometrica, la sala de delante tapa a la de atras. -->
        {#each dibujo as sala (sala.clave)}
          <g class="sala" class:principal={sala.principal}>
            <polygon points={sala.suelo} fill={sala.color} fill-opacity=".13"
              stroke={sala.color} stroke-width="1.4" stroke-opacity=".45" />
            <polygon points={sala.fondo} fill={tono(sala.color, 0.42)} />
            <polygon points={sala.izq} fill={tono(sala.color, 0.28)} />
            <polygon points={sala.cantoFondo} fill={tono(sala.color, 0.60)} />
            <polygon points={sala.cantoIzq} fill={tono(sala.color, 0.52)} />

            <!-- la puerta, en la pared izquierda -->
            <polygon points={sala.puertaMarco} fill={tono(sala.color, -0.18)} />
            <polygon points={sala.puerta} fill="#F7F9FC" />
            <!-- cuadros en la pared izquierda -->
            {#each sala.cuadros as c, ci (ci)}
              <polygon points={c} fill="#FFFFFF" fill-opacity=".82" stroke={tono(sala.color, -0.1)} stroke-width="1" />
            {/each}

            <!-- el nombre, pintado en el suelo de SU oficina -->
            {#if !sala.repiteNombre}
            <g transform="matrix({sala.suelo_texto.matriz} {sala.suelo_texto.centro[0]} {sala.suelo_texto.centro[1]})">
              <text x="0" y="0" text-anchor="middle" fill={tono(sala.color, -0.4)}
                font-size={sala.suelo_texto.cuerpo} font-weight="800"
                letter-spacing={sala.suelo_texto.cuerpo * 0.1}
                opacity=".8">{sala.area.toUpperCase()}</text>
            </g>
            {/if}

            {#each sala.miembros as m (m.agente.nombre)}
              <g class="celda" class:apagado={!pasa(m.agente)}
                 transform="translate({m.pos[0]}, {m.pos[1]})">
                <PuestoAgente
                  agente={m.agente}
                  numero={m.numero}
                  lado={LADO}
                  {entrada}
                  ejes={rej.ejes}
                  cambio={delta[m.agente.nombre]}
                  {ahora}
                  enSala={true}
                  alSeleccionar={seleccionar}
                />
              </g>
            {/each}

          </g>
        {/each}

        <!-- LOS ROTULOS, TODOS AL FINAL. Dibujados dentro de cada sala, la
             sala de delante los tapaba a medias: se leia "...CTURACION" y
             "...ION AL CLIENTE". Pintados al final quedan por encima de todo
             y ninguno pierde su nombre. -->

        <ActividadViva eventos={panorama?.eventos || []} {posiciones} lado={LADO} />
      </g>
    </svg>

    <div class="camara">
      <button onclick={() => botonZoom(1 / 1.3)} title="Alejar" aria-label="Alejar">−</button>
      <button onclick={() => botonZoom(1.3)} title="Acercar" aria-label="Acercar">+</button>
      <button onclick={ajustar} disabled={enSuSitio} title="Volver al encuadre automático">Ajustar</button>
    </div>
  </div>

  <div class="filtros">
    {#each Object.entries(FILTROS) as [k, f] (k)}
      <button class:activo={filtro === k} disabled={cuentas[k] === 0 && k !== 'todos'}
        onclick={() => (filtro = k)}>
        {f.rotulo}<span class="n">{cuentas[k]}</span>
      </button>
    {/each}
  </div>

  <SistemasExternos servicios={panorama?.servicios || []} {ms} />

  <div class="pieplanta">
    {#if !entrada}
      <!-- Se dice que falta en vez de adivinarlo: deducir la puerta de
           entrada del "primer rol orientado al cliente" es el error que dejo
           a un suscriptor sin internet hablando con el agente comercial. -->
      <span class="falta" title="El motor no envió rol_de_entrada para este tenant">
        Sin recepción declarada
      </span>
    {/if}
    <!-- QUIEN TRATA CON EL CLIENTE Y QUIEN NO. Esta banda se perdio al pasar
         a salas por area --el pie quedo listando areas y nada mas-- y eso
         borraba justo lo que esta pantalla muestra y el resto no: por donde
         entra la gente y quien trabaja para adentro. Son dos cosas distintas
         de las areas, y van las dos. Lo cazo PlantaOficina.test.js, no mirar
         la pantalla: el rotulo seguia calculandose y solo dejo de pintarse. -->
    {#each zonasPresentes as z (z)}
      <span class="zona"><i style="background:{ZONAS[z].color}"></i>{ZONAS[z].rotulo}</span>
    {/each}
    <span class="sep"></span>
    {#each areasPresentes as a (a)}
      <span class="zona"><i style="background:{colorDeArea(a, areasPresentes)}"></i>{a}</span>
    {/each}
    <span class="crece"></span>
    {#if segundosDesdeLaLectura != null}
      <span class="frescura" title="Los datos llegan por sondeo: lo que se ve es una lectura, no un flujo continuo">
        leído hace {segundosDesdeLaLectura}s
      </span>
    {/if}
  </div>
</div>

<style>
  .planta { position: relative; width: 100%; height: 100%; min-height: 320px; display: flex; flex-direction: column; }
  /* El lienzo se arrastra: el cursor lo anuncia antes de que nadie lo
     intente. `touch-action:none` es lo que deja que el gesto lo maneje la
     pantalla en vez del navegador. */
  .lienzo { position: relative; flex: 1; min-height: 0; cursor: grab; touch-action: none; overflow: hidden; }
  .lienzo.arrastrando { cursor: grabbing; }
  svg { display: block; width: 100%; height: 100%; }

  /* El filtro ATENUA en vez de esconder: la planta no cambia de forma, asi
     que no hay que volver a ubicarse en cada filtro. */
  .celda { transition: opacity .2s ease; }
  .celda.apagado { opacity: .14; pointer-events: none; }

  .camara { position: absolute; right: 8px; bottom: 8px; display: flex; gap: 4px; }
  .camara button {
    font: inherit; font-size: 11px; font-weight: 700; line-height: 1;
    padding: 5px 9px; border: 1px solid #c9d1dc; border-radius: 5px;
    background: rgb(255 255 255 / 92%); color: #475569; cursor: pointer;
  }
  .camara button:hover:not(:disabled) { background: #f1f5f9; color: #0f172a; }
  .camara button:disabled { opacity: .4; cursor: default; }

  .filtros { flex: 0 0 auto; display: flex; gap: 5px; flex-wrap: wrap; padding: 6px 0 0; }
  .filtros button {
    font: inherit; font-size: 10.5px; font-weight: 700; letter-spacing: .03em;
    padding: 4px 10px; border: 1px solid #c9d1dc; border-radius: 5px;
    background: #fff; color: #475569; cursor: pointer;
  }
  .filtros button:hover:not(:disabled) { background: #f1f5f9; }
  .filtros button.activo { background: #0f172a; border-color: #0f172a; color: #fff; }
  .filtros button:disabled { opacity: .4; cursor: default; }
  .filtros .n { font-family: ui-monospace, monospace; opacity: .75; margin-left: 5px; }

  @media (prefers-reduced-motion: reduce) { .celda { transition: none; } }

  .pieplanta {
    flex: 0 0 auto; display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
    padding: 6px 4px 0;
  }
  .sep { width: 1px; align-self: stretch; background: #DCE3EC; }
  .zona, .frescura, .falta {
    display: flex; align-items: center; gap: 5px;
    font-size: 9px; letter-spacing: .06em; text-transform: uppercase; font-weight: 600;
    color: #475569;
  }
  .zona i { width: 9px; height: 9px; border-radius: 2px; }
  .crece { flex: 1; }
  .frescura { font-family: ui-monospace, monospace; color: #94A3B8; letter-spacing: .04em; }
  .falta {
    color: #92400E; background: #FEF3C7; border: 1px solid #FCD34D;
    border-radius: 4px; padding: 2px 7px;
  }
</style>
