<!--
  UNA ORDEN DEL DÍA, en su tarjeta (29/10/2026). Pedido del usuario: «cada
  ticket que lo dibuje en una tarjeta organizada, que no salga la información
  revuelta».

  De arriba abajo, lo que se lee primero va primero: su lugar en el orden del
  día (el que arma el Supervisor y sigue la app), el número, la prioridad y
  cuándo vence; el asunto como título; a quién y dónde; y abajo, lo de la
  operación (estado, técnicos, quién la asignó y si le llegó el aviso).

  La SIGUIENTE —la que el técnico hace al terminar— lleva el borde y el número
  en el color del Supervisor, y lo dice en su cabecera. Lo terminado se atenúa.
-->
<script>
  import {
    quienLaAsigno,
    textoDelAviso,
    textoDelVencimiento,
    textoDePrioridad,
    textoDeSeguimiento,
    textoDeTiempos,
    tonoDelVencimiento
  } from './dia-publicado.js';

  /** @type {{ orden: any, dia: string, marca?: string }} */
  let { orden, dia, marca = '' } = $props();

  let terminada = $derived(['completada_campo', 'cerrada'].includes(orden.estado));
  let tono = $derived(tonoDelVencimiento(orden.vence_en, dia));
  let aviso = $derived(textoDelAviso(orden.aviso));
  //  El seguimiento (30/10/2026): cuánto lleva y si dejó de reportar.
  let tiempos = $derived(textoDeTiempos(orden.tiempos));
  let seguimiento = $derived(textoDeSeguimiento(orden.seguimiento));
</script>

<article
  class="od"
  class:od-siguiente={orden.siguiente}
  class:od-terminada={terminada}
  aria-label={`Orden ${orden.numero}${orden.orden_del_dia ? `, ${orden.orden_del_dia}ª del día` : ''}`}
>
  <header class="od-cabeza">
    {#if orden.orden_del_dia}
      <span class="od-lugar" title="Lugar en el orden del día">{orden.orden_del_dia}</span>
    {/if}
    <span class="od-numero">OT {orden.numero}</span>
    {#if orden.prioridad}
      <span class="od-prioridad od-prioridad-{orden.prioridad}">{textoDePrioridad(orden.prioridad)}</span>
    {/if}
    <span class="od-vence od-vence-{tono}">{textoDelVencimiento(orden.vence_en, dia)}</span>
    {#if orden.siguiente && marca}
      <span class="od-marca">{marca}</span>
    {/if}
  </header>

  <p class="od-asunto">{orden.asunto || orden.tipo}</p>

  <div class="od-quien">
    <span class="od-cliente">{orden.cliente || 'Sin cliente'}</span>
    {#if orden.barrio}<span class="od-barrio">{orden.barrio}</span>{/if}
  </div>

  {#if tiempos || seguimiento}
    <p class="od-tiempos">
      {tiempos}{#if seguimiento}<span class="od-seguimiento" class:od-seguimiento-vencido={orden.seguimiento?.tipo === 'vencido'}>{seguimiento}</span>{/if}
    </p>
  {/if}

  <footer class="od-pie">
    <span>
      <span class="od-estado">{orden.estado_texto}</span>
      {#if orden.tecnicos?.length}<span class="od-tecnicos">{orden.tecnicos.join(', ')}</span>{/if}
    </span>
    <span class="od-asigno">
      {quienLaAsigno(orden, dia)}{#if aviso}<span class="od-aviso" class:od-aviso-mal={orden.aviso === 'no_llego' || orden.aviso === 'sin_telefono'}>{aviso}</span>{/if}
    </span>
  </footer>
</article>

<style>
  .od {
    /* El ámbar de «vence hoy» y de la prioridad media: el Supervisor NOC no
       tiene uno propio, y no se toca el sistema compartido por una tarjeta. */
    --od-ambar: #8a5300;
    --od-ambar-fondo: #ffe9c7;
    display: grid;
    gap: 6px;
    padding: 10px 12px;
    background: var(--snoc-surface-container-lowest);
    border: 1px solid var(--snoc-outline-variant);
    border-radius: var(--snoc-r-xl);
  }
  .od-siguiente {
    border-color: var(--snoc-primary);
    box-shadow: inset 3px 0 0 var(--snoc-primary);
  }
  .od-terminada { opacity: 0.6; }

  .od-cabeza {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    font-size: 12px;
    line-height: 18px;
  }
  .od-lugar {
    display: inline-grid;
    place-items: center;
    width: 22px;
    height: 22px;
    border-radius: 50%;
    background: var(--snoc-surface-container-high);
    color: var(--snoc-primary);
    font-weight: 700;
    font-variant-numeric: tabular-nums;
  }
  .od-siguiente .od-lugar {
    background: var(--snoc-primary);
    color: var(--snoc-on-primary);
  }
  .od-numero {
    font-family: 'JetBrains Mono', ui-monospace, monospace;
    font-weight: 600;
    color: var(--snoc-on-surface-variant);
  }
  .od-prioridad {
    padding: 0 8px;
    border-radius: 999px;
    font-weight: 600;
  }
  .od-prioridad-alta { background: var(--snoc-error-container); color: var(--snoc-on-error-container); }
  .od-prioridad-media { background: var(--od-ambar-fondo); color: var(--od-ambar); }
  .od-prioridad-baja { background: var(--snoc-surface-container); color: var(--snoc-on-surface-variant); }
  .od-vence { color: var(--snoc-secondary); }
  .od-vence-vencida { color: var(--snoc-error); font-weight: 600; }
  .od-vence-hoy { color: var(--od-ambar); font-weight: 600; }
  .od-marca {
    margin-left: auto;
    color: var(--snoc-primary);
    font-weight: 700;
  }

  .od-asunto {
    margin: 0;
    font-size: 14px;
    line-height: 19px;
    font-weight: 600;
    color: var(--snoc-on-surface);
    overflow-wrap: anywhere;
  }

  .od-quien {
    display: flex;
    justify-content: space-between;
    gap: 8px;
    flex-wrap: wrap;
    font-size: 13px;
    line-height: 17px;
    color: var(--snoc-on-surface-variant);
  }
  .od-barrio { color: var(--snoc-secondary); }

  .od-pie {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 4px 12px;
    flex-wrap: wrap;
    padding-top: 6px;
    border-top: 1px solid var(--snoc-surface-container-high);
    font-size: 12px;
    line-height: 16px;
    color: var(--snoc-secondary);
  }
  .od-estado {
    font-weight: 600;
    color: var(--snoc-on-surface-variant);
  }
  .od-tecnicos { margin-left: 6px; }
  .od-aviso { margin-left: 6px; }
  .od-aviso-mal { color: var(--snoc-error); }

  /* Los tiempos y la regla de los 30 minutos (30/10/2026). */
  .od-tiempos {
    margin: 0;
    font-size: 12px;
    color: var(--snoc-secondary);
    display: flex;
    flex-wrap: wrap;
    gap: 4px 10px;
  }
  .od-seguimiento { font-weight: 600; }
  .od-seguimiento-vencido { color: var(--snoc-error); }
</style>
