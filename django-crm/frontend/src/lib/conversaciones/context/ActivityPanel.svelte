<script>
  /**
   * Cómo llegó la conversación a estas manos.
   *
   * El relevo escribe un evento por transición desde B3.3 y hasta ahora nadie
   * los leía: la pantalla decía QUIÉN la lleva, no CÓMO llegó. Una reasignación
   * de supervisor y una devolución a la IA se veían igual desde afuera — la
   * conversación aparecía en otras manos y no había dónde mirar por qué.
   *
   * Es presentación pura: los eventos llegan del server load y la traducción a
   * palabras vive en actividad.js, fuera de Svelte y con pruebas. Acá no se
   * deduce nada — ni quién actuó, ni el desenlace de una devolución.
   */
  import { lineaDeActividad } from '$lib/conversaciones/actividad.js';

  let { eventos = [] } = $props();

  // Del más reciente al más viejo: lo último que pasó es lo que se busca al
  // abrir el panel. El motor los devuelve en orden cronológico.
  const lineas = $derived([...eventos].reverse().map(lineaDeActividad));

  function hora(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    return Number.isNaN(d.getTime())
      ? ''
      : d.toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit' });
  }
  function dia(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    return Number.isNaN(d.getTime())
      ? ''
      : d.toLocaleDateString('es-CO', { day: 'numeric', month: 'short' });
  }
</script>

<!-- SIN MOVIMIENTOS TAMBIÉN SE DIBUJA, y eso cambió el 21/09/2026.
     Antes este panel vivía apilado con otros nueve: no tener nada que decir
     equivalía a no ocupar espacio, y estaba bien. Desde que la columna se
     organiza en cinco pestañas, callar significa que quien abre "Actividad"
     encuentra una pestaña en blanco -- que se lee como una pantalla rota, no
     como una conversación sin movimientos.
     Y no es lo mismo "no sabemos" que "no pasó nada": el relevo escribe un
     evento por transición desde B3.3, así que una lista vacía es un hecho
     comprobado -- la conversación no cambió de manos nunca. Decirlo es
     información. -->
{#if lineas.length === 0}
  <section class="actividad">
    <p class="panel-titulo">Relevo</p>
    <p class="panel-nota">
      Todavía no cambió de manos: no hay ninguna toma, devolución, reasignación
      ni cierre registrado en esta conversación.
    </p>
  </section>
{:else}
  <section class="actividad">
    <p class="panel-titulo">Relevo · {lineas.length} movimiento{lineas.length === 1 ? '' : 's'}</p>

    <ol class="linea-tiempo">
      {#each lineas as l, i (i)}
        <li class="evento evento-{l.tono}">
          <span class="marca" aria-hidden="true"></span>
          <div class="cuerpo">
            <p class="que">{l.texto}</p>
            {#if l.detalle}<p class="detalle">{l.detalle}</p>{/if}
            <p class="cuando">
              <!-- Fecha y hora, no "hace 3 horas": esto es un registro de
                   auditoría y quien lo lee suele estar reconstruyendo una
                   secuencia, no midiendo qué tan reciente es. -->
              <time datetime={l.cuando}>{dia(l.cuando)} · {hora(l.cuando)}</time>
            </p>
          </div>
        </li>
      {/each}
    </ol>
  </section>
{/if}

<style>
  .actividad {
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--v2-line-soft);
  }


  .linea-tiempo {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
  }

  /* El hilo vertical lo dibuja el borde izquierdo de cada entrada, no un
     pseudo-elemento absoluto: así crece con el contenido y no hay que
     recalcular alturas cuando un detalle envuelve en dos líneas. */
  .evento {
    position: relative;
    display: flex;
    gap: 9px;
    padding: 0 0 12px 0;
  }
  .evento::before {
    content: '';
    position: absolute;
    left: 3px;
    top: 12px;
    bottom: 0;
    width: 1px;
    background: var(--bandeja-borde);
  }
  .evento:last-child {
    padding-bottom: 0;
  }
  .evento:last-child::before {
    display: none;
  }

  .marca {
    flex: none;
    width: 7px;
    height: 7px;
    margin-top: 4px;
    border-radius: 50%;
    background: var(--bandeja-texto-3);
    z-index: 1;
  }
  .evento-ia .marca {
    background: var(--bandeja-ia);
  }
  .evento-humano .marca {
    background: var(--bandeja-humano);
  }
  .evento-aviso .marca {
    background: var(--bandeja-aviso);
  }

  .cuerpo {
    min-width: 0;
  }

  .que {
    margin: 0;
    font-size: 12.5px;
    line-height: 1.4;
    color: var(--bandeja-texto);
  }

  .detalle {
    margin: 2px 0 0;
    font-size: 11.5px;
    line-height: 1.4;
    color: var(--bandeja-texto-2);
    overflow-wrap: anywhere;
  }

  .cuando {
    margin: 2px 0 0;
    font-family: var(--bandeja-mono);
    font-size: 10px;
    color: var(--bandeja-texto-3);
  }
</style>
