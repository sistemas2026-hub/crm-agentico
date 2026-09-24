<script>
  /**
   * El agente, como nodo de un diagrama radial: un disco con su cara, la
   * carga que lleva dentro, y el nombre y la tarea colgando hacia afuera.
   *
   * POR QUE UN DISCO Y NO UNA TARJETA (24/09/2026)
   * La tarjeta rectangular decia mas por agente, y justamente por eso el
   * tablero dejaba de leerse: ocho bloques de texto compiten entre si y
   * ninguno gana. El disco dice tres cosas y las dice de lejos -- quien es
   * (la cara), cuanto lleva (la cifra), en que estado esta (el color del
   * aro) -- y lo demas vive en la ficha, a un clic.
   *
   * Lo que se mide aqui: NADA. La cifra, el estado y la frase vienen del
   * motor; este componente solo decide como se ven.
   *
   * QUIEN LO COLOCA
   * El componente no sabe donde esta: recibe `x` e `y` del CommandCenter, que
   * los saca de lib/centro-mando/disposicion.js. Sin `x`/`y` se pinta en el
   * flujo normal, que es lo que pasa cuando el lienzo es demasiado angosto
   * para un anillo.
   */
  import { colorDe, rotuloDe } from '$lib/centro-mando/estados.js';

  /** @type {{ agente: any, x?: number|null, y?: number|null, haciaArriba?: boolean,
   *           compacto?: boolean, alSeleccionar?: (a: any) => void }} */
  let {
    agente,
    x = null,
    y = null,
    haciaArriba = false,
    compacto = false,
    alSeleccionar = () => {}
  } = $props();

  const PISTAS_CARA = [
    [/vent|comercial/, 'ventas'],
    [/factur|cartera|pago|cobr/, 'facturacion'],
    [/fibra|ftth|red|olt|tecnic/, 'soporte'],
    [/campo|instal|visita/, 'campo'],
    [/supervis|administra|analista/, 'supervisor'],
    [/identidad|verific/, 'identidad'],
    [/dato|analit|informe/, 'datos'],
    [/cliente|recepcion|router|chat|guiad|config/, 'router']
  ];

  const cara = $derived.by(() => {
    const texto = `${agente.nombre} ${agente.area || ''} ${agente.cargo || ''}`.toLowerCase();
    const encontrada = PISTAS_CARA.find(([patron]) => patron.test(texto));
    return `/centro-mando/avatares/${encontrada ? encontrada[1] : 'router'}.webp`;
  });

  const carga = $derived(agente.conversaciones || 0);
  const suelto = $derived(x == null || y == null);
</script>

<button
  class="nodo-agente"
  class:hacia-arriba={haciaArriba}
  class:compacto
  class:suelto
  style="--c:{colorDe(agente.estado)}{suelto ? '' : `;left:${x}px;top:${y}px`}"
  title="{agente.nombre.replaceAll('_', ' ')} — {rotuloDe(agente.estado)}{agente.haciendo
    ? ` · ${agente.haciendo}`
    : ''}"
  onclick={() => alSeleccionar(agente)}
>
  <span class="aro" class:quieto={!carga}>
    <img src={cara} alt="" />
    <span class="carga">{carga || '—'}</span>
    <span class="unidad">{carga ? 'conv' : 'sin carga'}</span>
  </span>
  <span class="nombre">{agente.nombre.replaceAll('_', ' ')}</span>
  <span class="tarea">{agente.haciendo || agente.area || ''}</span>
</button>

<style>
  .nodo-agente {
    position: absolute;
    transform: translate(-50%, -50%);
    width: 156px;
    background: none;
    border: 0;
    padding: 0;
    cursor: pointer;
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
  }
  /* Si no hay anillo (lienzo angosto), el nodo vuelve al flujo normal. */
  .nodo-agente.suelto { position: static; transform: none; }

  .aro {
    position: relative;
    width: 88px;
    height: 88px;
    border-radius: 50%;
    background: #fff;
    border: 2px solid var(--c);
    box-shadow: 0 2px 10px color-mix(in srgb, var(--c) 20%, transparent);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 2px;
    transition: box-shadow .15s;
  }
  .nodo-agente:hover .aro { box-shadow: 0 2px 18px color-mix(in srgb, var(--c) 45%, transparent); }

  .aro img { width: 30px; height: 30px; border-radius: 50%; object-fit: cover; border: 1.5px solid var(--c); }
  .carga { font-family: ui-monospace, monospace; font-size: 19px; font-weight: 700; line-height: 1; color: var(--c); }
  .quieto .carga { color: #64748b; }
  .unidad { font-size: 7.5px; letter-spacing: .14em; color: #475569; text-transform: uppercase; }

  .nombre {
    font-size: 10px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase;
    line-height: 1.25; margin-top: 9px; color: #0f172a;
  }
  /* Dos lineas y no una: la frase la arma el motor y "20 esperan a una
     persona, 5 en curso" no entra en una sola -- se cortaba a la mitad. */
  .tarea {
    display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2;
    max-width: 100%; margin-top: 3px; overflow: hidden;
    font-family: ui-monospace, monospace; font-size: 9px; line-height: 1.35; color: var(--c);
  }

  /* Version compacta: cuando el alto no da para el anillo completo, el nodo
     se encoge y suelta la linea de tarea -- que sigue en el title y en la
     ficha. Es preferible a perder el mapa entero: en produccion, con la
     cabecera de la pagina descontada, quedaban 514 px de alto y el tablero
     caia a rejilla con sitio de sobra a los lados (24/09/2026). */
  .compacto .aro { width: 74px; height: 74px; }
  .compacto .aro img { width: 24px; height: 24px; }
  .compacto .carga { font-size: 16px; }
  .compacto .unidad { font-size: 7px; }
  .compacto .nombre { font-size: 9px; margin-top: 6px; }
  /* La tarea se va por CSS y no con un {#if}: el trazado prueba el nodo entero
     y luego el compacto, midiendo el DOM entre uno y otro. Con un {#if}, esa
     medida dependia de si Svelte ya habia re-renderizado, y el resultado
     oscilaba -- 153, 125, 94 y vuelta a empezar, cada medio segundo. */
  .compacto .tarea { display: none; }

  /* El texto va SIEMPRE hacia afuera del centro. Colgando siempre abajo, el
     de los nodos de arriba queda entre el disco y el nucleo, y la via lo
     atraviesa -- se veia en la primera version del anillo. */
  .hacia-arriba .aro { order: 3; }
  .hacia-arriba .nombre { order: 1; margin-top: 0; margin-bottom: 3px; }
  .hacia-arriba .tarea { order: 2; margin-top: 0; margin-bottom: 9px; }
</style>
