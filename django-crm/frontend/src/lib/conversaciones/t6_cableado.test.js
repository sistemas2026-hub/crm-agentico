/**
 * El cableado de T6, leído del código (fase 1.4C).
 *
 * Por qué es un test de texto y no de componente: el harness de vitest corre en
 * `node` sin el plugin de Svelte, así que no puede compilar un `.svelte`. Lo
 * que sí puede es leerlo y afirmar sobre las decisiones que no tienen otra
 * guarda — las que, si se rompen, no las ve ni `svelte-check` ni un test de
 * lógica, porque son correctas como tipos y como CSS y aun así mandan un
 * segundo mensaje al cliente.
 *
 * Cada aserción de acá existe por un defecto concreto que ya ocurrió, no por
 * completar una grilla.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const leer = (rel) =>
  readFileSync(fileURLToPath(new URL(rel, import.meta.url)), 'utf-8');

const pagina = leer('../../routes/(app)/conversaciones/[id]/+page.svelte');
const layout = leer('../../routes/(app)/conversaciones/+layout.svelte');
const composer = leer('./composer/MessageComposer.svelte');
const proxy = leer('../../routes/api/conversaciones/[id]/humano/+server.js');
const ticket = leer('../../routes/(app)/tickets/[id]/+page.svelte');

describe('la clave de idempotencia', () => {
  it('se genera al armar la burbuja, no dentro del fetch', () => {
    // Si se generara en el cuerpo del POST, cada reintento llevaría una clave
    // nueva y el cliente recibiría el mensaje otra vez.
    const cuerpoDelPost = pagina.slice(pagina.indexOf('/humano`'));
    expect(cuerpoDelPost.slice(0, 600)).not.toMatch(/randomUUID/);
  });

  it('el reintento reusa la del mensaje', () => {
    expect(pagina).toMatch(/clave_idempotencia:\s*m\.clave_idempotencia/);
  });

  it('el reintento conserva también la intención de devolver', () => {
    // Sin esto un T6 fallido se reintenta como envío normal: el mensaje sale y
    // la conversación se queda en manos de la persona sin que nadie lo decida.
    const reintento = pagina.slice(pagina.indexOf('async function reintentar'));
    expect(reintento.slice(0, 1500)).toMatch(/devolver_al_asistente:\s*m\.devolver === true/);
  });

  it('la intención se congela con la burbuja, no se lee de `modo` al responder', () => {
    const envio = pagina.slice(pagina.indexOf('const devolviendo'));
    expect(envio.slice(0, 1800)).toMatch(/devolver_al_asistente:\s*devolviendo/);
  });
});

describe('el doble envío', () => {
  it('se corta antes de tocar nada', () => {
    expect(pagina).toMatch(/if \(!texto \|\| enviando\) return;/);
  });

  it('y el botón de enviar queda deshabilitado mientras hay un envío en vuelo', () => {
    expect(composer).toMatch(/type="submit"[\s\S]{0,120}disabled=\{enviando/);
  });

  it('devolver no se puede apretar dos veces ni en medio de un envío', () => {
    /* CAMBIO EL 22/09/2026: «devolver» dejo de ser un MODO y paso a ser una
       ACCION -- antes elegirlo no devolvia nada, habia que ademas escribir y
       enviar, y en produccion se apreto esperando que devolviera. Lo que la
       guarda protege no cambio: que no se dispare dos veces. Ahora son dos
       banderas, porque son dos caminos: con texto manda (`enviando`), sin
       texto devuelve solo (`devolviendoAIA`). */
    const boton = composer.slice(composer.indexOf('barra-devolver'));
    expect(boton.slice(0, 500)).toMatch(/disabled=\{enviando \|\| devolviendoAIA\}/);
  });
});

describe('el control no cambia antes de tiempo', () => {
  it('solo se refleja control=ia cuando el motor lo confirma', () => {
    // Nunca optimista: el mensaje puede no haber salido, y entonces la
    // conversación NO volvió a la IA.
    for (const bloque of pagina.split("conversacion.control = 'ia'").slice(0, -1)) {
      expect(bloque).toMatch(/datos\.devuelto_al_asistente[\s\S]{0,200}$/);
    }
  });

  it('el botón de devolver solo existe con la conversación en manos de personas', () => {
    /* Devolver supone tener. Con la IA atendiendo, el motor responde 409 y el
       boton no tendria a que. Se mide sobre el marcado --el `{#if escalada}`
       que lo envuelve-- y no sobre un `disabled`: un boton deshabilitado
       igual invita a apretarlo y a preguntarse por que no anda. */
    const i = composer.indexOf('barra-devolver');
    expect(i, 'no se encontro el boton de devolver').toBeGreaterThan(-1);
    const antes = composer.slice(Math.max(0, i - 700), i);
    expect(antes).toMatch(/\{#if escalada\}/);
  });
});

describe('el aviso de una conversación no aparece en otra', () => {
  // El aislamiento NO lo da un $effect que limpie: lo da el remonte. El layout
  // envuelve al hijo en {#key abierta} con abierta = page.params.id, así que al
  // cambiar de conversación Svelte destruye la página y la recrea, y todo su
  // $state arranca de cero -- el aviso incluido.
  //
  // Esta prueba existe porque esa garantía es estructural y ya se intentó
  // cambiar DOS veces: el comentario del propio layout cuenta que se probó
  // resincronizar con un $effect para evitar el parpadeo, y las dos veces el
  // panel se quedó mostrando la conversación anterior. Si alguien lo intenta
  // una tercera vez, el resultado de un T6 de A se vería en B.
  it('el layout remonta la página al cambiar de conversación', () => {
    expect(layout).toMatch(/\{#key abierta\}[\s\S]{0,200}\{@render children\(\)\}[\s\S]{0,40}\{\/key\}/);
    expect(layout).toMatch(/let abierta = \$derived\(page\.params\.id/);
  });

  it('el aviso vive en el estado de la página, que es lo que el remonte reinicia', () => {
    expect(pagina).toMatch(/let avisoDevolucion = \$state\(/);
    // Si viviera en un módulo compartido, sobreviviría al remonte y cruzaría.
    expect(pagina).not.toMatch(/import .*avisoDevolucion/);
  });

  it('y empezar un envío nuevo lo descarta, para no mezclar dos intentos', () => {
    expect(pagina).toMatch(/if \(!texto \|\| enviando\) return;\s*\n\s*avisoDevolucion = null;/);
    const reintento = pagina.slice(pagina.indexOf('async function reintentar'));
    expect(reintento.slice(0, 900)).toMatch(/avisoDevolucion = null;/);
  });
});

describe('el proxy no inventa nada', () => {
  it('rechaza T6 sin clave en vez de fabricar una', () => {
    expect(proxy).toMatch(/devolver_al_asistente && !CLAVE\.test/);
    expect(proxy).toMatch(/clave_requerida/);
  });

  it('no decide el éxito por su cuenta: devuelve lo que contestó el motor', () => {
    expect(proxy).toMatch(/return json\(datos\);/);
    expect(proxy).not.toMatch(/devuelto_al_asistente\s*[:=]\s*(true|false)/);
  });
});

describe('failed vs unknown en la pantalla', () => {
  it('la página no clasifica por su cuenta: usa devolucion.js', () => {
    expect(pagina).toMatch(/import \{ estadoDeDevolucion \}/);
    // Y no reimplementa la regla al lado.
    expect(pagina).not.toMatch(/resultado === 'incierto'/);
  });

  it('el ticket distingue el caso que antes quedaba mudo', () => {
    expect(ticket).toMatch(/form\.resultado !== 'aceptado'/);
    expect(ticket).toMatch(/no podemos confirmar/i);
  });

  it('y no ofrece reintentar lo que pudo haber salido', () => {
    const aviso = ticket.slice(ticket.indexOf('no podemos confirmar'));
    expect(aviso.slice(0, 400)).not.toMatch(/reintentar|volver a enviar</i);
  });
});

describe('lo que 1.4B dejó cerrado sigue en pie', () => {
  it('Enter envía y Shift+Enter hace salto de línea', () => {
    expect(composer).toMatch(/e\.key === 'Enter' && !e\.shiftKey/);
  });

  it('Enter respeta el modo nota', () => {
    expect(composer).toMatch(/if \(modo === 'nota'\) onGuardarNota\?\.\(\);/);
  });

  it('la ventana cerrada sigue bloqueando el texto y ofreciendo plantilla', () => {
    expect(composer).toMatch(/disabled=\{enviando \|\| bloqueadoPorVentana \|\| bloqueadoPorIA\}/);
    expect(composer).toMatch(/Elegir plantilla/);
  });

  it('con la IA atendiendo no hay herramientas ni envío', () => {
    expect(composer).toMatch(/hidden=\{modo === 'nota' \|\| bloqueadoPorIA\}/);
  });

  it('la nota interna sigue diciendo que no sale al cliente', () => {
    expect(composer).toMatch(/Solo la ve el equipo/);
  });
});
