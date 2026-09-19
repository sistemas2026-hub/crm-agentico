<script>
  /**
   * Qué se le hizo al equipo del cliente en esta conversación, y si funcionó.
   *
   * LO QUE NO ESTÁ, Y POR QUÉ. La referencia de diseño muestra potencia
   * óptica, OLT, PON, CTO, MAC, firmware, temperatura, dispositivos conectados
   * e incidentes de zona — y ella misma separa una sección «STITCH MOCK /
   * FUTURE DATA — NOT AVAILABLE TODAY» con la mayoría. Dexter no los persiste
   * (PRD RNF-01) y no hay vía de consulta por conversación. Traerlos en vivo
   * repetiría la decisión que 1.7 ya cerró: no se convierte la Bandeja en una
   * segunda fuente de verdad.
   *
   * LOS BOTONES «PING ONT» Y «REBOOT ONT» TAMPOCO ESTÁN, y no es por falta de
   * tiempo:
   *
   *   Reiniciar corta el servicio de alguien. Pasa por la cola de acciones
   *   propuestas con confirmación (PRD §7.4, fail-closed en código). Un botón
   *   acá sería una segunda puerta a la misma acción, sin esa confirmación.
   *
   *   El ping no sirve como veredicto: medido dos veces en producción, el
   *   mismo equipo sano devuelve `1 de 3`, `2 de 3` y `3 de 3` en corridas
   *   seguidas, y un reinicio real y confirmado dejó el ping igual antes y
   *   después. Un botón que devuelve eso invita a concluir lo que no se puede.
   *
   * Lo que sí hay es el veredicto del seguimiento de acciones, que es el dato
   * honesto: se ejecutó algo, y el sistema midió si produjo su efecto.
   */
  import { CircleCheck, CircleX, CircleHelp, Clock } from '@lucide/svelte';
  import { lineaDeAccion } from '$lib/conversaciones/red.js';

  let { acciones = [], serial = null } = $props();

  const lineas = $derived(acciones.map(lineaDeAccion));

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
  <p class="bloque-titulo">Equipo del cliente</p>

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

  {#if serial}
    <p class="serial">
      <span class="v2-sub">Equipo identificado</span>
      <span class="mono">{serial}</span>
    </p>
  {/if}

  <p class="nota-fuente">
    La potencia óptica, la OLT y el estado de la ONU se consultan desde el
    sistema del ISP cuando el asistente los necesita, y no se guardan acá.
    Reiniciar un equipo pasa por la cola de acciones con confirmación: no se
    hace desde esta pantalla.
  </p>
</section>

<style>
  .red {
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--v2-line-soft);
  }

  .bloque-titulo {
    margin: 0;
    font-family: var(--bandeja-mono);
    font-size: 9.5px;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--bandeja-texto-2);
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
  .mono {
    font-family: var(--bandeja-mono);
    font-size: 12px;
    font-variant-numeric: tabular-nums;
    color: var(--bandeja-texto);
    overflow-wrap: anywhere;
  }

  .nota-fuente {
    margin: 2px 0 0;
    font-size: 11px;
    line-height: 1.45;
    color: var(--bandeja-texto-2);
  }
</style>
