<script>
  /**
   * Cómo llegó la conversación a estas manos — el registro de relevo.
   *
   * El relevo escribe un evento por transición desde B3.3. La pantalla decía
   * QUIÉN la lleva, no CÓMO llegó: una reasignación de supervisor y una
   * devolución a la IA se veían igual desde afuera.
   *
   * Es presentación pura: los eventos llegan del server load y la traducción a
   * palabras vive en actividad.js, fuera de Svelte y con pruebas. Acá no se
   * deduce nada — ni quién actuó, ni el desenlace de una devolución, ni el
   * rótulo de la insignia.
   *
   * EL ORDEN CAMBIO EL 21/09/2026, Y ES UNA CORRECCION
   * --------------------------------------------------
   * Este panel mostraba el evento más reciente arriba, con el argumento de que
   * "lo último que pasó es lo que se busca al abrir". Era el argumento
   * equivocado para esta pestaña: acá no se consulta un estado --ese está en la
   * cabecera, que dice quién la lleva ahora mismo-- sino que se RECONSTRUYE una
   * secuencia. "Ana la tomó, la soltó, Luis la tomó, el supervisor se la pasó
   * de vuelta a Ana" sólo se lee en el orden en que ocurrió; al revés hay que
   * leerla entera y darla vuelta en la cabeza.
   *
   * Y el orden es el de la VERSION DE RELEVO, no el del reloj (D27). Dos
   * eventos pueden compartir marca de tiempo --se escriben en la misma
   * transacción-- y la hora no los desempata; la versión sí. El motor ya los
   * devuelve en ese orden, así que acá no se reordena nada: se dibujan como
   * llegan. El pie lo dice, porque una lista con horas invita a suponer que
   * están ordenadas por hora.
   */
  import { lineaDeActividad } from '$lib/conversaciones/actividad.js';

  let { eventos = [] } = $props();

  /* Sin `.reverse()`: el orden del motor ES el orden de la versión de relevo.
     Darlos vuelta acá rompería D27 además de la lectura. */
  const lineas = $derived(eventos.map(lineaDeActividad));

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

<section class="actividad">
  <!-- La cabecera lleva el conteo a la derecha, no dentro del título: es el
       dato que dice de un vistazo si hubo mucho movimiento, y pegado al
       rótulo se lee como parte del nombre del panel. -->
  <div class="cabecera">
    <span class="rotulo">Registro de relevo</span>
    <span class="conteo">
      {lineas.length}
      {lineas.length === 1 ? 'evento' : 'eventos'}
    </span>
  </div>

  <!-- SIN MOVIMIENTOS TAMBIÉN SE DIBUJA. Desde que la columna se organiza en
       pestañas, callar significa que quien abre "Actividad" encuentra una
       pestaña en blanco -- que se lee como una pantalla rota, no como una
       conversación sin movimientos.
       Y no es lo mismo "no sabemos" que "no pasó nada": el relevo escribe un
       evento por transición, así que una lista vacía es un hecho comprobado. -->
  {#if lineas.length === 0}
    <p class="vacio">
      Todavía no cambió de manos: no hay ninguna toma, devolución, reasignación
      ni cierre registrado en esta conversación.
    </p>
  {:else}
    <ol class="linea-tiempo">
      {#each lineas as l, i (i)}
        <li class="evento tono-{l.tono}">
          <span class="marca" aria-hidden="true"></span>
          <div class="cuerpo">
            <div class="encabezado">
              <time class="hora" datetime={l.cuando} title={dia(l.cuando)}>{hora(l.cuando)}</time>
              <span class="punto" aria-hidden="true">·</span>
              <span class="insignia">{l.insignia}</span>
              <!-- Quién actuó, a la derecha. `actorDe()` nunca inventa: cuando
                   el evento no lo registra dice "Sin registro", y eso se
                   muestra tal cual en vez de dejar el hueco. -->
              <span class="actor">{l.quien}</span>
            </div>
            <p class="que">{l.texto}</p>
            {#if l.detalle}<p class="detalle">{l.detalle}</p>{/if}
          </div>
        </li>
      {/each}
    </ol>

    <p class="pie">Ordenado por versión de relevo — las horas son de referencia.</p>
  {/if}
</section>

<style>
  .actividad {
    display: flex;
    flex-direction: column;
  }

  .cabecera {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    padding-bottom: 10px;
    margin-bottom: 14px;
    border-bottom: 1px solid var(--bandeja-borde);
  }
  .rotulo {
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--bandeja-texto);
  }
  .conteo {
    font-family: var(--bandeja-mono);
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--bandeja-texto-3);
    white-space: nowrap;
  }

  .vacio {
    margin: 0;
    font-size: 12px;
    line-height: 1.5;
    color: var(--bandeja-texto-2);
  }

  /* EL RIEL ES UNO SOLO, no el borde de cada entrada.
     Con un borde por ítem, el hilo se corta en cada separación y el último
     evento necesita una regla aparte para no dejar un muñón colgando. Un
     único absoluto acotado con top/bottom entra y sale a la altura de los
     puntos extremos, que es como lo dibuja la referencia. */
  .linea-tiempo {
    position: relative;
    list-style: none;
    margin: 0;
    padding: 0 0 0 17px;
    display: flex;
    flex-direction: column;
    gap: 18px;
  }
  .linea-tiempo::before {
    content: '';
    position: absolute;
    left: 4px;
    top: 6px;
    bottom: 6px;
    width: 1px;
    background: var(--bandeja-borde);
  }

  .evento {
    position: relative;
    display: flex;
    gap: 10px;
  }

  /* Cuadrado, no círculo: el sistema visual prohíbe las píldoras y las formas
     redondas fuera de los avatares, y un cuadrito de 2px de radio se distingue
     del punto de "en curso" de la cola, que sí es un círculo. */
  .marca {
    position: absolute;
    left: -17px;
    top: 4px;
    width: 9px;
    height: 9px;
    border-radius: 2px;
    background: var(--bandeja-texto-3);
    z-index: 1;
  }
  .tono-ia .marca {
    background: var(--bandeja-ia);
  }
  .tono-humano .marca {
    background: var(--bandeja-humano);
  }
  .tono-aviso .marca {
    background: var(--bandeja-aviso);
  }
  .tono-ok .marca {
    background: var(--bandeja-ok);
  }

  .cuerpo {
    min-width: 0;
    flex: 1;
  }

  .encabezado {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 3px;
  }
  .hora {
    font-family: var(--bandeja-mono);
    font-size: 10px;
    font-weight: 500;
    color: var(--bandeja-texto-3);
    flex: none;
  }
  .punto {
    color: var(--bandeja-borde-fuerte);
    flex: none;
  }

  .insignia {
    font-family: var(--bandeja-mono);
    font-size: 9.5px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    padding: 1px 5px;
    border-radius: 3px;
    border: 1px solid var(--bandeja-borde);
    background: var(--bandeja-superficie-suave);
    color: var(--bandeja-texto-2);
    flex: none;
    white-space: nowrap;
  }
  .tono-ia .insignia {
    background: var(--bandeja-ia-fondo);
    border-color: var(--bandeja-ia-borde);
    color: var(--bandeja-ia);
  }
  .tono-humano .insignia {
    background: var(--bandeja-humano-fondo);
    border-color: var(--bandeja-humano-borde);
    color: var(--bandeja-humano);
  }
  .tono-aviso .insignia {
    background: var(--bandeja-aviso-fondo);
    border-color: var(--bandeja-aviso-borde);
    color: var(--bandeja-aviso);
  }
  /* `--bandeja-ok` no tiene pareja de fondo y borde declarada, así que se
     derivan con color-mix en vez de inventar dos hex sueltos fuera del
     sistema de tokens. Mismo recurso que ya usa la píldora de verificación
     del panel de cliente. */
  .tono-ok .insignia {
    background: color-mix(in srgb, var(--bandeja-ok) 10%, transparent);
    border-color: color-mix(in srgb, var(--bandeja-ok) 30%, transparent);
    color: var(--bandeja-ok);
  }

  /* PEGADO A LA INSIGNIA, no al borde derecho. Estaba con `margin-left:auto`
     y el ojo tenía que cruzar la columna entera para juntar «TOMADA» con
     quién la tomó -- que es una sola frase. La referencia los pone juntos:
     hora · insignia · nombre, y el nombre en oscuro porque es lo que se
     busca al recorrer la lista. */
  .actor {
    font-size: 11.5px;
    font-weight: 600;
    color: var(--bandeja-texto);
    min-width: 0;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  .que {
    margin: 0;
    font-size: 12px;
    line-height: 1.45;
    color: var(--bandeja-texto);
  }

  .detalle {
    margin: 2px 0 0;
    font-family: var(--bandeja-mono);
    font-size: 11px;
    line-height: 1.4;
    color: var(--bandeja-texto-3);
    overflow-wrap: anywhere;
  }

  .pie {
    margin: 20px 0 0;
    padding-top: 10px;
    border-top: 1px solid var(--bandeja-borde);
    font-family: var(--bandeja-mono);
    font-size: 10px;
    line-height: 1.4;
    text-align: center;
    color: var(--bandeja-texto-3);
  }
</style>
