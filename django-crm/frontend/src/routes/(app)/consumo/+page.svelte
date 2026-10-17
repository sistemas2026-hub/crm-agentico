<script>
  /**
   * Consumo del asistente: gasto, tokens y en qué punto del tope está.
   *
   * MISMA ESTRUCTURA QUE LA MAQUETA, con una corrección: cada bloque está
   * atado al estado que viene del motor, en vez de dibujarse siempre.
   *
   * La maqueta mostraba a la vez "Tope mensual: sin límite", "Uso del tope:
   * 0% de ilimitado" y "Asistente frenado: se alcanzó el tope" — tres cosas
   * que no pueden ser ciertas juntas. Y peor: sin tarifa cargada el costo es
   * SIEMPRE cero, así que el tope no puede alcanzarse nunca y "frenado" es
   * inalcanzable en ese estado.
   *
   * Los estados y qué desaparece en cada uno:
   *
   *   sin_tarifa  hay tokens y no hay precio. El costo es ficción: no se
   *               dibuja el eje de costo del gráfico, ni el medidor, ni el
   *               panel de frenado. Ninguno podría decir algo cierto.
   *   sin_tope    hay tarifa pero nadie puso límite. Sin medidor (un "0% de
   *               ilimitado" no significa nada) y sin panel de frenado.
   *   seguir      todo normal.
   *   avisar      del 80% al 100%: el medidor avisa.
   *   frenar      alcanzado: panel de frenado, y el medidor al tope.
   */
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import Pill from '$lib/v2/components/Pill.svelte';
  import { toast } from 'svelte-sonner';
  import { AlertCircle, MessagesSquare, Target, Wrench, Users, Cpu, Info } from '@lucide/svelte';

  /** @type {{ data: any }} */
  let { data } = $props();

  let c = $state(data.consumo);

  const estado = $derived(c?.estado ?? 'sin_tarifa');
  const sinTarifa = $derived(estado === 'sin_tarifa');
  const sinTope = $derived(estado === 'sin_tope');
  const frenado = $derived(estado === 'frenar');
  /** El medidor solo tiene sentido si hay tarifa Y hay tope. */
  const hayMedidor = $derived(!sinTarifa && !sinTope);

  const dias = $derived(c?.dias_detalle ?? []);

  /* El desglose de `asistente.consumo_eventos`, que llega vacío si la
     migración todavía no corrió — y entonces esta sección no se dibuja y la
     pantalla queda como estaba. */
  const desglose = $derived(c?.desglose ?? {});
  const porOrigen = $derived(desglose.por_origen ?? []);
  const porServicio = $derived(desglose.por_servicio ?? []);
  const porModelo = $derived(desglose.por_modelo ?? []);
  const sinTarifaDetalle = $derived(desglose.sin_tarifa ?? []);
  const hayDesglose = $derived(porOrigen.length > 0 || porServicio.length > 0);

  /* Lo que de verdad se le factura a la empresa. El resto se gastó igual,
     pero no cuenta para el tope. */
  const costoProduccion = $derived(
    porOrigen.find((o) => o.origen === 'production')?.costo ?? 0
  );
  const costoNoFacturable = $derived(
    porOrigen.filter((o) => o.origen !== 'production')
             .reduce((t, o) => t + (o.costo ?? 0), 0)
  );

  const ORIGEN_ES = {
    production: 'Producción',
    evaluation: 'Evaluaciones',
    test: 'Pruebas'
  };
  const SERVICIO_ES = {
    conversation: 'Conversación',
    vision: 'Análisis de imágenes',
    transcription: 'Transcripción de audios',
    embeddings: 'Búsqueda (embeddings)',
    tts: 'Voz (TTS)'
  };
  /* Cuatro decimales y no los dos de `usd`: el costo POR SERVICIO son
     centavos --una llamada de visión cuesta ~$0.0007-- y redondear a dos los
     dejaría a todos en $0.00, que se lee como "no gastó nada". */
  const usdFino = (/** @type {number} */ n) => '$' + (Number(n) || 0).toFixed(4);
  const maxTokens = $derived(
    Math.max(1, ...dias.map((/** @type {any} */ d) => d.tokens_entrada + d.tokens_salida))
  );
  /** El primer día del mes en que el gasto acumulado pasó el tope. Es lo más
   *  fino que se puede decir: el consumo se guarda por día, no por turno, así
   *  que una hora exacta sería inventada. */
  const frenadoDesde = $derived.by(() => {
    if (!frenado || !c?.tope) return null;
    let acum = 0;
    for (const d of [...dias].reverse()) {
      acum += d.costo_usd;
      if (acum >= c.tope) return d.dia;
    }
    return null;
  });

  let guardando = $state(false);
  let tarifaEntrada = $state('');
  let tarifaCache = $state('');
  let tarifaSalida = $state('');
  let topeNuevo = $state('');

  const usd = (/** @type {number} */ n) =>
    '$' + (Number(n) || 0).toLocaleString('es-CO', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const miles = (/** @type {number} */ n) => {
    const v = Number(n) || 0;
    return v >= 1000 ? (v / 1000).toFixed(1) + 'K' : String(v);
  };
  const fecha = (/** @type {string} */ s) =>
    new Date(s + 'T12:00:00').toLocaleDateString('es-CO', { day: 'numeric', month: 'short' });

  async function recargar() {
    const resp = await fetch('/api/consumo?dias=30');
    if (resp.ok) c = await resp.json();
  }

  async function guardar(/** @type {'tarifa'|'tope'} */ accion, cuerpo) {
    guardando = true;
    try {
      const resp = await fetch('/api/consumo', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ accion, ...cuerpo })
      });
      const datos = await resp.json();
      if (!resp.ok) {
        toast.error(datos?.error || 'No se pudo guardar.');
        return false;
      }
      await recargar();
      return true;
    } finally {
      guardando = false;
    }
  }

  async function guardarTarifa() {
    const entrada = parseFloat(tarifaEntrada), salida = parseFloat(tarifaSalida);
    if (!(entrada >= 0) || !(salida >= 0)) {
      toast.error('Poné las dos tarifas, en USD por millón de tokens.');
      return;
    }
    const cache = tarifaCache.trim() === '' ? null : parseFloat(tarifaCache);
    if (cache !== null && !(cache >= 0)) {
      toast.error('El precio de entrada cacheada tiene que ser un número.');
      return;
    }
    if (await guardar('tarifa', { modelo: c.modelo, entrada, salida, entrada_cache: cache })) {
      toast.success('Tarifa cargada. El costo se calcula desde ahora.');
      tarifaEntrada = tarifaCache = tarifaSalida = '';
    }
  }

  async function guardarTope() {
    const tope = topeNuevo.trim() === '' ? null : parseFloat(topeNuevo);
    if (tope !== null && !(tope > 0)) {
      toast.error('El tope tiene que ser mayor que cero. Dejalo vacío para sacarlo.');
      return;
    }
    if (await guardar('tope', { tope })) {
      toast.success(tope === null ? 'Tope quitado.' : 'Tope guardado.');
      topeNuevo = '';
    }
  }
</script>

<PageHeader title="Consumo">
  {#snippet sub()}
    Uso del asistente y gasto por tokens, de los últimos 30 días.
  {/snippet}
</PageHeader>

{#if data.error || !c}
  <p class="aviso-error">⚠️ {data.error ?? 'No hay datos de consumo.'}</p>
{:else}
  <div class="v2-pad" style="padding-top:14px;padding-bottom:32px;display:flex;flex-direction:column;gap:14px">

    <!-- ===== franja: solo cuando falta la tarifa ===================== -->
    {#if sinTarifa}
      <div class="franja">
        <span class="franja-icono"><AlertCircle size={17} /></span>
        <div style="flex:1;min-width:0">
          <div style="font-weight:700;font-size:13.5px">Sin tarifa para el modelo en producción</div>
          <p style="margin:2px 0 0;font-size:12.5px;line-height:1.5">
            Se están generando tokens, pero el costo no se puede calcular porque no hay tarifa
            cargada para <span class="v2-num">{c.modelo}</span>. Los tokens de abajo son reales;
            el gasto, no.
          </p>
        </div>
        <a href="#cargar-tarifa" class="v2-btn v2-btn-primary" style="flex:none">Cargar tarifa</a>
      </div>
    {/if}

    <!-- ===== tarjetas ================================================ -->
    <div class="tarjetas">
      <div class="v2-card tarjeta" class:destacada={!sinTarifa}>
        <div class="rotulo">Gasto del mes (USD)</div>
        {#if sinTarifa}
          <div class="cifra apagada">—</div>
          <Pill tone="clay">Sin tarifa configurada</Pill>
          <div class="pie">No se puede calcular</div>
        {:else}
          <div class="cifra">{usd(c.gastado)}</div>
          {#if c.tope}
            <div class="pie">{(c.porcentaje * 100).toFixed(0)}% del tope mensual</div>
          {:else}
            <div class="pie">Sin tope configurado</div>
          {/if}
        {/if}
      </div>

      <div class="v2-card tarjeta">
        <div class="rotulo">Tope mensual (USD)</div>
        {#if c.tope}
          <div class="cifra">{usd(c.tope)}</div>
          <div class="pie">Al alcanzarlo, las conversaciones pasan a una persona</div>
        {:else}
          <div class="cifra apagada">Sin límite</div>
          <div class="pie">No hay red de contención</div>
        {/if}
      </div>

      <div class="v2-card tarjeta">
        <div class="rotulo">Estado</div>
        {#if sinTarifa}
          <Pill tone="clay">Sin tarifa</Pill>
          <div class="pie">El costo no se calcula hasta cargar la tarifa del modelo.</div>
        {:else if sinTope}
          <Pill tone="slate">Sin tope</Pill>
          <div class="pie">El asistente no se frena por gasto.</div>
        {:else if frenado}
          <Pill tone="rust">Frenado</Pill>
          <div class="pie">Se alcanzó el tope del mes.</div>
        {:else if estado === 'avisar'}
          <Pill tone="clay">Cerca del tope</Pill>
          <div class="pie">Queda {usd(c.tope - c.gastado)} de margen.</div>
        {:else}
          <Pill tone="moss">Normal</Pill>
          <div class="pie">Dentro del tope del mes.</div>
        {/if}
      </div>

      <div class="v2-card tarjeta">
        <div class="rotulo"><MessagesSquare size={13} /> Mensajes (turnos)</div>
        <div class="cifra">{(c.totales.n_mensajes || 0).toLocaleString('es-CO')}</div>
        <div class="pie">
          {dias.length ? `Promedio diario: ${Math.round(c.totales.n_mensajes / dias.length)}` : 'Sin datos todavía'}
        </div>
      </div>

      <div class="v2-card tarjeta">
        <div class="rotulo"><Target size={13} /> Tokens totales</div>
        <div class="cifra">{miles(c.totales.tokens_entrada + c.totales.tokens_salida)}</div>
        <div class="pie">
          Entrada: {miles(c.totales.tokens_entrada)} · Salida: {miles(c.totales.tokens_salida)}
        </div>
      </div>
    </div>

    <!-- ===== desglose por origen, servicio y modelo ==================
         Lo que `usage_daily` no podía dar: esa tabla agrega por (empresa,
         día) y nada más, así que no sabía de qué servicio ni de qué modelo
         venía el gasto.

         La separación por ORIGEN es la que importa leer primero: sólo
         producción cuenta para el tope. Una corrida de casos dorados gasta
         dinero real y aparece acá, pero no puede frenar a la empresa.

         Si la migración todavía no corrió, `desglose` llega vacío y esta
         sección no se dibuja: la pantalla queda exactamente como estaba. -->
    {#if hayDesglose}
      <div class="v2-card" style="padding:16px 18px;margin-bottom:14px">
        <div class="v2-label" style="margin-bottom:12px">
          Desglose por origen y servicio
        </div>

        <div class="desglose-origen">
          {#each porOrigen as o (o.origen)}
            <div class="origen" class:facturable={o.origen === 'production'}>
              <span class="origen-nombre">{ORIGEN_ES[o.origen] ?? o.origen}</span>
              <span class="origen-costo">{usdFino(o.costo)}</span>
              <span class="origen-n">{(o.n ?? 0).toLocaleString('es-CO')} llamadas</span>
            </div>
          {/each}
        </div>
        {#if costoNoFacturable > 0}
          <p class="nota-origen">
            De ese total, <b>{usdFino(costoProduccion)}</b> es lo que cuenta para el
            tope. {usdFino(costoNoFacturable)} se gastaron en pruebas y evaluaciones:
            son dinero real, pero no frenan la atención.
          </p>
        {/if}

        {#if porServicio.length}
          <table class="tabla-desglose">
            <thead>
              <tr><th>Servicio</th><th>Origen</th><th class="num">Llamadas</th><th class="num">Costo</th></tr>
            </thead>
            <tbody>
              {#each porServicio as s (s.servicio + s.origen)}
                <tr>
                  <td>{SERVICIO_ES[s.servicio] ?? s.servicio}</td>
                  <td class="tenue">{ORIGEN_ES[s.origen] ?? s.origen}</td>
                  <td class="num">{(s.n ?? 0).toLocaleString('es-CO')}</td>
                  <td class="num">{usdFino(s.costo)}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        {/if}

        {#if porModelo.length}
          <table class="tabla-desglose">
            <thead>
              <tr><th>Proveedor</th><th>Modelo</th><th class="num">Llamadas</th><th class="num">Costo</th></tr>
            </thead>
            <tbody>
              {#each porModelo as m (m.proveedor + m.modelo)}
                <tr>
                  <td>{m.proveedor}</td>
                  <td>{m.modelo}</td>
                  <td class="num">{(m.n ?? 0).toLocaleString('es-CO')}</td>
                  <td class="num">
                    {#if m.con_tarifa}{usdFino(m.costo)}{:else}<span class="aviso-tarifa">sin tarifa</span>{/if}
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        {/if}

        <!-- "Hubo gasto y no sabemos cuánto" NO es lo mismo que "no hubo
             gasto", y antes las dos cosas se veían como un cero. -->
        {#if sinTarifaDetalle.length}
          <p class="nota-sin-tarifa">
            Hay consumo sin tarifa cargada: su costo no se puede calcular y
            queda fuera de todos los totales de arriba.
            {#each sinTarifaDetalle as t (t.proveedor + t.modelo)}
              <b>{t.proveedor}/{t.modelo}</b> ({(t.tokens ?? 0).toLocaleString('es-CO')} tokens).
            {/each}
          </p>
        {/if}
      </div>
    {/if}

    <!-- ===== gráfico + medidor + panel de estado ===================== -->
    <div class="fila-media">
      <div class="v2-card" style="padding:16px 18px;min-width:0">
        <div class="v2-label" style="margin-bottom:12px">Tendencia diaria (últimos 30 días)</div>
        {#if dias.length === 0}
          <div class="vacio">
            Todavía no hay consumo registrado. Esta pantalla se llena sola a medida que
            el asistente atiende.
          </div>
        {:else}
          <div class="leyenda">
            <span><i class="punto entrada"></i>Tokens de entrada</span>
            <span><i class="punto salida"></i>Tokens de salida</span>
            <!-- Sin tarifa NO se dibuja la serie de costo: seria una recta en
                 cero ocupando un eje entero, afirmando que no se gasto nada. -->
            {#if !sinTarifa}<span><i class="punto costo"></i>Costo (USD)</span>{/if}
          </div>
          <div class="grafico">
            {#each [...dias].reverse() as d (d.dia)}
              <div class="columna" title="{fecha(d.dia)}: {miles(d.tokens_entrada + d.tokens_salida)} tokens">
                <div class="barras">
                  <span class="barra entrada" style="height:{(d.tokens_entrada / maxTokens) * 100}%"></span>
                  <span class="barra salida" style="height:{(d.tokens_salida / maxTokens) * 100}%"></span>
                </div>
              </div>
            {/each}
          </div>
          <div class="eje">
            <span>{fecha(dias[dias.length - 1].dia)}</span>
            <span>{fecha(dias[0].dia)}</span>
          </div>
        {/if}
      </div>

      {#if hayMedidor}
        <div class="v2-card" style="padding:16px 18px;text-align:center">
          <div class="v2-label" style="margin-bottom:14px">Uso del tope mensual</div>
          <div class="medidor" style="--pct:{Math.min(1, c.porcentaje)}"
               class:alto={estado === 'avisar'} class:tope={frenado}>
            <span>{(c.porcentaje * 100).toFixed(0)}%</span>
          </div>
          <div class="pie" style="margin-top:10px">
            {usd(c.gastado)} de {usd(c.tope)}
          </div>
        </div>
      {/if}

      <div style="display:flex;flex-direction:column;gap:14px;min-width:0">
        {#if frenado}
          <div class="v2-card panel-frenado">
            <div class="panel-cabeza">
              <span style="font-weight:700">Asistente frenado</span>
              <Pill tone="rust">Activo</Pill>
            </div>
            <dl class="v2-kv" style="margin:0;font-size:12.5px">
              <dt>Desde</dt>
              <dd>{frenadoDesde ? fecha(frenadoDesde) : 'este mes'}</dd>
              <dt>Motivo</dt>
              <dd>Se alcanzó el tope de gasto mensual.</dd>
              <dt>Qué pasa</dt>
              <dd>Las conversaciones no pasan por el modelo y quedan marcadas para
                que las tome una persona.</dd>
            </dl>
          </div>
        {/if}

        <div class="v2-card" style="padding:14px 16px">
          <div class="v2-label" style="margin-bottom:10px">Modelo en producción</div>
          <div style="display:flex;align-items:center;gap:8px">
            <Cpu size={15} style="color:var(--v2-slate)" />
            <span class="v2-num" style="font-weight:700;font-size:13px">{c.modelo}</span>
          </div>
          {#if c.tarifa}
            <div class="pie" style="margin-top:6px">
              Por millón de tokens: {usd(c.tarifa.entrada)} entrada nueva{#if c.tarifa.entrada_cache != null} ·
              {usd(c.tarifa.entrada_cache)} cacheada{/if} · {usd(c.tarifa.salida)} salida
            </div>
            {#if c.tarifa.entrada_cache == null}
              <div class="pie" style="margin-top:4px">
                Sin precio de entrada cacheada: se cobra todo como nueva, así que el gasto
                mostrado es mayor que el real.
              </div>
            {/if}
          {:else}
            <div style="margin-top:8px"><Pill tone="clay">Sin tarifa cargada</Pill></div>
          {/if}
        </div>
      </div>
    </div>

    <!-- ===== tres cifras de contexto ================================= -->
    <div class="v2-card tres-cifras">
      <div>
        <div class="rotulo"><Wrench size={13} /> Llamadas a herramientas</div>
        <div class="cifra chica">{(c.herramientas.n || 0).toLocaleString('es-CO')}</div>
        <div class="pie">
          {c.herramientas.p95_ms ? `p95: ${(c.herramientas.p95_ms / 1000).toFixed(1)} s` : 'sin duraciones'}
        </div>
      </div>
      <div>
        <div class="rotulo"><Users size={13} /> Conversaciones</div>
        <div class="cifra chica">{(c.conversaciones || 0).toLocaleString('es-CO')}</div>
        <div class="pie">En los últimos {c.dias} días</div>
      </div>
      <div>
        <div class="rotulo">Ajustes</div>
        <div style="display:flex;flex-direction:column;gap:4px;margin-top:6px">
          <a href="#cargar-tarifa" class="enlace">Cargar o cambiar la tarifa</a>
          <a href="#configurar-tope" class="enlace">Configurar el tope mensual</a>
        </div>
      </div>
    </div>

    <!-- ===== tabla + explicación ===================================== -->
    <div class="fila-baja">
      <div class="v2-card" style="padding:0;overflow:hidden;min-width:0">
        <div class="v2-label" style="padding:14px 16px 10px">Detalle diario</div>
        {#if dias.length === 0}
          <div class="vacio" style="padding:0 16px 16px">Sin días registrados todavía.</div>
        {:else}
          <div style="overflow-x:auto">
            <table class="tabla">
              <thead>
                <tr>
                  <th>Fecha</th><th>Turnos</th><th>Entrada</th><th>Salida</th>
                  <th>Total</th><th>Costo</th>
                </tr>
              </thead>
              <tbody>
                {#each dias.slice(0, 8) as d (d.dia)}
                  <tr>
                    <td>{fecha(d.dia)}</td>
                    <td class="v2-num">{d.n_mensajes}</td>
                    <td class="v2-num">{d.tokens_entrada.toLocaleString('es-CO')}</td>
                    <td class="v2-num">{d.tokens_salida.toLocaleString('es-CO')}</td>
                    <td class="v2-num">{(d.tokens_entrada + d.tokens_salida).toLocaleString('es-CO')}</td>
                    <td class="v2-num">{sinTarifa ? '—' : usd(d.costo_usd)}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {/if}
      </div>

      <div style="display:flex;flex-direction:column;gap:14px;min-width:0">
        {#if sinTarifa}
          <div class="v2-card nota" id="cargar-tarifa">
            <div style="display:flex;gap:8px;align-items:flex-start">
              <Info size={15} style="flex:none;margin-top:2px" />
              <div>
                <div style="font-weight:700;font-size:13px">¿Por qué el costo aparece vacío?</div>
                <p style="margin:4px 0 0;font-size:12.5px;line-height:1.5">
                  No hay tarifa cargada para <span class="v2-num">{c.modelo}</span>. Los tokens
                  que ves son reales; el costo <strong>no se estima</strong>, porque un número
                  inventado se vería igual de real que uno correcto.
                </p>
              </div>
            </div>
          </div>
        {/if}

        <div class="v2-card" style="padding:14px 16px" id={sinTarifa ? undefined : 'cargar-tarifa'}>
          <div class="v2-label" style="margin-bottom:8px">
            Tarifa de {c.modelo}
          </div>
          <p class="pie" style="margin:0 0 8px">
            USD por millón de tokens, como los publica el proveedor. La entrada
            <strong>cacheada</strong> es opcional pero cambia mucho la cuenta: acá casi todo el
            prompt se repite turno a turno, y un token cacheado puede costar 30 veces menos.
            Si se deja vacío se cobra todo como entrada nueva.
          </p>
          <div class="campos-tarifa">
            <label>Entrada nueva
              <input class="v2-input" type="number" step="0.001" min="0"
                     placeholder="0.44" bind:value={tarifaEntrada} /></label>
            <label>Entrada cacheada
              <input class="v2-input" type="number" step="0.001" min="0"
                     placeholder="0.014" bind:value={tarifaCache} /></label>
            <label>Salida
              <input class="v2-input" type="number" step="0.001" min="0"
                     placeholder="1.32" bind:value={tarifaSalida} /></label>
          </div>
          <button class="v2-btn v2-btn-primary" style="margin-top:8px"
                  onclick={guardarTarifa} disabled={guardando}>Guardar tarifa</button>
        </div>

        <div class="v2-card" style="padding:14px 16px" id="configurar-tope">
          <div class="v2-label" style="margin-bottom:8px">Tope mensual</div>
          <p class="pie" style="margin:0 0 8px">
            Al alcanzarlo el asistente deja de responder solo y las conversaciones pasan a una
            persona. Vacío = sin tope.
          </p>
          <div style="display:flex;gap:8px">
            <input class="v2-input" type="number" step="1" min="0" style="flex:1"
                   placeholder={c.tope ? String(c.tope) : 'Sin tope'} bind:value={topeNuevo} />
            <button class="v2-btn" onclick={guardarTope} disabled={guardando}>Guardar</button>
          </div>
        </div>
      </div>
    </div>
  </div>
{/if}

<style>
  .aviso-error {
    margin: 16px 18px; padding: 10px 14px; border-radius: 6px;
    background: color-mix(in srgb, var(--v2-rust) 10%, transparent);
    color: var(--v2-rust); font-size: 13px;
  }

  .franja {
    display: flex; align-items: center; gap: 12px; padding: 12px 16px;
    border-radius: 8px;
    background: color-mix(in srgb, var(--v2-clay) 10%, transparent);
    border: 1px solid color-mix(in srgb, var(--v2-clay) 30%, transparent);
    color: var(--v2-ink);
  }
  .franja-icono {
    display: grid; place-items: center; width: 28px; height: 28px; flex: none;
    border-radius: 50%; background: var(--v2-clay); color: #fff;
  }

  .tarjetas { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; }
  .tarjeta { padding: 14px 16px; display: flex; flex-direction: column; gap: 6px; }
  .tarjeta.destacada { border-color: color-mix(in srgb, var(--v2-accent, #2563eb) 35%, transparent); }

  .rotulo {
    display: flex; align-items: center; gap: 5px;
    font-size: 11.5px; color: var(--v2-slate);
    text-transform: uppercase; letter-spacing: .4px;
  }
  .cifra { font-size: 26px; font-weight: 700; letter-spacing: -.5px; font-variant-numeric: tabular-nums; }
  .cifra.chica { font-size: 20px; }
  .cifra.apagada { color: var(--v2-slate); font-size: 22px; }
  .pie { font-size: 11.5px; color: var(--v2-slate); line-height: 1.45; }

  .fila-media { display: grid; grid-template-columns: 2fr 1fr 1fr; gap: 14px; align-items: start; }
  .fila-baja { display: grid; grid-template-columns: 2fr 1fr; gap: 14px; align-items: start; }
  @media (max-width: 1100px) {
    .fila-media, .fila-baja { grid-template-columns: 1fr; }
  }

  .leyenda { display: flex; gap: 14px; font-size: 11.5px; color: var(--v2-slate); margin-bottom: 10px; }
  .leyenda span { display: flex; align-items: center; gap: 5px; }
  .punto { width: 9px; height: 3px; border-radius: 2px; display: inline-block; }
  .punto.entrada { background: #3b82f6; }
  .punto.salida { background: #34d399; }
  .punto.costo { background: var(--v2-slate); }

  .grafico { display: flex; align-items: flex-end; gap: 3px; height: 150px; }
  .columna { flex: 1; height: 100%; display: flex; align-items: flex-end; }
  .barras { display: flex; align-items: flex-end; gap: 1px; width: 100%; height: 100%; }
  .barra { flex: 1; border-radius: 2px 2px 0 0; min-height: 2px; }
  .barra.entrada { background: #3b82f6; }
  .barra.salida { background: #34d399; }
  .eje {
    display: flex; justify-content: space-between;
    font-size: 11px; color: var(--v2-slate); margin-top: 6px;
  }

  /* Anillo simple con conic-gradient: sin librería, y el porcentaje entra por
     variable CSS para que el estado lo controle el servidor y no el estilo. */
  .medidor {
    width: 132px; height: 132px; margin: 0 auto; border-radius: 50%;
    display: grid; place-items: center;
    background: conic-gradient(var(--tono, #3b82f6) calc(var(--pct) * 360deg),
                               var(--v2-line-soft) 0);
  }
  .medidor::before {
    content: ''; grid-area: 1/1; width: 104px; height: 104px;
    border-radius: 50%; background: var(--v2-surface, #fff);
  }
  .medidor span {
    grid-area: 1/1; font-size: 24px; font-weight: 700;
    font-variant-numeric: tabular-nums;
  }
  .medidor.alto { --tono: var(--v2-clay); }
  .medidor.tope { --tono: var(--v2-rust); }

  .panel-frenado {
    padding: 14px 16px;
    border-color: color-mix(in srgb, var(--v2-rust) 32%, transparent);
    background: color-mix(in srgb, var(--v2-rust) 6%, transparent);
  }
  .panel-cabeza { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }

  .tres-cifras {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 18px; padding: 14px 18px;
  }

  .nota {
    padding: 14px 16px;
    background: color-mix(in srgb, var(--v2-accent, #2563eb) 6%, transparent);
    border-color: color-mix(in srgb, var(--v2-accent, #2563eb) 22%, transparent);
  }

  .campos-tarifa { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
  .campos-tarifa label {
    display: flex; flex-direction: column; gap: 4px;
    font-size: 11px; color: var(--v2-slate);
  }

  .enlace { font-size: 12.5px; color: var(--v2-accent, #2563eb); text-decoration: none; }
  .enlace:hover { text-decoration: underline; }

  .vacio { font-size: 12.5px; color: var(--v2-slate); line-height: 1.5; padding: 20px 0; }

  .tabla { width: 100%; border-collapse: collapse; font-size: 12.5px; }
  .tabla th {
    text-align: left; font-size: 10.5px; text-transform: uppercase; letter-spacing: .4px;
    color: var(--v2-slate); padding: 8px 16px; border-bottom: 1px solid var(--v2-line-soft);
    white-space: nowrap;
  }
  .tabla td { padding: 9px 16px; border-bottom: 1px solid var(--v2-line-soft); white-space: nowrap; }
  .tabla tr:last-child td { border-bottom: none; }

  /* ===== desglose ===== */
  .desglose-origen { display:flex; flex-wrap:wrap; gap:10px; margin-bottom:10px; }
  .origen {
    display:flex; flex-direction:column; gap:1px;
    padding:8px 12px; border-radius:8px;
    border:1px solid var(--v2-line, #e2e8f0);
    min-width:140px;
  }
  /* Lo facturable se distingue del resto: es la única cifra que puede frenar
     la atención, y mezclarla con las otras dos invita a leer el total como si
     todo contara igual. */
  .origen.facturable { border-color:var(--v2-slate, #475569); }
  .origen-nombre { font-size:0.75rem; color:var(--v2-muted, #64748b); }
  .origen-costo { font-size:1.05rem; font-weight:600; }
  .origen-n { font-size:0.7rem; color:var(--v2-muted, #64748b); }
  .nota-origen, .nota-sin-tarifa {
    margin:0 0 12px; font-size:0.8125rem; line-height:1.5;
    color:var(--v2-slate, #475569);
  }
  .nota-sin-tarifa { color:var(--v2-muted, #64748b); }
  .tabla-desglose {
    width:100%; border-collapse:collapse; margin:10px 0 0; font-size:0.8125rem;
  }
  .tabla-desglose th {
    text-align:left; font-weight:600; font-size:0.7rem; padding:4px 8px;
    color:var(--v2-muted, #64748b);
    border-bottom:1px solid var(--v2-line, #e2e8f0);
  }
  .tabla-desglose td { padding:5px 8px; border-bottom:1px solid var(--v2-line, #f1f5f9); }
  .tabla-desglose .num { text-align:right; font-variant-numeric:tabular-nums; }
  .tabla-desglose .tenue { color:var(--v2-muted, #64748b); }
  .aviso-tarifa { color:var(--v2-muted, #64748b); font-style:italic; }
</style>
