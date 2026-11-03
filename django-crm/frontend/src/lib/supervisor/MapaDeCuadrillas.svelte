<!--
  DÓNDE ESTÁ CADA CUADRILLA (31/10/2026). Pedido del usuario: «un mapa donde
  uno pueda ver la posición actual de cada técnico, para hacerle seguimiento».

  CON OPENSTREETMAP, Y ES UNA DECISIÓN. Google y Mapbox recibirían la
  ubicación de los técnicos, y la autorización de tratamiento que firma el
  cliente nombra a los proveedores: meterlos obliga a un trámite antes de
  encender nada. OSM no agrega un tercero.

  LO QUE NO HACE, A PROPÓSITO:
  - no dibuja un pin de quien no reportó: «sin señal» NO es «no se movió»;
  - no muestra una posición vieja como actual: lo que pasa los 30 minutos sale
    atenuado y con su hora;
  - no dibuja recorridos: no se guardan.

  Y LO QUE UN PIN SIGNIFICA: que el teléfono de esa persona reportó esa
  coordenada. No prueba que la persona esté ahí, y el mapa lo dice, porque un
  punto en una pantalla se lee como un hecho sobre alguien.

  Leaflet se carga solo en el navegador (`onMount`): en el render del servidor
  no hay `window` y el módulo revienta al importarse arriba.
-->
<script>
  import { onMount } from 'svelte';

  import { opcionesDelIcono } from './icono-de-cuadrilla.js';

  /** @type {{ cuadrillas: any[] }} */
  let { cuadrillas } = $props();

  /** Las que tienen algo que dibujar. */
  let conPosicion = $derived((cuadrillas ?? []).filter((c) => c.posicion));
  let sinSenal = $derived((cuadrillas ?? []).filter((c) => !c.posicion));

  /** @type {HTMLDivElement | undefined} */
  let caja = $state();
  /** @type {any} */
  let mapa = null;
  /** @type {any} */
  let capa = null;
  /** @type {any} */
  let L = null;
  /** @type {any} */
  let capasBase = null;

  /** Qué capa se está viendo. Sobrevive al redibujo de los pines. */
  let vista = $state('mapa');

  /**
   * LAS DOS CAPAS (02/11/2026). El usuario: «el mapa se ve viejo, ¿no se
   * puede importar un mapa y cambiar a modo satélite?».
   *
   * Ninguna de las dos pide cuenta, clave ni tarjeta, y ninguna recibe la
   * ubicación de nadie: un servidor de tiles solo ve QUÉ ZONA se está
   * mirando, nunca las coordenadas del técnico. Es la misma exposición que
   * ya tenía OpenStreetMap.
   *
   *   mapa     CARTO Voyager — el mismo dato de OSM con un diseño limpio;
   *            el OSM crudo es lo que se veía viejo.
   *   satelite Esri World Imagery.
   *
   * Las dos son gratis con atribución y uso razonable. Si esto creciera a
   * muchas empresas mirando mapas todo el día, hay que revisar sus términos.
   */
  const CAPAS = {
    mapa: {
      url: 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png',
      opciones: {
        maxZoom: 20,
        subdomains: 'abcd',
        attribution: '&copy; OpenStreetMap &copy; CARTO'
      }
    },
    satelite: {
      url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      opciones: {
        maxZoom: 19,
        attribution: 'Imágenes &copy; Esri'
      }
    }
  };

  /** @param {'mapa' | 'satelite'} cual */
  function cambiarCapa(cual) {
    vista = cual;
    if (!mapa || !L || !capasBase) return;
    for (const [nombre, capaBase] of Object.entries(capasBase)) {
      if (nombre === cual) capaBase.addTo(mapa);
      else mapa.removeLayer(capaBase);
    }
  }

  //  LA LIMPIEZA VA EN UN `onMount` SÍNCRONO (01/11/2026). Un `onMount`
  //  asíncrono devuelve una promesa, y Svelte ignora lo que resuelva: la
  //  función de limpieza nunca corría y el mapa quedaba vivo al salir de la
  //  pantalla, con su reloj y sus oyentes. Lo marcó `svelte-check`; sin eso
  //  no se nota hasta que la memoria crece.
  onMount(() => {
    let vivo = true;
    (async () => {
      L = (await import('leaflet')).default;
      await import('leaflet/dist/leaflet.css');
      //  Entre el import y acá el supervisor pudo haberse ido de la pantalla.
      if (!vivo || !caja) return;
      mapa = L.map(caja, { attributionControl: true, zoomControl: true });
      capasBase = Object.fromEntries(
        Object.entries(CAPAS).map(([n, c]) => [n, L.tileLayer(c.url, c.opciones)])
      );
      capasBase[vista].addTo(mapa);
      capa = L.layerGroup().addTo(mapa);
      //  Sin nada que mostrar, el mapa igual tiene que verse: Soledad.
      mapa.setView([10.9185, -74.7668], 13);
      dibujar();
    })();
    return () => {
      vivo = false;
      mapa?.remove();
      mapa = null;
      capa = null;
    };
  });

  //  Los pines se rehacen cuando cambian los datos; el sondeo de la pantalla
  //  los trae cada 15 s, así que el mapa se mueve solo.
  $effect(() => {
    void conPosicion;
    dibujar();
  });

  function dibujar() {
    if (!mapa || !capa || !L) return;
    capa.clearLayers();
    const puntos = [];
    for (const c of conPosicion) {
      const p = c.posicion;
      const color = p.fresca ? '#1f7a3d' : '#6b7280';
      //  LA MOTO CON TRÁILER (02/11/2026), en vez de un punto. El color
      //  sigue diciendo lo mismo: lleno = reportó hace poco, apagado = es
      //  dónde estuvo. Ver `icono-de-cuadrilla.js`.
      const marca = L.marker([p.latitud, p.longitud], {
        icon: L.divIcon(opcionesDelIcono(color, p.fresca)),
        title: c.cuadrilla ?? ''
      });
      marca.bindPopup(textoDelPopup(c));
      marca.addTo(capa);
      puntos.push([p.latitud, p.longitud]);
      //  La precisión, cuando es pobre, como un círculo: así el supervisor ve
      //  que es el barrio y no la casa, en vez de creerle al punto.
      if (p.precision_pobre && p.precision_m) {
        L.circle([p.latitud, p.longitud], {
          radius: p.precision_m, color, weight: 1, opacity: 0.4, fillOpacity: 0.07
        }).addTo(capa);
      }
    }
    if (puntos.length === 1) mapa.setView(puntos[0], 15);
    else if (puntos.length > 1) mapa.fitBounds(puntos, { padding: [40, 40] });
  }

  /** @param {any} c */
  function textoDelPopup(c) {
    const p = c.posicion;
    const foco = (c.ordenes ?? []).find((/** @type {any} */ o) => o.siguiente) ?? (c.ordenes ?? [])[0];
    const filas = [
      `<strong>${esc(c.cuadrilla)}</strong>`,
      `Reportó: ${esc(p.de ?? '—')}`,
      `Hace ${p.minutos} min${p.fresca ? '' : ' · no es donde está ahora'}`
    ];
    if (foco) filas.push(`OT #${esc(String(foco.numero))} · ${esc(foco.asunto || foco.tipo || '')}`);
    if (p.precision_m) filas.push(`Precisión ± ${p.precision_m} m`);
    if (p.bateria !== null && p.bateria !== undefined) filas.push(`Batería ${p.bateria}%`);
    return filas.join('<br>');
  }

  /** @param {string} s */
  function esc(s) {
    return String(s).replace(/[&<>"']/g, (ch) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[ch] ?? ch);
  }
</script>

<section class="mp" aria-label="Dónde está cada cuadrilla">
  <div class="mp-cab">
    <span class="snoc-label">Dónde está cada cuadrilla</span>
    <span class="mp-cuenta snoc-secundario">
      {conPosicion.length} de {(cuadrillas ?? []).length} reportando
    </span>
  </div>

  <div class="mp-caja" bind:this={caja}>
    <!-- MAPA / SATÉLITE: encima del mapa, como en el boceto del usuario. -->
    <div class="mp-capas">
      <button type="button" class:on={vista === 'mapa'}
              onclick={() => cambiarCapa('mapa')}>Mapa</button>
      <button type="button" class:on={vista === 'satelite'}
              onclick={() => cambiarCapa('satelite')}>Satélite</button>
    </div>
  </div>

  <!-- SIN CUADRILLAS ARMADAS (01/11/2026): se dice, en vez de dejar un mapa
       vacío que no se distingue de uno roto. -->
  {#if !(cuadrillas ?? []).length}
    <p class="mp-vacio snoc-secundario">
      No hay cuadrillas armadas para este día: no hay a quién ubicar.
    </p>
  {/if}

  <p class="mp-nota snoc-secundario">
    Un punto dice que el teléfono de esa persona reportó esa coordenada, no que la persona esté ahí.
    Lo atenuado pasó los 30 minutos: es dónde estuvo, no dónde está.
  </p>

  {#if sinSenal.length}
    <p class="mp-sin snoc-secundario">
      Sin señal: {sinSenal.map((c) => c.cuadrilla).join(' · ')}
    </p>
  {/if}
</section>

<style>
  .mp { display: grid; gap: var(--snoc-xs); min-width: 0; }
  .mp-cab { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 8px; }
  .mp-cuenta { font-size: 12px; }
  .mp-caja {
    position: relative;
    height: 360px;
    border-radius: var(--snoc-r-xl);
    border: 1px solid var(--snoc-outline-variant);
    background: var(--snoc-surface-container);
    overflow: hidden;
  }
  .mp-nota, .mp-sin, .mp-vacio { margin: 0; font-size: 12px; }
  .mp-vacio { font-weight: 600; }
  .mp-sin { font-weight: 600; }
  .mp-capas {
    position: absolute;
    top: 10px;
    left: 10px;
    z-index: 500;
    display: flex;
    gap: 2px;
    padding: 2px;
    border-radius: 999px;
    background: var(--snoc-surface-container-lowest);
    border: 1px solid var(--snoc-outline-variant);
    box-shadow: 0 1px 4px rgb(0 0 0 / 18%);
  }
  .mp-capas button {
    border: none;
    background: transparent;
    color: var(--snoc-on-surface-variant);
    font: inherit;
    font-size: 12px;
    font-weight: 600;
    padding: 5px 12px;
    border-radius: 999px;
    cursor: pointer;
  }
  .mp-capas button.on {
    background: var(--snoc-primary);
    color: var(--snoc-on-primary, #fff);
  }
  /* El ícono del vehículo: sin fondo ni borde propios de Leaflet. */
  :global(.mp-vehiculo) { background: none; border: none; }
  /* Leaflet dibuja dentro de la caja; su CSS llega con el módulo. */
  :global(.leaflet-container) { font: inherit; background: var(--snoc-surface-container); }
</style>
