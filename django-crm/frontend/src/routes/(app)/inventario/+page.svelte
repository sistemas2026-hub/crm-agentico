<script>
  /**
   * El inventario: qué hay, dónde, y por dónde pasó cada aparato.
   *
   * DE DÓNDE SALE ESTE DISEÑO
   * -------------------------
   * Del proyecto "Modulo Inventario Dexter" de Google Stitch: diez pantallas, una
   * por pestaña, portadas una a una. El sistema visual vive en `inventario.css`
   * --tokens Material 3, generados desde el config de Stitch-- y las clases
   * conservan el nombre que les puso Stitch para que el marcado no pase por un
   * renombrado donde se pierde fidelidad.
   *
   * LO QUE EL DISEÑO PIDE Y EL SISTEMA TODAVÍA NO TIENE
   * ---------------------------------------------------
   * Stitch agregó indicadores que no existen en el backend: "equipos en
   * tránsito", la última sincronización del teléfono, un historial de entregas.
   * Quedan PUESTOS, con `—` en lugar del número, porque el dato llega después y
   * el hueco tiene que verse. Lo que no se hace nunca es inventar la cifra: un
   * número falso en una pantalla de inventario manda a un técnico a la calle sin
   * material. Cada uno está marcado con `data-sin-dato` para poder encontrarlos.
   *
   * LO QUE SÍ ES REAL SE CALCULA, NO SE SUPONE
   * ------------------------------------------
   * Las tres primeras métricas, el aviso de descuadre y todas las tablas salen de
   * `+page.server.js`. El botón "Ajustar saldo" del diseño resultó ser una
   * función que ya existe --el conteo físico de esa ubicación-- así que lleva ahí.
   */
  import { enhance } from '$app/forms';
  import './inventario.css';

  import Existencias from '$lib/v2/inventario/Existencias.svelte';
  import RegistrarEntrada from '$lib/v2/inventario/RegistrarEntrada.svelte';
  import Despachar from '$lib/v2/inventario/Despachar.svelte';
  import RecibirDevolucion from '$lib/v2/inventario/RecibirDevolucion.svelte';
  import Trasladar from '$lib/v2/inventario/Trasladar.svelte';
  import Reservas from '$lib/v2/inventario/Reservas.svelte';
  import ConteoFisico from '$lib/v2/inventario/ConteoFisico.svelte';
  import ComprasYValor from '$lib/v2/inventario/ComprasYValor.svelte';
  import Reportes from '$lib/v2/inventario/Reportes.svelte';
  import BuscarAparato from '$lib/v2/inventario/BuscarAparato.svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  let existencias = $derived(data.existencias ?? []);
  let materiales = $derived(data.materiales ?? []);
  let ubicaciones = $derived(data.ubicaciones ?? []);
  let personas = $derived(data.personas ?? []);
  let metricas = $derived(data.metricas ?? {});

  /** Las bodegas y vehículos: de acá sale y acá vuelve el material. */
  let internas = $derived(
    ubicaciones.filter((u) => u.tipo === 'bodega' || u.tipo === 'vehiculo')
  );

  /**
   * La pestaña viene de la URL y no de un `$state`.
   *
   * Las secciones de Fase 2 y 3 se cargan en el servidor según `?ver=`, así que
   * una pestaña local mostraría la sección vacía: el load no se vuelve a correr
   * al cambiar una variable. Y de paso una pestaña abierta se puede compartir por
   * link, que es lo que alguien hace cuando quiere mostrarle un descuadre a otra
   * persona.
   */
  let pestana = $derived(data.ver ?? 'existencias');
  let ubicacionElegida = $derived(data.ubicacionElegida ?? '');

  /** Las diez pestañas del diseño, en su orden. */
  const PESTANAS = [
    { id: 'existencias', texto: 'Existencias' },
    { id: 'entrada', texto: 'Registrar entrada' },
    { id: 'despacho', texto: 'Despachar' },
    { id: 'devolucion', texto: 'Recibir devolución' },
    { id: 'traslado', texto: 'Trasladar' },
    { id: 'reservas', texto: 'Reservas' },
    { id: 'conteo', texto: 'Conteo físico' },
    { id: 'compras', texto: 'Compras y valor' },
    { id: 'reportes', texto: 'Reportes' },
    { id: 'serie', texto: 'Buscar aparato' }
  ];

  /**
   * Las pestañas que pintan el resultado con su propio aviso, más rico que el
   * genérico. En esas, el de arriba no se muestra: el mismo mensaje dos veces en
   * la misma pantalla se lee como dos problemas distintos.
   */
  const CON_AVISO_PROPIO = new Set([
    'despacho',
    'devolucion',
    'traslado',
    'reservas',
    'conteo',
    'compras'
  ]);

  /** @param {string} ver */
  function enlace(ver) {
    const q = new URLSearchParams();
    q.set('ver', ver);
    if (ubicacionElegida) q.set('ubicacion', ubicacionElegida);
    return `?${q}`;
  }
</script>

<svelte:head>
  <title>Inventario</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin="" />
  <!--
    Las tres familias del diseño. Material Symbols es la fuente de iconos: sin
    ella, cada `<span class="material-symbols-outlined">warehouse</span>` se
    dibuja como la palabra "warehouse". Mismo enlace que usa supervisor-noc, que
    es la otra pantalla portada de Stitch.
  -->
  <link
    href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500;600;700&family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200&display=swap"
    rel="stylesheet"
  />
</svelte:head>

<div class="inv">
  <!--
    v2-scroll NO ES DECORACIÓN: es el único contenedor que hace scroll.

    El shell de (app) es `height:100vh; overflow:hidden` y `.v2-main` también
    recorta (lib/v2/styles/v2.css). Sin esta envoltura la pantalla se ve entera
    solo si cabe: todo lo que pase del alto de la ventana queda cortado y no hay
    forma de llegar a lo de abajo. Ya pasó dos veces en este repo, las dos por
    una pantalla que traía su propio CSS.
  -->
  <div class="v2-scroll">
    <div class="w-full px-gutter pb-space-xl">
      <!-- ============ CABECERA ============ -->
      <div class="pt-margin pb-space-lg">
        <h1 class="font-headline-lg text-headline-lg text-on-surface">Inventario</h1>
        <p class="font-body-md text-body-md text-secondary mt-space-xs">
          Controlá qué hay en bodega, qué tiene cada técnico y por dónde pasó cada equipo.
        </p>
      </div>

      <!-- ============ PESTAÑAS ============ -->
      <!--
        Son enlaces y no botones: cada pestaña es una URL (`?ver=`), se puede
        compartir y el servidor carga solo lo de esa sección.
      -->
      <!--
        LAS PESTAÑAS ENVUELVEN EN VEZ DE DESPLAZARSE.

        El diseño de Stitch usa `overflow-x-auto` y funciona en su lienzo de
        1280px, que no tiene barra lateral. Acá el shell de la app se lleva 222px,
        así que las diez no entran: medido, el nav pide 1227px y dispone de 1186.
        Con scroll horizontal, «Buscar aparato» queda cortada y aparece una barra
        gris dentro de la página. Envolviendo a dos filas se ven las diez, que es
        lo que la barra de pestañas existe para hacer.
      -->
      <nav class="flex flex-wrap items-center gap-gutter">
        {#each PESTANAS as p (p.id)}
          {#if p.id === pestana}
            <a
              href={enlace(p.id)}
              aria-current="page"
              class="h-10 px-space-md inline-flex items-center transition-colors text-primary font-headline-sm border-b-2 border-primary bg-surface-container-lowest"
            >{p.texto}</a>
          {:else}
            <a
              href={enlace(p.id)}
              class="h-10 px-space-md inline-flex items-center text-on-surface-variant hover:text-on-surface font-body-md text-body-md transition-colors"
            >{p.texto}</a>
          {/if}
        {/each}
      </nav>

      <div class="pt-margin flex flex-col w-full gap-space-lg">
        <!-- ============ AVISOS ============ -->
        {#if data.noSePudoLeer}
          <div class="bg-error-container/40 px-space-lg py-space-md rounded-xl flex items-start gap-space-md shadow-sm">
            <span class="material-symbols-outlined text-error text-[20px] shrink-0">report_problem</span>
            <p class="font-body-md text-body-md text-on-surface">
              <span class="font-semibold text-error">No se pudo leer el inventario.</span>
              Lo que sigue puede estar incompleto: no se muestran ceros porque no sabemos si
              son ceros. Reintentá, y si sigue así avisá a soporte.
            </p>
          </div>
        {/if}

        {#if data.errorExtra}
          <div class="bg-error-container/40 px-space-lg py-space-md rounded-xl flex items-start gap-space-md shadow-sm">
            <span class="material-symbols-outlined text-error text-[20px] shrink-0">report_problem</span>
            <p class="font-body-md text-body-md text-on-surface">
              <span class="font-semibold text-error">No se pudo leer esta sección.</span>
              Lo que sigue puede estar incompleto. No se muestran ceros porque no sabemos si
              son ceros.
            </p>
          </div>
        {/if}

        {#if form?.hecho && !CON_AVISO_PROPIO.has(pestana)}
          <div class="bg-primary-fixed/40 px-space-lg py-space-md rounded-xl flex items-start gap-space-md shadow-sm">
            <span class="material-symbols-outlined text-primary text-[20px] shrink-0">task_alt</span>
            <p class="font-body-md text-body-md text-on-surface">{form.hecho}</p>
          </div>
        {/if}

        {#if form?.error && !CON_AVISO_PROPIO.has(pestana)}
          <!--
            EL MENSAJE DEL BACKEND VIAJA ENTERO. Cuando un despacho choca, dice
            DÓNDE está el aparato: «la serie X figura en la Custodia de Juan»
            resuelve el caso en el acto, y un «no se pudo despachar» obliga a
            investigar de cero.
          -->
          <div class="bg-error-container/40 px-space-lg py-space-md rounded-xl flex items-start gap-space-md shadow-sm">
            <span class="material-symbols-outlined text-error text-[20px] shrink-0">error</span>
            <p class="font-body-md text-body-md text-on-surface">{form.error}</p>
          </div>
        {/if}

        {#if form?.incidencias?.length && !CON_AVISO_PROPIO.has(pestana)}
          <!--
            NI ÉXITO NI ERROR: algo que hay que MIRAR. La devolución entró y
            además falta material. En verde se leería «todo bien» y en rojo
            «falló la operación», y ninguna de las dos es cierta.
          -->
          <div class="bg-tertiary-container/20 px-space-lg py-space-md rounded-xl shadow-sm">
            <div class="flex items-start gap-space-md">
              <span class="material-symbols-outlined text-tertiary text-[20px] shrink-0">pending_actions</span>
              <div class="flex flex-col gap-space-xs">
                <p class="font-body-md text-body-md text-on-surface">
                  <span class="font-semibold text-tertiary">Quedó una diferencia abierta.</span>
                  La devolución se registró por lo que llegó, y lo que falta quedó como
                  incidencia — no se absorbió en un ajuste:
                </p>
                <ul class="flex flex-col gap-space-xs">
                  {#each form.incidencias as i (i.id)}
                    <li class="font-body-sm text-body-sm text-on-surface">
                      <span class="font-label-code text-label-code font-semibold">{i.material}</span>
                      · faltan {i.cantidad} · {i.motivo}
                    </li>
                  {/each}
                </ul>
              </div>
            </div>
          </div>
        {/if}

        <!-- ============ LA SECCIÓN DE LA PESTAÑA ============ -->
        {#if pestana === 'existencias'}
          <Existencias {existencias} {metricas} {enlace} />
        {:else if pestana === 'entrada'}
          <RegistrarEntrada {materiales} {internas} {form} />
        {:else if pestana === 'despacho'}
          <Despachar
            {materiales}
            {personas}
            {internas}
            {existencias}
            {ubicaciones}
            plantillas={data.plantillas}
            {form}
          />
        {:else if pestana === 'devolucion'}
          <RecibirDevolucion {materiales} {personas} {internas} {existencias} {ubicaciones} {form} />
        {:else if pestana === 'traslado'}
          <Trasladar {materiales} {internas} {existencias} {form} />
        {:else if pestana === 'reservas'}
          <Reservas
            libre={data.libre}
            reservas={data.reservas}
            {materiales}
            {internas}
            {ubicacionElegida}
            {form}
          />
        {:else if pestana === 'conteo'}
          <ConteoFisico
            conteos={data.conteos}
            {materiales}
            {internas}
            {ubicacionElegida}
            {form}
          />
        {:else if pestana === 'compras'}
          <ComprasYValor
            proveedores={data.proveedores}
            valorizacion={data.valorizacion}
            {materiales}
            {internas}
            {ubicacionElegida}
            {form}
          />
        {:else if pestana === 'reportes'}
          <Reportes reporte={data.reporte} {internas} />
        {:else if pestana === 'serie'}
          <BuscarAparato consulta={data.consulta} serieConsultada={data.serieConsultada} />
        {/if}
      </div>
    </div>
  </div>
</div>
