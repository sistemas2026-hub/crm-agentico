/**
 * Las pestañas de la cola tienen que cerrar la suma (04/11/2026).
 *
 * El defecto que motivó esto: «Por atender 20 · En atención 2 · Resueltas 17»
 * sobre «Todos 50». Los 11 que faltaban —abiertos, los lleva la IA— no
 * estaban en ninguna pestaña salvo «Todos». Se afirma sobre el EFECTO: que
 * cada chat cae en al menos una pestaña y que la cuenta coincide con lo que
 * la lista filtra, no que exista una función con cierto nombre.
 */
import { describe, it, expect } from 'vitest';
import {
  llevaLaIA,
  deLaPestana,
  contarPestanas,
  esperaEnPalabras,
  titularDeCola
} from './pestanas.js';
import { pendiente, enAtencion, resuelta } from '$lib/conversaciones/estado.js';

/* Un chat de cada forma, con los campos que de verdad miran los predicados
   de estado.js. */
const escaladaSinTomar = { id: 'a', estado: 'abierta', escalada_a_humano: true };
const tomada = { id: 'b', estado: 'abierta', escalada_a_humano: true, tomada_por: 'ana' };
const laLlevaLaIA = { id: 'c', estado: 'abierta' };
const cerrada = { id: 'd', estado: 'cerrada' };
/* Un chat con DOS abiertas en estados distintos: la fila está tomada y otra
   abierta del mismo número espera a una persona. */
const dosAbiertas = {
  id: 'e',
  estado: 'abierta',
  tomada_por: 'ana',
  abiertas: [{ id: 'e2', estado: 'abierta', escalada_a_humano: true }]
};

describe('Lleva la IA es el complemento de las otras tres', () => {
  it('un chat abierto que nadie pidió ni tomó cae ahí, y en ninguna otra', () => {
    expect(llevaLaIA(laLlevaLaIA)).toBe(true);
    expect(pendiente(laLlevaLaIA) || enAtencion(laLlevaLaIA) || resuelta(laLlevaLaIA)).toBe(false);
  });

  it('no se lleva ni una pedida, ni una tomada, ni una cerrada', () => {
    expect(llevaLaIA(escaladaSinTomar)).toBe(false);
    expect(llevaLaIA(tomada)).toBe(false);
    expect(llevaLaIA(cerrada)).toBe(false);
  });

  it('cerrada pero con otra abierta del mismo número NO es resuelta: la cuenta alguien', () => {
    const vuelve = { id: 'f', estado: 'cerrada', abiertas: [{ id: 'f2', estado: 'abierta' }] };
    expect(resuelta(vuelve)).toBe(false);
    expect(llevaLaIA(vuelve)).toBe(true);
  });
});

describe('la cuenta y la lista dicen lo mismo', () => {
  const base = [escaladaSinTomar, tomada, laLlevaLaIA, cerrada];

  it('sin chats dobles, las cuatro primeras suman el total', () => {
    const { n, suma, cierra } = contarPestanas(base);
    expect(n).toEqual({ 'por-atender': 1, 'en-atencion': 1, 'lleva-ia': 1, resueltas: 1, todas: 4 });
    expect(suma).toBe(4);
    expect(cierra).toBe(true);
  });

  it('cada número es el largo de lo que la pestaña filtra', () => {
    const conDoble = [...base, dosAbiertas];
    const { n } = contarPestanas(conDoble);
    for (const id of ['por-atender', 'en-atencion', 'lleva-ia', 'resueltas', 'todas']) {
      expect(deLaPestana(conDoble, id).length).toBe(n[id]);
    }
  });

  it('un chat con dos abiertas en estados distintos cuenta en dos y la suma no cierra', () => {
    const { n, suma, cierra } = contarPestanas([dosAbiertas]);
    expect(n['por-atender']).toBe(1);
    expect(n['en-atencion']).toBe(1);
    expect(suma).toBe(2);
    expect(cierra).toBe(false);
  });

  it('ningún chat queda fuera de las cuatro primeras', () => {
    const conDoble = [...base, dosAbiertas];
    const ids = ['por-atender', 'en-atencion', 'lleva-ia', 'resueltas'];
    for (const c of conDoble) {
      expect(ids.some((id) => deLaPestana([c], id).length === 1)).toBe(true);
    }
  });

  it('una pestaña desconocida no vacía la cola', () => {
    expect(deLaPestana(base, 'no-existe')).toBe(base);
    expect(deLaPestana(base, 'todas')).toBe(base);
  });
});

describe('la frase de arriba', () => {
  it('sin pendientes dice que no hay nada, sin cifra', () => {
    expect(titularDeCola(0, 5)).toEqual({ cifra: null, texto: 'Nada por atender', espera: null });
  });

  it('con pendientes, la cifra aparte y la espera en palabras', () => {
    expect(titularDeCola(20, 2.2)).toEqual({
      cifra: 20,
      texto: 'por atender',
      espera: 'la más antigua espera 2 h'
    });
  });

  it('con una sola, no habla de «la más antigua»', () => {
    expect(titularDeCola(1, 0.5).espera).toBe('espera 30 min');
  });

  it('si la espera no se sabe, se omite esa parte en vez de inventarla', () => {
    expect(titularDeCola(3, null).espera).toBe(null);
  });

  it('la espera en palabras, por tramos', () => {
    expect(esperaEnPalabras(null)).toBe(null);
    expect(esperaEnPalabras(0.001)).toBe('1 min');
    expect(esperaEnPalabras(47)).toBe('47 h');
    expect(esperaEnPalabras(30)).toBe('30 h');
    expect(esperaEnPalabras(50)).toBe('2 días');
    expect(esperaEnPalabras(30 * 24)).toBe('30 días');
  });
});
