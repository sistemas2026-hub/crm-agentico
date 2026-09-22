<script>
  /**
   * Qué se le hizo al equipo del cliente en esta conversación, y si funcionó.
   *
   * EL ESTADO DEL ENLACE SE LEE EN VIVO, desde el 21/09/2026. Antes este
   * panel sólo mostraba el veredicto de las acciones ya ejecutadas, y este
   * comentario decía que traer la medición en vivo convertiría a la Bandeja
   * en una segunda fuente de verdad. No es lo que pasa: el motor consulta y
   * NO guarda nada, así que no hay segunda copia que pueda contradecir a la
   * primera. Lo que sí hay que sostener es la hora: cada medición se muestra
   * con su `leido_en`, porque un valor óptico sin su hora es una afirmación
   * sobre el presente que puede tener cinco minutos.
   *
   * NO SE CONSULTA SOLA SIEMPRE. El proveedor pide no usar estas rutas en
   * bucle, así que la lectura automática ocurre únicamente cuando la
   * conversación está en manos de una persona --que es cuando el diagnóstico
   * se usa para decidir-- y en el resto queda el botón. El motor cachea cinco
   * minutos por equipo.
   *
   * EL PING SIGUE SIN ESTAR, y no es por falta de tiempo: medido dos veces en
   * producción, el mismo equipo sano devuelve `1 de 3`, `2 de 3` y `3 de 3`
   * en corridas seguidas, y un reinicio real y confirmado dejó el ping igual
   * antes y después. Un botón que devuelve eso invita a concluir lo que no se
   * puede concluir.
   */
  import { CircleCheck, CircleX, CircleHelp, Clock, RefreshCw, Power,
           TriangleAlert, Copy, Check } from '@lucide/svelte';
  import { lineaDeAccion } from '$lib/conversaciones/red.js';
  import { medicionDe, enlaceCaido, potenciaAtenuada } from '$lib/conversaciones/optica.js';

  let {
    acciones = [],
    serial = null,
    /** La lectura óptica que trajo el server load, o su motivo de ausencia. */
    optica = null,
    conversacionId = ''
  } = $props();

  const lineas = $derived(acciones.map(lineaDeAccion));

  /* La lectura que se está mostrando. Arranca con la del server load y la
     reemplaza la del botón: una sola fuente para el panel, así no puede
     quedar la hora vieja al lado del valor nuevo. */
  let lectura = $state(optica);
  $effect(() => { lectura = optica; });

  let consultando = $state(false);
  let errorConsulta = $state('');

  async function consultarAhora() {
    if (consultando || !conversacionId) return;
    consultando = true;
    errorConsulta = '';
    try {
      const r = await fetch(`/api/conversaciones/${conversacionId}/optica?forzar=1`);
      const cuerpo = await r.json();
      if (!r.ok) throw new Error(cuerpo?.error || 'No se pudo consultar el equipo.');
      lectura = cuerpo;
      if (!cuerpo.disponible) errorConsulta = MOTIVO[cuerpo.motivo] ?? 'No se pudo leer el equipo.';
    } catch (/** @type {any} */ e) {
      errorConsulta = e?.message || 'No se pudo consultar el equipo.';
    } finally {
      consultando = false;
    }
  }

  /** Por qué no hay medición. Cada motivo dice algo distinto y ninguno es
      "error": que el asistente no haya identificado el equipo no es una falla
      del sistema, y decirlo así manda a alguien a buscar un problema que no
      existe. */
  const MOTIVO = {
    sin_equipo: 'Todavía no se identificó el equipo de este cliente.',
    sin_herramienta: 'Esta empresa no tiene conectado su sistema de red.',
    sin_conexion: 'El sistema de red no respondió.',
    no_consultada: 'Sin consultar.',
    sin_respuesta: 'Sin consultar.'
  };

  /* LA LECTURA SE TRADUCE EN 'optica.js', NO ACA.
     Estaba en este archivo y por eso nadie pudo probarla: el 22/09/2026 se vio
     en produccion que el distintivo del estado decia «TRUE» --el `status` del
     SOBRE de SmartOLT, que significa "la llamada salio bien"-- y que la
     potencia no aparecia nunca, porque se buscaba `signal_1310` donde la API
     devuelve `onu_signal_1490`. Las dos cosas tienen ahora una guarda que
     falla si vuelven. */
  const medicion = $derived(medicionDe(lectura));

  /* ── reiniciar el equipo ───────────────────────────────────────────────
     Tres estados y nada más: pidiendo (con el motivo), en curso, y pedido.
     No hay un cuarto estado "reiniciado con éxito" a propósito: eso no se
     sabe todavía cuando el sistema del ISP contesta. Lo dice la comprobación
     posterior, que ya existe y aparece en "Acciones sobre el equipo". */
  let pidiendoReinicio = $state(false);
  let motivoReinicio = $state('');
  let reiniciando = $state(false);
  let errorReinicio = $state('');
  let reinicioPedido = $state(false);

  async function reiniciar() {
    const motivo = motivoReinicio.trim();
    if (reiniciando || !motivo || !conversacionId) return;
    reiniciando = true;
    errorReinicio = '';
    try {
      const r = await fetch(`/api/conversaciones/${conversacionId}/equipo/reiniciar`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ motivo })
      });
      const cuerpo = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(cuerpo?.error || 'No se pudo reiniciar el equipo.');
      reinicioPedido = true;
      pidiendoReinicio = false;
      motivoReinicio = '';
    } catch (/** @type {any} */ e) {
      errorReinicio = e?.message || 'No se pudo reiniciar el equipo.';
    } finally {
      reiniciando = false;
    }
  }

  /* El veredicto del enlace y el de la potencia son DOS cosas distintas: una
     ONU puede estar Online y aun así con la señal al borde, que es justamente
     el caso que conviene ver antes de que se caiga. */
  const caido = $derived(enlaceCaido(medicion) === true);

  /** El umbral de la empresa, o null si no definió ninguno. */
  const umbral = $derived(
    lectura?.umbral_rx_dbm === null || lectura?.umbral_rx_dbm === undefined
      ? null
      : Number(lectura.umbral_rx_dbm)
  );

  /* ¿Está atenuado? null = no se puede afirmar (sin umbral, o sin lectura).
     Es la distinción de siempre: "no sabemos" no es "está bien". */
  const atenuado = $derived(potenciaAtenuada(medicion, umbral));

  /** Dónde está conectado el equipo, o null si no vino. */
  const topologia = $derived(lectura?.optica?.topologia ?? null);

  /* LA ESCALA DE LA BARRA, construida sólo con números reales.
     La referencia dibuja un medidor con un rango de industria (-14 a -24 dBm)
     que ningún sistema nuestro declara. Acá el eje se arma con los dos
     únicos valores ciertos --la lectura y el umbral que declara la empresa--
     más dos dB de aire a cada lado para que ninguna de las dos marcas quede
     pegada al borde. Los extremos se rotulan con su valor, así que la
     posición de la marca se puede comprobar leyendo el eje.

     En dBm, menos negativo es mejor: el lado izquierdo es el bueno.
     Sin umbral no hay eje y no se dibuja nada. */
  const escala = $derived.by(() => {
    if (!medicion || medicion.rx === null || umbral === null) return null;
    const mejor = Math.max(medicion.rx, umbral) + 2;
    const peor = Math.min(medicion.rx, umbral) - 2;
    const largo = mejor - peor;
    if (!(largo > 0)) return null;
    const pct = (/** @type {number} */ v) =>
      Math.min(100, Math.max(0, ((mejor - v) / largo) * 100));
    return {
      mejor: Number(mejor.toFixed(1)),
      peor: Number(peor.toFixed(1)),
      pctValor: pct(medicion.rx),
      pctUmbral: pct(umbral)
    };
  });


  let copiado = $state('');
  async function copiar(/** @type {string} */ valor) {
    try {
      await navigator.clipboard.writeText(valor);
      copiado = valor;
      setTimeout(() => { if (copiado === valor) copiado = ''; }, 1500);
    } catch {
      // Portapapeles bloqueado (sin https o sin permiso): el valor está a la
      // vista y se puede seleccionar a mano. No se avisa de un fallo que no
      // impide nada.
    }
  }

  function haceCuanto(/** @type {string} */ iso) {
    if (!iso) return '';
    const seg = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
    if (seg < 60) return `hace ${seg}s`;
    if (seg < 3600) return `hace ${Math.round(seg / 60)} min`;
    return `hace ${Math.round(seg / 3600)} h`;
  }

  function hora(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    return Number.isNaN(d.getTime())
      ? ''
      : d.toLocaleString('es-CO', {
          day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'
        });
  }
</script>

<section class="red">
  <!-- ── LA BANDA DE PROCEDENCIA ──────────────────────────────────────────
       «Confirmado — en vivo desde SmartOLT», con el punto y el distintivo
       LIVE. Es el elemento central de la pantalla canónica de la referencia y
       no es decoración: separa lo que un sistema conectado acaba de responder
       de lo que sería una suposición.

       La referencia pone debajo una SEGUNDA tarjeta, punteada y gris, con
       modelo de ONT, firmware, temperatura, voltaje y corriente de bias, y
       la rotula «STITCH MOCK / FUTURE DATA — NOT AVAILABLE TODAY · Design
       placeholder. Do not implement as real data». No se implementa, por
       orden expresa de la propia referencia: ninguno de esos cinco lo
       devuelve hoy ningún sistema conectado, y dibujarlos --aunque fuera en
       gris-- los convertiría en un dato que alguien va a leer.

       La topología (OLT, slot, puerto, PON) aparece allá marcada MOCK, y acá
       NO lo está: `consultar_topologia_ont` la trae de verdad desde
       `get_onu_details`. La referencia se hizo antes de que existiera esa
       herramienta. Va en esta sección, la de lo confirmado. -->
  <!-- ══════════════════════════════════════════════════════════════════════
       LA FORMA DE LA IMAGEN, CON LOS DATOS QUE SÍ EXISTEN

       Pedido explícito: que Equipo se vea como la tarjeta de la NOC Console
       --banda de alarma, unidad ONT, telemetría óptica con barra, las cuatro
       celdas, planta física y controles--. Eso es lo que hay abajo, sección
       por sección y en el mismo orden.

       LO ÚNICO QUE NO SE COPIA SON LOS NÚMEROS INVENTADOS. Cada fila que el
       sistema del ISP no devuelve hoy se dibuja igual, en su lugar, pero con
       un guion y en gris: la pantalla mantiene la forma y no afirma nada.
       Cuáles son y por qué, medido contra la API real (skill `smartolt-api`,
       verificada el 14/08/2026):

         modelo, firmware, voltaje, corriente de bias
             no están en ninguna de las respuestas verificadas de SmartOLT.
             No es que falte conectarlos: no existen del otro lado.

         temperatura, potencia Tx, Tx de la OLT, MAC
             SÍ existen, en 'Optical status' y 'ONU WAN Interfaces' de
             `get_onu_full_status_info`. Esta pantalla todavía no llama esa
             ruta --tarda ~10 s y el proveedor pide no usarla en bucle--, así
             que hoy salen vacías y se llenan cuando el motor las traiga.

       La diferencia entre las dos listas importa: la primera no se va a
       llenar nunca, la segunda es trabajo pendiente. Por eso el pie las
       nombra distinto.
       ══════════════════════════════════════════════════════════════════════ -->

  <!-- ── LA BANDA DE ALARMA ────────────────────────────────────────────────
       En la imagen es lo primero: fondo rojo, punto, «LOS ALARM ACTIVE» y el
       distintivo OFFLINE a la derecha. Acá dice lo mismo y sale de lo medido
       -- enlace caído o potencia por debajo del umbral de la empresa. Cuando
       no hay alarma, la banda es la de procedencia: qué sistema contestó. -->
  {#if medicion && (caido || atenuado === true)}
    <div class="alarma">
      <span class="alarma-punto" aria-hidden="true"></span>
      <span class="alarma-textos">
        <b>{caido ? 'Enlace óptico caído' : 'Potencia fuera de rango'}</b>
        <span class="alarma-sub">
          {#if caido}
            El equipo no responde en la OLT{medicion.desde ? ` desde ${medicion.desde}` : ''}
          {:else}
            {medicion.rx} dBm, por debajo del umbral de la empresa
          {/if}
        </span>
      </span>
      <span class="alarma-chip">{caido ? 'OFFLINE' : 'DEGRADADO'}</span>
    </div>
  {/if}

  <div class="procedencia">
    <span class="procedencia-punto" class:procedencia-punto-mal={!medicion} aria-hidden="true"></span>
    <span class="procedencia-rotulo">Confirmado — en vivo desde SmartOLT</span>
    {#if medicion}<span class="procedencia-vivo">LIVE</span>{/if}
  </div>

  {#if medicion}
    <!-- ── 1. LA UNIDAD ─────────────────────────────────────────────────── -->
    <div class="eq-seccion">
      <div class="eq-cabeza">
        <span class="panel-titulo">Unidad ONT / ONU</span>
        <span class="eq-marca">GPON</span>
      </div>

      <div class="panel-fila">
        <span class="panel-etiqueta">Estado</span>
        <span class="panel-valor con-punto">
          <span class="punto-enlace" class:punto-mal={caido} aria-hidden="true"></span>
          <b>{medicion.enlace ?? '—'}</b>
          {#if medicion.desde}<span class="desde">desde {medicion.desde}</span>{/if}
        </span>
      </div>

      <div class="panel-fila">
        <span class="panel-etiqueta">Modelo</span>
        <span class="panel-valor eq-sin">—</span>
      </div>

      {#if medicion.serial}
        <div class="panel-fila">
          <span class="panel-etiqueta">Serial GPON</span>
          <span class="panel-valor eq-serial">
            <span class="panel-chip">{medicion.serial}</span>
            <button
              type="button"
              class="copiar"
              title="Copiar el serial"
              onclick={() => copiar(medicion.serial)}
            >
              {#if copiado === medicion.serial}<Check size={12} />{:else}<Copy size={12} />{/if}
            </button>
          </span>
        </div>
      {/if}

      <div class="panel-fila">
        <span class="panel-etiqueta">MAC</span>
        <span class="panel-valor eq-sin">—</span>
      </div>

      <div class="panel-fila">
        <span class="panel-etiqueta">Firmware</span>
        <span class="panel-valor eq-sin">—</span>
      </div>

      {#if medicion.causaCaida}
        <div class="panel-fila">
          <span class="panel-etiqueta">Última caída</span>
          <span class="panel-valor">{medicion.causaCaida}</span>
        </div>
      {/if}
    </div>

    <!-- ── 2. LA TELEMETRÍA ÓPTICA ──────────────────────────────────────── -->
    <div class="eq-seccion">
      <div class="eq-cabeza">
        <span class="panel-titulo">Telemetría óptica</span>
        {#if lectura?.leido_en}
          <span class="eq-marca">Leído {haceCuanto(lectura.leido_en)}</span>
        {/if}
      </div>

      {#if medicion.rx !== null}
        <!-- EL VALOR GRANDE, como en la imagen: el número es el protagonista
             de la sección y no una fila más. -->
        <div class="rx-cabeza">
          <span class="panel-etiqueta">Potencia óptica (RX)</span>
          <b class="rx-grande" class:rx-mal={atenuado === true}>{medicion.rx} dBm</b>
        </div>

        <!-- ── LA BARRA ───────────────────────────────────────────────────
             La imagen dibuja una escala con el valor sobre ella. Acá la
             escala NO es un rango de industria inventado: se construye con
             los dos únicos números reales que hay --la medición y el umbral
             que declara la empresa-- más dos dB de aire a cada lado, y los
             dos extremos van rotulados con su valor. La marca gruesa es la
             lectura; la fina, el umbral.

             Sin umbral no hay barra. Una escala sin números propios es una
             regla dibujada a ojo, y sobre ella cualquier posición miente. -->
        {#if escala}
          <div class="rx-barra" role="img"
               aria-label="Potencia {medicion.rx} dBm; el umbral de la empresa es {umbral} dBm">
            <span class="rx-pista"></span>
            <span class="rx-umbral" style="left:{escala.pctUmbral}%"></span>
            <span class="rx-marca" class:rx-marca-mal={atenuado === true}
                  style="left:{escala.pctValor}%"></span>
          </div>
          <div class="rx-escala">
            <span>{escala.mejor} dBm</span>
            <span class="rx-escala-umbral">umbral {umbral}</span>
            <span>{escala.peor} dBm</span>
          </div>
        {/if}

        <div class="rx-pie">
          {#if medicion.veredicto}
            <span class="rx-chip" class:rx-chip-mal={atenuado === true}>{medicion.veredicto}</span>
          {/if}
          {#if medicion.clasificacion}
            <span class="rx-clasif">{medicion.clasificacion}</span>
          {/if}
        </div>

        {#if umbral === null && !medicion.veredicto}
          <!-- Sin umbral Y sin veredicto no se dice si está bien o mal: un
               veredicto con un número inventado es peor que ninguno. -->
          <p class="panel-nota">
            Esta empresa no definió un umbral óptico, así que la lectura se
            muestra sin veredicto y sin escala.
          </p>
        {/if}
      {/if}

      <!-- LAS CUATRO CELDAS de la imagen. Dos tienen dato hoy; las otras dos
           esperan la lectura profunda. Se dibujan las cuatro para que la
           rejilla no cambie de forma según lo que haya venido. -->
      <div class="eq-celdas">
        <div class="eq-celda">
          <span class="eq-celda-rotulo">Subida (1310 nm)</span>
          <b class="eq-celda-valor" class:eq-sin={medicion.rxSubida === null}>
            {medicion.rxSubida !== null ? `${medicion.rxSubida} dBm` : '—'}
          </b>
        </div>
        <div class="eq-celda">
          <span class="eq-celda-rotulo">Temperatura</span>
          <b class="eq-celda-valor eq-sin">—</b>
        </div>
        <div class="eq-celda">
          <span class="eq-celda-rotulo">Voltaje</span>
          <b class="eq-celda-valor eq-sin">—</b>
        </div>
        <div class="eq-celda">
          <span class="eq-celda-rotulo">Corriente de bias</span>
          <b class="eq-celda-valor eq-sin">—</b>
        </div>
      </div>
    </div>

    <!-- ── 3. LA PLANTA FÍSICA ──────────────────────────────────────────
         En la imagen estos campos son inventados; acá son reales --
         `consultar_topologia_ont` los trae de `get_onu_details`. Es la
         sección donde la referencia y nosotros nos cruzamos al revés: ellos
         la dibujan sin datos, nosotros tenemos los datos. -->
    {#if topologia}
      <div class="eq-seccion">
        <div class="eq-cabeza">
          <span class="panel-titulo">Planta física</span>
          {#if topologia.zone_name}<span class="eq-marca">{topologia.zone_name}</span>{/if}
        </div>

        {#if topologia.olt_name}
          <div class="panel-fila">
            <span class="panel-etiqueta">OLT</span>
            <span class="panel-valor panel-mono">{topologia.olt_name}</span>
          </div>
        {/if}
        {#if topologia.board !== undefined || topologia.port !== undefined}
          <div class="panel-fila">
            <span class="panel-etiqueta">Tarjeta / puerto</span>
            <span class="panel-valor panel-mono">{topologia.board ?? '—'} / {topologia.port ?? '—'}</span>
          </div>
        {/if}
        {#if topologia.onu !== undefined}
          <div class="panel-fila">
            <span class="panel-etiqueta">Índice ONU</span>
            <span class="panel-valor panel-mono">{topologia.onu}</span>
          </div>
        {/if}
        {#if topologia.odb_name}
          <div class="panel-fila">
            <span class="panel-etiqueta">Caja (CTO)</span>
            <span class="panel-valor panel-mono">{topologia.odb_name}</span>
          </div>
        {/if}
      </div>
    {/if}

    <!-- EL PIE, que separa las dos ausencias. No es lo mismo «esto no existe»
         que «esto todavía no lo pedimos», y una pantalla con seis guiones sin
         explicación se lee como rota. -->
    <p class="eq-pie">
      Sin dato: modelo, firmware, voltaje y corriente de bias no los devuelve
      el sistema de red. Temperatura y MAC sí existen, pero salen de una
      consulta profunda que esta pantalla todavía no hace.
    </p>
  {:else}
    <p class="vacio">{MOTIVO[lectura?.motivo] ?? 'Sin consultar.'}</p>
  {/if}

  <div class="opt-pie">
    <button
      type="button"
      class="v2-btn v2-btn-sm"
      onclick={consultarAhora}
      disabled={consultando || !conversacionId}
      aria-busy={consultando}
    >
      <RefreshCw size={12} />
      {consultando ? 'Consultando…' : 'Consultar ahora'}
    </button>
    {#if lectura?.leido_en}
      <span class="opt-hora">Leído {haceCuanto(lectura.leido_en)}</span>
    {/if}
  </div>
  {#if errorConsulta}
    <p class="opt-error">{errorConsulta}</p>
  {/if}

  <!-- REINICIAR CORTA EL SERVICIO DE ALGUIEN.
       El botón no ejecuta: abre la confirmación, y la confirmación pide un
       motivo. El motivo no es burocracia -- es el renglón que dentro de un
       mes contesta por qué alguien dejó a un cliente sin internet dos
       minutos.
       Y el diálogo NO es la garantía: quien llame la ruta directo no lo ve.
       Las condiciones reales están en el motor (control humano, dueño o
       ADMIN, conversación abierta, motivo). Acá sólo se pregunta. -->
  {#if medicion}
    {#if !pidiendoReinicio}
      <button
        type="button"
        class="v2-btn v2-btn-sm opt-reiniciar"
        onclick={() => { pidiendoReinicio = true; errorReinicio = ''; }}
      >
        <Power size={12} /> Reiniciar el equipo
      </button>
    {:else}
      <div class="opt-confirmar">
        <p class="opt-aviso">
          <TriangleAlert size={13} />
          El cliente pierde el servicio unos dos minutos.
        </p>
        <label class="opt-motivo">
          <span>Motivo (queda en el expediente)</span>
          <input
            type="text"
            bind:value={motivoReinicio}
            placeholder="Por qué hace falta reiniciar"
            maxlength="200"
          />
        </label>
        <div class="opt-acciones">
          <button
            type="button"
            class="v2-btn v2-btn-sm"
            onclick={() => { pidiendoReinicio = false; motivoReinicio = ''; errorReinicio = ''; }}
            disabled={reiniciando}
          >
            Cancelar
          </button>
          <button
            type="button"
            class="v2-btn v2-btn-sm v2-btn-danger"
            onclick={reiniciar}
            disabled={reiniciando || !motivoReinicio.trim()}
            aria-busy={reiniciando}
          >
            {reiniciando ? 'Reiniciando…' : 'Reiniciar'}
          </button>
        </div>
        {#if errorReinicio}<p class="opt-error">{errorReinicio}</p>{/if}
      </div>
    {/if}
    {#if reinicioPedido}
      <!-- 'Se pidió' y no 'se reinició': lo que se sabe es que el sistema del
           ISP aceptó la orden. Que el equipo volviera lo dice la comprobación
           posterior, que aparece abajo, en las acciones sobre el equipo. -->
      <p class="opt-ok">
        Reinicio pedido. Se comprueba solo en un par de minutos y el resultado
        aparece abajo.
      </p>
    {/if}
  {/if}

  <p class="panel-titulo opt-sep">Acciones sobre el equipo</p>

  {#if lineas.length === 0}
    <!-- Estado vacío honesto: no es que falte el dato, es que no se hizo nada.
         Distinguirlo de «no se pudo consultar» es justo lo que esta fase
         tiene que sostener. -->
    <p class="vacio">
      No se ejecutó ninguna acción sobre el equipo en esta conversación.
    </p>
  {:else}
    <ul class="acciones">
      {#each lineas as l, i (i)}
        <li class="accion accion-{l.tono}">
          <span class="icono" aria-hidden="true">
            {#if l.clave === 'confirmada'}<CircleCheck size={14} />
            {:else if l.clave === 'no_confirmada'}<CircleX size={14} />
            {:else if l.clave === 'pendiente'}<Clock size={14} />
            {:else}<CircleHelp size={14} />{/if}
          </span>
          <div class="cuerpo">
            <p class="nombre">{l.nombre}</p>
            <p class="veredicto">{l.texto}</p>
            {#if l.matiz}<p class="matiz">{l.matiz}</p>{/if}
            {#if l.porQue}<p class="porque">{l.porQue}</p>{/if}
            <p class="cuando">
              <time datetime={l.cuando}>{hora(l.cuando)}</time>{#if l.intentos}
                · {l.intentos}{/if}
            </p>
          </div>
        </li>
      {/each}
    </ul>
  {/if}

  <!-- El serial se muestra en la tarjeta "Identificadores", con su botón de
       copiar. Acá abajo salía una segunda vez, sin botón: el mismo dato dos
       veces en una columna de 304px. Se deja sólo cuando la tarjeta NO se
       dibujó -- es decir, cuando no hay medición pero el equipo sí está
       identificado. -->
  {#if serial && !medicion}
    <p class="serial">
      <span class="v2-sub">Equipo identificado</span>
      <span class="panel-mono">{serial}</span>
    </p>
  {/if}

  <!-- Esta nota decía que la potencia óptica y el estado de la ONU sólo se
       consultaban cuando el asistente los necesitaba, y que desde esta
       pantalla no se veían. Dejó de ser cierto el 21/09/2026 y una nota que
       describe mal lo que el usuario está viendo arriba es peor que ninguna. -->
  <p class="panel-nota">
    Estas mediciones se leen del sistema del ISP en el momento y no se guardan
    acá: por eso cada una viene con la hora en que se leyó. Se consultan solas
    cuando la conversación está en manos de una persona; en el resto, con el
    botón.
  </p>
</section>

<style>
  /* ── LA BANDA DE PROCEDENCIA ───────────────────────────────────────────
     Reemplaza al rótulo «Estado del enlace», que nombraba la sección pero no
     decía de dónde salía el dato -- que es la pregunta que decide si se manda
     un técnico. El punto se apaga cuando no hay medición: sin lectura no se
     afirma que haya nada en vivo. */
  .procedencia {
    display: flex;
    align-items: center;
    gap: 7px;
    padding-bottom: 9px;
    margin-bottom: 11px;
    border-bottom: 1px solid var(--bandeja-borde);
  }

  .procedencia-punto {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--bandeja-ok);
    flex: none;
  }
  .procedencia-punto-mal {
    background: var(--bandeja-texto-3);
  }

  .procedencia-rotulo {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--bandeja-texto);
    line-height: 1.3;
  }

  /* `margin-left:auto` y no un espaciador: el distintivo queda a la derecha
     sin importar cuánto envuelva el rótulo en una columna angosta. */
  .procedencia-vivo {
    margin-left: auto;
    flex: none;
    padding: 1px 5px;
    border: 1px solid color-mix(in srgb, var(--bandeja-ok) 30%, transparent);
    border-radius: 3px;
    background: color-mix(in srgb, var(--bandeja-ok) 10%, transparent);
    font-family: var(--bandeja-mono);
    font-size: 9.5px;
    font-weight: 600;
    letter-spacing: 0.04em;
    color: var(--bandeja-ok);
  }

  /* ── la medición óptica ────────────────────────────────────────────────
     Rótulo a la izquierda y valor a la derecha, en la misma retícula que el
     resto de los paneles de contexto. Denso: son siete renglones en una
     columna de 304px. */
  .optica {
    margin: 6px 0 0;
    display: flex;
    flex-direction: column;
    gap: 3px;
  }

  .opt-fila {
    display: grid;
    grid-template-columns: 5.5rem 1fr;
    gap: 8px;
    align-items: baseline;
    font-size: 11.5px;
  }



  /* El enlace es lo único de la ficha que es un veredicto, y va con palabra:
     el color refuerza, no informa. */
  .opt-estado {
    font-weight: 650;
    color: var(--bandeja-ok);
  }

  .opt-caido {
    color: var(--bandeja-error);
  }

  .opt-pie {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    margin-top: 8px;
  }

  /* Cuándo se leyó. Va al lado del botón y no escondida: es la diferencia
     entre un dato que sirve para decidir y uno que hay que volver a pedir. */
  .opt-hora {
    font-family: var(--bandeja-mono);
    font-size: 9.5px;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--bandeja-texto-3);
  }

  .opt-error {
    margin: 6px 0 0;
    font-size: 11px;
    color: var(--bandeja-aviso);
  }

  .opt-sep {
    margin-top: 14px;
    padding-top: 10px;
    border-top: 1px solid var(--bandeja-borde);
  }






  /* El veredicto del enlace, con palabra. Nunca sólo color. */
  .insignia {
    padding: 1px 6px;
    border: 1px solid var(--bandeja-borde);
    border-radius: var(--bandeja-radio-sm);
    background: var(--bandeja-superficie-suave);
    font-family: var(--bandeja-mono);
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--bandeja-ok);
    white-space: nowrap;
  }

  .insignia-mal {
    color: var(--bandeja-error);
    background: var(--bandeja-error-fondo);
    border-color: var(--bandeja-error-borde);
  }

  /* LA POTENCIA, EN GRANDE. Es el dato por el que se abre esta pestaña y en
     la referencia ocupa una línea entera. */
  .rx {
    margin: 2px 0 0;
    font-family: var(--bandeja-mono);
    font-size: 24px;
    font-weight: 700;
    line-height: 1.1;
    letter-spacing: -0.02em;
    font-variant-numeric: tabular-nums;
    color: var(--bandeja-texto);
  }

  .rx-mal {
    color: var(--bandeja-error);
  }

  /* Gris y en peso normal: acompana al numero, no compite con el. */
  .rx-clase {
    margin-left: 8px;
    font-family: var(--bandeja-sans);
    font-size: 11.5px;
    font-weight: 500;
    color: var(--bandeja-texto-2);
    letter-spacing: 0;
  }

  .rx-unidad {
    margin-left: 5px;
    font-size: 12px;
    font-weight: 600;
    color: var(--bandeja-texto-2);
  }

  .rx-umbral {
    margin: 2px 0 0;
    font-size: 10.5px;
    color: var(--bandeja-texto-2);
  }

  .rx-umbral-mal {
    color: var(--bandeja-error);
    font-weight: 600;
  }

  /* ── identificadores ───────────────────────────────────────────────── */
  .ident-fila {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 2px 6px;
    align-items: center;
  }

  .ident-rotulo {
    grid-column: 1 / -1;
    font-family: var(--bandeja-mono);
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: var(--bandeja-texto-2);
  }

  .ident-valor {
    padding: 3px 6px;
    border: 1px solid var(--bandeja-borde);
    border-radius: var(--bandeja-radio-sm);
    background: var(--bandeja-superficie-suave);
    font-size: 11.5px;
    overflow-wrap: anywhere;
  }

  .ident-copiar {
    display: grid;
    place-items: center;
    padding: 4px;
    border: 1px solid var(--bandeja-borde);
    border-radius: var(--bandeja-radio-sm);
    background: var(--bandeja-superficie);
    color: var(--bandeja-texto-2);
    cursor: pointer;
  }

  .ident-copiar:hover {
    color: var(--bandeja-texto);
    border-color: var(--bandeja-texto-3);
  }

  /* ── reiniciar ─────────────────────────────────────────────────────────
     El botón NO va en rojo: en reposo es una acción más, y el rojo se guarda
     para el momento en que de verdad se está por ejecutar. Un botón
     permanentemente rojo deja de avisar. */
  .opt-reiniciar {
    margin-top: 8px;
  }

  .opt-confirmar {
    margin-top: 8px;
    padding: 8px 10px;
    border: 1px solid var(--bandeja-error-borde);
    border-radius: var(--bandeja-radio-sm);
    background: var(--bandeja-error-fondo);
  }

  .opt-aviso {
    display: flex;
    align-items: flex-start;
    gap: 5px;
    margin: 0 0 8px;
    font-size: 11.5px;
    font-weight: 600;
    line-height: 1.35;
    color: var(--bandeja-error);
  }

  .opt-motivo {
    display: grid;
    gap: 3px;
    font-family: var(--bandeja-mono);
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: var(--bandeja-texto-2);
  }

  .opt-motivo input {
    font-family: var(--bandeja-sans);
    font-size: 12px;
    text-transform: none;
    letter-spacing: normal;
    color: var(--bandeja-texto);
    padding: 5px 7px;
    border: 1px solid var(--bandeja-borde);
    border-radius: var(--bandeja-radio-sm);
    background: var(--bandeja-superficie);
  }

  .opt-acciones {
    display: flex;
    justify-content: flex-end;
    gap: 6px;
    margin-top: 8px;
  }

  .opt-ok {
    margin: 8px 0 0;
    font-size: 11.5px;
    line-height: 1.4;
    color: var(--bandeja-ok);
  }

  .red {
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--v2-line-soft);
  }


  .vacio {
    margin: 0;
    font-size: 12px;
    line-height: 1.45;
    color: var(--bandeja-texto-2);
  }

  .acciones {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .accion {
    display: flex;
    gap: 8px;
    padding: 8px 9px;
    border: 1px solid var(--bandeja-borde);
    border-radius: var(--bandeja-radio-sm);
  }
  .icono {
    flex: none;
    margin-top: 1px;
    color: var(--bandeja-texto-3);
  }
  .accion-ok .icono {
    color: var(--bandeja-ok);
  }
  .accion-mal .icono {
    color: var(--bandeja-error);
  }
  .accion-aviso .icono {
    color: var(--bandeja-aviso);
  }

  .cuerpo {
    min-width: 0;
  }

  .nombre {
    margin: 0;
    font-size: 12.5px;
    font-weight: 600;
    color: var(--bandeja-texto);
  }
  .veredicto {
    margin: 2px 0 0;
    font-size: 12px;
    line-height: 1.4;
    color: var(--bandeja-texto);
  }
  /* El matiz en el mismo cuerpo y no como nota al pie: si se separa, se lee
     como opcional -- y es justo la parte que evita cerrar el caso de más. */
  .matiz {
    margin: 3px 0 0;
    font-size: 11px;
    line-height: 1.4;
    color: var(--bandeja-texto-2);
    font-style: italic;
  }
  .porque {
    margin: 3px 0 0;
    font-size: 11.5px;
    line-height: 1.4;
    color: var(--bandeja-texto-2);
    overflow-wrap: anywhere;
  }
  .cuando {
    margin: 3px 0 0;
    font-family: var(--bandeja-mono);
    font-size: 10px;
    color: var(--bandeja-texto-3);
  }

  .serial {
    display: flex;
    flex-direction: column;
    gap: 3px;
    margin: 0;
  }
  .serial > .v2-sub {
    font-size: 11.5px;
  }



  .con-punto {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }

  /* Verde cuando el enlace responde. El punto acompaña a la palabra, no la
     reemplaza: 'Online' sigue escrito. */
  .punto-enlace {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--bandeja-ok);
    flex: none;
  }
  .punto-mal {
    background: var(--bandeja-error);
  }

  .desde {
    font-family: var(--bandeja-mono);
    font-size: 10px;
    color: var(--bandeja-texto-3);
  }



  .rx-chip {
    padding: 1px 5px;
    border-radius: 3px;
    border: 1px solid color-mix(in srgb, var(--bandeja-ok) 30%, transparent);
    background: color-mix(in srgb, var(--bandeja-ok) 10%, transparent);
    font-family: var(--bandeja-mono);
    font-size: 9.5px;
    font-weight: 600;
    color: var(--bandeja-ok);
    white-space: nowrap;
  }
  .rx-chip-mal {
    border-color: var(--bandeja-error-borde);
    background: var(--bandeja-error-fondo);
    color: var(--bandeja-error);
  }


  .id-con-copia {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    justify-content: flex-end;
  }


  /* ── LA FORMA DE LA IMAGEN ─────────────────────────────────────────────
     Secciones con filete, encabezado en versalita y una marca a la derecha;
     dentro, filas etiqueta/valor. Es la misma estructura de la tarjeta de la
     NOC Console, con los tokens congelados de la Bandeja. */
  .eq-seccion {
    border: 1px solid var(--bandeja-borde);
    border-radius: var(--bandeja-radio-sm);
    background: var(--bandeja-superficie);
    padding: 10px 12px;
    margin-bottom: 10px;
    display: flex;
    flex-direction: column;
    gap: 5px;
  }

  .eq-cabeza {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    padding-bottom: 6px;
    margin-bottom: 2px;
    border-bottom: 1px solid var(--bandeja-borde);
  }

  /* La marca de la derecha del encabezado: GPON, la zona, la hora de lectura.
     Es contexto de la sección, no un dato de una fila. */
  .eq-marca {
    flex: none;
    font-family: var(--bandeja-mono);
    font-size: 9.5px;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--bandeja-texto-3);
  }

  /* EL GUION DE LO QUE NO HAY. Apagado a propósito y sin fondo: tiene que
     verse que la fila existe y que está vacía, sin competir con un valor. */
  .eq-sin {
    color: var(--bandeja-texto-3);
  }

  .eq-serial {
    display: inline-flex;
    align-items: center;
    gap: 5px;
  }

  /* ── la telemetría ─────────────────────────────────────────────────────
     El número grande, como en la imagen: en una columna de 350px es lo único
     que se lee de un vistazo sin enfocar. */
  .rx-cabeza {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 10px;
  }

  .rx-grande {
    font-family: var(--bandeja-mono);
    font-size: 20px;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    letter-spacing: -0.02em;
    color: var(--bandeja-ok);
  }

  .rx-grande.rx-mal {
    color: var(--bandeja-error);
  }

  .rx-barra {
    position: relative;
    height: 12px;
    margin-top: 2px;
  }

  .rx-pista {
    position: absolute;
    inset: 4px 0;
    border-radius: 2px;
    /* De bueno a malo, de izquierda a derecha. El degradado NO afirma dónde
       está el corte -- eso lo dice la marca del umbral, que es un número. */
    background: linear-gradient(
      to right,
      var(--bandeja-ok),
      var(--bandeja-aviso-borde) 55%,
      var(--bandeja-error)
    );
    opacity: 0.55;
  }

  /* El umbral: una raya fina y oscura. Es un límite, no una medición. */
  .rx-umbral {
    position: absolute;
    top: 0;
    bottom: 0;
    width: 1px;
    background: var(--bandeja-texto);
    opacity: 0.55;
  }

  /* La lectura: una marca gruesa con halo, para que se distinga del umbral
     aunque queden pegadas. */
  .rx-marca {
    position: absolute;
    top: -1px;
    bottom: -1px;
    width: 3px;
    margin-left: -1.5px;
    border-radius: 2px;
    background: var(--bandeja-ok);
    box-shadow: 0 0 0 1.5px var(--bandeja-superficie);
  }

  .rx-marca-mal {
    background: var(--bandeja-error);
  }

  .rx-escala {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 6px;
    font-family: var(--bandeja-mono);
    font-size: 9.5px;
    font-variant-numeric: tabular-nums;
    color: var(--bandeja-texto-3);
  }

  .rx-escala-umbral {
    color: var(--bandeja-texto-2);
    font-weight: 600;
  }

  .rx-pie {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 6px;
  }

  .rx-clasif {
    font-size: 11px;
    color: var(--bandeja-texto-2);
  }

  /* ── las cuatro celdas ────────────────────────────────────────────────
     Rejilla de dos columnas, como la imagen. Se dibujan las cuatro siempre:
     si aparecieran y desaparecieran según lo que vino, la sección cambiaría
     de alto en cada consulta y no se podría comparar dos lecturas. */
  .eq-celdas {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px;
    margin-top: 4px;
  }

  .eq-celda {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 6px 8px;
    border: 1px solid var(--bandeja-borde);
    border-radius: 3px;
    background: var(--bandeja-superficie-suave);
    min-width: 0;
  }

  .eq-celda-rotulo {
    font-size: 10px;
    color: var(--bandeja-texto-2);
  }

  .eq-celda-valor {
    font-family: var(--bandeja-mono);
    font-size: 12px;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    color: var(--bandeja-texto);
  }

  /* ── la banda de alarma ───────────────────────────────────────────────
     Lo primero de la imagen cuando algo anda mal. Sale de lo medido: enlace
     caído, o potencia por debajo del umbral que declara la empresa. Si no
     hay ninguna de las dos, no se dibuja -- una alarma permanente no es una
     alarma. */
  .alarma {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 10px;
    margin-bottom: 8px;
    border: 1px solid var(--bandeja-error-borde);
    border-radius: var(--bandeja-radio-sm);
    background: var(--bandeja-error-fondo);
  }

  .alarma-punto {
    flex: none;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--bandeja-error);
  }

  .alarma-textos {
    display: flex;
    flex-direction: column;
    gap: 1px;
    min-width: 0;
    flex: 1 1 auto;
  }

  .alarma-textos b {
    font-size: 12px;
    font-weight: 700;
    color: var(--bandeja-error);
  }

  .alarma-sub {
    font-size: 11px;
    line-height: 1.35;
    color: var(--bandeja-texto-2);
  }

  .alarma-chip {
    flex: none;
    padding: 1px 6px;
    border-radius: 3px;
    background: var(--bandeja-error);
    color: #fff;
    font-family: var(--bandeja-mono);
    font-size: 9.5px;
    font-weight: 700;
    letter-spacing: 0.06em;
  }

  /* El pie que separa las dos ausencias. Sin él, seis guiones seguidos se
     leen como una pantalla rota en vez de como un límite conocido. */
  .eq-pie {
    margin: 0 0 10px;
    font-size: 10.5px;
    line-height: 1.45;
    color: var(--bandeja-texto-3);
  }

</style>
