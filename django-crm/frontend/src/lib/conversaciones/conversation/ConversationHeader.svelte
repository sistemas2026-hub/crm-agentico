<script>
  /**
   * El encabezado de la conversación: quién es, por qué canal, en qué estado,
   * y los dos botones que viven ahí.
   *
   * Es presentación. No decide nada: la navegación, el estado de la columna de
   * contexto y el reinicio siguen viviendo en la página, que es la que tiene
   * que saber de fetches y de rutas. Acá sólo llegan props y salen avisos.
   */
  import { ArrowLeft, Phone, User, PanelRight } from '@lucide/svelte';
  import Pill from '$lib/v2/components/Pill.svelte';
  import Avatar from '$lib/v2/components/Avatar.svelte';

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
  const canalLabel = (c) => CANAL_LABEL[c] ?? c;
  const canalTone = (c) => (c === 'whatsapp' ? 'moss' : 'slate');
  const estadoTone = (e) => (e === 'abierta' ? 'clay' : 'slate');

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
</script>

<header class="centro-top">
  <a class="volver" href="/conversaciones" aria-label="Volver a la lista">
    <ArrowLeft size={16} />
  </a>

  {#if conversacion.nombre_cliente}
    <Avatar name={conversacion.nombre_cliente} size={32} />
  {:else if esTelefono(conversacion.usuario_externo)}
    <span class="ident" aria-hidden="true"><Phone size={15} /></span>
  {:else if !conversacion.usuario_externo || esUuid(conversacion.usuario_externo)}
    <span class="ident" aria-hidden="true"><User size={15} /></span>
  {:else}
    <Avatar name={conversacion.usuario_externo} size={32} />
  {/if}

  <div class="centro-quien">
    <!-- IDENTIDAD Y METADATOS EN EL MISMO RENGLÓN, como en la referencia:
         nombre, y al lado los identificadores en mono separados por puntos.
         Antes el nombre se llevaba un renglón entero y debajo iban tres
         píldoras; así entra más dato en menos alto y se lee como una ficha
         de consola en vez de como el título de una página.

         Sólo se dibuja lo que la conversación TRAE. El teléfono y el id del
         ISP están siempre; el resto de la ficha del cliente --documento,
         plan, dirección-- vive en el sistema del ISP y esta pantalla no lo
         carga: está en la pestaña Cliente, que es la que sí lo consulta. -->
    <div class="centro-identidad">
      <h2>{conversacion.nombre_cliente || quien(conversacion.usuario_externo)}</h2>
      <span class="centro-ids">
        {#if conversacion.nombre_cliente && conversacion.usuario_externo}
          <span class="centro-id">{quien(conversacion.usuario_externo)}</span>
        {/if}
        {#if conversacion.id_cliente}
          <span class="centro-id">ISP <b>{conversacion.id_cliente}</b></span>
        {/if}
        <!-- LA FICHA DEL ISP, leída en vivo. Documento, plan y estado del
             servicio son lo que alguien mira antes de contestarle a un
             cliente, y hasta ahora había que abrir otra pantalla para verlos.
             Cada uno se dibuja sólo si vino: la ficha llega incompleta a
             propósito --el motor filtra por una lista blanca-- y un renglón
             con "—" no informa nada. -->
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
      </span>
    </div>

    <div class="centro-meta">
      <!-- QUIÉN LA LLEVA, arriba de todo y con palabra. Antes esto solo se
           deducía del compositor bloqueado, así que alguien que miraba el
           encabezado no sabía si estaba leyendo una conversación de la IA o
           una suya. Es la misma pregunta que responde la cola, y conviene que
           la respondan igual. -->
      <span class="control {escalada ? 'control-humano' : 'control-ia'}">
        <span class="control-punto"></span>
        {#if escalada}
          {asignadaA ? `Humano · ${asignadaA}` : 'Humano · sin asignar'}
        {:else}
          La atiende la IA
        {/if}
      </span>
      <Pill tone={canalTone(conversacion.canal)}>{canalLabel(conversacion.canal)}</Pill>
      <Pill tone={estadoTone(conversacion.estado)}>{conversacion.estado}</Pill>
    </div>
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
  /* El distintivo de control, con la misma forma que los de la cola: mono,
     versalita, punto y filete. Que se lean igual en las dos pantallas es
     deliberado -- es la misma pregunta. */
  .control {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 1px 6px;
    border: 1px solid;
    border-radius: var(--bandeja-radio-sm);
    font-family: var(--bandeja-mono);
    font-size: 9.5px;
    font-weight: 600;
    letter-spacing: 0.02em;
    text-transform: uppercase;
    white-space: nowrap;
  }

  .control-punto {
    width: 5px;
    height: 5px;
    border-radius: 50%;
    background: currentColor;
    flex: none;
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

  .centro-top {
    flex: none;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 16px;
    border-bottom: 1px solid var(--bandeja-borde);
  }
  .centro-quien {
    min-width: 0;
    /* Crece para empujar el botón de contexto al borde derecho, como la
       referencia empuja sus acciones. */
    flex: 1 1 auto;
  }

  /* Nombre e identificadores en la misma línea. Envuelve antes que recortar:
     en angosto los ids bajan solos. */
  .centro-identidad {
    display: flex;
    align-items: baseline;
    flex-wrap: wrap;
    gap: 4px 10px;
    min-width: 0;
  }

  /* Los identificadores: mono, apagados y separados por un filete vertical,
     igual que la línea `DNI · Account · Plan` de la referencia. Son datos que
     se COMPARAN contra otro sistema, así que van en mono y con cifras
     tabulares. */
  .centro-ids {
    display: flex;
    align-items: baseline;
    flex-wrap: wrap;
    gap: 8px;
    min-width: 0;
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

  /* En un teléfono la línea de identificadores envuelve en cuatro renglones y
     la cabecera se come el hilo: medido a 390px, 153px sólo de encabezado.
     Se queda el teléfono --que es con lo que se responde-- y el resto se lee
     en la pestaña Cliente, que los tiene todos y a un toque. */
  @media (max-width: 760px) {
    .centro-ids .centro-id:not(:first-child) {
      display: none;
    }
    .centro-id + .centro-id {
      padding-left: 0;
      border-left: 0;
    }
  }

  /* El plan es lo único de la fila que no es un identificador: es lo que el
     cliente contrató, y se lee más que se compara. */
  .centro-id-plan {
    color: var(--bandeja-texto-2);
    font-weight: 600;
  }

  .centro-top h2 {
    margin: 0;
    font-size: 14.5px;
    font-weight: 640;
    letter-spacing: -0.01em;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  /* Envuelve. Las píldoras --quién la lleva, el canal, el estado-- miden 285px
     y a 390px de ancho el bloque del nombre son 189: sin `wrap` se salían 96px
     y, como acá nada recorta en X, "WhatsApp" y "abierta" se pintaban debajo
     del botón "Contexto" (medido el 21/09/2026 a 390x844). Envolver y no
     recortar: cada píldora dice algo distinto, y la que se perdía --el estado--
     no es la menos importante. */
  .centro-meta {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
    row-gap: 4px;
    margin-top: 3px;
  }
  .ident {
    flex: none;
    width: 32px;
    height: 32px;
    border-radius: 50%;
    display: grid;
    place-items: center;
    background: var(--bandeja-superficie-suave);
    color: var(--bandeja-texto-2);
  }
  /* Volver sólo tiene sentido cuando la lista no está al lado. */
  .volver {
    display: none;
    color: var(--bandeja-texto-2);
  }
  /* Por encima de 1240px la columna está siempre a la vista: ni botón para
     abrirla, ni botón para cerrarla, ni fondo que interceptar.
     La regla original agrupaba .contexto-toggle con .info-cerrar y .info-fondo,
     que son del `<aside>` y siguen en la pagina. Separarlas no cambia lo
     calculado: es la misma declaracion para los mismos elementos. */
  .contexto-toggle {
    display: none;
  }

  /* Debajo de 1240px las tres columnas ahogan el hilo. El contexto deja de
     estar fijo al lado y pasa a abrirse con el botón del encabezado -- no
     desaparece: el ticket y la documentación siguen estando a un clic. */
  @media (max-width: 1240px) {
    .contexto-toggle {
      display: inline-flex;
      margin-left: auto;
      flex: none;
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
