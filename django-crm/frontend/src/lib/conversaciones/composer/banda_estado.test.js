/**
 * LA BANDA DE ESTADO DEL COMPOSITOR, dibujada de verdad.
 *
 * POR QUE ESTA PRUEBA EXISTE
 * --------------------------
 * El 22/09/2026 se fundieron dos bandas en una --la de la ventana de 24 h y
 * la de quien controla la conversacion-- y la rama nueva quedo ANTES que la
 * de la IA. Resultado: con la IA atendiendo Y la ventana de WhatsApp cerrada,
 * la banda dejaba de dibujar el boton «Intervenir» y no habia forma de tomar
 * el control. No lo vio ningun test: las guardas del compositor son greps
 * sobre el archivo, y un grep no sabe que rama gana.
 *
 * Asi que esto no mira el archivo: RENDERIZA el componente con cada
 * combinacion y afirma sobre lo que sale. Es la diferencia entre comprobar
 * que el mecanismo existe y comprobar el efecto -- la misma leccion que el
 * proyecto ya pago una vez con tres pruebas en verde y el sintoma vivo.
 *
 * Las combinaciones no son adorno: son los estados que la Bandeja produce de
 * verdad. Una conversacion puede estar en manos de la IA con la ventana
 * cerrada, o escalada con la ventana cerrada, o en modo nota con cualquiera
 * de las dos -- y en cada caso la banda tiene que decir lo que se puede hacer
 * AHORA, sin esconder la unica accion disponible.
 */
import { describe, it, expect } from 'vitest';
import { render } from 'svelte/server';
import MessageComposer from './MessageComposer.svelte';

/** Lo minimo para que el compositor se dibuje. Nada de esto es la prueba. */
const BASE = {
  conversacion: { id: 'x', canal: 'whatsapp', estado: 'abierta' },
  error: '',
  escalada: false,
  enviando: false,
  avisoDevolucion: null,
  bloqueadoPorIA: false,
  bloqueadoPorVentana: false,
  interviniendo: false,
  errorIntervenir: '',
  adjunto: null,
  grabando: false,
  grabPausada: false,
  segundos: 0,
  limites: {},
  ventanaAbierta: true,
  ventanaRestante: 3600,
  ventanaPorCerrarse: false,
  plantillas: [],
  cargandoPlantillas: false,
  errorPlantillas: '',
  enviandoPlantilla: false,
  plantillaCompleta: false,
  vistaPreviaPlantilla: '',
  hayPlantillaDeServicio: false,
  etiquetasPlantilla: [],
  plantillaBloqueada: false,
  entrada: '',
  modo: 'responder',
  campoTexto: null,
  adjuntarAbierto: false,
  emojisAbiertos: false,
  arrastrando: false,
  eligiendoPlantilla: false,
  plantillaElegida: null,
  valoresPlantilla: {},
  EMOJIS: [],
  reloj: (n) => `0:0${n}`,
  comoDuracion: () => '3 h'
};

/** El HTML de la banda, sin etiquetas, para poder afirmar sobre el texto. */
function banda(props) {
  const { body } = render(MessageComposer, { props: { ...BASE, ...props } });
  const m = body.match(/<div class="[^"]*\bbanda\b[^"]*"[\s\S]*?<\/div>\s*<!--/);
  const trozo = m ? m[0] : body;
  return {
    html: trozo,
    texto: trozo
      .replace(/<[^>]+>/g, ' ')
      .replace(/&middot;|&#183;/g, '·')
      .replace(/\s+/g, ' ')
      .trim(),
    cuerpo: body
  };
}

describe('la banda dice lo que se puede hacer AHORA', () => {
  it('la IA atendiendo: ofrece tomar el control', () => {
    const b = banda({ bloqueadoPorIA: true });
    expect(b.texto).toMatch(/atiende la IA/i);
    expect(b.texto).toMatch(/Intervenir/);
  });

  it('LA COMBINACION QUE SE ROMPIO: IA atendiendo Y ventana cerrada', () => {
    /* Las dos cosas son ciertas a la vez y las dos hay que decirlas, pero el
       orden importa: primero se toma el control, y recien despues la ventana
       es un problema de uno. Si la ventana gana, esta rama no se dibuja y el
       boton desaparece -- que es exactamente lo que paso. */
    const b = banda({ bloqueadoPorIA: true, bloqueadoPorVentana: true });
    expect(b.texto, 'sin «Intervenir» no hay forma de tomar el control')
      .toMatch(/Intervenir/);
    expect(b.texto, 'y la ventana cerrada tambien tiene que constar')
      .toMatch(/ventana de WhatsApp/i);
    // El control primero, la ventana despues. Se compara por posicion y no
    // por la existencia de los dos textos: los dos existian antes tambien.
    expect(b.texto.indexOf('Intervenir'))
      .toBeLessThan(b.texto.search(/ventana de WhatsApp/i));
  });

  it('ventana cerrada sin la IA: dice que hace falta una plantilla', () => {
    const b = banda({ escalada: true, bloqueadoPorVentana: true });
    expect(b.texto).toMatch(/Ventana de WhatsApp cerrada/i);
    expect(b.texto).toMatch(/plantilla aprobada/i);
    expect(b.texto, 'sin la IA atendiendo no hay nada que intervenir')
      .not.toMatch(/Intervenir/);
  });

  it('escalada y sin trabas: avisa que sale DIRECTO al cliente', () => {
    const b = banda({ escalada: true });
    expect(b.texto).toMatch(/directo al cliente/i);
    expect(b.texto).toMatch(/no pasa por el asistente/i);
  });

  it('nota interna: dice que el cliente no la ve, gane lo que gane', () => {
    /* La nota va PRIMERA en las ramas y tiene que seguir yendo: es el estado
       que mas caro sale confundir. Una nota que parezca un mensaje enviado se
       lee como algo que se le dijo al cliente. */
    for (const extra of [
      {},
      { bloqueadoPorVentana: true },
      { bloqueadoPorIA: true },
      { escalada: true, bloqueadoPorVentana: true, bloqueadoPorIA: true }
    ]) {
      const b = banda({ modo: 'nota', ...extra });
      expect(b.texto, JSON.stringify(extra)).toMatch(/Solo la ve el equipo/i);
      expect(b.texto, JSON.stringify(extra)).toMatch(/no se le envía al cliente/i);
    }
  });

  it('responder y devolver: dice las dos cosas que van a pasar', () => {
    const b = banda({ escalada: true, modo: 'responder_y_devolver' });
    expect(b.texto).toMatch(/vuelve a la IA/i);
    expect(b.texto, 'la condicion no es obvia y tiene que constar')
      .toMatch(/solo si el mensaje sale/i);
  });

  it('nunca sale vacia: en cualquier combinacion dice algo', () => {
    /* Una banda vacia es peor que no tenerla: ocupa el lugar donde se busca
       la respuesta y no la da. */
    for (const modo of ['responder', 'nota', 'responder_y_devolver']) {
      for (const escalada of [true, false]) {
        for (const ia of [true, false]) {
          for (const ventana of [true, false]) {
            const b = banda({
              modo,
              escalada,
              bloqueadoPorIA: ia,
              bloqueadoPorVentana: ventana
            });
            const caso = `modo=${modo} escalada=${escalada} ia=${ia} ventana=${ventana}`;
            expect(b.texto.length, caso).toBeGreaterThan(12);
          }
        }
      }
    }
  });

  it('el sello de la derecha no contradice al texto', () => {
    /* Texto, sello y tono describen el MISMO estado, y salen de tres listas
       distintas: una `{#if}` en el marcado y dos `$derived` en el script. El
       22/09/2026 se reordeno una y no las otras, y la banda quedo diciendo
       «ventana cerrada» con el sello «responde el asistente» al lado.

       Esto compara los tres en las combinaciones donde se separaron. */
    const casos = [
      [{ bloqueadoPorIA: true }, /atiende la IA/i, /RESPONDE EL ASISTENTE/i],
      [{ bloqueadoPorIA: true, bloqueadoPorVentana: true }, /atiende la IA/i, /RESPONDE EL ASISTENTE/i],
      [{ escalada: true, bloqueadoPorVentana: true }, /Ventana de WhatsApp cerrada/i, /24 h/],
      [{ escalada: true }, /directo al cliente/i, /CANAL DIRECTO/i],
      [{ modo: 'nota' }, /Solo la ve el equipo/i, /INTERNO/i]
    ];
    for (const [props, texto, sello] of casos) {
      const b = banda(props);
      const etiqueta = JSON.stringify(props);
      expect(b.texto, etiqueta).toMatch(texto);
      expect(b.html, etiqueta).toMatch(sello);
    }
  });
});

describe('el cuadro de texto se encoge cuando no se puede escribir', () => {
  it('una fila bloqueado, dos cuando se puede escribir', () => {
    /* Son 64px de caja donde nadie puede tipear, en una columna donde el hilo
       se quedaba con el 18%. */
    const conFilas = (props) => {
      const { body } = render(MessageComposer, { props: { ...BASE, ...props } });
      return body.match(/<textarea[^>]*\brows="(\d)"/)?.[1] ?? null;
    };
    expect(conFilas({ escalada: true })).toBe('2');
    expect(conFilas({ bloqueadoPorIA: true })).toBe('1');
    expect(conFilas({ bloqueadoPorVentana: true })).toBe('1');
  });
});

describe('la banda de la ventana de 24 h solo aparece cuando avisa algo', () => {
  /* Se dibujaba SIEMPRE, tambien para decir «ventana abierta», que es el
     estado normal: 48px de una columna de 702 para no decir nada. Abierta lo
     dice el sello del canal de la barra; cerrada lo dice la banda de estado. */
  const hayVentana = (props) => {
    const { body } = render(MessageComposer, { props: { ...BASE, ...props } });
    return / class="ventana/.test(body);
  };

  it('abierta y tranquila: no se dibuja', () => {
    expect(hayVentana({ escalada: true })).toBe(false);
  });

  it('cerrada: tampoco, porque lo dice la banda de estado', () => {
    expect(
      hayVentana({ escalada: true, ventanaAbierta: false, bloqueadoPorVentana: true })
    ).toBe(false);
  });

  it('por cerrarse: SI, porque pide una decision', () => {
    /* Es el unico de los tres estados que cambia lo que conviene hacer
       ahora: escribir, o quedarse sin poder. */
    expect(hayVentana({ escalada: true, ventanaPorCerrarse: true })).toBe(true);
  });
});
