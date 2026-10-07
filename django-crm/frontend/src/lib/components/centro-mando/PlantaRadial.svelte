<script>
  /**
   * El orquestador al centro y las areas en anillo.
   *
   * Es LA planta del centro de mando desde el 07/10/2026. Nacio como
   * propuesta en paralelo a una rejilla de salas, se compararon las dos en un
   * banco y se descarto la otra.
   *
   * QUE TOMA DE LA REFERENCIA, Y QUE NO
   * De la ilustracion de referencia se toman cuatro cosas, y las cuatro se
   * llenan con dato que el payload YA trae:
   *   - la ficha pegada a la oficina  -> conversaciones, esperando_humano,
   *                                      ultima_herramienta, estado
   *   - el numero grande en la pared  -> el orden del puesto
   *   - el grafico en el monitor      -> `serie`, 15 cubos de 2 minutos
   *   - el orquestador al centro      -> `rol_de_entrada`, del motor
   *
   * NO se toman tres, y el motivo es el mismo en las tres: no hay con que
   * sostenerlas.
   *   - "Calidad 98%": no existe ninguna metrica de calidad.
   *   - "Conectado" bajo cada sistema: no hacemos healthcheck a ninguno. Lo
   *     que sabemos es la tasa de fallo de las llamadas que hicimos, que es
   *     otra cosa -- un sistema caido al que no llamamos hace media hora se
   *     veria "Conectado". Eso ya lo dice la franja de sistemas, y lo dice
   *     bien.
   *   - cintas de trafico entre oficinas: el destino de cada derivacion vive
   *     en tool_calls.parametros y hoy no sale en el payload. Los pasillos
   *     radiales dicen ESTRUCTURA --de la entrada se deriva a las areas--,
   *     que si es cierto; un grosor o un brillo dirian CUANTO, que no lo es.
   */
  import { untrack, onDestroy } from 'svelte';
  import PuestoAgente from './PuestoAgente.svelte';
  import { anilloDeSalas } from '$lib/centro-mando/planta-radial.js';
  import { zonaDe, ZONAS, cambios, colorDeArea, poli, iso, tono } from '$lib/centro-mando/planta.js';
  import { colorDe, rotuloDe, normalizar } from '$lib/centro-mando/estados.js';
  import SistemasExternos from './SistemasExternos.svelte';
  import { eventosNuevos } from '$lib/centro-mando/actividad.js';

  /** @type {{ panorama: any, ms?: (v:any)=>string, alSeleccionar?: (a:any)=>void }} */
  let {
    panorama,
    ms = (v) => (v == null ? '—' : v >= 1000 ? `${(v / 1000).toFixed(1)} s` : `${v} ms`),
    alSeleccionar = () => {}
  } = $props();

  const agentes = $derived(panorama?.agentes || []);
  const entrada = $derived(panorama?.rol_de_entrada || null);

  /* La puerta de entrada del tenant va al CENTRO y las areas alrededor. No
     es una preferencia de dibujo: todo el que escribe por un canal publico
     entra por `rol_de_entrada` y de ahi se deriva, asi que el centro es la
     topologia real. Si el tenant no lo declara, no hay centro y el anillo se
     cierra solo -- que es justo lo que debe verse cuando falta el dato. */
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
  /* La recepcion ya se nombra en la banda de zonas. Listarla otra vez entre
     las areas la hacia aparecer DOS VECES seguidas en el pie, con dos colores
     distintos, como si fueran dos cosas. */
  const areaPrincipal = $derived(grupos.find((g) => g.principal)?.area ?? null);

  /* Que cambio entre dos fotos: con sondeo cada 12 s no hay tiempo real que
     animar, y lo unico honesto es la diferencia entre dos lecturas. */
  let anteriores = $state(/** @type {any[]} */ ([]));
  let delta = $state(/** @type {Record<string, any>} */ ({}));
  $effect(() => {
    const ahora = panorama?.agentes || [];
    /* `anteriores` se lee con untrack: sin eso el efecto se lee a si mismo y
       vuelve a dispararse al escribirse -- Svelte corta en
       effect_update_depth_exceeded y la planta no llega a pintarse. */
    const previos = untrack(() => anteriores);
    delta = cambios(previos, ahora);
    anteriores = ahora;
  });

  /* El sello de frescura. Es lo menos vistoso de esta pantalla y lo mas
     importante: deja dicho que lo que se ve es una lectura cada 12 s y no un
     flujo continuo. Sin el, una planta que se mueve sugiere una continuidad
     que no existe. */
  let ahora = $state(new Date());
  $effect(() => {
    const t = setInterval(() => (ahora = new Date()), 1000);
    return () => clearInterval(t);
  });
  const segundosDesdeLaLectura = $derived.by(() => {
    if (!panorama?.generado_en) return null;
    return Math.max(0, Math.round((ahora.getTime() - new Date(panorama.generado_en).getTime()) / 1000));
  });

  const zonasPresentes = $derived(
    [...new Set(agentes.map((a) => zonaDe(a, entrada)))].sort((a, b) => ZONAS[a].orden - ZONAS[b].orden)
  );

  /* LOS FILTROS. Lo primero que se pide en una operacion real: "mostrame solo
     los que tienen errores". Atenua en vez de esconder -- la planta no cambia
     de forma al filtrar, asi que no hay que volver a ubicarse cada vez. */
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

  let envoltura = $state(/** @type {any} */ (null));
  let caja = $state({ ancho: 0, alto: 0 });

  const LADO = 100, SEP = 30;
  const MARGEN_SUP = LADO * 0.9, MARGEN_INF = LADO * 0.2, MARGEN_LAT = 26;

  const an = $derived(
    anilloDeSalas(grupos.map((g) => ({ n: g.n, principal: !!g.principal, area: g.area })), {
      ancho: Math.max(160, caja.ancho - MARGEN_LAT * 2),
      alto: Math.max(160, caja.alto),
      lado: LADO, separacion: SEP, rotulo: LADO * 0.34,
      holguraAlto: (MARGEN_SUP + MARGEN_INF) / LADO
    })
  );

  const ALTO_PARED = 46;
  /** Para comparar un area con el nombre de un rol: una lleva tildes, el otro no. */
  const sinTildes = (t) => String(t).normalize('NFD').replace(/[̀-ͯ]/g, '')
    .replaceAll('_', ' ').trim().toUpperCase();

  /** Una sala lista para dibujar: paredes, puerta, cuadros, rotulos y puestos. */
  function vestir(sala, g, e) {
    const { u0, v0, u1, v1, rotulo: FR } = sala;
    const H = ALTO_PARED;
    const c = g.principal ? '#8B5FBF' : colorDeArea(g.area, areasPresentes);
    return {
      clave: g.area, area: g.area, color: c, principal: !!g.principal,
      profundidad: (u0 + v0),
      suelo: poli(e, [u0,v0,0], [u1,v0,0], [u1,v1,0], [u0,v1,0]),
      fondo: poli(e, [u0,v0,0], [u1,v0,0], [u1,v0,H], [u0,v0,H]),
      izq:   poli(e, [u0,v0,0], [u0,v1,0], [u0,v1,H], [u0,v0,H]),
      cantoFondo: poli(e, [u0,v0,H], [u1,v0,H], [u1,v0-4,H], [u0,v0-4,H]),
      cantoIzq:   poli(e, [u0,v0,H], [u0,v1,H], [u0-4,v1,H], [u0-4,v0,H]),
      // la puerta, en la pared izquierda: en la del fondo le comia el ancho
      // al cartel del agente y el nombre se recortaba.
      puerta: poli(e, [u0, v1-66, 2], [u0, v1-22, 2], [u0, v1-22, H-4], [u0, v1-66, H-4]),
      puertaMarco: poli(e, [u0, v1-70, 0], [u0, v1-18, 0], [u0, v1-18, H], [u0, v1-70, H]),
      cuadros: [
        poli(e, [u0, v0+26, H*0.66], [u0, v0+62, H*0.66], [u0, v0+62, H*0.26], [u0, v0+26, H*0.26])
      ],
      /* EL NUMERO GRANDE EN LA PARED, como en la referencia. Va en el plano
         y=0: el eje horizontal se proyecta en (ex,ey) y el vertical en (0,1),
         asi que el texto baja con la perspectiva sin deformarse. */
      /* EL NUMERO VA EN LA PARED IZQUIERDA. Estaba en la del fondo, en la
         esquina, y ahi es justo donde esta el archivador: uno tapaba al
         otro. La izquierda tiene sitio de sobra entre el cuadro y la puerta.
         LA MATRIZ IMPORTA. La pared izquierda es el plano x=u0, y recorrerla
         de frente a fondo da determinante NEGATIVO: el texto sale espejado.
         Se recorre al reves --v decreciente desde `vref`-- y entonces la
         matriz es (ex, -ey, 0, 1), cuyo determinante es ex > 0. El origen es
         un punto del propio plano, calculado con la misma proyeccion que
         todo lo demas, no escrito a mano. */
      numero: {
        matriz: `${e.ex} ${-e.ey} 0 1 ${iso(u0, v0 + 116, H * 0.26, e).join(' ')}`,
        cuerpo: H * 0.5
      },
      /* En una sala de UN agente cuyo nombre coincide con el del area, el
         suelo y el cartel decian lo mismo: "VENTAS" dos veces, una encima de
         la otra. Lo mismo paso en la planta en rejilla y aqui se repitio --
         por eso esta prueba existe en las dos. */
      repiteNombre: g.miembros.length === 1 && sinTildes(g.area) === sinTildes(g.miembros[0].nombre),
      /* El nombre pintado en el suelo, en la franja libre del frente. El
         cuerpo sale del ANCHO DE SU SALA: con un numero fijo, "ATENCION AL
         CLIENTE" se desbordaba y cruzaba las oficinas vecinas. */
      sueloTexto: {
        centro: iso(u0 + (u1-u0)/2, v1 - FR*0.45, 0, e),
        matriz: `${e.ex} ${e.ey} ${-e.ex} ${e.ey}`,
        cuerpo: Math.max(10, Math.min(FR*0.62, ((u1-u0) - 30) / Math.max(1, String(g.area).length * 0.68)))
      },
      /* Un archivador en la esquina del fondo. Es lo que separa una caja de
         colores de una oficina: los muebles que nadie mira pero que uno
         espera encontrar. */
      archivador: {
        tapa:   poli(e, [u0+10,v0+8,40], [u0+44,v0+8,40], [u0+44,v0+30,40], [u0+10,v0+30,40]),
        frente: poli(e, [u0+10,v0+30,0], [u0+44,v0+30,0], [u0+44,v0+30,40], [u0+10,v0+30,40]),
        canto:  poli(e, [u0+44,v0+8,40], [u0+44,v0+30,40], [u0+44,v0+30,0], [u0+44,v0+8,0]),
        tirador: poli(e, [u0+18,v0+30,26], [u0+36,v0+30,26], [u0+36,v0+30,23], [u0+18,v0+30,23])
      },
      miembros: g.miembros.map((a, k) => ({
        agente: a, numero: k + 1, pos: iso(sala.puestos[k].u, sala.puestos[k].v, 0, e)
      }))
    };
  }

  /* Salas y centro en UNA lista ordenada por profundidad: en isometrica lo
     que esta delante tapa a lo que esta detras, y el centro no es una
     excepcion -- las areas de abajo pasan por delante de el. */
  const dibujo = $derived.by(() => {
    const e = an.ejes;
    const porArea = new Map(grupos.map((g) => [g.area, g]));
    const lista = [];
    for (const s of an.salas || []) {
      const g = porArea.get(s.area);
      if (g) lista.push(vestir(s, g, e));
    }
    if (an.centro) {
      const g = grupos.find((x) => x.principal);
      if (g) lista.push({ ...vestir(an.centro, g, e), esCentro: true });
    }
    return lista.sort((a, b) => a.profundidad - b.profundidad);
  });

  /* Salas y muebles en UNA lista por profundidad. Dibujar todos los muebles
     antes que todas las salas era lo comodo y esta mal: una palmera de
     delante quedaria tapada por una oficina del fondo. */
  const escena = $derived.by(() => {
    /* `d` va tipado como any y es deliberado: aqui conviven dos formas
       distintas --una sala y un mueble-- y lo que las distingue es `k`, que
       el chequeo estatico no usa para estrechar la union. Tiparlas por
       separado obligaria a partir la lista, que es justo lo que no se puede
       hacer: el orden de pintado las necesita juntas. */
    const piezas = /** @type {{k:string, d:any, profundidad:number}[]} */ ([
      ...dibujo.map((d) => ({ k: 'sala', d, profundidad: d.profundidad })),
      ...exterior.map((x) => ({ k: 'mueble', d: x, profundidad: x.profundidad }))
    ]);
    return piezas.sort((a, b) => a.profundidad - b.profundidad);
  });

  /* LO QUE AMUEBLA EL EXTERIOR. Palmeras en los huecos del anillo y un par
     de bancos frente a la entrada. Es decoracion declarada: no dice nada de
     la operacion y por eso no cambia nunca ni se mueve -- si se moviera,
     competiria con lo unico que si significa algo, que es el movimiento
     atado a un evento. */
  const exterior = $derived.by(() => {
    const e = an.ejes, R = an.radio || 0;
    /* Misma razon que en `escena`: palmera y banco son dos formas distintas
       en una sola lista, y lo que las separa es `tipo`. */
    const piezas = /** @type {any[]} */ ((an.jardin || []).map((j) => ({
      tipo: 'palmera', clave: `pal-${j.semilla}`, u: j.u, v: j.v,
      /* Un puesto mide 100 y quien lo ocupa ronda 30. A 62 + hojas la
         palmera salia mas alta que el puesto entero y tapaba el rotulo del
         area -- un adorno que tapa un dato esta al reves. */
      alto: 34 + (j.semilla % 3) * 6,
      pos: iso(j.u, j.v, 0, e), profundidad: j.u + j.v
    })));
    /* Dos bancos de espera delante del centro: el sitio donde de verdad
       estaria quien espera en una recepcion. */
    /* Los bancos van en el HUECO ENTRE DUCTOS, no a una coordenada fija.
       Puestos a mano quedaban encima de un pasillo --un banco plantado en
       mitad del corredor-- y ademas cualquier coordenada fija deja de valer
       en cuanto cambia el numero de areas. El hueco ya esta calculado: es el
       mismo angulo medio donde van las palmeras, a menos radio. */
    const huecos = an.jardin || [];
    for (const k of [0, 2]) {
      const h = huecos[k % Math.max(1, huecos.length)];
      if (!h) continue;
      const rr = R * 0.34, w = 56, d = 21, z = 13;
      const u = rr * Math.cos(h.angulo) - w / 2, v = rr * Math.sin(h.angulo);
      piezas.push({
        tipo: 'banco', clave: `ban-${k}`, profundidad: u + v,
        asiento: poli(e, [u,v,z], [u+w,v,z], [u+w,v+d,z], [u,v+d,z]),
        frente:  poli(e, [u,v+d,0], [u+w,v+d,0], [u+w,v+d,z], [u,v+d,z]),
        canto:   poli(e, [u+w,v,z], [u+w,v+d,z], [u+w,v+d,0], [u+w,v,0]),
        respaldo: poli(e, [u,v,z], [u+w,v,z], [u+w,v,z+22], [u,v,z+22])
      });
    }
    return piezas;
  });

  /** Los pasillos radiales: del centro a cada area. Estructura, no trafico. */
  const vias = $derived.by(() => {
    const e = an.ejes;
    return (an.radios || []).map((r) => ({
      area: r.area,
      poligono: r.esquinas.map((q) => iso(q[0], q[1], 0, e).join(',')).join(' '),
      desde: iso(r.eje.desde[0], r.eje.desde[1], 0, e),
      hasta: iso(r.eje.hasta[0], r.eje.hasta[1], 0, e)
    }));
  });

  /** El suelo del edificio: un rombo que abarca el anillo entero. */
  const piso = $derived.by(() => {
    const R = an.radio;
    if (!R) return null;
    const m = R * 1.42;
    return poli(an.ejes, [-m,-m,0], [m,-m,0], [m,m,0], [-m,m,0]);
  });

  $effect(() => {
    if (!envoltura) return;
    /* Se mide AL MONTAR y ademas se observa: el ResizeObserver no garantiza
       una primera entrega, y sin la lectura inicial el lienzo se queda en
       0x0 y no se dibuja nada aunque los elementos SI esten en el DOM. */
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

  const encuadre = $derived.by(() => {
    const esc = an.escala || 1;
    const anchoTotal = an.ancho * esc;
    const altoTotal = (an.alto + MARGEN_SUP + MARGEN_INF) * esc;
    return {
      // al centrado se le suma el corrimiento propio del anillo, que es lo
      // que lleva el dibujo al origen
      dx: (caja.ancho - anchoTotal) / 2 + (an.dx || 0) * esc,
      dy: (caja.alto - altoTotal) / 2 + MARGEN_SUP * esc + (an.dy || 0) * esc,
      esc
    };
  });

  /* ------------------------------------------------------------ LA CAMARA
     Igual que en la planta en uso: el encaje automatico se recalcula con
     cada foto y la camara se aplica ENCIMA, asi quien se acerco a un puesto
     sigue mirando ese puesto despues del repintado. */
  let vista = $state({ k: 1, x: 0, y: 0 });
  const MIN_K = 0.6, MAX_K = 5;
  const enSuSitio = $derived(vista.k === 1 && vista.x === 0 && vista.y === 0);

  function acercar(factor, cx, cy) {
    const k = Math.max(MIN_K, Math.min(MAX_K, vista.k * factor));
    if (k === vista.k) return;
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
    /* NO se captura el puntero aqui: con `setPointerCapture` activa el
       `click` se dispara en el DIV y no en el <g> del puesto, y abrir la
       ficha deja de funcionar sin dar ningun error. Se captura mas abajo,
       solo cuando el gesto resulta ser un arrastre de verdad. */
    arrastre = { x: ev.clientX, y: ev.clientY, vx: vista.x, vy: vista.y, movido: 0, capturado: false };
  }
  function alMover(ev) {
    if (!arrastre) return;
    const dx = ev.clientX - arrastre.x, dy = ev.clientY - arrastre.y;
    arrastre.movido = Math.max(arrastre.movido, Math.abs(dx) + Math.abs(dy));
    if (arrastre.movido < UMBRAL) return;
    if (!arrastre.capturado) {
      arrastre.capturado = true;
      try { ev.currentTarget.setPointerCapture(ev.pointerId); } catch { /* sin captura */ }
    }
    vista = { ...vista, x: arrastre.vx + dx, y: arrastre.vy + dy };
  }
  let ultimoGesto = $state(0);
  function alSoltarGesto() { ultimoGesto = arrastre ? arrastre.movido : 0; arrastre = null; }
  function seleccionar(a) { if (ultimoGesto < UMBRAL) alSeleccionar(a); }
  function ajustar() { vista = { k: 1, x: 0, y: 0 }; }
  function botonZoom(f) {
    const c = envoltura?.getBoundingClientRect();
    if (c) acercar(f, c.width / 2, c.height / 2);
  }

  /* -------------------------------------------------- QUIEN VA POR EL PASILLO
     Alguien recorre el pasillo de un area cuando el motor conto un evento de
     un agente de esa area. NO hay figurantes dando vueltas: si en una
     ventana no paso nada, los pasillos estan vacios, y que esten vacios ES
     la informacion. Es la misma linea que ya rige la capa de actividad --dar
     a entender que la operacion esta viva, sin fingir que lo esta--.
     Lo que el paseo NO dice es que el caso venga de recepcion: el destino de
     cada derivacion vive en tool_calls.parametros y no sale en el payload.
     Dice "en esa area pasó algo", que es lo que si esta medido. */
  const areaDe = $derived.by(() => {
    /** @type {Record<string,string>} */
    const m = {};
    for (const g of grupos) for (const a of g.miembros) m[a.nombre] = g.area;
    return m;
  });

  let caminantes = $state(/** @type {any[]} */ ([]));
  let vistos = [];
  let relojes = [];
  onDestroy(() => relojes.forEach(clearTimeout));

  const POR_LECTURA = 3, PASEO_MS = 3000;
  $effect(() => {
    const ahora = panorama?.eventos || [];
    const nuevos = eventosNuevos(vistos, ahora);
    vistos = ahora;
    if (!nuevos.length) return;
    // untrack: `vias` y `areaDe` son derivados de este mismo arbol, y leerlos
    // aqui haria que el efecto se dispare a si mismo en cada repintado.
    const porArea = new Map(untrack(() => vias).map((v) => [v.area, v]));
    const mapa = untrack(() => areaDe);
    nuevos.slice(0, POR_LECTURA).forEach((ev, i) => {
      const via = porArea.get(mapa[ev.agente]);
      if (!via) return;
      const id = `${Date.now()}-${i}`;
      const t = setTimeout(() => {
        caminantes = [...caminantes, { id, via }];
        relojes.push(setTimeout(() => {
          caminantes = caminantes.filter((c) => c.id !== id);
        }, PASEO_MS));
      }, i * 1400);
      relojes.push(t);
    });
  });

  /* ------------------------------------------------------------- LA FICHA
     UNA a la vez, y solo la del puesto que se esta mirando. La referencia
     las dibuja todas abiertas, y eso en una ilustracion no molesta: en esta
     pantalla --1366x675 medidos, con oficinas de 310x193-- siete fichas
     taparian una quinta parte del lienzo, y justo encima de las oficinas. */
  let mirando = $state(/** @type {any} */ (null));
  const FW = 250, FH = 128;
  const ficha = $derived.by(() => {
    if (!mirando) return null;
    const a = mirando.agente, p = mirando.pos;
    /* La ficha se situa en COORDENADAS DE PANTALLA, no de planta. Dos cosas
       salen de ahi, y las dos hacen falta:
       - se puede voltear cuando no cabe. Anclada siempre arriba a la derecha
         se salia del lienzo en las oficinas del borde, y media ficha fuera
         no se lee.
       - no se deforma con el zoom: se lee igual de cerca que de lejos, que
         es lo que se espera de una etiqueta y no de un mueble. */
    const k = vista.k, esc = encuadre.esc;
    const px = vista.x + k * (encuadre.dx + esc * p[0]);
    const py = vista.y + k * (encuadre.dy + esc * p[1]);
    const M = 10;
    let x = px + 30, y = py - FH - 46;
    if (x + FW > caja.ancho - M) x = px - FW - 30;
    x = Math.max(M, Math.min(x, caja.ancho - FW - M));
    if (y < M) y = py + 46;
    y = Math.max(M, Math.min(y, caja.alto - FH - M));
    return {
      agente: a, x, y,
      color: colorDe(a.estado), rotulo: rotuloDe(a.estado),
      filas: [
        ['Conversaciones', a.conversaciones ?? 0, false],
        ['Esperan a una persona', a.esperando_humano ?? 0, (a.esperando_humano ?? 0) > 0],
        ['Herramienta', a.ultima_herramienta || '—', false]
      ]
    };
  });
</script>

<div class="planta">
<div class="lienzo" bind:this={envoltura}
  onwheel={alaRueda} onpointerdown={alBajar} onpointermove={alMover}
  onpointerup={alSoltarGesto} onpointercancel={alSoltarGesto}
  onpointerleave={() => { alSoltarGesto(); mirando = null; }}
  role="presentation">
  <svg role="img" aria-label="Planta radial: el orquestador al centro y las areas alrededor"
    viewBox="0 0 {Math.max(1, caja.ancho)} {Math.max(1, caja.alto)}">
    <g transform="translate({vista.x}, {vista.y}) scale({vista.k}) translate({encuadre.dx}, {encuadre.dy}) scale({encuadre.esc})">
      {#if piso}
        <polygon points={piso} fill="#EDF1F6" stroke="#D8DFE8" stroke-width="1.5" />
      {/if}

      <!-- Los pasillos del centro a cada area. Dicen POR DONDE se deriva, no
           cuanto: el cuanto no esta en el payload. -->
      {#each vias as v (v.area)}
        <polygon points={v.poligono} fill="#FAFCFE" />
      {/each}

      {#each caminantes as c (c.id)}
        <g class="andando" aria-hidden="true"
          style="--x0:{c.via.desde[0]}px; --y0:{c.via.desde[1]}px;
                 --x1:{c.via.hasta[0]}px; --y1:{c.via.hasta[1]}px; --dur:{PASEO_MS}ms">
          <g class="paso">
            <ellipse cx="0" cy="3" rx="9" ry="4" fill="#0F172A" opacity=".14" />
            <rect x="-5.5" y="-23" width="11" height="18" rx="5" fill="#7C8AA0" />
            <circle cx="0" cy="-26" r="5.6" fill="#E3B594" />
            <path d="M -5.6 -28 a 5.6 5.6 0 0 1 11.2 0 Z" fill="#3F3A46" />
          </g>
        </g>
      {/each}

      <!-- Salas y muebles en la MISMA pasada, ordenados por profundidad: lo
           que esta delante tapa a lo que esta detras, y un macetero no es
           una excepcion. -->
      {#each escena as it (it.d.clave)}
        {#if it.k === 'sala'}
          <g class="sala" class:centro={it.d.esCentro}>
            <!-- El suelo va en DOS capas. La de abajo es opaca y existe para
                 tapar el extremo del pasillo que se mete bajo la sala: con una
                 sola capa translucida el ducto se transparentaba y se veia
                 cruzar por dentro de la oficina. -->
            <polygon points={it.d.suelo} fill="#F7F9FC" />
            <polygon points={it.d.suelo} fill={it.d.color} fill-opacity=".13"
              stroke={it.d.color} stroke-width="1.4" stroke-opacity=".45" />
            <polygon points={it.d.fondo} fill={tono(it.d.color, 0.42)} />
            <polygon points={it.d.izq} fill={tono(it.d.color, 0.28)} />
            <polygon points={it.d.cantoFondo} fill={tono(it.d.color, 0.60)} />
            <polygon points={it.d.cantoIzq} fill={tono(it.d.color, 0.52)} />

            <polygon points={it.d.puertaMarco} fill={tono(it.d.color, -0.18)} />
            <polygon points={it.d.puerta} fill="#F7F9FC" />
            {#each it.d.cuadros as c, ci (ci)}
              <polygon points={c} fill="#FFFFFF" fill-opacity=".82"
                stroke={tono(it.d.color, -0.1)} stroke-width="1" />
            {/each}

            <polygon points={it.d.archivador.frente} fill="#C6CEDA" />
            <polygon points={it.d.archivador.canto} fill="#B3BDCB" />
            <polygon points={it.d.archivador.tapa} fill="#DCE3EC" stroke="#AAB6C6" stroke-width="1" />
            <polygon points={it.d.archivador.tirador} fill="#8E9AAB" />

            <!-- el numero de oficina, grande, en la pared del fondo -->
            <g transform="matrix({it.d.numero.matriz})">
              <text x="0" y="0" font-size={it.d.numero.cuerpo} font-weight="800"
                font-family="ui-monospace, monospace" fill={tono(it.d.color, -0.25)}
                opacity=".85">{String(it.d.miembros[0]?.numero ?? 1).padStart(2, '0')}</text>
            </g>

            <!-- el nombre del area, pintado en su propio suelo -->
            {#if !it.d.repiteNombre}
            <g transform="matrix({it.d.sueloTexto.matriz} {it.d.sueloTexto.centro[0]} {it.d.sueloTexto.centro[1]})">
              <text x="0" y="0" text-anchor="middle" fill={tono(it.d.color, -0.4)}
                font-size={it.d.sueloTexto.cuerpo} font-weight="800"
                letter-spacing={it.d.sueloTexto.cuerpo * 0.1} opacity=".8">
                {it.d.area.toUpperCase()}
              </text>
            </g>
            {/if}

            {#each it.d.miembros as m (m.agente.nombre)}
              <g class="celda" class:apagado={!pasa(m.agente)}
               transform="translate({m.pos[0]}, {m.pos[1]})"
                 onpointerenter={() => (mirando = m)}
                 role="presentation">
                <PuestoAgente
                  agente={m.agente} numero={m.numero} lado={LADO} {entrada}
                  ejes={an.ejes} cambio={delta[m.agente.nombre]}
                  enSala={true} serie={true}
                  alSeleccionar={seleccionar} />
              </g>
            {/each}
          </g>
        {:else if it.d.tipo === 'palmera'}
          <!-- Una palmera en el hueco entre dos oficinas. Decoracion
               declarada: no cambia nunca y no se mueve. -->
          <g transform="translate({it.d.pos[0]}, {it.d.pos[1]})" aria-hidden="true">
            <ellipse cx="0" cy="0" rx="18" ry="8" fill="#0F172A" opacity=".10" />
            <path d="M -11 -3 L 11 -3 L 8 -22 L -8 -22 Z" fill="#C08B6A" />
            <ellipse cx="0" cy="-22" rx="8" ry="3.4" fill="#D9A585" />
            <path d="M 0 -22 q -5 {-it.d.alto * 0.5} 2 {-it.d.alto}"
              stroke="#8A6B4A" stroke-width="4.5" fill="none" stroke-linecap="round" />
            {#each [-72, -34, 0, 34, 72, 128] as gr (gr)}
              <path d="M 0 0 q 16 -13 34 -6 q -16 3 -34 6 Z" fill="#3F8C6B"
                fill-opacity={gr === 0 ? 0.95 : 0.82}
                transform="translate(2, {-it.d.alto}) rotate({gr})" />
            {/each}
            <circle cx="2" cy={-it.d.alto} r="3.2" fill="#2F6E52" />
          </g>
        {:else}
          <!-- Un banco de espera frente a la entrada. -->
          <g aria-hidden="true">
            <polygon points={it.d.frente} fill="#B9C3D1" />
            <polygon points={it.d.canto} fill="#A8B3C3" />
            <polygon points={it.d.asiento} fill="#DCE3EC" stroke="#AAB6C6" stroke-width="1" />
            <polygon points={it.d.respaldo} fill="#C8D2DE" stroke="#AAB6C6" stroke-width="1" />
          </g>
        {/if}
      {/each}

    </g>

    <!-- LA FICHA, una sola y la del puesto que se mira, POR ENCIMA de la
         escena y fuera de su transformacion. La referencia dibuja las siete
         abiertas a la vez; medido en esta pantalla --1366x675, oficinas de
         310x193-- eso taparia una quinta parte del lienzo, y justo encima de
         las oficinas. -->
    {#if ficha}
      <g class="ficha" transform="translate({ficha.x}, {ficha.y})" aria-hidden="true">
        <rect x="0" y="0" width={FW} height={FH} rx="10"
          fill="#FFFFFF" stroke="#D9E0EA" stroke-width="1.5" />
        <rect x="0" y="0" width="6" height={FH} rx="3" fill={ficha.color} />
        <text x="18" y="27" font-size="15" font-weight="800" fill="#0F172A">
          {String(ficha.agente.nombre).replaceAll('_', ' ')}
        </text>
        <rect x="18" y="36" width={ficha.rotulo.length * 7.2 + 18} height="20" rx="10"
          fill={ficha.color} fill-opacity=".14" />
        <text x={27} y="50" font-size="11.5" font-weight="700" fill={tono(ficha.color, -0.25)}>
          {ficha.rotulo}
        </text>
        {#each ficha.filas as f, i (f[0])}
          <text x="18" y={78 + i * 19} font-size="12" fill="#64748B">{f[0]}</text>
          <text x={FW - 18} y={78 + i * 19} text-anchor="end" font-size="12.5" font-weight="700"
            fill={f[2] ? '#6D28D9' : '#0F172A'}>{f[1]}</text>
        {/each}
      </g>
    {/if}
  </svg>

  <div class="mandos">
    <button type="button" onclick={() => botonZoom(1 / 1.25)} aria-label="Alejar">−</button>
    <button type="button" onclick={() => botonZoom(1.25)} aria-label="Acercar">+</button>
    <button type="button" onclick={ajustar} disabled={enSuSitio}>Ajustar</button>
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

<!-- La salud de los sistemas externos va AQUI, al pie de la planta, y no en
     otra columna: cuando uno se cae, el efecto son varios puestos en rojo, y
     tener la causa lejos obliga a cruzar la pantalla para unir las dos. -->
<SistemasExternos servicios={panorama?.servicios || []} {ms} />

<div class="pieplanta">
  {#if !entrada}
    <!-- Se dice que falta en vez de adivinarlo: deducir la puerta de entrada
         del "primer rol orientado al cliente" es el error que dejo a un
         suscriptor sin internet hablando con el agente comercial. -->
    <span class="falta" title="El motor no envió rol_de_entrada para este tenant">
      Sin recepción declarada
    </span>
  {/if}
  {#each zonasPresentes as z (z)}
    <span class="zona"><i style="background:{ZONAS[z].color}"></i>{ZONAS[z].rotulo}</span>
  {/each}
  <span class="sep"></span>
  {#each areasPresentes.filter((a) => a !== areaPrincipal) as a (a)}
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
  .planta { position: relative; width: 100%; height: 100%; min-height: 320px;
            display: flex; flex-direction: column; }
  .lienzo { position: relative; flex: 1; min-height: 0; touch-action: none; cursor: grab; overflow: hidden; }
  .lienzo:active { cursor: grabbing; }
  svg { width: 100%; height: 100%; display: block; }
  /* El filtro ATENUA en vez de esconder: la planta no cambia de forma, asi
     que no hay que volver a ubicarse en cada filtro. */
  .celda { cursor: pointer; transition: opacity .2s ease; }
  .celda.apagado { opacity: .14; pointer-events: none; }

  .filtros { flex: 0 0 auto; display: flex; gap: 6px; flex-wrap: wrap; padding: 6px 2px 0; }
  .filtros button {
    font: inherit; font-size: 11.5px; font-weight: 600; line-height: 1;
    padding: 5px 10px; border: 1px solid #D9E0EA; border-radius: 999px;
    background: #fff; color: #475569; cursor: pointer;
  }
  .filtros button.activo { background: #0F172A; color: #fff; border-color: #0F172A; }
  .filtros button:disabled { opacity: .45; cursor: default; }
  .filtros .n { margin-left: 6px; opacity: .7; font-variant-numeric: tabular-nums; }

  .pieplanta {
    flex: 0 0 auto; display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
    padding: 6px 4px 0;
  }
  .sep { width: 1px; align-self: stretch; background: #DCE3EC; }
  .crece { flex: 1; }
  .zona, .frescura, .falta {
    display: flex; align-items: center; gap: 5px;
    font-size: 10.5px; letter-spacing: .04em; text-transform: uppercase; color: #64748B;
  }
  .zona i { width: 9px; height: 9px; border-radius: 2px; display: inline-block; }
  .falta { color: #B45309; font-weight: 700; }
  /* El paseo dura menos que el intervalo entre lecturas: si no, el
     repintado lo cortaria por la mitad. */
  @keyframes andar {
    from { transform: translate(var(--x0), var(--y0)); }
    to   { transform: translate(var(--x1), var(--y1)); }
  }
  @keyframes pisar {
    0%, 100% { transform: translateY(0) scaleY(1); }
    50%      { transform: translateY(-1.5px) scaleY(1.035); }
  }
  .andando { animation: andar var(--dur) linear forwards; pointer-events: none; }
  .andando .paso { animation: pisar 460ms ease-in-out infinite; }

  /* Quien pidio menos movimiento no recibe ninguno. La informacion sigue en
     las cifras y en la ficha, que no se mueven. */
  @media (prefers-reduced-motion: reduce) {
    .andando, .andando .paso { animation: none; }
    .andando { display: none; }
  }

  .ficha { pointer-events: none; filter: drop-shadow(0 6px 16px rgba(15, 23, 42, .18)); }
  .mandos { position: absolute; right: 10px; bottom: 10px; display: flex; gap: 6px; }
  .mandos button {
    font: inherit; font-size: 12px; padding: 4px 10px; border-radius: 7px;
    border: 1px solid #D9E0EA; background: #fff; color: #334155; cursor: pointer;
  }
  .mandos button:disabled { opacity: .45; cursor: default; }
</style>
