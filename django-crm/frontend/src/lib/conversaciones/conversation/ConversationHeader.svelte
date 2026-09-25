<script>
  /**
   * El encabezado de la conversación: quién es, por qué canal, en qué estado,
   * y los dos botones que viven ahí.
   *
   * Es presentación. No decide nada: la navegación, el estado de la columna de
   * contexto y el reinicio siguen viviendo en la página, que es la que tiene
   * que saber de fetches y de rutas. Acá sólo llegan props y salen avisos.
   *
   * REFERENCIA: «Human Control State (Assigned to Me)»
   * (`c427b43a84534a489891f111217439a4`). De ahí salen la ficha cuadrada de
   * iniciales, el filete vertical y el bloque de control de dos renglones.
   */
  import { ArrowLeft, Phone, User, PanelRight } from '@lucide/svelte';

  let {
    conversacion,
    /** Quién controla la conversación AHORA, ya resuelto por el motor
        (`control_efectivo`, B3.3b) y derivado en la página. Llega como prop y
        NO se recalcula acá: si este componente dedujera el control por su
        cuenta, dos partes de la pantalla podrían decir cosas distintas. */
    escalada = false,
    /** El dueño durable de Dexter, o '' si no tiene. Nunca el del ticket del
        CRM: eso es D28 y es otra cosa. */
    asignadaA = '',
    /** Si la columna de contexto está abierta. La abre y la cierra la página:
        el mismo valor lo lee el `<aside>`, que no es hijo de este componente. */
    contextoAbierto = false,
    /** La ficha del cliente en el sistema del ISP, o null. La lee el motor en
        vivo y NO se guarda, así que puede venir vacía o no venir -- cada
        campo se dibuja sólo si llegó. */
    ficha = null,
    onAlternarContexto
  } = $props();

  const CANAL_LABEL = { whatsapp: 'WhatsApp', 'whatsapp-simulado': 'Simulador' };
  const canalLabel = (/** @type {string} */ c) => CANAL_LABEL[c] ?? c;

  // Mismo criterio que la lista del layout: un telefono o un uuid no dan
  // iniciales, y diez digitos seguidos no se leen.
  const esTelefono = (/** @type {string} */ v) => !!v && /^\+?\d[\d\s-]{5,}$/.test(v);
  const esUuid = (/** @type {string} */ v) =>
    !!v && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v);
  function quien(/** @type {string} */ v) {
    if (!v) return 'Sin identificar';
    const d = v.replace(/\D/g, '');
    if (esTelefono(v) && d.length === 10) return `${d.slice(0, 3)} ${d.slice(3, 6)} ${d.slice(6)}`;
    return v;
  }

  /** Las dos primeras iniciales del nombre. La referencia usa una ficha
      CUADRADA de 36px con las iniciales en negrita, no un avatar redondo: en
      una consola el círculo se lee como "persona del equipo" --así se dibujan
      los operadores-- y quien está del otro lado del hilo no lo es. */
  const iniciales = (/** @type {string} */ v) =>
    (v || '')
      .trim()
      .split(/\s+/)
      .slice(0, 2)
      .map((p) => p[0])
      .join('')
      .toUpperCase();

  const nombre = $derived(conversacion.nombre_cliente || '');
  const telefono = $derived(
    esTelefono(conversacion.usuario_externo) ? quien(conversacion.usuario_externo) : ''
  );
</script>

<header class="centro-top">
  <a class="volver" href="/conversaciones" aria-label="Volver a la lista">
    <ArrowLeft size={16} />
  </a>

  {#if nombre}
    <span class="ident" aria-hidden="true">{iniciales(nombre)}</span>
  {:else if esTelefono(conversacion.usuario_externo)}
    <span class="ident" aria-hidden="true"><Phone size={15} /></span>
  {:else if !conversacion.usuario_externo || esUuid(conversacion.usuario_externo)}
    <span class="ident" aria-hidden="true"><User size={15} /></span>
  {:else}
    <span class="ident" aria-hidden="true">{iniciales(conversacion.usuario_externo)}</span>
  {/if}

  <div class="centro-quien">
    <!-- PRIMER RENGLÓN: nombre, teléfono y las dos fichas de estado. La
         referencia pone el teléfono en mono al lado del nombre --es un dato
         que se marca, no un título-- y el canal como ficha gris. -->
    <div class="centro-identidad">
      <h2>{nombre || quien(conversacion.usuario_externo)}</h2>
      {#if telefono}
        <span class="centro-tel v2-num">{telefono}</span>
      {/if}
      <span class="cab-chip">{canalLabel(conversacion.canal)}</span>
      <span class="cab-chip">{conversacion.estado}</span>
    </div>

    <!-- SEGUNDO RENGLÓN: los identificadores, en mono y separados por puntos,
         igual que la línea `DNI · Account · Plan` de la referencia. Son datos
         que se COMPARAN contra otro sistema, así que van en mono y con cifras
         tabulares.

         Sólo se dibuja lo que la conversación TRAE. La ficha del ISP llega
         incompleta a propósito --el motor filtra por una lista blanca-- y un
         renglón con "—" no informa nada. -->
    <div class="centro-ids">
      {#if conversacion.id_cliente}
        <span class="centro-id">ISP <b>{conversacion.id_cliente}</b></span>
      {/if}
      {#if ficha?.cedula}
        <span class="centro-id">CC <b>{ficha.cedula}</b></span>
      {/if}
      {#if ficha?.plan_internet}
        <span class="centro-id centro-id-plan">{ficha.plan_internet}</span>
      {/if}
      {#if ficha?.estado}
        <span class="centro-id">{ficha.estado}</span>
      {/if}
      {#if conversacion.ticket_operativo}
        <span class="centro-id">Ticket <b>{conversacion.ticket_operativo}</b></span>
      {/if}
    </div>
  </div>

  <span class="centro-sep" aria-hidden="true"></span>

  <!-- QUIÉN LA LLEVA, con palabra y en un bloque propio. Antes era una píldora
       de 9,5px apretada entre el canal y el estado, o sea el dato más
       importante del encabezado con el mismo peso que "abierta". La referencia
       le da una caja con filete, punto y dos renglones: qué control es, y de
       quién. Es la misma pregunta que responde la cola, y conviene que la
       respondan igual. -->
  <div class="control {escalada ? 'control-humano' : 'control-ia'}">
    <span class="control-punto" aria-hidden="true"></span>
    <span class="control-textos">
      <span class="control-rotulo">{escalada ? 'Control humano' : 'La atiende la IA'}</span>
      <span class="control-detalle">
        {#if escalada}
          {asignadaA ? `Asignada a ${asignadaA}` : 'Sin asignar'}
        {:else}
          Dexter responde solo
        {/if}
      </span>
    </span>
  </div>

  <!-- Solo aparece cuando la columna de contexto no cabe al lado. Ahí se
       abre como panel, no se pierde: el ticket y la documentación siguen a
       un clic. -->
  <button
    type="button"
    class="v2-btn v2-btn-sm contexto-toggle"
    onclick={() => onAlternarContexto?.()}
    aria-expanded={contextoAbierto}
  >
    <PanelRight size={14} /> Contexto
  </button>
</header>

<style>
  .centro-top {
    flex: none;
    display: flex;
    align-items: center;
    gap: 12px;
    /* px-5 py-3 en la referencia. */
    padding: 12px 20px;
    background: var(--bandeja-superficie);
    border-bottom: 1px solid var(--bandeja-borde);
  }

  /* La ficha cuadrada de iniciales: 36px, radio 4, superficie y filete azules
     --el azul de las personas, que es de quien es este lado del hilo. */
  .ident {
    flex: none;
    width: 36px;
    height: 36px;
    border-radius: var(--bandeja-radio-sm);
    display: grid;
    place-items: center;
    background: var(--bandeja-humano-fondo);
    border: 1px solid var(--bandeja-humano-borde);
    color: var(--bandeja-humano);
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.02em;
  }

  .centro-quien {
    min-width: 0;
    /* Crece para empujar el bloque de control y el botón de contexto al borde
       derecho, como la referencia empuja sus acciones. */
    flex: 1 1 auto;
  }

  /* Nombre, teléfono y fichas en la misma línea. Envuelve antes que recortar:
     en angosto las fichas bajan solas. */
  .centro-identidad {
    display: flex;
    align-items: baseline;
    flex-wrap: wrap;
    gap: 3px 8px;
    min-width: 0;
  }

  .centro-top h2 {
    margin: 0;
    font-size: 14px;
    font-weight: 640;
    letter-spacing: -0.01em;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .centro-tel {
    font-family: var(--bandeja-mono);
    font-size: 11.5px;
    font-variant-numeric: tabular-nums;
    color: var(--bandeja-texto-2);
  }

  /* La ficha gris de la referencia: `bg-slate-100`, filete, 10px. */
  .cab-chip {
    flex: none;
    padding: 1px 6px;
    border: 1px solid var(--bandeja-borde);
    border-radius: 3px;
    background: var(--bandeja-superficie-suave);
    color: var(--bandeja-texto-2);
    font-size: 10px;
    font-weight: 600;
    line-height: 1.5;
    white-space: nowrap;
  }

  .centro-ids {
    display: flex;
    align-items: baseline;
    flex-wrap: wrap;
    gap: 8px;
    min-width: 0;
    margin-top: 2px;
    font-family: var(--bandeja-mono);
    font-size: 10.5px;
    font-variant-numeric: tabular-nums;
    color: var(--bandeja-texto-3);
  }

  .centro-id + .centro-id {
    padding-left: 8px;
    border-left: 1px solid var(--bandeja-borde);
  }

  .centro-id b {
    font-weight: 600;
    color: var(--bandeja-texto-2);
  }

  /* El plan es lo único de la fila que no es un identificador: es lo que el
     cliente contrató, y se lee más que se compara. */
  .centro-id-plan {
    color: var(--bandeja-texto-2);
    font-weight: 600;
  }

  /* El filete vertical que la referencia pone entre la identidad y el estado
     de control. Separa dos cosas distintas sin gastar un renglón. */
  .centro-sep {
    flex: none;
    width: 1px;
    height: 32px;
    background: var(--bandeja-borde);
  }

  /* ── el bloque de control ───────────────────────────────────────────── */
  .control {
    flex: none;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 5px 10px;
    border: 1px solid;
    border-radius: var(--bandeja-radio-sm);
  }

  .control-punto {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: currentColor;
    flex: none;
  }

  .control-textos {
    display: flex;
    flex-direction: column;
    gap: 1px;
    min-width: 0;
  }

  .control-rotulo {
    font-family: var(--bandeja-mono);
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    line-height: 1;
    white-space: nowrap;
  }

  .control-detalle {
    font-size: 11px;
    font-weight: 500;
    line-height: 1.2;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .control-ia {
    color: var(--bandeja-ia);
    background: var(--bandeja-ia-fondo);
    border-color: var(--bandeja-ia-borde);
  }

  .control-humano {
    color: var(--bandeja-humano);
    background: var(--bandeja-humano-fondo);
    border-color: var(--bandeja-humano-borde);
  }

  /* Volver sólo tiene sentido cuando la lista no está al lado. */
  .volver {
    display: none;
    color: var(--bandeja-texto-2);
  }

  /* Por encima de 1240px la columna está siempre a la vista: ni botón para
     abrirla, ni botón para cerrarla, ni fondo que interceptar. */
  .contexto-toggle {
    display: none;
  }

  /* Debajo de 1240px las tres columnas ahogan el hilo. El contexto deja de
     estar fijo al lado y pasa a abrirse con el botón del encabezado -- no
     desaparece: el ticket y la documentación siguen estando a un clic. */
  @media (max-width: 1240px) {
    .contexto-toggle {
      display: inline-flex;
      flex: none;
    }
  }

  /* En un teléfono la línea de identificadores envuelve en cuatro renglones y
     la cabecera se come el hilo: medido a 390px, 153px sólo de encabezado.
     Se queda el primero y el resto se lee en la pestaña Cliente, que los
     tiene todos y a un toque. El filete vertical y el segundo renglón del
     bloque de control tampoco entran: el rótulo solo ya dice quién la lleva. */
  @media (max-width: 760px) {
    .centro-top {
      gap: 8px;
      padding: 10px 14px;
    }
    .centro-ids .centro-id:not(:first-child) {
      display: none;
    }
    .centro-id + .centro-id {
      padding-left: 0;
      border-left: 0;
    }
    .centro-sep,
    .control-detalle {
      display: none;
    }
  }

  /* Y debajo de 1000px la lista deja de estar al lado (ver el layout), así que
     hace falta una forma de volver. */
  @media (max-width: 1000px) {
    .volver {
      display: grid;
      place-items: center;
    }
  }
</style>
