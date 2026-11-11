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
   * (`c427b43a84534a489891f111217439a4`). De ahí sale la ficha cuadrada de
   * iniciales. El bloque de control y el chip de estado de la referencia se
   * fueron el 04/11/2026: el estado se dice una sola vez, en la línea de
   * HandoffControls (lib/conversaciones/estado-unico.js).
   */
  import { ArrowLeft, Phone, User, PanelRightOpen, PanelRightClose, MessageSquareDot } from '@lucide/svelte';
  import SelectorDeEtiquetas from '$lib/conversaciones/etiquetas/SelectorDeEtiquetas.svelte';
  import { rotuloDe } from '$lib/conversaciones/rotulos.js';
  import { telefonoLegible } from '$lib/conversaciones/formato.js';

  let {
    conversacion,
    /* `escalada` y `asignadaA` se fueron el 04/11/2026: quién la lleva lo
       dice la línea de estado de HandoffControls, una sola vez. La caja de
       control que los usaba acá era la segunda voz del mismo dato. */
    /** Si la columna de contexto está abierta. La abre y la cierra la página:
        el mismo valor lo lee el `<aside>`, que no es hijo de este componente. */
    contextoAbierto = false,
    /** La ficha del cliente en el sistema del ISP, o null. La lee el motor en
        vivo y NO se guarda, así que puede venir vacía o no venir -- cada
        campo se dibuja sólo si llegó. */
    ficha = null,
    /** Cómo se lee cada caso en esta empresa (lib/conversaciones/rotulos.js). */
    rotulos = {},
    onAlternarContexto,
    /* ETIQUETAS DEL EQUIPO (11/11/2026): el catálogo de la empresa y las del
       chat. Guarda la página; acá solo se dibujan y se avisa el cambio. */
    catalogoEtiquetas = [],
    etiquetasAsignadas = [],
    guardandoEtiquetas = false,
    errorEtiquetas = '',
    onCambiarEtiquetas = undefined,
    /* «MARCAR COMO NO LEÍDA» (11/11/2026). Sin el aviso no se dibuja el
       botón. Lo que dice si no se pudo (p. ej. el chat no tiene mensajes del
       cliente) va en `avisoLectura`. */
    onMarcarNoLeida = undefined,
    marcandoNoLeida = false,
    avisoLectura = ''
  } = $props();

  /* REINCIDENCIA (29/10/2026): la cuenta la hace el motor
     (db.reincidencia_de); acá solo se dice. Desde la SEGUNDA conversación: con
     una sola no hay nada que repetir. */
  const reincide = $derived(
    conversacion?.reincidencia && conversacion.reincidencia.total >= 2
      ? conversacion.reincidencia
      : null
  );
  const casoQueSeRepite = $derived(
    reincide?.por_caso?.[0]?.n >= 2 ? reincide.por_caso[0] : null
  );

  const CANAL_LABEL = { whatsapp: 'WhatsApp', 'whatsapp-simulado': 'Simulador' };
  const canalLabel = (/** @type {string} */ c) => CANAL_LABEL[c] ?? c;

  // Mismo criterio que la lista del layout: un telefono o un uuid no dan
  // iniciales, y diez digitos seguidos no se leen.
  const esTelefono = (/** @type {string} */ v) => !!v && /^\+?\d[\d\s-]{5,}$/.test(v);
  const esUuid = (/** @type {string} */ v) =>
    !!v && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v);
  /* Con indicativo, la forma de formato.js (04/11/2026): «+57 300 123 4567».
     Antes salía pegado, «573001234567». Los 10 dígitos locales se quedan con
     su regla: telefonoLegible les antepondría un «+» que no tienen. */
  function quien(/** @type {string} */ v) {
    if (!v) return 'Sin identificar';
    if (esTelefono(v)) {
      const d = v.replace(/\D/g, '');
      if (d.length === 10) return `${d.slice(0, 3)} ${d.slice(3, 6)} ${d.slice(6)}`;
      return telefonoLegible(d);
    }
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
      <!-- Sin nombre, el título YA es el teléfono: repetirlo al lado era el
           mismo número dos veces (visto en producción el 04/11/2026). -->
      {#if telefono && nombre}
        <span class="centro-tel v2-num">{telefono}</span>
      {/if}
      <span class="cab-chip">{canalLabel(conversacion.canal)}</span>
      <!-- El chip «cerrada» se fue el 04/11/2026: la línea de estado de
           abajo empieza por «Cerrada · la resolvió…», y dos voces para el
           mismo dato eran justo lo que estado-unico.js vino a sacar. -->
    </div>

    <!-- SEGUNDO RENGLÓN: los identificadores, separados por filetes, igual
         que la línea `DNI · Account · Plan` de la referencia. Desde el
         04/11/2026 el renglón va en texto normal y solo los NÚMEROS en mono
         --son lo que se compara contra otro sistema--: «ISP» es una palabra.

         Sólo se dibuja lo que la conversación TRAE. La ficha del ISP llega
         incompleta a propósito --el motor filtra por una lista blanca-- y un
         renglón con "—" no informa nada.

         La cédula NO va acá (04/11/2026): vive en el panel Cliente. Repetir
         un documento de identidad en la cabecera lo deja a la vista de quien
         pase por detrás, en cada conversación, sin que nadie lo haya ido a
         buscar. -->
    <div class="centro-ids">
      {#if conversacion.id_cliente}
        <span class="centro-id">ISP <b class="centro-num">{conversacion.id_cliente}</b></span>
      {/if}
      {#if ficha?.plan_internet}
        <span class="centro-id centro-id-plan">{ficha.plan_internet}</span>
      {/if}
      {#if ficha?.estado}
        <span class="centro-id">{ficha.estado}</span>
      {/if}
      {#if conversacion.ticket_operativo}
        <span class="centro-id">Ticket <b class="centro-num">{conversacion.ticket_operativo}</b></span>
      {/if}
      {#if reincide}
        <!-- «3 en 30 días» no decía de qué (04/11/2026): se lee la palabra, y
             el `title` dice qué se cuenta. -->
        <span
          class="centro-id reincide"
          title="Cuenta las conversaciones de este número en los últimos {reincide.dias} días, contando esta"
        >
          <b>{reincide.total}</b> conversaciones en {reincide.dias} días{#if casoQueSeRepite}
            · {rotuloDe(casoQueSeRepite.caso, rotulos)} ×{casoQueSeRepite.n}{/if}
        </span>
      {/if}
    </div>

    <!-- TERCER RENGLÓN: las etiquetas que el equipo le puso al chat
         (11/11/2026). Solo si la empresa tiene catálogo. -->
    <SelectorDeEtiquetas
      catalogo={catalogoEtiquetas}
      asignadas={etiquetasAsignadas}
      guardando={guardandoEtiquetas}
      error={errorEtiquetas}
      onCambiar={onCambiarEtiquetas}
    />
    {#if avisoLectura}
      <p class="aviso-lectura" role="status">{avisoLectura}</p>
    {/if}
  </div>

  <!-- La caja «Control humano / La atiende la IA» y su filete se fueron el
       04/11/2026: quién la lleva lo dice la línea de estado, justo debajo, con
       las mismas palabras que la cola. Dos respuestas a la misma pregunta en
       la misma pantalla son una invitación a que se contradigan. -->

  <!-- Solo aparece cuando la columna de contexto no cabe al lado. Ahí se
       abre como panel, no se pierde: el ticket y la documentación siguen a
       un clic. -->
  <!-- Solo ícono (10/11/2026): el texto «Contexto» ocupaba ancho de la
       cabecera para algo que el ícono del panel ya dice. El nombre sigue en
       'aria-label' (lector de pantalla) y en 'title' (al pasar el mouse), y
       el ícono cambia según si el panel está abierto o no. -->
  <!-- «Marcar como no leída» (11/11/2026): un ícono, como el de contexto, y
       con su nombre en 'aria-label' y 'title'. Lo usa quien abrió el chat
       para dejarlo «para después»: vuelve a la lista con el chat en negrita,
       como en WhatsApp. -->
  {#if onMarcarNoLeida}
    <button
      type="button"
      class="v2-btn v2-btn-sm boton-icono"
      onclick={() => onMarcarNoLeida?.()}
      disabled={marcandoNoLeida}
      aria-label="Marcar como no leída"
      title="Marcar como no leída"
    >
      <MessageSquareDot size={16} aria-hidden="true" />
    </button>
  {/if}

  <button
    type="button"
    class="v2-btn v2-btn-sm contexto-toggle boton-icono"
    onclick={() => onAlternarContexto?.()}
    aria-expanded={contextoAbierto}
    aria-label={contextoAbierto ? 'Ocultar el panel de contexto' : 'Mostrar el panel de contexto'}
    title={contextoAbierto ? 'Ocultar el panel de contexto' : 'Mostrar el panel de contexto'}
  >
    {#if contextoAbierto}
      <PanelRightClose size={16} aria-hidden="true" />
    {:else}
      <PanelRightOpen size={16} aria-hidden="true" />
    {/if}
  </button>
</header>

<style>
  .aviso-lectura {
    margin: 4px 0 0;
    font-size: 12px;
    color: var(--bandeja-texto-2);
  }

  /* La reincidencia se lee como aviso, no como un identificador más: cambia
     lo que conviene ofrecerle al cliente. */
  .reincide {
    padding: 0 6px;
    border: 1px solid var(--bandeja-aviso-borde);
    border-radius: var(--bandeja-radio-sm);
    background: var(--bandeja-aviso-fondo);
    color: var(--bandeja-aviso);
  }

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

  /* EL NOMBRE NO SE CORTA (04/11/2026). Con 14px y puntos suspensivos,
     «María Fernanda Rodríguez Ca…» obligaba a abrir el panel Cliente para
     saber con quién se hablaba. Barlow a 22px, y si no entra envuelve a un
     segundo renglón: es el dato más importante de la cabecera. */
  .centro-top h2 {
    margin: 0;
    min-width: 0;
    font-family: var(--bandeja-titulo);
    font-size: 22px;
    font-weight: 600;
    line-height: 1.15;
    letter-spacing: 0;
    overflow-wrap: anywhere;
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

  /* Texto normal, no mono (04/11/2026): «ISP», «Ticket» y el plan son
     palabras. Solo los números van en mono (`.centro-num`), que es lo que se
     compara contra otro sistema. */
  .centro-ids {
    display: flex;
    align-items: baseline;
    flex-wrap: wrap;
    gap: 4px 8px;
    min-width: 0;
    margin-top: 4px;
    font-family: var(--bandeja-sans);
    font-size: 12px;
    color: var(--bandeja-texto-2);
  }

  .centro-id + .centro-id {
    padding-left: 8px;
    border-left: 1px solid var(--bandeja-borde);
  }

  .centro-id b {
    font-weight: 600;
    color: var(--bandeja-texto);
  }

  .centro-num {
    font-family: var(--bandeja-mono);
    font-variant-numeric: tabular-nums;
  }

  /* El plan es lo único de la fila que no es un identificador: es lo que el
     cliente contrató, y se lee más que se compara. Sin mayúsculas forzadas:
     se muestra como lo escribe el ISP. */
  .centro-id-plan {
    color: var(--bandeja-texto);
    text-transform: none;
  }

  /* Volver sólo tiene sentido cuando la lista no está al lado. */
  .volver {
    display: none;
    color: var(--bandeja-texto-2);
  }

  /* Desde el 29/10/2026 el botón está en todos los tamaños: por encima de
     1240px recoge y despliega la columna; por debajo abre el cajón. */
  .contexto-toggle {
    display: inline-flex;
    flex: none;
  }
  /* Cuadrado y con el ícono al centro: un botón de solo ícono con el
     relleno de uno de texto queda angosto y desparejo. */
  .boton-icono {
    display: inline-flex;
    flex: none;
    width: 32px;
    height: 32px;
    padding: 0;
    justify-content: center;
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
     tiene todos y a un toque. El nombre baja a 18px: a 22 un nombre de cuatro
     palabras se llevaba tres renglones. */
  @media (max-width: 760px) {
    .centro-top {
      gap: 8px;
      padding: 10px 14px;
    }
    .centro-top h2 {
      font-size: 18px;
    }
    .centro-ids .centro-id:not(:first-child) {
      display: none;
    }
    .centro-id + .centro-id {
      padding-left: 0;
      border-left: 0;
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
