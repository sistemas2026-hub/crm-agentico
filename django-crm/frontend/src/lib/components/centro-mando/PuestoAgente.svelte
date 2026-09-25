<script>
  /**
   * Un puesto de trabajo de la planta: piso, tabiques, escritorio, monitores,
   * teclado, la persona sentada y el rotulo colgado de la pared.
   *
   * POR QUE ESTE COMPONENTE EXISTE, Y NO SE DIBUJA TODO EN LA PLANTA
   * Por la animacion. La planta se repinta cada 12 segundos con datos nuevos
   * (sondeo -- ver lib/centro-mando/eventos.js), y si el SVG se recreara
   * entero en cada refresco no habria nada que animar: no se puede hacer
   * transicionar un elemento que se destruye. Al ser un componente con clave
   * --{#each agentes as a (a.nombre)}-- Svelte lo CONSERVA entre refrescos y
   * solo cambia los atributos que cambiaron, que es justo lo que las
   * transiciones de CSS necesitan.
   *
   * QUE SE ANIMA Y QUE NO
   * Lo que llega es una foto cada 12 s, no un flujo. Lo unico honesto de
   * animar es la DIFERENCIA entre dos fotos, y eso es lo que se hace:
   *   - el color de estado vira en vez de saltar
   *   - la carga cuenta de un numero al otro
   *   - un puesto que ENTRA en alarma da un destello, una sola vez
   * No hay movimiento perpetuo -- nadie teclea, ninguna luz titila. En un
   * tablero de operacion el movimiento es senal: si algo se mueve siempre,
   * deja de significar.
   */
  import { colorDe, rotuloDe, pulsaEn } from '$lib/centro-mando/estados.js';
  import {
    iso, poli, ZONAS, zonaDe, semillaDe, tomaDe, tono,
    cuerpoQueCabe, recortar, COLORES_AGENTE
  } from '$lib/centro-mando/planta.js';

  /** @type {{ agente: any, numero: number, lado: number, entrada: string|null,
   *           ejes: {ex:number,ey:number}, cambio?: any, ahora?: Date,
   *           alSeleccionar?: (a:any)=>void }} */
  let {
    agente, numero, lado: L, entrada, ejes: e,
    cambio = null, ahora = new Date(), alSeleccionar = () => {}
  } = $props();

  const zona = $derived(zonaDe(agente, entrada));
  const esRecep = $derived(zona === 'recepcion');
  const color = $derived(colorDe(agente.estado));
  /* 'esperando_humano' NO es un estado -- lo dice el motor: se probo como
     estado y tapaba lo demas. Es una cifra aparte, y manda sobre el aspecto
     del puesto entero porque es lo unico que hace que alguien se levante. */
  const llaman = $derived((agente.esperando_humano || 0) + (agente.esperando_aprobacion || 0));

  const semilla = $derived(semillaDe(agente.nombre));
  const colorAgente = $derived(esRecep ? '#7C5BAF' : tomaDe(semilla, 23, COLORES_AGENTE));
  const piel = $derived(tomaDe(semilla, 0, ['#C9906A', '#E0B48C', '#8D5C3D', '#F0C9A6', '#A56F4A', '#6E4630']));
  const pelo = $derived(tomaDe(semilla, 5, ['#2B2118', '#4A3524', '#12100E', '#6B4A2F', '#8A6B45', '#57381F']));
  /* Ropa de oficina, apagada a proposito: saturada competiria con los colores
     de estado, que son los que tienen que ganar en un tablero. */
  const ropa = $derived(tomaDe(semilla, 11, ['#4F6D9A', '#7A5C8E', '#B26A4C', '#3F8C7C', '#5B6B7C', '#9E4F6B', '#6B8E4E', '#8C6239']));
  const peinado = $derived((semilla >>> 17) % 6);

  /* --- ANTIGUEDAD -----------------------------------------------------
     Un agente que termino hace 20 segundos y uno que no toca nada hace tres
     horas se veian identicos. El puesto se apaga con el tiempo, nunca por
     debajo de .55 -- mas abajo dejaria de leerse, que seria cambiar un
     problema por otro. */
  const frescura = $derived.by(() => {
    if (!agente.ultima_actividad) return 0.62;
    const min = (ahora.getTime() - new Date(agente.ultima_actividad).getTime()) / 60000;
    return min <= 10 ? 1 : Math.max(0.55, 1 - (min - 10) / 240);
  });

  /* --- LA CIFRA QUE CUENTA --------------------------------------------
     Ver "8 → 12" dice algo que "12" no dice: hacia donde va. Solo cuenta
     cuando hubo foto previa; la primera pintada muestra el valor y ya. */
  // Arranca en 0 y el efecto de abajo pone el valor en la primera pasada:
  // leer la prop aqui captura solo su valor inicial y deja de seguirla.
  let mostrada = $state(0);
  let animando = null;
  $effect(() => {
    const destino = agente.conversaciones || 0;
    const desde = cambio && cambio.cargaPrevia != null ? cambio.cargaPrevia : destino;
    if (desde === destino) { mostrada = destino; return; }
    if (animando) cancelAnimationFrame(animando);
    // 600 ms: se ve el recorrido y termina mucho antes de la proxima foto.
    const t0 = performance.now(), dur = 600;
    const paso = (t) => {
      const p = Math.min(1, (t - t0) / dur);
      mostrada = Math.round(desde + (destino - desde) * (1 - Math.pow(1 - p, 3)));
      if (p < 1) animando = requestAnimationFrame(paso);
    };
    animando = requestAnimationFrame(paso);
    return () => { if (animando) cancelAnimationFrame(animando); };
  });

  /* --- EL DESTELLO AL ENTRAR EN ALARMA --------------------------------
     Una sola vez, al entrar. Seguir en alarma no dispara nada: un destello
     que se repite cada 12 segundos deja de avisar y pasa a ser ruido. */
  let destella = $state(false);
  $effect(() => {
    if (cambio && (cambio.entroEnAlarma || cambio.empezoAEsperar)) {
      destella = true;
      const t = setTimeout(() => (destella = false), 1400);
      return () => clearTimeout(t);
    }
  });

  // --- geometria del puesto, toda derivada del lado ---
  const H = $derived(L * 0.34);
  const ex0 = $derived(L * 0.11), ey0 = $derived(L * 0.12);
  const ew = $derived(L * 0.78), eh = $derived(L * 0.34), ez = $derived(L * 0.17);
  const u = $derived(L / 100);

  const p = (x, y, z = 0) => iso(x, y, z, e);
  const anchoC = $derived(L * 0.98);
  const altoC = $derived(L * 0.21);
  const za = $derived(H + L * 0.16);
  const xa = $derived((L - anchoC) / 2);

  const nombreArea = $derived(String(agente.area || agente.nombre).toUpperCase());
  const zonaX = $derived(L * 0.22);
  const zonaW = $derived(anchoC - L * 0.22 - L * 0.20);
  const cuerpoNombre = $derived(cuerpoQueCabe(nombreArea, zonaW, L * 0.072, L * 0.036));

  // Medidas del mobiliario. Viven aqui y no en el marcado porque son
  // calculo -- y porque {@const} suelto entre etiquetas no compila.
  const tecX = $derived(ex0 + ew * 0.20);
  const tecY = $derived(ey0 + eh * 0.60);
  const tecW = $derived(ew * 0.46);
  const tecD = $derived(eh * 0.26);
  const rat = $derived(p(tecX + tecW + ew * 0.08, tecY + tecD * 0.42, ez));
  const tz = $derived(p(ex0 + ew * 0.90, ey0 + eh * 0.34, ez));
  const mc = $derived(p(L * 0.90, L * 0.86, 0));
  const puerta = $derived(p(L * 0.5, L * 1.04, L * 0.10));
  const mon = $derived([ex0 + ew * 0.09, ex0 + ew * 0.52]);
  const mw = $derived(ew * 0.38);
  const mh = $derived(L * 0.165);

  // La persona, y su cabeza
  const base = $derived(p(ex0 + ew * 0.5, ey0 + eh + L * 0.21, 0));
  const bx = $derived(base[0]);
  const by = $derived(base[1]);
  const cabY = $derived(by - 37.5 * u);
  const rc = $derived(6.2 * u);

  // La chapa de "esperan", en coordenadas del rotulo
  const chW = $derived(L * 0.26);
  const chH = $derived(L * 0.145);
  const chX = $derived(anchoC - chW);
  const chY = $derived(-chH - L * 0.05);
  const icX = $derived(chX + chW - chH * 0.46);
  const icY = $derived(chY + chH * 0.5);

  const titulo = $derived(
    `${String(agente.nombre).replaceAll('_', ' ')} — ${rotuloDe(agente.estado)}`
    + (agente.haciendo ? ` · ${agente.haciendo}` : '')
    + (llaman ? ` · ${llaman} esperan a una persona` : '')
    + (esRecep ? ' · PUERTA DE ENTRADA' : '')
  );
</script>

<!-- svelte-ignore a11y_click_events_have_key_events -->
<g
  class="puesto"
  class:destella
  class:llamando={llaman > 0}
  role="button"
  tabindex="0"
  opacity={frescura.toFixed(3)}
  onclick={() => alSeleccionar(agente)}
  onkeydown={(ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); alSeleccionar(agente); } }}
>
  <title>{titulo}</title>

  <!-- halo: permanente cuando llaman a una persona -->
  <polygon
    class="halo" points={poli(e, [-4,-4,0], [L+4,-4,0], [L+4,L+4,0], [-4,L+4,0])}
    fill={color} fill-opacity=".10" stroke={color} stroke-width="1.5"
  />

  <!-- piso, con la franja de su zona -->
  <polygon points={poli(e, [0,0,0], [L,0,0], [L,L,0], [0,L,0])}
    fill={llaman ? '#FBF7FF' : '#FCFDFE'} stroke="#C9D1DC" stroke-width="1" />
  <polygon class="tenido" points={poli(e, [0,L,0], [L,L,0], [L,L-3,0], [0,L-3,0])}
    fill={color} fill-opacity=".55" />
  <polygon points={poli(e, [L,0,0], [L,L,0], [L-3,L,0], [L-3,0,0])} fill={ZONAS[zona].color} />
  <polygon points={poli(e, [L*0.18,L*0.50,0], [L*0.82,L*0.50,0], [L*0.82,L*0.92,0], [L*0.18,L*0.92,0])}
    fill={ZONAS[zona].color} fill-opacity=".16" />

  <!-- tabiques: la pared lleva el color del AGENTE, que no cambia nunca -->
  <polygon points={poli(e, [0,0,0], [L,0,0], [L,0,H], [0,0,H])} fill={tono(colorAgente, 0.52)} />
  <polygon points={poli(e, [0,0,0], [0,L,0], [0,L,H], [0,0,H])} fill={tono(colorAgente, 0.38)} />
  <polygon points={poli(e, [0,0,H], [L,0,H], [L,-2.5,H], [0,-2.5,H])} fill={tono(colorAgente, 0.66)} />
  <polygon points={poli(e, [0,0,H], [0,L,H], [-2.5,L,H], [-2.5,0,H])} fill={tono(colorAgente, 0.58)} />
  <polygon points={poli(e, [L*0.62,0.6,H*0.72], [L*0.86,0.6,H*0.72], [L*0.86,0.6,H*0.28], [L*0.62,0.6,H*0.28])}
    fill="#FFFFFF" fill-opacity=".72" />

  <!-- escritorio -->
  <polygon points={poli(e, [ex0+L*0.04, ey0+eh*0.72, 0], [ex0+L*0.075, ey0+eh*0.72, 0],
    [ex0+L*0.075, ey0+eh*0.72, ez*0.82], [ex0+L*0.04, ey0+eh*0.72, ez*0.82])} fill="#AAB4C2" />
  <polygon points={poli(e, [ex0+ew-L*0.075, ey0+eh*0.72, 0], [ex0+ew-L*0.04, ey0+eh*0.72, 0],
    [ex0+ew-L*0.04, ey0+eh*0.72, ez*0.82], [ex0+ew-L*0.075, ey0+eh*0.72, ez*0.82])} fill="#AAB4C2" />
  <polygon points={poli(e, [ex0,ey0+eh,0],[ex0+ew,ey0+eh,0],[ex0+ew,ey0+eh,ez],[ex0,ey0+eh,ez])} fill="#D3DBE5" />
  <polygon points={poli(e, [ex0,ey0,0],[ex0,ey0+eh,0],[ex0,ey0+eh,ez],[ex0,ey0,ez])} fill="#BFC9D6" />
  <polygon points={poli(e, [ex0,ey0,ez],[ex0+ew,ey0,ez],[ex0+ew,ey0+eh,ez],[ex0,ey0+eh,ez])}
    fill="#E9EEF4" stroke="#AEB9C8" stroke-width="0.8" />

  <!-- monitores: la pantalla lleva el estado, y vira en vez de saltar -->
  {#each mon as mx (mx)}
    <polygon points={poli(e, [mx+mw*0.42, ey0+eh*0.3, ez], [mx+mw*0.58, ey0+eh*0.3, ez],
      [mx+mw*0.58, ey0+eh*0.3, ez+mh*0.18], [mx+mw*0.42, ey0+eh*0.3, ez+mh*0.18])} fill="#B6BFCC" />
    <polygon class="tenido" class:pulsa={pulsaEn(agente.estado)}
      points={poli(e, [mx, ey0+eh*0.22, ez+mh*0.16], [mx+mw, ey0+eh*0.22, ez+mh*0.16],
        [mx+mw, ey0+eh*0.30, ez+mh], [mx, ey0+eh*0.30, ez+mh])}
      fill={color} fill-opacity=".82" />
    <polygon points={poli(e, [mx, ey0+eh*0.22, ez+mh*0.16], [mx+mw, ey0+eh*0.22, ez+mh*0.16],
      [mx+mw, ey0+eh*0.30, ez+mh], [mx, ey0+eh*0.30, ez+mh])}
      fill="none" stroke="#334155" stroke-width="1.1" />
  {/each}

  <!-- teclado y raton: lo que convierte una mesa con pantallas en un puesto -->
  <polygon points={poli(e, [tecX,tecY,ez], [tecX+tecW,tecY,ez], [tecX+tecW,tecY+tecD,ez], [tecX,tecY+tecD,ez])}
    fill="#F4F7FA" stroke="#9AA6B6" stroke-width={L * 0.008} />
  {#each [1, 2, 3] as k (k)}
    {@const a = p(tecX + tecW * 0.06, tecY + (tecD * k) / 4, ez)}
    {@const b = p(tecX + tecW * 0.94, tecY + (tecD * k) / 4, ez)}
    <line x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} stroke="#B9C3D0" stroke-width={L * 0.011} stroke-linecap="round" />
  {/each}
  <ellipse cx={rat[0]} cy={rat[1]} rx={L * 0.032} ry={L * 0.022}
    fill="#F4F7FA" stroke="#9AA6B6" stroke-width={L * 0.008} transform="rotate(-30 {rat[0]} {rat[1]})" />

  <!-- taza: la pieza que hace que el puesto parezca ocupado por alguien -->
  <ellipse cx={tz[0]} cy={tz[1] + L * 0.022} rx={L * 0.028} ry={L * 0.014} fill="#CBD5E1" />
  <path d="M {tz[0]-L*0.026} {tz[1]+L*0.020} L {tz[0]-L*0.020} {tz[1]-L*0.016} L {tz[0]+L*0.020} {tz[1]-L*0.016} L {tz[0]+L*0.026} {tz[1]+L*0.020} Z"
    fill="#FFFFFF" stroke="#AEB9C8" stroke-width="0.8" />
  <ellipse cx={tz[0]} cy={tz[1] - L * 0.016} rx={L * 0.021} ry={L * 0.009} fill="#6B4A32" />

  <!-- planta en maceta -->
  <ellipse cx={mc[0]} cy={mc[1] + L*0.012} rx={L*0.05} ry={L*0.024} fill="#000" fill-opacity=".06" />
  {#each [[-0.035,-0.055,0.040], [0.033,-0.050,0.036], [0,-0.085,0.042], [-0.010,-0.030,0.034]] as h (h[0] + ':' + h[1])}
    <circle cx={mc[0] + L*h[0]} cy={mc[1] + L*h[1]} r={L*h[2]} fill="#5FA87C" />
  {/each}
  <path d="M {mc[0]-L*0.038} {mc[1]-L*0.014} L {mc[0]+L*0.038} {mc[1]-L*0.014} L {mc[0]+L*0.028} {mc[1]+L*0.018} L {mc[0]-L*0.028} {mc[1]+L*0.018} Z" fill="#C98A63" />

  <!-- LA PERSONA: sentada de espaldas, mirando su monitor.
       La ROPA la identifica; la SILLA lleva el estado. -->
  <ellipse cx={bx} cy={by} rx={13*u} ry={6.5*u} fill="#000" fill-opacity=".07" />
  <ellipse cx={bx} cy={by - 1*u} rx={9*u} ry={4.4*u} fill="#8E99A8" />
  <rect x={bx - 1.8*u} y={by - 13*u} width={3.6*u} height={12*u} fill="#9AA5B3" />
  <ellipse class="tenido" cx={bx} cy={by - 13.5*u} rx={11*u} ry={5.2*u} fill={color} />
  {#each [-1, 1] as lado (lado)}
    <path d="M {bx + lado*8.2*u} {by - 28*u} L {bx + lado*11.5*u} {by - 25*u} L {bx + lado*9.5*u} {by - 33.5*u} L {bx + lado*5.5*u} {by - 32*u} Z" fill={ropa} />
    <ellipse cx={bx + lado*8*u} cy={by - 34*u} rx={2.6*u} ry={2*u} fill={piel} />
  {/each}
  <path d="M {bx - 7.5*u} {by - 13*u} L {bx + 7.5*u} {by - 13*u} L {bx + 9*u} {by - 26*u} Q {bx + 9.5*u} {by - 30*u} {bx + 5*u} {by - 31*u} L {bx - 5*u} {by - 31*u} Q {bx - 9.5*u} {by - 30*u} {bx - 9*u} {by - 26*u} Z" fill={ropa} />
  <path d="M {bx - 4.6*u} {by - 30.6*u} L {bx + 4.6*u} {by - 30.6*u} L {bx + 3.2*u} {by - 28.4*u} L {bx - 3.2*u} {by - 28.4*u} Z" fill="#000" fill-opacity=".16" />
  <rect class="tenido" x={bx - 6.2*u} y={by - 22*u} width={12.4*u} height={9*u} rx={2.2*u} fill={color} fill-opacity=".92" />
  <rect x={bx - 6.2*u} y={by - 22*u} width={12.4*u} height={9*u} rx={2.2*u} fill="none" stroke="#000" stroke-opacity=".18" stroke-width={u} />
  <rect x={bx - 2.4*u} y={by - 34*u} width={4.8*u} height={4*u} fill={piel} />
  <circle cx={bx} cy={cabY} r={rc} fill={piel} />

  <!-- seis peinados, derivados del NOMBRE y no del azar -->
  {#if peinado === 0}
    <path d="M {bx-rc} {cabY} a {rc} {rc} 0 0 1 {2*rc} 0 q {-1.2*u} {2.2*u} {-rc} {2.2*u} q {-rc+1.2*u} 0 {-rc} {-2.2*u} Z" fill={pelo} />
  {:else if peinado === 1}
    <path d="M {bx-rc-0.8*u} {cabY-0.6*u} a {rc+0.8*u} {rc+0.8*u} 0 0 1 {2*(rc+0.8*u)} 0 L {bx+rc+0.8*u} {cabY+6.5*u} q {-1.6*u} {1.3*u} {-3.6*u} {0.3*u} L {bx+rc-1.8*u} {cabY+2.6*u} q {-rc+1.8*u} {1.9*u} {-2*(rc-1.8*u)} 0 L {bx-rc+1.8*u} {cabY+2.9*u} q {-2*u} {u} {-3.6*u} {-0.3*u} Z" fill={pelo} />
  {:else if peinado === 2}
    <path d="M {bx-rc} {cabY} a {rc} {rc} 0 0 1 {2*rc} 0 q {-1.2*u} {2.6*u} {-rc} {2.6*u} q {-rc+1.2*u} 0 {-rc} {-2.6*u} Z" fill={pelo} />
    <circle cx={bx} cy={cabY - rc - 1.4*u} r={3.3*u} fill={pelo} />
  {:else if peinado === 3}
    <path d="M {bx-rc} {cabY} a {rc} {rc} 0 0 1 {2*rc} 0 q {-1.2*u} {2.6*u} {-rc} {2.6*u} q {-rc+1.2*u} 0 {-rc} {-2.6*u} Z" fill={pelo} />
    <path d="M {bx-2*u} {cabY+1.2*u} q {-3.6*u} {4.8*u} {-1.2*u} {8.8*u} q {2.6*u} {1.7*u} {4.8*u} {-0.6*u} q {-1.8*u} {-3.8*u} {0.4*u} {-7.9*u} Z" fill={pelo} />
  {:else if peinado === 4}
    <circle cx={bx} cy={cabY - 0.9*u} r={rc + 2.5*u} fill={pelo} />
    <circle cx={bx - 4.6*u} cy={cabY - 3.8*u} r={3.5*u} fill={pelo} />
    <circle cx={bx + 4.6*u} cy={cabY - 3.8*u} r={3.5*u} fill={pelo} />
    <circle cx={bx} cy={cabY + 2.8*u} r={4.7*u} fill={piel} />
  {:else}
    <path d="M {bx-rc} {cabY} a {rc} {rc} 0 0 1 {2*rc} 0 Z" fill={pelo} fill-opacity=".34" />
    <path d="M {bx-rc+0.5*u} {cabY-1.6*u} a {rc} {rc} 0 0 1 {2*(rc-0.5*u)} 0 Z" fill={pelo} fill-opacity=".9" />
  {/if}

  <!-- mostrador y puerta: solo la recepcion, que es por donde entra todo -->
  {#if esRecep}
    <polygon points={poli(e, [L*0.14,L*0.72,0],[L*0.86,L*0.72,0],[L*0.86,L*0.72,L*0.26],[L*0.14,L*0.72,L*0.26])} fill="#DCCCF0" />
    <polygon points={poli(e, [L*0.14,L*0.62,L*0.26],[L*0.86,L*0.62,L*0.26],[L*0.86,L*0.72,L*0.26],[L*0.14,L*0.72,L*0.26])} fill="#EDE3FA" stroke="#B79AD8" stroke-width="0.8" />
    <path d="M {puerta[0]} {puerta[1]+L*0.16} L {puerta[0]-L*0.055} {puerta[1]+L*0.04} L {puerta[0]-L*0.022} {puerta[1]+L*0.04} L {puerta[0]-L*0.022} {puerta[1]-L*0.06} L {puerta[0]+L*0.022} {puerta[1]-L*0.06} L {puerta[0]+L*0.022} {puerta[1]+L*0.04} L {puerta[0]+L*0.055} {puerta[1]+L*0.04} Z"
      fill="#C8A2E8" />
  {/if}

  <!-- EL ROTULO, en el PLANO de la pared. La matriz es la del plano y=0:
       el eje horizontal se proyecta en (ex, ey) y el vertical en (0,1), asi
       que el texto baja siguiendo la perspectiva sin deformarse. -->
  <g transform="matrix({e.ex} {e.ey} 0 1 {xa * e.ex} {xa * e.ey - za})">
    <rect x="0" y="0" width={anchoC} height={altoC} rx={L * 0.028}
      fill="#FFFFFF" stroke={llaman ? '#6D28D9' : '#C9D1DC'} stroke-width={llaman ? 2 : 1} />
    <rect class="tenidoRelleno" x="0" y="0" width={L * 0.185} height={altoC} rx={L * 0.028} fill={colorAgente} />
    <rect class="tenidoRelleno" x={L * 0.12} y="0" width={L * 0.065} height={altoC} fill={colorAgente} />
    <text x={L * 0.0925} y={altoC * 0.66} text-anchor="middle" fill="#fff"
      font-family="ui-monospace, monospace" font-size={L * 0.098} font-weight="700">
      {esRecep ? '◆' : String(numero).padStart(2, '0')}
    </text>
    <text x={zonaX} y={altoC * 0.66} font-size={cuerpoNombre} font-weight="800" letter-spacing={L * 0.002} fill="#0F172A">
      {recortar(nombreArea, zonaW, cuerpoNombre)}
    </text>
    <text class="cifra" x={anchoC - L * 0.055} y={altoC * 0.70} text-anchor="end"
      font-family="ui-monospace, monospace" font-size={L * 0.105} font-weight="700"
      fill={agente.conversaciones ? color : '#94A3B8'}>
      {agente.conversaciones ? mostrada : '—'}
    </text>

    <!-- la chapa de "alguien tiene que mirar esto": numero y silueta.
         La palabra que estaba aqui no se leia a ese cuerpo y obligaba a la
         chapa a medir un 35% mas. La frase entera vive en el tooltip. -->
    {#if llaman > 0}
      <circle class="onda" cx={chX + chH * 0.5} cy={icY} r={chH * 0.5}
        fill="none" stroke="#6D28D9" stroke-width="2" />
      <rect x={chX} y={chY} width={chW} height={chH} rx={chH * 0.5} fill="#6D28D9" />
      <text x={chX + chH * 0.52} y={chY + chH * 0.68} text-anchor="middle" fill="#fff"
        font-family="ui-monospace, monospace" font-size={chH * 0.56} font-weight="700">{llaman}</text>
      <circle cx={icX} cy={icY - chH * 0.17} r={chH * 0.14} fill="#fff" />
      <path d="M {icX - chH*0.23} {icY + chH*0.26} a {chH*0.23} {chH*0.21} 0 0 1 {chH*0.46} 0 Z" fill="#fff" />
    {/if}
  </g>
</g>

<style>
  .puesto { cursor: pointer; transition: opacity .4s ease; }
  .puesto:focus { outline: none; }
  .puesto:focus .halo, .puesto:hover .halo { opacity: 1; }
  .halo { opacity: 0; transition: opacity .14s; }
  .puesto.llamando .halo { opacity: 1; }

  /* El color de estado VIRA en vez de saltar. Es la animacion principal de
     esta pantalla y la unica que ocurre en cada foto: con sondeo cada 12 s,
     un agente que pasa de trabajando a con-errores cambiaba de golpe y el
     cambio se perdia si uno parpadeaba. */
  .tenido { transition: fill .45s ease, fill-opacity .45s ease; }
  .tenidoRelleno { transition: fill .45s ease; }
  .cifra { transition: fill .45s ease; }

  /* El pulso SOLO lo llevan los dos estados que piden una persona. Antes lo
     llevaban cuatro, 'working' incluido: con ocho agentes trabajando la
     planta entera parpadeaba, y un tablero donde todo parpadea no dirige la
     mirada a ningun lado. */
  @keyframes latido { 0%, 100% { opacity: 1; } 50% { opacity: .3; } }
  .pulsa { animation: latido 1.8s ease-in-out infinite; }

  @keyframes ondaFuera { from { r: 6px; opacity: .5; } to { r: 22px; opacity: 0; } }
  .onda { animation: ondaFuera 2.4s ease-out infinite; }

  /* El destello: UNA vez, al entrar en alarma o al empezar a esperar a una
     persona. Seguir en alarma no dispara nada. */
  @keyframes aviso {
    0%, 100% { filter: none; }
    30% { filter: brightness(1.5) saturate(1.3); }
  }
  .puesto.destella { animation: aviso .7s ease-in-out 2; }

  @media (prefers-reduced-motion: reduce) {
    .pulsa, .onda, .puesto.destella { animation: none; }
    .tenido, .tenidoRelleno, .cifra, .puesto { transition: none; }
  }
</style>
