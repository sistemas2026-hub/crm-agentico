<script>
  /**
   * El caso del CRM detrás de esta conversación: su etiqueta, a quién está
   * asignado EL TICKET y el enlace para abrirlo.
   *
   * OJO CON EL DUEÑO (D28). El "Asignado a" de acá es el dueño del ticket del
   * CRM, que puede no coincidir con quién atiende la conversación en Dexter --
   * eso último es la asignación durable y vive en HandoffControls. Son dos
   * cosas distintas a propósito y no se reconcilian todavía: la fuente de
   * verdad del relevo es Dexter. No usar este valor para decidir Tomar,
   * Soltar, Reasignar ni nada de la cola.
   */
  import { ChevronDown, ArrowRight, TriangleAlert } from '@lucide/svelte';
  import Pill from '$lib/v2/components/Pill.svelte';
  import Avatar from '$lib/v2/components/Avatar.svelte';
  import { enhance } from '$app/forms';

  let {
    caso, conversacion, owners = [], ownerActual,
    /** El dueño DURABLE de Dexter, ya resuelto por la página (legado vs
        gobernada). Llega para poder decir cuándo NO coincide con el del
        ticket, que es lo que el panel antes callaba. */
    asignadaDexter = '',
    asignadoA = $bindable(''),
    listaAbierta = $bindable(false),
    formularioAsignar = $bindable()
  } = $props();

  const ETIQUETA_TONE = { soporte_tecnico: 'clay', facturacion: 'moss', comercial: 'slate', queja: 'rust' };
  const etiquetaTone = (e) => ETIQUETA_TONE[e] ?? 'ink';
  const etiquetaLabel = (e) => (e ? e.replaceAll('_', ' ') : '');
  const CANAL = { whatsapp: 'WhatsApp', 'whatsapp-simulado': 'Simulador' };

  // D28 HECHO VISIBLE. Son dos dueños distintos y no se reconcilian: el del
  // ticket del CRM y el de la conversación en Dexter. Hasta ahora el panel
  // mostraba el primero rotulado sólo como "Asignado a", y era fácil leerlo
  // como si dijera quién atiende -- que es justo lo que no dice.
  //
  // Se comparan NOMBRES porque es lo único que hay: el CRM y Dexter no
  // comparten identidad de usuario, y eso es precisamente lo que D28 dice que
  // todavía no está resuelto. Por eso la comparación sólo sirve en una
  // dirección: dos nombres distintos prueban que son dos asignaciones
  // distintas; dos nombres iguales NO prueban que sean la misma persona, y el
  // panel no lo insinúa. La aclaración de abajo va siempre, coincidan o no.
  const nombreCrm = $derived((ownerActual?.name ?? '').trim());
  const duenosDistintos = $derived(
    !!nombreCrm && !!asignadaDexter && nombreCrm !== asignadaDexter.trim()
  );
</script>

  {#if caso}
  <div class="caso-panel">
  <!-- LO DE DEXTER PRIMERO, y separado de lo del CRM. Antes los campos de las
       dos cosas iban mezclados en una sola lista, y "Asignado a" se leía como
       si dijera quién atiende la conversación. -->
  <p class="panel-titulo">Conversación · Dexter</p>

  <div class="caso-campo">
    <span class="v2-sub">Canal</span>
    <span class="panel-dato">{CANAL[conversacion.canal] ?? conversacion.canal}</span>
  </div>

  <div class="caso-campo">
    <span class="v2-sub">Clasificación</span>
    {#if conversacion.etiqueta}
      <Pill tone={etiquetaTone(conversacion.etiqueta)}>{etiquetaLabel(conversacion.etiqueta)}</Pill>
    {:else}
      <span class="v2-muted">Sin clasificar</span>
    {/if}
  </div>

  <div class="caso-campo">
    <span class="v2-sub">A cargo en Dexter</span>
    {#if asignadaDexter}
      <span class="panel-dato">{asignadaDexter}</span>
    {:else}
      <span class="v2-muted">Sin asignar</span>
    {/if}
  </div>

  <p class="panel-titulo bloque-crm">Caso del CRM</p>

  <div class="caso-campo">
    <span class="v2-sub">Estado</span>
    <span class="panel-dato">{caso.status ?? '—'}</span>
  </div>

  <div class="caso-campo">
    <span class="v2-sub">Dueño del ticket</span>
    <form
      method="POST"
      action="?/asignar"
      bind:this={formularioAsignar}
      use:enhance={() => ({ update }) => update({ reset: false })}
    >
      <input type="hidden" name="caso_id" value={caso.id} />
      <input type="hidden" name="assigned_to" value={asignadoA} />
      <div class="asignado-picker">
        <button
          type="button"
          class="v2-btn asignado-trigger"
          onclick={() => (listaAbierta = !listaAbierta)}
        >
          {#if ownerActual}
            <Avatar name={ownerActual.name} size={18} />
            <span>{ownerActual.name}</span>
          {:else}
            <span class="v2-muted">Sin asignar</span>
          {/if}
          <ChevronDown size={14} style="margin-left:auto;opacity:0.6" />
        </button>
        {#if listaAbierta}
          <!-- Fondo invisible: cerrar al hacer clic afuera, patron estandar
               sin depender de ninguna libreria de popover. -->
          <button
            type="button"
            class="asignado-fondo"
            aria-label="Cerrar"
            onclick={() => (listaAbierta = false)}
          ></button>
          <ul class="asignado-content">
            <li>
              <button
                type="button"
                class="asignado-item"
                onclick={() => {
                  asignadoA = '';
                  listaAbierta = false;
                  formularioAsignar.requestSubmit();
                }}
              >
                <span class="v2-muted">Sin asignar</span>
              </button>
            </li>
            {#each owners as o (o.id)}
              <li>
                <button
                  type="button"
                  class="asignado-item"
                  onclick={() => {
                    asignadoA = o.id;
                    listaAbierta = false;
                    formularioAsignar.requestSubmit();
                  }}
                >
                  <Avatar name={o.name} size={18} />
                  <span>{o.name}</span>
                </button>
              </li>
            {/each}
          </ul>
        {/if}
      </div>
    </form>
  </div>

  <!-- El aviso que faltaba. No es un error ni algo que haya que arreglar: el
       ticket del CRM y la conversación de Dexter se asignan por separado a
       propósito. Lo que no puede pasar es que alguien lea el nombre de arriba
       y crea que dice quién está atendiendo. -->
  {#if duenosDistintos}
    <p class="aviso-duenos">
      <TriangleAlert size={13} />
      <span>
        El ticket lo lleva <b>{nombreCrm}</b> y la conversación la atiende
        <b>{asignadaDexter}</b>. Son dos asignaciones distintas.
      </span>
    </p>
  {/if}

  <!-- SIEMPRE, coincidan los nombres o no. Que dos nombres sean iguales no
       prueba que sean la misma persona: el CRM y Dexter no comparten identidad
       de usuario, así que lo único que hay para comparar es un texto. Sin esta
       línea, dos homónimos se leerían como "está bien asignado" -- una
       afirmación que Dexter no puede hacer. Lo que sí puede decir es de dónde
       sale cada dato y cuál manda. -->
  <p class="nota-autoridad">
    La asignación del CRM es informativa. Quién atiende esta conversación lo
    determina Dexter.
  </p>

  <a class="v2-btn v2-btn-sm caso-link" href="/tickets/{caso.id}">
    Ver ticket completo <ArrowRight size={14} />
  </a>

  <!-- Sólo si la conversación tiene uno. La mayoría no: no se muestra un
       campo vacío para completar la composición. -->
  {#if conversacion.ticket_operativo}
    <p class="panel-titulo">Ticket operativo</p>
    <div class="caso-campo">
      <span class="v2-sub">Identificador</span>
      <span class="panel-dato panel-mono">{conversacion.ticket_operativo}</span>
    </div>
  {/if}
  </div>
  {/if}

<style>


  /* En la columna angosta los campos del ticket se apilan; en fila no
     entraban ni el nombre del responsable. */
  .caso-panel {
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--v2-line-soft);
  }

  .bloque-crm {
    margin-top: 4px;
    padding-top: 12px;
    border-top: 1px solid var(--bandeja-borde);
  }


  .aviso-duenos {
    display: flex;
    align-items: flex-start;
    gap: 6px;
    margin: 0;
    padding: 7px 9px;
    border: 1px solid var(--bandeja-aviso-borde);
    border-radius: var(--bandeja-radio-sm);
    background: var(--bandeja-aviso-fondo);
    color: var(--bandeja-aviso);
    font-size: 11.5px;
    line-height: 1.45;
  }
  .aviso-duenos :global(svg) {
    flex: none;
    margin-top: 1px;
  }

  /* Discreta pero permanente: no es una alarma, es la regla de autoridad. Si
     gritara, el aviso de arriba --que sí es un hallazgo-- dejaría de destacar. */
  .nota-autoridad {
    margin: -4px 0 0;
    font-size: 11px;
    line-height: 1.45;
    color: var(--bandeja-texto-2);
  }

  .caso-campo {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 5px;
  }

  .caso-campo > .v2-sub {
    font-size: 11.5px;
    white-space: nowrap;
  }

  .caso-link {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    align-self: flex-start;
  }

  .asignado-picker {
    position: relative;
  }

  .asignado-trigger {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
  }

  /* Fondo invisible a pantalla completa: clic afuera cierra la lista. Es el
     patron sin dependencias -- ver por que se saco bits-ui mas arriba. */
  .asignado-fondo {
    position: fixed;
    inset: 0;
    z-index: 40;
    background: transparent;
    border: none;
    cursor: default;
    padding: 0;
  }

  .asignado-content {
    position: absolute;
    top: calc(100% + 4px);
    left: 0;
    background: var(--bandeja-superficie);
    border: 1px solid var(--bandeja-borde);
    border-radius: 10px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
    padding: 6px;
    min-width: 200px;
    z-index: 50;
    list-style: none;
    margin: 0;
  }

  .asignado-item {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    padding: 7px 10px;
    border-radius: 7px;
    font-size: 13.5px;
    cursor: pointer;
    background: none;
    border: none;
    text-align: left;
    color: inherit;
    font-family: inherit;
  }

  .asignado-item:hover,
  .asignado-item:focus-visible {
    background: var(--bandeja-superficie-suave);
    outline: none;
  }
</style>
