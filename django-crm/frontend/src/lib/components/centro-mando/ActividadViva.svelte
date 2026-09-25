<script>
  /**
   * Lo que se mueve en la planta: una capa encima de los puestos.
   *
   * QUE SE ANIMA, Y POR QUE TAN POCO
   * Cada animacion corresponde a un evento que el motor conto de verdad --
   * una escalada, una accion, una herramienta que fallo. Lo unico que decide
   * esta capa es DONDE y CUANDO se dibuja; el que haya pasado lo decide la
   * base de datos.
   *
   * No hay movimiento inventado. Si en una ventana no paso nada, la planta
   * se queda quieta, y que este quieta ES la informacion. Esa es la linea
   * entre dar a entender que la operacion esta viva --que es lo que se
   * busca-- y fingir actividad, que seria mentir sobre la operacion.
   *
   * POR QUE ESTA SEPARADO DEL PUESTO
   * Un puesto se dibuja a si mismo y no sabe donde estan los demas. Esta capa
   * si: recibe la posicion de cada uno y por eso puede dibujar lo que va DE
   * un sitio A otro, que es justo lo que un puesto no puede hacer solo.
   */
  import { onDestroy } from 'svelte';
  import { eventosNuevos, repartir } from '$lib/centro-mando/actividad.js';

  /** @type {{ eventos: any[], posiciones: Record<string, {x:number,y:number}>,
   *           lado: number, intervaloMs?: number }} */
  let { eventos, posiciones, lado: L, intervaloMs = 12000 } = $props();

  /** Las que estan en pantalla ahora mismo. */
  let vivas = $state(/** @type {any[]} */ ([]));
  let descartados = $state(0);

  let anteriores = [];
  let temporizadores = [];
  const limpiarTodo = () => {
    temporizadores.forEach(clearTimeout);
    temporizadores = [];
  };
  onDestroy(limpiarTodo);

  $effect(() => {
    const ahora = eventos || [];
    // `anteriores` es una variable normal y no $state a proposito: es memoria
    // entre lecturas, y guardarla en el sistema reactivo haria que escribirla
    // vuelva a disparar este mismo efecto.
    const nuevos = eventosNuevos(anteriores, ahora);
    anteriores = ahora;
    if (!nuevos.length) return;

    const { programadas, descartados: fuera } = repartir(nuevos, {
      ventanaMs: intervaloMs,
      desde: Date.now()
    });
    descartados = fuera;

    for (const p of programadas) {
      const t = setTimeout(() => {
        vivas = [...vivas, p];
        const t2 = setTimeout(() => {
          vivas = vivas.filter((v) => v.id !== p.id);
        }, p.duracion);
        temporizadores.push(t2);
      }, p.retraso);
      temporizadores.push(t);
    }
  });

  /** Donde nace una animacion: el puesto de su agente. */
  const puntoDe = (nombre) => posiciones?.[nombre] || null;
</script>

<g class="actividad" aria-hidden="true">
  {#each vivas as v (v.id)}
    {@const p = puntoDe(v.evento.agente)}
    {#if p}
      {#if v.forma === 'sale'}
        <!-- La escalada: el caso deja el edificio y pasa a una persona. Es lo
             unico que se ve SALIR, porque es lo unico que de verdad se va. -->
        <g class="sale" style="--dur:{v.duracion}ms" transform="translate({p.x}, {p.y})">
          <circle r={L * 0.075} fill="#A15C07" />
          <circle r={L * 0.075} fill="none" stroke="#A15C07" stroke-width={L * 0.02} opacity=".5" />
        </g>
      {:else if v.forma === 'falla'}
        <!-- Una herramienta que fallo: un aro rojo que se abre y se apaga. -->
        <circle class="falla" style="--dur:{v.duracion}ms; --r1:{L * 0.55}px"
          cx={p.x} cy={p.y} r={L * 0.12}
          fill="none" stroke="#B91C1C" stroke-width={L * 0.025} />
      {:else}
        <!-- Una consulta o una accion: un pulso corto sobre el puesto. -->
        <circle class="herramienta" style="--dur:{v.duracion}ms; --r1:{L * 0.34}px"
          cx={p.x} cy={p.y} r={L * 0.08}
          fill="none" stroke="#0E7490" stroke-width={L * 0.018} />
      {/if}
    {/if}
  {/each}
</g>

<style>
  /* Las animaciones no se pueden interrumpir a media ventana, asi que duran
     siempre menos que el intervalo entre lecturas -- lo garantiza `repartir`,
     no este archivo. */
  .actividad { pointer-events: none; }

  @keyframes salir {
    0%   { transform: translate(0, 0) scale(1); opacity: 0; }
    15%  { opacity: 1; }
    100% { transform: translate(60px, 90px) scale(.5); opacity: 0; }
  }
  .sale > circle { animation: salir var(--dur) cubic-bezier(.4, 0, .7, 1) forwards; }

  @keyframes abrirse {
    from { r: var(--r0, 10px); opacity: .85; }
    to   { r: var(--r1); opacity: 0; }
  }
  .falla, .herramienta { animation: abrirse var(--dur) ease-out forwards; }

  /* Quien pidio menos movimiento no recibe ninguno: la informacion sigue en
     el ticker de eventos y en las cifras, que no se mueven. */
  @media (prefers-reduced-motion: reduce) {
    .sale > circle, .falla, .herramienta { animation: none; opacity: 0; }
  }
</style>
