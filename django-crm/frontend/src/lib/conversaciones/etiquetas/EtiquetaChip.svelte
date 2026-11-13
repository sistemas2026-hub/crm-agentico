<script>
  /**
   * Una etiqueta del equipo dibujada (11/11/2026): su nombre en su color.
   *
   * Plano: texto del color, fondo apenas teñido y filete de 1px, radio chico.
   * La palabra va siempre -- el color solo no dice qué etiqueta es, y un 8% de
   * la gente no distingue rojo de verde --. El color sale de la paleta cerrada
   * (lib/conversaciones/etiquetas.js), nunca del dato: el `style` no puede
   * llevar nada que no esté en esa tabla.
   */
  import { estiloDeColor } from '$lib/conversaciones/etiquetas.js';

  let {
    nombre = '',
    color = 'gris',
    /** 'fila' (la cola, 11px) o 'normal' (cabecera y ajustes, 12px). */
    tamano = 'normal'
  } = $props();
</script>

<span class="etq" class:etq-fila={tamano === 'fila'} style={estiloDeColor(color)} title={nombre}>{nombre}</span>

<style>
  .etq {
    display: inline-block;
    max-width: 14em;
    padding: 0 6px;
    border: 1px solid var(--etq-borde);
    border-radius: 4px;
    background: var(--etq-fondo);
    color: var(--etq-texto);
    font-size: 12px;
    font-weight: 600;
    line-height: 18px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    vertical-align: middle;
  }

  /* En la fila de la cola: más chico y más angosto, para que dos entren al
     lado del plazo y del dueño sin empujarlos fuera de la columna. */
  .etq-fila {
    max-width: 9em;
    padding: 0 4px;
    font-size: 11px;
    line-height: 16px;
  }
</style>
