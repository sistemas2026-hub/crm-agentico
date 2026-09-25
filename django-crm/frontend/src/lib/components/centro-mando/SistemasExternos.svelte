<script>
  /**
   * Los sistemas externos, al pie de la planta.
   *
   * POR QUE AQUI Y NO EN LA COLUMNA LATERAL
   * Esta pantalla existe para saber que pasa, y cuando algo falla lo primero
   * que se ve son varios puestos en rojo. La causa suele ser UNA: un sistema
   * externo caido. Tenerla en otra columna, en chips de 10 px con un borde
   * rojo por toda senal, obliga a cruzar dos sitios de la pantalla para unir
   * el efecto con su causa. Va debajo de la oficina, que es donde se mira el
   * efecto.
   *
   * POR QUE UNA FRANJA PLANA Y NO LOS RACKS ISOMETRICOS DEL PROTOTIPO
   * Se dibujaron primero como una fila de racks 3D dentro del lienzo. Se ve
   * bonito y no sirve: se comian 1.10 L de alto, y como la escala de la
   * planta sale del espacio que queda, en 1366x768 --la resolucion donde se
   * mira este tablero-- TODO encogia: los racks quedaban diminutos y los
   * nombres de los puestos, ilegibles. Fuera del lienzo y con alto fijo no
   * compiten por la escala con la oficina.
   *
   * DE DONDE SALE LA LISTA
   * De `servicios` del panorama, que el motor arma contando `tool_calls`. No
   * hay una lista de sistemas declarada a mano en ningun sitio: si una
   * empresa conecta uno nuevo, aparece solo en cuanto se use.
   */

  /** @type {{ servicios: any[], ms: (v: any) => string, maximo?: number }} */
  let { servicios, ms, maximo = 6 } = $props();

  const lista = $derived((servicios || []).slice(0, maximo));

  /**
   * La salud de un sistema, por TASA y no por cuenta.
   *
   * Dos fallos de dos llamadas y dos de doscientas son cosas distintas, y el
   * numero solo no las separa: el primero es un sistema caido, el segundo es
   * ruido normal. El umbral de 20% no pretende ser exacto -- separa "algo va
   * mal ahi" de "fallo alguna suelta", que es la unica distincion que esta
   * franja tiene que soportar.
   */
  function salud(s) {
    const usos = s.usos || 0;
    const fallos = s.fallos || 0;
    if (fallos === 0) return { color: '#15803D', rotulo: 'responde' };
    if (usos && fallos / usos > 0.2) return { color: '#B91C1C', rotulo: 'fallando' };
    return { color: '#A15C07', rotulo: 'con fallos sueltos' };
  }
</script>

{#if lista.length}
  <div class="sistemas">
    <span class="et">Sistemas<br />externos</span>
    {#each lista as s (s.herramienta)}
      {@const e = salud(s)}
      <div class="sis" title="{s.herramienta} — {e.rotulo}: {s.usos || 0} usos{s.fallos ? `, ${s.fallos} fallaron` : ''}{s.duracion_media_ms != null ? `, ${ms(s.duracion_media_ms)} de media` : ''}{s.ultimo_agente ? ` · último: ${String(s.ultimo_agente).replaceAll('_', ' ')}` : ''}">
        <span class="barra" style="background:{e.color}"></span>
        <span class="cuerpo">
          <span class="n">{s.herramienta}</span>
          <span class="d">
            {s.usos || 0} usos
            {#if s.fallos}· <b style="color:{e.color}">{s.fallos} fallaron</b>{/if}
            {#if s.duracion_media_ms != null}· {ms(s.duracion_media_ms)}{/if}
          </span>
        </span>
      </div>
    {/each}
  </div>
{/if}

<style>
  .sistemas {
    flex: 0 0 auto; display: flex; align-items: stretch; gap: 8px;
    padding: 7px 0 0; overflow-x: auto; max-height: 62px;
  }
  /* Horizontal y corta. En vertical (writing-mode) el rotulo estiraba la
     franja y la empujaba fuera de la pantalla: existia, tenia sus tarjetas,
     y no se veia ninguna. */
  .et {
    font-size: 8.5px; letter-spacing: .1em; text-transform: uppercase;
    font-weight: 700; color: #94a3b8; flex: 0 0 auto;
    align-self: center; line-height: 1.25;
  }
  .sis {
    display: flex; align-items: stretch; gap: 8px; flex: 1 1 0; min-width: 138px;
    background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px;
    overflow: hidden;
  }
  .barra { width: 4px; flex: 0 0 auto; }
  .cuerpo { padding: 5px 8px 5px 2px; display: flex; flex-direction: column; justify-content: center; min-width: 0; }
  .n {
    font-family: ui-monospace, monospace; font-size: 10.5px; font-weight: 700; color: #0f172a;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .d { font-size: 9.5px; color: #475569; margin-top: 2px; white-space: nowrap; }
</style>
