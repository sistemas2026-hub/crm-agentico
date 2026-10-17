/**
 * La sesión de grabación de una nota de voz: el micrófono, el `MediaRecorder`
 * y el cronómetro, con UN SOLO camino de liberación.
 *
 * POR QUÉ ESTO ES UN MÓDULO Y NO CÓDIGO SUELTO EN LA PÁGINA (D29)
 * ---------------------------------------------------------------
 * Porque el defecto que arregla no se puede probar de otra forma. El harness
 * de vitest de este frontend corre en `node`, sin plugin de Svelte: no compila
 * `.svelte`, así que un test no puede montar `[id]/+page.svelte` ni observar su
 * desmontaje. Un módulo plano sobre `navigator.mediaDevices` y `MediaRecorder`
 * sí se prueba, con los dos stubeados en `globalThis`.
 *
 * La página sigue siendo la dueña: crea la sesión, refleja su estado y la
 * suelta en `onDestroy`. Esto no es un componente y no dibuja nada;
 * `MessageComposer` sigue siendo presentación pura.
 *
 * EL DEFECTO, EN DOS FORMAS
 * -------------------------
 * La conversación se remonta entera al cambiar de chat (`{#key abierta}` en
 * `+layout.svelte`), y antes de esto no existía un solo `onDestroy`. Así que:
 *
 *   1. grabando y me voy      → el micrófono quedaba abierto, el cronómetro
 *                               vivo y el `onstop` podía armar un adjunto para
 *                               una pantalla que ya no existe;
 *   2. me voy y el permiso
 *      del micrófono se
 *      concede DESPUÉS        → `getUserMedia` resolvía sobre una pantalla
 *                               muerta y encendía el micrófono igual.
 *
 * La segunda es la que `onDestroy` por sí solo NO arregla: en el instante del
 * desmontaje no hay nada que apagar todavía. Por eso `soltada` es un
 * interruptor de ida, y se vuelve a mirar DESPUÉS del `await`.
 */

/** Lo que graba el navegador tiene que ser uno de los formatos que WhatsApp
    acepta. Chrome y Firefox dan 'audio/webm' por defecto, que NO está en la
    lista de Meta -- ogg/opus sí, y es el mismo códec. */
const FORMATOS = ['audio/ogg;codecs=opus', 'audio/mp4', 'audio/mpeg'];

export function formatoDeGrabacion() {
  // `globalThis` y no `window`: es lo mismo en el navegador y además deja que
  // el test lo stubee sin DOM.
  const Grabador = globalThis.MediaRecorder;
  return FORMATOS.find((m) => Grabador?.isTypeSupported?.(m)) ?? '';
}

export const SIN_FORMATO =
  'Este navegador no graba en un formato que WhatsApp acepte. Podés adjuntar un audio ya grabado.';
export const SIN_MICROFONO = 'No se pudo usar el micrófono. Revisá el permiso del navegador.';

/**
 * @param {{
 *   alArchivo: (f: File) => void,
 *   alFallar: (mensaje: string) => void,
 *   alCambiar: (e: { grabando: boolean, pausada: boolean }) => void,
 *   alSegundo: (s: number) => void
 * }} avisos
 */
export function sesionDeGrabacion({ alArchivo, alFallar, alCambiar, alSegundo }) {
  /** @type {any} */
  let grabador = null;
  /** @type {any} */
  let cronometro = null;
  let pausada = false;
  let segundos = 0;
  // El interruptor de D29. Una vez soltada la sesión, ningún micrófono que
  // llegue tarde puede encenderse.
  let soltada = false;

  function limpiarCronometro() {
    if (cronometro !== null) {
      clearInterval(cronometro);
      cronometro = null;
    }
  }

  /**
   * Suelta todo SIN armar archivo, y sin fallar si ya estaba suelto.
   *
   * Desmontar no es terminar de grabar: por eso lo primero que se hace es
   * desarmar el `onstop`, que en una grabación normal es justo el que arma el
   * adjunto. Es el mismo orden que ya usaba «Cancelar», ahora en un solo lugar.
   *
   * `definitivo` distingue las dos razones para soltar: el desmontaje cierra la
   * sesión para siempre; «Cancelar» la deja lista para volver a grabar.
   */
  function soltar({ definitivo = true } = {}) {
    if (definitivo) soltada = true;
    limpiarCronometro();
    const r = grabador;
    grabador = null;
    pausada = false;
    segundos = 0;
    if (!r) return;
    r.onstop = null;
    r.ondataavailable = null;
    r.stream?.getTracks().forEach((/** @type {any} */ t) => t.stop());
    // `stop()` sobre un recorder ya detenido lanza InvalidStateError, y este
    // teardown tiene que poder correr dos veces.
    if (r.state !== 'inactive') r.stop();
  }

  return {
    get soltada() {
      return soltada;
    },
    get activa() {
      return grabador !== null;
    },

    async iniciar() {
      const formato = formatoDeGrabacion();
      if (!formato) {
        alFallar(SIN_FORMATO);
        return;
      }
      /** @type {any} */
      let flujo = null;
      try {
        flujo = await globalThis.navigator.mediaDevices.getUserMedia({ audio: true });
        // D29, la carrera. El permiso puede resolverse DESPUÉS de que quien
        // atiende cambió de conversación: en este punto el micrófono ya está
        // abierto, así que hay que cerrarlo acá mismo y no seguir.
        if (soltada) {
          flujo.getTracks().forEach((/** @type {any} */ t) => t.stop());
          return;
        }
        const trozos = /** @type {Blob[]} */ ([]);
        grabador = new globalThis.MediaRecorder(flujo, { mimeType: formato });
        grabador.ondataavailable = (/** @type {any} */ ev) => ev.data.size && trozos.push(ev.data);
        grabador.onstop = () => {
          // El micrófono se suelta SIEMPRE: sin esto el navegador deja el
          // indicador de grabación encendido hasta cerrar la pestaña.
          flujo.getTracks().forEach((/** @type {any} */ t) => t.stop());
          limpiarCronometro();
          grabador = null;
          pausada = false;
          alCambiar({ grabando: false, pausada: false });
          if (!trozos.length) return;
          const base = formato.split(';')[0];
          alArchivo(
            new File([new Blob(trozos, { type: base })], `nota-de-voz.${base.split('/')[1]}`, {
              type: base
            })
          );
        };
        grabador.start();
        segundos = 0;
        pausada = false;
        alSegundo(0);
        alFallar('');
        alCambiar({ grabando: true, pausada: false });
        cronometro = setInterval(() => {
          if (!pausada) alSegundo((segundos += 1));
        }, 1000);
      } catch {
        // Si falló DESPUÉS de conseguir el flujo (un MediaRecorder que no
        // acepta el formato, por ejemplo), el micrófono ya estaba abierto.
        flujo?.getTracks().forEach((/** @type {any} */ t) => t.stop());
        alFallar(SIN_MICROFONO);
      }
    },

    pausar() {
      if (!grabador) return;
      if (pausada) {
        grabador.resume();
        pausada = false;
      } else {
        grabador.pause();
        pausada = true;
      }
      alCambiar({ grabando: true, pausada });
    },

    /** Parar deja la grabación como adjunto pendiente de confirmación: el
        `onstop` sí corre y sí arma el archivo. */
    parar() {
      grabador?.stop();
    },

    /** Cancelar la tira. La sesión queda utilizable: se puede volver a grabar. */
    cancelar() {
      soltar({ definitivo: false });
      alCambiar({ grabando: false, pausada: false });
    },

    soltar
  };
}

/**
 * El cuerpo del `onDestroy` de la conversación, en una función para poder
 * probarlo.
 *
 * El object URL se revoca porque es NUESTRO: `adjunto.url` nace en un único
 * lugar (`tomarArchivo`) y siempre de `URL.createObjectURL`, nunca de una URL
 * remota del servidor -- los medios que llegan en el hilo son otra cosa y no
 * pasan por acá. Si algún día `adjunto.url` pudiera venir de afuera, esta
 * condición deja de ser correcta.
 *
 * @param {{ sesion?: { soltar: (o?: any) => void } | null, adjunto?: any,
 *           revocar?: (url: string) => void }} recursos
 */
export function soltarRecursosDelCompositor({
  sesion,
  adjunto,
  revocar = (url) => URL.revokeObjectURL(url)
}) {
  sesion?.soltar();
  if (adjunto?.url) revocar(adjunto.url);
}
