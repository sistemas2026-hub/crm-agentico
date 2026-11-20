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
  import { opcionesDelDestino, ordenDelFoco, queDibujar } from './destino-de-la-orden.js';
  import { desdeHace, filasDeSeguimiento, horaCorta } from './relojes-del-mapa.js';

  /**
   * `verificadoEn`: cuándo la PANTALLA preguntó por última vez (ms epoch).
   * Lo pone quien sondea --la página, cada 15 s-- y no este componente: acá
   * no se sabe si la respuesta llegó o falló. Ausente, la línea no miente:
   * no inventa una hora.
   *
   * @type {{ cuadrillas: any[], verificadoEn?: number | null }}
   */
  let { cuadrillas, verificadoEn = null } = $props();

  /** Las que tienen algo que dibujar. */
  let conPosicion = $derived((cuadrillas ?? []).filter((c) => c.posicion));
  let sinSenal = $derived((cuadrillas ?? []).filter((c) => !c.posicion));

  /**
   * LOS CUATRO ESCENARIOS (05/11/2026), uno por cuadrilla. Ver
   * `destino-de-la-orden.js`: una cuadrilla sin señal pero con destino
   * conocido SÍ se dibuja --se ve a dónde va-- y una orden sin coordenadas
   * se nombra en vez de inventarle un punto.
   */
  let planos = $derived((cuadrillas ?? []).map((c) => ({ c, q: queDibujar(c) })));
  /** Lo que hay que decir en palabras: una línea por cuadrilla a la que le falta algo. */
  let faltantes = $derived(
    planos.filter(({ q }) => q.falta && q.escenario !== 'C')
      .map(({ c, q }) => `${c.cuadrilla}: ${q.falta}`)
  );

  /** La línea plegada: las cuentas, sin obligar a leer el detalle. */
  let resumenDeAbajo = $derived(
    [
      sinSenal.length ? `${sinSenal.length} sin señal` : '',
      faltantes.length ? `${faltantes.length} sin ubicación` : '',
      'qué significa un punto'
    ].filter(Boolean).join(' · ')
  );

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
   * AHORA, LATIENDO CADA SEGUNDO. Sin esto, «hace 8 s» se quedaría escrito
   * hasta el siguiente sondeo y una pantalla congelada se vería idéntica a
   * una viva --que es exactamente lo que el usuario pidió poder distinguir--.
   * Es un contador, no una consulta: no le pide nada al servidor.
   */
  let ahora = $state(Date.now());
  $effect(() => {
    const t = setInterval(() => { ahora = Date.now(); }, 1000);
    return () => clearInterval(t);
  });

  /** Las filas de abajo. Ver `relojes-del-mapa.js`. */
  let filas = $derived(filasDeSeguimiento(cuadrillas));

  /** Hace cuánto preguntó la pantalla. '' mientras no haya preguntado. */
  let haceDeLaConsulta = $derived(
    verificadoEn ? desdeHace((ahora - verificadoEn) / 1000) : ''
  );
  let horaDeLaConsulta = $derived(verificadoEn ? horaCorta(verificadoEn, true) : '');

  /** Los marcadores vivos, para abrir el globo del que se centra. */
  /** @type {{jornada: string, marca: any}[]} */
  let marcas = [];

  /**
   * ACERCAR EL MAPA A UNA CUADRILLA. Pedido del usuario: «un botón que yo le
   * dé clic y me acerque el mapa al técnico».
   *
   * Abre además su globo: acercarse sin decir a quién deja al supervisor
   * mirando una calle, sin saber cuál de los cinco puntos quedó en el centro.
   *
   * @param {string} jornada
   */
  function acercarA(jornada) {
    const c = (cuadrillas ?? []).find((/** @type {any} */ x) => x.jornada === jornada);
    if (!mapa || !c?.posicion) return;
    mapa.setView([c.posicion.latitud, c.posicion.longitud], 17, { animate: true });
    for (const m of marcas) {
      if (m.jornada === jornada) { m.marca.openPopup(); break; }
    }
  }

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
      //  ESRI Y NO CARTO (05/11/2026). CARTO pasó a pedir clave y empezó a
      //  servir las imágenes con «API KEY REQUIRED» encima: el mapa quedó
      //  ilegible. Esri World Street Map no pide clave --es el mismo
      //  proveedor del satélite, que ya andaba-- y se ve igual de moderno.
      url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
      opciones: {
        maxZoom: 19,
        attribution: 'Mapa &copy; Esri'
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
    marcas = [];
    const puntos = [];
    for (const { c, q } of planos) {
      //  EL DESTINO DEL CLIENTE, cuando la orden lo tiene. Un pin distinto
      //  --una casa-- para que no se confunda con el vehículo.
      if (q.destino) {
        const foco = ordenDelFoco(c);
        L.marker([q.destino.latitud, q.destino.longitud], {
          icon: L.divIcon(opcionesDelDestino()),
          title: foco ? `OT #${foco.numero}` : ''
        })
          .bindPopup(textoDelDestino(c, foco))
          .addTo(capa);
        puntos.push([q.destino.latitud, q.destino.longitud]);
      }
      //  LA LÍNEA entre los dos, solo cuando se saben las DOS puntas. Con
      //  una sola sería una ruta inventada hacia un punto que nadie midió.
      if (q.une && q.vehiculo && q.destino) {
        //  DOS TRAZOS, Y EL DE ABAJO ES EL QUE LA HACE VISIBLE (06/11/2026).
        //  Era una sola línea marrón al 45% de opacidad: sobre el mapa claro
        //  se leía, y sobre el satélite --una foto aérea de un barrio-- se
        //  perdía del todo. El usuario tenía las dos puntas dibujadas y no
        //  veía la ruta entre ellas.
        //
        //  Mismo recurso que el ícono del técnico: un halo blanco debajo que
        //  la recorta contra CUALQUIER fondo. El trazo de arriba va opaco,
        //  porque una ruta a medio tono se lee como «aproximada» y esta no lo
        //  es: une dos puntos medidos.
        const extremos = [
          [q.vehiculo.latitud, q.vehiculo.longitud],
          [q.destino.latitud, q.destino.longitud]
        ];
        L.polyline(extremos, {
          color: '#fff', weight: 6, opacity: 0.85, dashArray: '8 7'
        }).addTo(capa);
        L.polyline(extremos, {
          color: '#b45309', weight: 3, opacity: 1, dashArray: '8 7'
        }).addTo(capa);
      }
      if (!c.posicion) continue;
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
      marcas.push({ jornada: c.jornada, marca });
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

  /** @param {any} c @param {any} foco */
  function textoDelDestino(c, foco) {
    const filas = ['<strong>A dónde va</strong>'];
    if (foco) {
      filas.push(`OT #${esc(String(foco.numero))} · ${esc(foco.asunto || foco.tipo || '')}`);
      if (foco.cliente) filas.push(esc(foco.cliente));
      if (foco.direccion) filas.push(esc(foco.direccion));
    }
    filas.push(esc(c.cuadrilla ?? ''));
    return filas.join('<br>');
  }

  /** @param {any} c */
  function textoDelPopup(c) {
    const p = c.posicion;
    //  EL MISMO CRITERIO QUE EL MAPA (05/11/2026): este globo tenía su
    //  propia regla --`siguiente`-- y mostraba una OT distinta de la del pin
    //  del destino, en la misma pantalla. Ver `ordenDelFoco`.
    const foco = ordenDelFoco(c);
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

  <!-- CUÁNDO SE MIRÓ Y QUIÉN REPORTÓ (05/11/2026). Pedido del usuario: «ver
       el log de cuándo verificó las ubicaciones, con su fecha y hora» y «un
       botón que me acerque el mapa al técnico».

       NO ES UN HISTORIAL DE LAS CONSULTAS, y es a propósito: la pantalla
       pregunta cada 15 s, así que en una hora serían 240 renglones iguales.
       Informa la ÚLTIMA --con su hora y un contador que corre, que es lo que
       distingue una pantalla viva de una congelada-- y, debajo, la hora de
       cada teléfono, que es el dato que sí cambia.

       SON DOS RELOJES DISTINTOS A PROPÓSITO: si se congela el de arriba, el
       problema es esta pantalla; si se congela el de una fila, es ese
       teléfono. Con un solo número los dos fallos se ven iguales. -->
  {#if (cuadrillas ?? []).length}
    <div class="mp-reloj snoc-secundario">
      {#if horaDeLaConsulta}
        Ubicaciones verificadas {horaDeLaConsulta} · {haceDeLaConsulta}
      {:else}
        Verificando ubicaciones…
      {/if}
    </div>

    <ul class="mp-filas">
      {#each filas as f (f.jornada)}
        <li>
          <button type="button" class="mp-fila" disabled={!f.centrable}
                  onclick={() => acercarA(f.jornada)}
                  title={f.centrable
                    ? `Acercar el mapa a ${f.cuadrilla}`
                    : `${f.cuadrilla} no reportó: no hay a dónde acercarse`}>
            <span class="mp-punto" class:viejo={!f.fresca} class:mudo={!f.centrable}></span>
            <span class="mp-quien">{f.cuadrilla}</span>
            <span class="mp-cuando" class:alerta={!f.centrable}>{f.dice}</span>
          </button>
        </li>
      {/each}
    </ul>
  {/if}

  <!-- LO DE ABAJO, PLEGADO (05/11/2026). El usuario: «aparece información
       irrelevante debajo del mapa». No es irrelevante --qué significa un
       punto, y qué orden hay que corregir-- pero no se lee todos los días y
       ocupaba tres párrafos encima del seguimiento. Queda una línea con las
       cuentas, y el detalle a un clic. -->
  <details class="mp-detalle">
    <summary class="snoc-secundario">{resumenDeAbajo}</summary>
    <p class="mp-nota snoc-secundario">
      Un punto dice que el teléfono de esa persona reportó esa coordenada, no que la persona esté ahí.
      Lo atenuado pasó los 30 minutos: es dónde estuvo, no dónde está.
    </p>
    {#if faltantes.length}
      <!-- Una orden sin coordenadas no se rellena con un punto adivinado: se
           nombra para poder corregirla. -->
      <ul class="mp-faltan">
        {#each faltantes as f (f)}<li>{f}</li>{/each}
      </ul>
    {/if}
    {#if sinSenal.length}
      <p class="mp-sin snoc-secundario">
        Sin señal: {sinSenal.map((c) => c.cuadrilla).join(' · ')}
      </p>
    {/if}
  </details>
</section>

<style>
  .mp { display: grid; gap: var(--snoc-xs); min-width: 0; }
  .mp-cab { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 8px; }
  .mp-cuenta { font-size: 12px; }
  .mp-caja {
    position: relative;
    /*  MAS BAJO (05/11/2026): con 360 px el mapa se comia la pantalla y el
        seguimiento quedaba debajo del pliegue. */
    height: 260px;
    border-radius: var(--snoc-r-xl);
    border: 1px solid var(--snoc-outline-variant);
    background: var(--snoc-surface-container);
    overflow: hidden;
  }
  .mp-nota, .mp-sin, .mp-vacio { margin: 0; font-size: 12px; }
  .mp-reloj { font-size: 12px; font-variant-numeric: tabular-nums; }
  .mp-filas { list-style: none; margin: 0; padding: 0; display: grid; gap: 2px; }
  .mp-fila {
    display: grid;
    grid-template-columns: 10px minmax(0, 1fr) auto;
    align-items: center;
    gap: var(--snoc-xs);
    width: 100%;
    padding: 4px 6px;
    border: 0;
    border-radius: 6px;
    background: transparent;
    font: inherit;
    font-size: 12px;
    text-align: left;
    cursor: pointer;
  }
  .mp-fila:hover:not(:disabled) { background: rgba(0, 0, 0, 0.05); }
  .mp-fila:disabled { cursor: default; opacity: 0.75; }
  .mp-punto { width: 8px; height: 8px; border-radius: 50%; background: #1f7a3d; }
  .mp-punto.viejo { background: #6b7280; }
  /*  Sin señal no es un punto apagado: es NINGUN punto. Un circulo hueco no
      se confunde con una posicion vieja, que si es un dato. */
  .mp-punto.mudo { background: transparent; border: 1px solid #b91c1c; }
  .mp-quien { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .mp-cuando { font-variant-numeric: tabular-nums; white-space: nowrap; }
  .mp-cuando.alerta { color: #b91c1c; }
  .mp-detalle summary { font-size: 12px; cursor: pointer; }
  .mp-detalle > :not(summary) { margin-top: var(--snoc-xs); }
  .mp-faltan {
    margin: 0;
    padding-left: 18px;
    font-size: 12px;
    color: #8a5300;
  }
  /* El pin del destino: sin fondo ni borde propios de Leaflet. */
  :global(.mp-destino) { background: none; border: none; }
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
