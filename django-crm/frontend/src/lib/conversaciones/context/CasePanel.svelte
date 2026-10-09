<script>
  /**
   * El caso detrás de esta conversación: lo que es de Dexter, lo que es del
   * CRM, y el ticket operativo.
   *
   * OJO CON EL DUEÑO (D28). El "Dueño del ticket" es el del CRM, que puede no
   * coincidir con quién atiende la conversación en Dexter -- eso último es la
   * asignación durable y vive en HandoffControls. Son dos cosas distintas a
   * propósito y no se reconcilian todavía: la fuente de verdad del relevo es
   * Dexter. No usar este valor para decidir Tomar, Soltar ni Reasignar.
   *
   * EL PANEL YA NO DESAPARECE SIN CASO DEL CRM
   * ------------------------------------------
   * Todo el componente estaba dentro de un `{#if caso}`. Una conversación sin
   * caso en el CRM --que son la mayoría-- dejaba la pestaña "Caso" en blanco,
   * incluidos el identificador, el canal y la clasificación, que son de Dexter
   * y existen siempre. Se leía como una pestaña rota. Ahora el bloque de
   * Dexter va siempre y sólo se oculta lo que de verdad no hay.
   */
  import { ChevronDown, ArrowUpRight, TriangleAlert, Info, Copy, Check } from '@lucide/svelte';
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

  const etiquetaLabel = (e) => (e ? e.replaceAll('_', ' ') : '');
  const CANAL = { whatsapp: 'WhatsApp', 'whatsapp-simulado': 'Simulador' };

  // D28 HECHO VISIBLE. Son dos dueños distintos y no se reconcilian: el del
  // ticket del CRM y el de la conversación en Dexter.
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

  /* Mismo comportamiento que el serial en la pestaña de Red: el acuse dura un
     momento y un portapapeles bloqueado no se reporta como falla, porque el
     valor está a la vista y se puede seleccionar a mano. */
  let copiado = $state('');
  async function copiar(/** @type {string} */ valor) {
    try {
      await navigator.clipboard.writeText(valor);
      copiado = valor;
      setTimeout(() => { if (copiado === valor) copiado = ''; }, 1500);
    } catch {
      /* sin portapapeles: el valor sigue siendo seleccionable */
    }
  }
</script>

<div class="caso-panel">
  <!-- ── LO DE DEXTER ────────────────────────────────────────────────────
       Primero y separado de lo del CRM. Antes los campos de las dos cosas
       iban mezclados en una lista y "Asignado a" se leía como si dijera quién
       atiende la conversación. -->
  <div class="panel-tarjeta">
    <div class="panel-tarjeta-cabeza">
      <span class="panel-titulo">Conversación en Dexter</span>
    </div>
    <div class="bloque">
    <div class="panel-fila">
      <span class="panel-etiqueta">Identificador</span>
      <span class="panel-valor id-con-copia">
        <span class="panel-chip">{conversacion.id}</span>
        <button
          type="button"
          class="copiar"
          onclick={() => copiar(String(conversacion.id))}
          title="Copiar el identificador"
          aria-label="Copiar el identificador de la conversación"
        >
          {#if copiado === String(conversacion.id)}<Check size={12} />{:else}<Copy size={12} />{/if}
        </button>
      </span>
    </div>

    <div class="panel-fila">
      <span class="panel-etiqueta">Canal</span>
      <span class="panel-valor">{CANAL[conversacion.canal] ?? conversacion.canal}</span>
    </div>

    <div class="panel-fila">
      <span class="panel-etiqueta">Clasificación</span>
      {#if conversacion.etiqueta}
        <span class="panel-valor clasificacion">{etiquetaLabel(conversacion.etiqueta)}</span>
      {:else}
        <span class="panel-valor sin-dato">Sin clasificar</span>
      {/if}
    </div>

    <!-- El dueño cierra el bloque con su propio filete, como la referencia:
         es el dato que se contrasta con el del CRM más abajo. -->
    <div class="panel-fila panel-fila-sep">
      <span class="panel-etiqueta">A cargo en Dexter</span>
      {#if asignadaDexter}
        <span class="panel-valor con-punto">
          <span class="punto-dueno" aria-hidden="true"></span>{asignadaDexter}
        </span>
      {:else}
        <span class="panel-valor sin-dato">Sin asignar</span>
      {/if}
    </div>
    </div>
  </div>

  <!-- ── EL CASO DEL CRM ─────────────────────────────────────────────────
       Sólo si lo hay. La mayoría de las conversaciones no abren caso, y un
       bloque con tres guiones se lee como "el CRM está caído". -->
  {#if caso}
    <div class="panel-tarjeta">
      <div class="panel-tarjeta-cabeza">
        <span class="panel-titulo">Caso en el CRM</span>
        <a class="abrir" href="/tickets/{caso.id}">
          Abrir ticket <ArrowUpRight size={12} />
        </a>
      </div>

      <div class="bloque">
        <div class="panel-fila">
          <span class="panel-etiqueta">Identificador</span>
          <span class="panel-valor"><span class="panel-chip">{caso.id}</span></span>
        </div>

        <div class="panel-fila">
          <span class="panel-etiqueta">Estado</span>
          <span class="panel-valor">{caso.status ?? '—'}</span>
        </div>

        <div class="panel-fila">
          <span class="panel-etiqueta">Dueño del ticket</span>
          <span class="panel-valor">
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
                  class="asignado-trigger"
                  onclick={() => (listaAbierta = !listaAbierta)}
                >
                  {#if ownerActual}
                    <Avatar name={ownerActual.name} size={16} />
                    <span>{ownerActual.name}</span>
                  {:else}
                    <span class="sin-dato">Sin asignar</span>
                  {/if}
                  <ChevronDown size={13} style="opacity:0.6" />
                </button>
                {#if listaAbierta}
                  <!-- Fondo invisible: cerrar al hacer clic afuera, patrón
                       estándar sin depender de ninguna librería de popover. -->
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
                        <span class="sin-dato">Sin asignar</span>
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
          </span>
        </div>
      </div>

      <!-- El hallazgo, sólo cuando lo hay: los dos nombres diferían. -->
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
           prueba que sean la misma persona: el CRM y Dexter no comparten
           identidad de usuario, así que lo único que hay para comparar es un
           texto. Sin esta línea, dos homónimos se leerían como "está bien
           asignado" -- una afirmación que Dexter no puede hacer. -->
      <p class="nota-autoridad">
        <Info size={12} />
        <span>
          La asignación del CRM es informativa. Quién atiende esta conversación
          lo determina Dexter.
        </span>
      </p>
    </div>
  {/if}

  <!-- ── EL TICKET OPERATIVO ─────────────────────────────────────────────
       Sólo si la conversación tiene uno. No se muestra un campo vacío para
       completar la composición. -->
  {#if conversacion.ticket_operativo}
    <div class="panel-tarjeta">
      <div class="panel-tarjeta-cabeza"><span class="panel-titulo">Ticket operativo</span></div>
      <div class="bloque">
        <div class="panel-fila">
          <span class="panel-etiqueta">Identificador</span>
          <span class="panel-valor"><span class="panel-chip">{conversacion.ticket_operativo}</span></span>
        </div>
      </div>
    </div>
  {/if}
</div>

<style>
  .caso-panel {
    display: flex;
    flex-direction: column;
  }

  /* Las filas de una sección van juntas y apretadas: son una tabla, no una
     lista de párrafos. */
  /* Las filas de una tarjeta van juntas y apretadas: son una tabla, no una
     lista de párrafos. La separación ENTRE tarjetas la pone `.panel-tarjeta`
     en bandeja.css, así que acá no va margen -- con los dos, las secciones
     quedaban a 24px una de otra y entraban dos por pantalla. */
  .bloque {
    display: flex;
    flex-direction: column;
    gap: 7px;
  }



  /* El enlace al ticket va en la cabecera de SU sección y no al pie del
     panel: ahí queda claro a qué caso abre. Al final, con tres bloques
     debajo, había que deducir cuál. */
  .abrir {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    flex: none;
    padding: 2px 7px;
    border: 1px solid var(--bandeja-borde);
    border-radius: var(--bandeja-radio-sm);
    background: var(--bandeja-superficie);
    font-size: 11px;
    font-weight: 500;
    color: var(--bandeja-texto);
    text-decoration: none;
  }
  .abrir:hover {
    background: var(--bandeja-superficie-suave);
    border-color: var(--bandeja-texto-3);
  }

  .id-con-copia {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    justify-content: flex-end;
  }

  .copiar {
    display: grid;
    place-items: center;
    flex: none;
    padding: 3px;
    border: 1px solid var(--bandeja-borde);
    border-radius: var(--bandeja-radio-sm);
    background: var(--bandeja-superficie);
    color: var(--bandeja-texto-2);
    cursor: pointer;
  }
  .copiar:hover {
    color: var(--bandeja-texto);
    border-color: var(--bandeja-texto-3);
  }

  .clasificacion {
    text-transform: capitalize;
  }

  .sin-dato {
    color: var(--bandeja-texto-3);
  }

  .con-punto {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  /* Azul: es el dueño humano, y el azul es la firma de las personas en toda
     la Bandeja. Un dueño de Dexter nunca es la IA. */
  .punto-dueno {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--bandeja-humano);
    flex: none;
  }

  .aviso-duenos {
    display: flex;
    align-items: flex-start;
    gap: 6px;
    margin: 10px 0 0;
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
     gritara, el aviso de arriba --que sí es un hallazgo-- dejaría de
     destacar. */
  .nota-autoridad {
    display: flex;
    align-items: flex-start;
    gap: 5px;
    margin: 8px 0 0;
    padding-top: 7px;
    border-top: 1px solid var(--bandeja-borde);
    font-size: 11px;
    line-height: 1.45;
    color: var(--bandeja-texto-2);
  }
  .nota-autoridad :global(svg) {
    flex: none;
    margin-top: 1px;
  }

  .asignado-picker {
    position: relative;
  }

  .asignado-trigger {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 2px 6px;
    border: 1px solid var(--bandeja-borde);
    border-radius: var(--bandeja-radio-sm);
    background: var(--bandeja-superficie);
    font-size: 12px;
    font-family: inherit;
    color: var(--bandeja-texto);
    cursor: pointer;
  }
  .asignado-trigger:hover {
    background: var(--bandeja-superficie-suave);
  }

  /* Fondo invisible a pantalla completa: clic afuera cierra la lista. Es el
     patrón sin dependencias. */
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
    right: 0;
    background: var(--bandeja-superficie);
    border: 1px solid var(--bandeja-borde);
    border-radius: 8px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
    padding: 5px;
    min-width: 190px;
    z-index: 50;
    list-style: none;
    margin: 0;
  }

  .asignado-item {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    padding: 6px 9px;
    border-radius: 6px;
    font-size: 12.5px;
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
