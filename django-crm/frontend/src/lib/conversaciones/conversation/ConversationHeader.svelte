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
    /** Si la columna de contexto está abierta. La abre y la cierra la página:
        el mismo valor lo lee el `<aside>`, que no es hijo de este componente. */
    contextoAbierto = false,
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
    <h2>{conversacion.nombre_cliente || quien(conversacion.usuario_externo)}</h2>
    <div class="centro-meta">
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
  .centro-meta {
    display: flex;
    align-items: center;
    gap: 6px;
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
