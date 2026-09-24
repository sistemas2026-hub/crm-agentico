<script>
  /**
   * El orquestador: quien recibe lo que entra y lo reparte. No es un agente
   * mas -- no tiene conversaciones propias -- y por eso ocupa el centro del
   * mapa en vez de una posicion del anillo.
   *
   * El rotulo va DENTRO del disco: colgado debajo, el nodo de abajo del
   * anillo lo tapaba (visto el 24/09/2026).
   *
   * El reparto por estado sigue llegando aunque hoy no se pinte aqui: de el
   * salen el color y el grosor de cada via, que dibuja el CommandCenter.
   */
  /** @type {{ totales: any }} */
  let { totales } = $props();
</script>

<div class="nucleo">
  <span class="rot">Orquestador</span>
  <span class="n">{totales.conversaciones_activas ?? 0}</span>
  <span class="sub">en curso</span>
</div>

<style>
  .nucleo {
    position: absolute;
    left: 50%;
    top: 50%;
    transform: translate(-50%, -50%);
    width: 124px;
    height: 124px;
    border-radius: 50%;
    background: radial-gradient(circle at 50% 30%, #ffffff, #f1f5f9 72%);
    border: 2px solid #0e7490;
    box-shadow: 0 2px 16px rgba(14, 116, 144, .18);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
  }
  .rot { font-family: ui-monospace, monospace; font-size: 8px; letter-spacing: .2em; text-transform: uppercase; color: #0e7490; margin-bottom: 5px; }
  .n { font-family: ui-monospace, monospace; font-size: 26px; font-weight: 700; line-height: 1.05; color: #0f172a; }
  .sub { font-size: 8px; letter-spacing: .14em; color: #475569; text-transform: uppercase; }
</style>
