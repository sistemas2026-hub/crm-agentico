<script>
  /**
   * La cara del agente y el pod donde trabaja.
   *
   * Que dibujo le toca a cada rol es decision de PRESENTACION y vive aqui: el
   * motor manda nombre, area y cargo, y no tiene por que saber con que imagen
   * se representa. Se resuelve por palabras clave, con un respaldo generico
   * para el rol que no encaje en ninguna -- que es lo que pasa siempre que
   * una empresa nueva llama a sus areas de otra manera.
   *
   * La Fase 2 puede sustituir esto por la imagen que el tenant elija en su
   * configuracion, igual que ya se hace con los avatares: entonces `agente`
   * traera la ruta y estas pistas quedan como respaldo.
   */
  import { colorDe } from '$lib/centro-mando/estados.js';

  /** @type {{ agente: any, alto?: number, cara?: number }} */
  let { agente, alto = 128, cara = 62 } = $props();

  const PISTAS_POD = [
    [/vent|comercial/, 'ventas'],
    [/factur|cartera|pago|cobr/, 'facturacion'],
    [/fibra|ftth|red|olt/, 'soporte-fibra'],
    [/tecnic|soporte/, 'soporte'],
    [/campo|instal|visita|cuadrilla/, 'campo'],
    [/supervis|administra|analista|gerencia/, 'supervisor'],
    [/escala/, 'escalamiento'],
    [/espera|cola/, 'espera'],
    [/cliente|recepcion|router|chat|guiad|config/, 'chat']
  ];
  const PISTAS_CARA = [
    [/vent|comercial/, 'ventas'],
    [/factur|cartera|pago|cobr/, 'facturacion'],
    [/fibra|ftth|red|olt|tecnic/, 'soporte'],
    [/campo|instal|visita/, 'campo'],
    [/supervis|administra|analista/, 'supervisor'],
    [/identidad|verific/, 'identidad'],
    [/dato|analit|informe/, 'datos'],
    [/cliente|recepcion|router|chat|guiad|config/, 'router']
  ];

  function porPistas(/** @type {any[][]} */ pistas, /** @type {string} */ respaldo) {
    const texto = `${agente.nombre} ${agente.area || ''} ${agente.cargo || ''}`.toLowerCase();
    for (const [patron, archivo] of pistas) {
      if (patron.test(texto)) return archivo;
    }
    return respaldo;
  }

  const pod = $derived(`/centro-mando/estaciones/${porPistas(PISTAS_POD, 'generica')}.webp`);
  const rostro = $derived(`/centro-mando/avatares/${porPistas(PISTAS_CARA, 'router')}.webp`);
  const color = $derived(colorDe(agente.estado));
</script>

<div class="pod" style="--c:{color}; height:{alto}px">
  <img class="fondo" src={pod} alt="" />
  <div class="tinte" style="-webkit-mask-image:url({pod}); mask-image:url({pod})"></div>
  <img class="cara" src={rostro} alt="" style="width:{cara}px; height:{cara}px" />
</div>

<style>
  .pod { position: relative; overflow: hidden; background: #030a17; }
  .fondo { position: absolute; left: 50%; top: 52%; width: 235px; transform: translate(-50%, -50%); }
  /* El tinte lleva el color del estado a TODO el pod, no solo al borde: es lo
     que permite ver desde lejos quien esta en problemas. */
  .tinte {
    position: absolute; left: 50%; top: 52%; width: 235px; height: 235px;
    transform: translate(-50%, -50%); background: var(--c); opacity: .32;
    mix-blend-mode: color; -webkit-mask-size: 100% 100%; mask-size: 100% 100%;
  }
  .cara {
    position: absolute; left: 50%; top: 46%; transform: translate(-50%, -50%);
    border-radius: 50%; object-fit: cover;
    border: 2px solid var(--c); box-shadow: 0 0 16px var(--c);
  }
</style>
