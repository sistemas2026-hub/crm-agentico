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
  <div class="procedencia">
    <span class="procedencia-punto" class:procedencia-punto-mal={!medicion} aria-hidden="true"></span>
    <span class="procedencia-rotulo">Confirmado — en vivo desde SmartOLT</span>
    {#if medicion}<span class="procedencia-vivo">LIVE</span>{/if}
  </div>

  <!-- LA MEDICIÓN, CON SU HORA. La hora no es un adorno: decide si el dato
       sirve para mandar un técnico o hay que volver a consultar. -->
  {#if medicion}
    <!-- ── ESTADO DE LA ONU ─────────────────────────────────────────────
         Tarjeta con el veredicto arriba. La referencia pone la insignia
         "CRITICAL / LOS ALARM" al lado del título, y tiene razón: el estado
         del enlace es lo primero que se mira. -->
    <div class="tarjeta" class:tarjeta-mal={caido}>
      <div class="tarjeta-tope">
        <span class="tarjeta-titulo">Estado de la ONU</span>
        {#if medicion.enlace}
          <span class="insignia" class:insignia-mal={caido}>{medicion.enlace}</span>
        {/if}
      </div>
      <dl class="optica">
        <!-- 'Modelo' se fue: lo trae 'get_onu_details', no las dos rutas
             livianas que alimentan esta tarjeta, asi que el renglon no se
             dibujaba nunca. Un campo que no puede tener dato no es una
             ausencia honesta, es ruido. -->
        {#if medicion.desde}
          <div class="opt-fila"><dt>Desde</dt><dd class="panel-mono">{medicion.desde}</dd></div>
        {/if}
        {#if medicion.encendido}
          <div class="opt-fila"><dt>Encendido</dt><dd class="panel-mono">{medicion.encendido}</dd></div>
        {/if}
        {#if medicion.causaCaida}
          <div class="opt-fila"><dt>Última caída</dt><dd>{medicion.causaCaida}</dd></div>
        {/if}
      </dl>
    </div>

    <!-- ── POTENCIA ÓPTICA ──────────────────────────────────────────────
         El número grande, como en la referencia: es el dato por el que se
         abre esta pestaña. El veredicto contra el umbral SÓLO si la empresa
         definió uno -- sin umbral se muestra la potencia y nada más. -->
    <!-- `!== null` y NO `{#if medicion.rx}`: 0 dBm es una potencia valida y
         `0` es falsy, asi que la comprobacion corta habria escondido la
         tarjeta justo en el caso de senal mas fuerte posible. -->
    {#if medicion.rx !== null}
      <div class="tarjeta" class:tarjeta-mal={atenuado === true}>
        <div class="tarjeta-tope">
          <span class="tarjeta-titulo">Potencia óptica</span>
          {#if lectura?.leido_en}
            <span class="tarjeta-hora">{haceCuanto(lectura.leido_en)}</span>
          {/if}
        </div>
        {#if medicion.rx !== null}
          <p class="rx" class:rx-mal={atenuado === true}>
            {medicion.rx}<span class="rx-unidad">dBm</span>
            <!-- SmartOLT ya clasifica la senal en texto ("Very good"). Se
                 muestra al lado del numero y no en su lugar: quien no lee dBm
                 entiende igual, y quien los lee no pierde el valor exacto.
                 No es un veredicto nuestro -- viene del proveedor, y por eso
                 no depende del umbral de la empresa. -->
            {#if medicion.clasificacion}
              <span class="rx-clase">{medicion.clasificacion}</span>
            {/if}
          </p>
          {#if umbral !== null}
            <p class="rx-umbral" class:rx-umbral-mal={atenuado === true}>
              {#if atenuado}Por debajo del umbral{:else}Dentro del umbral{/if}
              <span class="panel-mono">({umbral} dBm)</span>
            </p>
          {:else}
            <!-- Sin umbral no se dice si está bien o mal. Un veredicto con un
                 número inventado es peor que ningún veredicto. -->
            <p class="rx-umbral">Sin umbral definido para esta empresa</p>
          {/if}
        {/if}
        <dl class="optica">
          <!-- La de SUBIDA (1310 nm, ONU->OLT). Va rotulada como tal y
               SEPARADA del numero grande: son dos medidas distintas, y
               confundirlas es exactamente el error que llevo a que esta
               tarjeta no mostrara nada durante semanas. El umbral de la
               empresa aplica a la de bajada, no a esta. -->
          {#if medicion.rxSubida !== null}
            <div class="opt-fila">
              <dt>Subida (1310 nm)</dt>
              <dd class="panel-mono">{medicion.rxSubida} dBm</dd>
            </div>
          {/if}
        </dl>
      </div>
    {/if}

    <!-- ── IDENTIFICADORES ──────────────────────────────────────────────
         Con botón de copiar, como la referencia: son valores que se pegan en
         otro sistema, y transcribir un serial GPON a mano es como se generan
         los tickets contra el equipo equivocado. -->
    {#if medicion.serial}
      <div class="tarjeta">
        <div class="tarjeta-tope"><span class="tarjeta-titulo">Identificadores</span></div>
        <div class="ident-fila">
          <span class="ident-rotulo">Serial GPON</span>
          <code class="ident-valor panel-mono">{medicion.serial}</code>
          <button
            type="button"
            class="ident-copiar"
            onclick={() => copiar(medicion.serial)}
            aria-label="Copiar el serial"
            title="Copiar"
          >
            {#if copiado === medicion.serial}<Check size={12} />{:else}<Copy size={12} />{/if}
          </button>
        </div>
      </div>
    {/if}
    <!-- ── TOPOLOGÍA ────────────────────────────────────────────────────
         Dónde está conectado el equipo. No es adorno: dos clientes en el
         mismo puerto PON con la misma caída no son dos casos, son uno, y
         eso se ve acá antes que en ningún lado.
         Sólo aparece si vino -- la empresa puede no tener declarada la
         herramienta, y hay ONUs cuya caja (ODB) viene en blanco. -->
    {#if topologia}
      <div class="tarjeta">
        <div class="tarjeta-tope"><span class="tarjeta-titulo">Topología</span></div>
        <dl class="optica">
          {#if topologia.olt_name}
            <div class="opt-fila"><dt>OLT</dt><dd class="panel-mono">{topologia.olt_name}</dd></div>
          {/if}
          {#if topologia.board || topologia.port}
            <div class="opt-fila">
              <dt>Tarjeta / puerto</dt>
              <dd class="panel-mono">{topologia.board ?? '?'} / {topologia.port ?? '?'}</dd>
            </div>
          {/if}
          {#if topologia.onu}
            <div class="opt-fila"><dt>Índice ONU</dt><dd class="panel-mono">{topologia.onu}</dd></div>
          {/if}
          {#if topologia.odb_name}
            <div class="opt-fila"><dt>Caja (CTO)</dt><dd class="panel-mono">{topologia.odb_name}</dd></div>
          {/if}
          {#if topologia.zone_name}
            <div class="opt-fila"><dt>Zona</dt><dd>{topologia.zone_name}</dd></div>
          {/if}
        </dl>
      </div>
    {/if}
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

  .opt-fila dt {
    font-family: var(--bandeja-mono);
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: var(--bandeja-texto-2);
  }

  .opt-fila dd {
    margin: 0;
    color: var(--bandeja-texto);
    overflow-wrap: anywhere;
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

  /* ── tarjetas ──────────────────────────────────────────────────────────
     La referencia agrupa la telemetría en tarjetas con su título arriba y
     una insignia de estado a la derecha. Filete y superficie, sin sombra:
     el mismo lenguaje que el resto de la Bandeja. */
  .tarjeta {
    margin-top: 8px;
    padding: 8px 10px;
    border: 1px solid var(--bandeja-borde);
    border-radius: var(--bandeja-radio);
    background: var(--bandeja-superficie);
  }

  .tarjeta-mal {
    border-color: var(--bandeja-error-borde);
    background: var(--bandeja-error-fondo);
  }

  .tarjeta-tope {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 4px;
  }

  .tarjeta-titulo {
    font-family: var(--bandeja-mono);
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--bandeja-texto-2);
  }

  .tarjeta-hora {
    font-family: var(--bandeja-mono);
    font-size: 9px;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--bandeja-texto-3);
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

</style>
