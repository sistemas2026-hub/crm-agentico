<script>
  /**
   * Quién es el cliente, con lo que Dexter efectivamente sabe.
   *
   * DOS ORIGENES, Y SE DISTINGUEN A PROPOSITO
   * -----------------------------------------
   * Lo que Dexter GUARDÓ de esta conversación --la identidad verificada y los
   * identificadores del equipo-- y lo que se LEE EN VIVO del sistema del ISP
   * --ubicación, servicio y facturación--. Lo segundo no se persiste: el PRD
   * lo prohíbe, y por eso el pie dice cuándo se leyó.
   *
   * Este comentario decía que esos campos NO estaban y que traerlos
   * convertiría al panel en una segunda fuente de verdad. Dejó de ser cierto
   * el 22/09/2026: el motor los lee sin guardarlos, así que no hay copia que
   * pueda contradecir al original. Y la referencia los marca `MOCK` --no los
   * tenía-- mientras que acá son reales.
   *
   * Lo que consta de la verificación de identidad, dentro de esta
   * conversación:
   *
   *   nombre_cliente · id_cliente   la persona, si se verificó
   *   equipo                        identificadores TÉCNICOS de su equipo
   *                                 (Sesion.CAMPOS_PERSISTIBLES), filtrados
   *                                 por el motor
   *
   * `id_cliente` es además la señal de que hubo verificación: los campos
   * técnicos sólo se escriben al verificar, y verificar exige id_cliente.
   */
  import { ShieldCheck, ShieldQuestion, ChevronDown } from '@lucide/svelte';
  import { tonoDeEstadoServicio, fechaLegible, montoLegible } from '$lib/conversaciones/formato.js';
  import { avisoDeCorte, telefonoDelCanal } from './ficha-cliente.js';

  let {
    conversacion,
    /** La ficha leída en vivo del sistema del ISP, o null. Cada campo se
        dibuja SÓLO si vino: la lista blanca del motor deja fuera lo que no
        corresponde, y un renglón con un guion no informa nada. */
    ficha = null
  } = $props();

  const ROTULO_EQUIPO = {
    sn_onu: 'Serial de la ONU',
    interfaz_lan: 'Interfaz'
  };

  const verificado = $derived(!!conversacion?.id_cliente);
  const equipo = $derived(Object.entries(conversacion?.equipo ?? {}).filter(([, v]) => v));

  /* Una seccion se dibuja si tiene AL MENOS un dato. Se calcula acá y no en
     el marcado para que el titulo y el contenido no puedan desincronizarse --
     un rotulo "Ubicacion" sin nada debajo es peor que no tenerlo. */
  const hayUbicacion = $derived(!!(ficha?.direccion || ficha?.localidad || ficha?.ciudad || ficha?.zona));
  const hayServicio = $derived(!!(ficha?.plan_internet || ficha?.estado || ficha?.fecha_instalacion));
  const hayFacturacion = $derived(
    !!(ficha?.estado_facturas || ficha?.fecha_corte) ||
      (ficha?.saldo !== undefined && ficha?.saldo !== null)
  );

  /* Cortado o suspendido se marca: es lo que explica la mitad de las
     consultas. Con palabra ademas del color -- 'estado' viene del ISP y no
     hay una lista cerrada de valores (ver tonoDeEstadoServicio). */
  const tonoServicio = $derived(tonoDeEstadoServicio(ficha?.estado));

  // Un BSUID de WhatsApp no es un teléfono y no hay que mostrarlo como tal.
  const esIdOpaco = $derived(
    !!conversacion?.usuario_externo && !/^\+?\d[\d\s-]{5,}$/.test(conversacion.usuario_externo)
  );

  /* 04/11/2026: LO QUE SÓLO SIRVE PARA BUSCAR EN OTRO SISTEMA, PLEGADO.
     El identificador opaco del canal (`CO.1360399936298471`) ocupaba el
     segundo renglón de Identidad, donde se busca a quién se le está
     contestando, y no le dice nada a quien atiende. Lo mismo el serial y la
     interfaz del equipo: el header de este archivo los llama «identificadores
     TÉCNICOS», y la pestaña Equipo ya muestra el serial con su botón de
     copiar. Siguen estando --quien depura los necesita--, pero cerrados. */
  const hayTecnicos = $derived(esIdOpaco || equipo.length > 0);

  /* La fecha de corte con su aviso: es lo que hay que saber ANTES de
     contestarle a un cliente que pregunta por su servicio. La regla vive en
     ficha-cliente.js, probada; acá sólo se dibuja. */
  const avisoCorte = $derived(avisoDeCorte(ficha?.fecha_corte));
</script>

<section class="cliente">
  <!-- ── IDENTIDAD ──────────────────────────────────────────────────────
       Rótulo de sección arriba y la píldora de verificación al PIE del
       bloque, como la referencia. Va al pie y no al tope a propósito: es el
       veredicto sobre los tres datos de arriba, y leerlo después de verlos
       es el orden en que se usa. -->
  <p class="panel-titulo">Identidad</p>

  <div class="bloque">
    {#if conversacion?.nombre_cliente}
      <div class="panel-fila">
        <span class="panel-etiqueta">Nombre</span>
        <span class="panel-valor nombre">{conversacion.nombre_cliente}</span>
      </div>
    {/if}

    <!-- Sólo cuando es un teléfono. El id opaco se fue al pie, a
         «Identificadores técnicos» (04/11/2026). -->
    {#if !esIdOpaco}
      <div class="panel-fila">
        <span class="panel-etiqueta">Teléfono</span>
        {#if conversacion?.usuario_externo}
          <span class="panel-valor panel-mono">{telefonoDelCanal(conversacion.usuario_externo)}</span>
        {:else}
          <span class="panel-valor sin-dato">Sin identificar</span>
        {/if}
      </div>
    {/if}

    {#if conversacion?.id_cliente}
      <div class="panel-fila">
        <span class="panel-etiqueta">Cliente en el ISP</span>
        <span class="panel-valor"><span class="panel-chip">{conversacion.id_cliente}</span></span>
      </div>
    {/if}

    {#if ficha?.cedula}
      <div class="panel-fila">
        <span class="panel-etiqueta">Documento</span>
        <span class="panel-valor panel-mono">{ficha.cedula}</span>
      </div>
    {/if}

    <p class="verificacion" class:v-si={verificado} class:v-no={!verificado}>
      {#if verificado}
        <ShieldCheck size={13} />
        <span>Identidad verificada en esta conversación</span>
      {:else}
        <ShieldQuestion size={13} />
        <!-- No es una falta: la mayoría de las consultas no necesitan
             verificar. Lo que no se puede es tratar los datos como
             confirmados. -->
        <span>Sin verificar — nada de lo de abajo está confirmado</span>
      {/if}
    </p>
  </div>

  <!-- ── LO QUE SE LEE EN VIVO DEL SISTEMA DEL ISP ──────────────────────
       Tres secciones, las mismas de la referencia. Allá LOCATION y BILLING
       están marcadas `MOCK` porque el diseño no tenía de dónde sacarlas;
       acá son reales. Ninguna se dibuja si no vino su dato: una sección con
       tres guiones se lee como "el sistema está roto", y lo que pasa es que
       ese cliente no tiene ese campo cargado. -->
  {#if hayUbicacion}
    <p class="panel-titulo panel-seccion">Ubicación</p>
    <div class="bloque">
      {#if ficha.direccion}
        <div class="panel-fila"><span class="panel-etiqueta">Dirección</span>
          <span class="panel-valor">{ficha.direccion}</span></div>
      {/if}
      {#if ficha.localidad || ficha.ciudad}
        <div class="panel-fila"><span class="panel-etiqueta">Localidad</span>
          <span class="panel-valor">{[ficha.localidad, ficha.ciudad].filter(Boolean).join(' · ')}</span></div>
      {/if}
      {#if ficha.zona}
        <div class="panel-fila"><span class="panel-etiqueta">Zona</span>
          <span class="panel-valor">{ficha.zona}</span></div>
      {/if}
    </div>
  {/if}

  {#if hayServicio}
    <p class="panel-titulo panel-seccion">Servicio</p>
    <div class="bloque">
      {#if ficha.plan_internet}
        <div class="panel-fila"><span class="panel-etiqueta">Plan</span>
          <span class="panel-valor">{ficha.plan_internet}</span></div>
      {/if}
      {#if ficha.estado}
        <!-- El único dato de la ficha que es un veredicto, y por eso es el
             único que va en una insignia con punto: la referencia lo dibuja
             así porque «Activo» y «Suspendido» cambian lo que se le puede
             prometer al cliente en la frase siguiente. -->
        <div class="panel-fila"><span class="panel-etiqueta">Estado del servicio</span>
          <span class="panel-valor">
            <span class="estado-servicio" class:estado-mal={tonoServicio === 'mal'}
                  class:estado-neutro={tonoServicio === 'neutro'}>
              <span class="estado-punto" aria-hidden="true"></span>{ficha.estado}
            </span>
          </span></div>
      {/if}
      {#if ficha.fecha_instalacion}
        <div class="panel-fila"><span class="panel-etiqueta">Instalado</span>
          <span class="panel-valor cifra">{fechaLegible(ficha.fecha_instalacion)}</span></div>
      {/if}
    </div>
  {/if}

  {#if hayFacturacion}
    <p class="panel-titulo panel-seccion">Facturación</p>
    <div class="bloque">
      {#if ficha.estado_facturas}
        <div class="panel-fila"><span class="panel-etiqueta">Cobranza</span>
          <span class="panel-valor">{ficha.estado_facturas}</span></div>
      {/if}
      {#if ficha.saldo !== undefined && ficha.saldo !== null}
        <div class="panel-fila"><span class="panel-etiqueta">Saldo</span>
          <!-- Sin moneda: varía por empresa y no se inventa. -->
          <span class="panel-valor cifra">{montoLegible(ficha.saldo)}</span></div>
      {/if}
      {#if ficha.fecha_corte}
        <div class="panel-fila"><span class="panel-etiqueta">Fecha de corte</span>
          <span class="panel-valor cifra">
            {fechaLegible(ficha.fecha_corte)}
            {#if avisoCorte}<span class="corte-aviso">{avisoCorte}</span>{/if}
          </span></div>
      {/if}
    </div>
  {/if}

  <!-- ── IDENTIFICADORES TÉCNICOS ──────────────────────────────────────
       Cerrado de entrada (04/11/2026): son datos para buscar en otro
       sistema, no para contestarle al cliente. Se dibuja sólo si hay algo
       adentro -- un plegable vacío es un clic que no lleva a nada. -->
  {#if hayTecnicos}
    <details class="panel-seccion tecnicos">
      <summary class="tecnicos-cabeza">
        <span class="panel-titulo">Identificadores técnicos</span>
        <ChevronDown size={14} class="tecnicos-flecha" />
      </summary>
      <div class="bloque">
        {#if esIdOpaco}
          <div class="panel-fila">
            <span class="panel-etiqueta">Identificador del canal</span>
            <span class="panel-valor panel-mono">{conversacion.usuario_externo}</span>
          </div>
        {/if}
        {#each equipo as [clave, valor] (clave)}
          <div class="panel-fila">
            <!-- Si el tenant captura un campo nuevo, aparece con su clave cruda
                 en vez de no aparecer: el motor ya lo manda, y esconderlo sería
                 perder un dato que alguien fue a buscar. -->
            <span class="panel-etiqueta">{ROTULO_EQUIPO[clave] ?? clave.replaceAll('_', ' ')}</span>
            <span class="panel-valor panel-mono">{valor}</span>
          </div>
        {/each}
      </div>
    </details>
  {/if}

  <p class="panel-nota">
    {#if ficha}
      La ubicación, el servicio y la facturación se leen del sistema del ISP al
      abrir la conversación y <b>no se guardan acá</b>. Lo que Dexter sí guarda
      de esta conversación es la identidad verificada y los identificadores del
      equipo.
    {:else}
      Dexter guarda de cada cliente lo que hizo falta para atenderlo: su
      identidad y los identificadores de su equipo. El plan, la dirección, el
      saldo y las facturas viven en el sistema del ISP — <b>hoy no se pudieron
      leer</b>.
    {/if}
  </p>
</section>

<style>
  .cliente {
    display: flex;
    flex-direction: column;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--v2-line-soft);
  }

  /* Las filas de una sección van juntas y apretadas: son una tabla, no una
     lista de párrafos. 04/11/2026: 8px y no 7/10, la escala de 4px de la
     Bandeja. */
  .bloque {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin-top: 8px;
  }

  /* 04/11/2026: la separación entre secciones es `.panel-seccion` de
     bandeja.css. Acá había un `.separado` con los mismos tres valores --la
     copia que ese archivo existe para evitar--. */

  .nombre {
    font-weight: 600;
  }

  .sin-dato {
    color: var(--bandeja-texto-3);
  }

  /* Fechas y saldo: cifras alineadas, pero en la letra del texto. Se leen,
     no se copian a otro sistema carácter por carácter, así que no van en
     mono (04/11/2026). */
  .cifra {
    font-variant-numeric: tabular-nums;
  }

  /* El corte que está cerca, o que ya pasó. Ámbar porque pide atención antes
     de contestar, no porque algo esté roto; y con palabra, nunca sólo color. */
  .corte-aviso {
    display: inline-block;
    margin-left: 4px;
    padding: 0 4px;
    border: 1px solid var(--bandeja-aviso-borde);
    border-radius: var(--bandeja-radio-sm);
    background: var(--bandeja-aviso-fondo);
    font-size: 12px;
    font-weight: 600;
    color: var(--bandeja-aviso);
    white-space: nowrap;
  }

  .verificacion {
    display: flex;
    align-items: center;
    gap: 6px;
    margin: 4px 0 0;
    padding: 4px 8px;
    border: 1px solid;
    border-radius: var(--bandeja-radio-sm);
    font-size: 12px;
    line-height: 1.35;
  }
  .verificacion :global(svg) {
    flex: none;
  }
  .v-si {
    color: var(--bandeja-ok);
    background: color-mix(in srgb, var(--bandeja-ok) 8%, transparent);
    border-color: color-mix(in srgb, var(--bandeja-ok) 30%, transparent);
  }
  /* Ámbar y no rojo: no verificar no es un error ni una falta del operador.
     La mayoría de las consultas no lo necesitan. */
  .v-no {
    color: var(--bandeja-aviso);
    background: var(--bandeja-aviso-fondo);
    border-color: var(--bandeja-aviso-borde);
  }

  /* El estado del servicio es el único dato de la ficha que es un veredicto,
     así que es el único que va en insignia. Con palabra además del color:
     'estado' viene del ISP y no hay una lista cerrada de valores, así que el
     color acompaña al texto pero no lo reemplaza. */
  .estado-servicio {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 0 6px;
    border-radius: var(--bandeja-radio-sm);
    border: 1px solid color-mix(in srgb, var(--bandeja-ok) 30%, transparent);
    background: color-mix(in srgb, var(--bandeja-ok) 10%, transparent);
    font-size: 12px;
    font-weight: 600;
    color: var(--bandeja-ok);
    white-space: nowrap;
  }
  .estado-punto {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: currentColor;
    flex: none;
  }

  .estado-mal {
    color: var(--bandeja-error);
    border-color: var(--bandeja-error-borde);
    background: var(--bandeja-error-fondo);
  }

  .estado-neutro {
    color: var(--bandeja-neutro-texto);
    border-color: var(--bandeja-neutro-borde);
    background: var(--bandeja-neutro-fondo);
  }

  /* ── identificadores técnicos ──────────────────────────────────────────
     Plegable con el mismo gesto que «Proceso de la IA»: la flecha gira al
     abrir y es el único indicio de que se despliega. */
  .tecnicos-cabeza {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    cursor: pointer;
    list-style: none;
    user-select: none;
    color: var(--bandeja-texto-3);
  }
  .tecnicos-cabeza::-webkit-details-marker {
    display: none;
  }
  .tecnicos :global(.tecnicos-flecha) {
    flex: none;
    transition: transform 0.15s ease;
  }
  .tecnicos[open] :global(.tecnicos-flecha) {
    transform: rotate(180deg);
  }
  .tecnicos-cabeza:focus-visible {
    outline: 2px solid var(--bandeja-accion);
    outline-offset: 2px;
    border-radius: 2px;
  }

  /* Acá los rótulos son largos («Identificador del canal») y la columna fija
     de `.panel-fila` los cortaba con puntos suspensivos. Dentro de este
     plegable el rótulo toma lo que necesita y el valor --un id que puede
     medir cualquier cosa-- se parte donde haga falta. */
  .tecnicos .panel-fila {
    grid-template-columns: max-content minmax(0, 1fr);
  }
</style>
