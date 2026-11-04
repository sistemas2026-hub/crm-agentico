import { describe, it, expect } from 'vitest';
import { sedeDe } from './sede.js';
import { salasDe } from './departamentos.js';
import PORDEFECTO from './__fixtures__/organizacion-por-defecto.json';
import { PLANTILLAS } from './plantillas.js';
import { celdaDe, conectividad, rejillaDe, transitable } from './navegacion.js';

/**
 * LA MATRIZ DE LAS ONCE SALAS: dato, dibujo y ruta tienen que decir lo mismo.
 *
 * Nace de una pregunta que una captura no puede contestar: cuando una oficina
 * «parece» no tener puerta, ¿falta la puerta en los datos, o existe y el
 * renderizador no la dibuja? Son dos defectos distintos y se arreglan en
 * sitios distintos.
 *
 * Por eso cada sala se mide en TRES sitios:
 *
 *     DATO     lo que la planta declara (`mundo.puertaX`)
 *     DIBUJO   si `oficina.ts` llega a pintar ese vano, con sus condiciones
 *     RUTA     si la rejilla deja pasar por ahí
 *
 * Tres columnas que coinciden es un sistema coherente. Dos de tres es un
 * defecto, y cuál falla dice dónde está.
 *
 * Y SE MIDE SOBRE LA EMPRESA DEL PILOTO, no sobre una sintética. Las guardas
 * de `navegacion.test.js` y `sede.test.js` arman su propia empresa con las
 * plantillas en orden, y eso les sirve para barrer tamaños — pero el defecto
 * que encontró esta matriz **sólo aparece en el reparto real**: el macetero de
 * una esquina de la franja de entrada caía delante del vano de Recepción, y en
 * la empresa sintética esa esquina queda en otro sitio.
 */

const SEDE = sedeDe(salasDe(PORDEFECTO), []);
const REJILLA = rejillaDe(SEDE);
const SALAS = SEDE.plantas.filter((p) => p.papel === 'sala');
//  Que plantilla pidio cada sala. La planta compuesta no lo lleva: lo declara
//  la empresa, y es lo unico que dice contra que comparar su mobiliario.
const PLANTILLA_DE = new Map(salasDe(PORDEFECTO).map((s) => [s.id, s.plantilla]));
const CIRCULACION = SEDE.plantas
  .filter((p) => p.papel === 'circulacion')
  .map((p) => ({ x: p.origen.gx, y: p.origen.gy, ancho: p.mundo.ancho, fondo: p.mundo.fondo }));

const LADOS = ['fondo', 'izquierda', 'frente', 'derecha'];

/** El vano declarado en un lado, si lo hay. */
const vanoDeclarado = (m, lado) => (
  lado === 'fondo' ? m.puerta
    : lado === 'izquierda' ? m.puertaLateral
      : lado === 'frente' ? m.puertaFrente
        : m.puertaDerecha) ?? null;

/**
 * ¿Llega la escena a pintar ese vano?
 *
 * Se replican acá las condiciones de `construirMuros` y `construirCerramiento`:
 * los muros altos de fondo e izquierda pintan su vano siempre que exista; los
 * dos del peto SÓLO si ese lado lleva peto. Esa condición de más es justamente
 * la que puede dejar un vano declarado sin dibujar.
 */
const seDibuja = (m, lado) => {
  const v = vanoDeclarado(m, lado);
  if (!v) return false;
  if (lado === 'frente') return Boolean(m.antepecho?.frente);
  if (lado === 'derecha') return Boolean(m.antepecho?.derecha);
  return true;
};

/** ¿Está libre la celda de justo afuera de ese vano? */
const sePasa = (p, lado) => {
  const v = vanoDeclarado(p.mundo, lado);
  if (!v) return false;
  const o = p.origen;
  const m = p.mundo;
  const medio = (v[0] + v[1]) / 2;
  const punto = lado === 'izquierda' ? [o.gx - 0.3, o.gy + medio]
    : lado === 'derecha' ? [o.gx + m.ancho + 0.3, o.gy + medio]
      : lado === 'frente' ? [o.gx + medio, o.gy + m.fondo + 0.3]
        : [o.gx + medio, o.gy - 0.3];
  const c = celdaDe(punto[0], punto[1]);
  return transitable(REJILLA, c.cx, c.cy);
};

/** ¿Hay otra sala pegada a este lado? */
const vecina = (p, lado) => SALAS.some((q) => {
  if (q === p) return false;
  const o = p.origen; const m = p.mundo;
  const oq = q.origen; const mq = q.mundo;
  if (lado === 'derecha') {
    return Math.abs(oq.gx - (o.gx + m.ancho)) < 0.01
      && oq.gy < o.gy + m.fondo && o.gy < oq.gy + mq.fondo;
  }
  return Math.abs(oq.gy - (o.gy + m.fondo)) < 0.01
    && oq.gx < o.gx + m.ancho && o.gx < oq.gx + mq.ancho;
});

describe('la matriz de las once salas', () => {
  it('hay once salas que auditar (si no, la matriz no prueba nada)', () => {
    //  Una matriz que recorre una lista vacía pasa siempre.
    expect(SALAS.length).toBe(11);
    expect(REJILLA.destinos.size).toBeGreaterThanOrEqual(30);
  });

  it('ninguna sala tiene un lado abierto al vacío', () => {
    for (const p of SALAS) {
      const m = p.mundo;
      //  Fondo e izquierda llevan muro alto siempre; los otros dos, peto —
      //  salvo que haya otra sala pegada, que ya los cierra con el suyo.
      expect(Boolean(m.antepecho?.frente) || vecina(p, 'frente'),
        `${p.sala}: abierta por el frente`).toBe(true);
      expect(Boolean(m.antepecho?.derecha) || vecina(p, 'derecha'),
        `${p.sala}: abierta por la derecha`).toBe(true);
    }
  });

  it('todo vano declarado se dibuja', () => {
    //  EL PRIMERO DE LOS TRES DESACUERDOS POSIBLES: la planta dice que hay
    //  puerta y la escena no la pinta porque falta la condición del peto.
    for (const p of SALAS) {
      for (const lado of LADOS) {
        if (!vanoDeclarado(p.mundo, lado)) continue;
        expect(seDibuja(p.mundo, lado),
          `${p.sala}: vano declarado en «${lado}» que NO se dibuja`).toBe(true);
      }
    }
  });

  it('por todo vano dibujado se pasa', () => {
    //  EL SEGUNDO, y es el que encontró la puerta de Recepción tapada por un
    //  macetero de la franja de entrada. La puerta estaba dibujada y la celda
    //  de justo afuera, ocupada.
    for (const p of SALAS) {
      for (const lado of LADOS) {
        if (!seDibuja(p.mundo, lado)) continue;
        expect(sePasa(p, lado),
          `${p.sala}: vano dibujado en «${lado}» por el que NO se pasa`).toBe(true);
      }
    }
  });

  it('y no se pasa por donde no hay vano dibujado', () => {
    //  EL TERCERO: un agujero en la rejilla sin puerta a la vista. Ahí un
    //  personaje atraviesa lo que parece una pared.
    for (const p of SALAS) {
      for (const lado of LADOS) {
        if (!vanoDeclarado(p.mundo, lado)) continue;
        if (seDibuja(p.mundo, lado)) continue;
        expect(sePasa(p, lado),
          `${p.sala}: se pasa por «${lado}» sin vano dibujado`).toBe(false);
      }
    }
  });

  it('cada sala tiene al menos una puerta', () => {
    for (const p of SALAS) {
      const cuantas = LADOS.filter((l) => seDibuja(p.mundo, l)).length;
      expect(cuantas, `${p.sala} no tiene ninguna puerta dibujada`).toBeGreaterThan(0);
    }
  });

  it('y todos sus puestos se alcanzan desde la circulación', () => {
    const { aislados } = conectividad(REJILLA, CIRCULACION);
    expect(aislados, `sin ruta: ${aislados.join(', ')}`).toEqual([]);
  });
});

describe('los tres niveles de cerramiento', () => {
  //  «Restringido, estándar y semipúblico», y la decisión de dónde vive ese
  //  dato importa: sale de la PLANTILLA, no del departamento. Que una sala de
  //  expedientes sea privada es una propiedad del tipo de sala, igual que
  //  tener estanterías — así cualquier empresa que elija esa plantilla recibe
  //  el cerramiento que le corresponde sin configurar nada, que es lo que
  //  CLAUDE.md §3.3 pide de todo lo que varía por empresa.

  const NIVELES = ['restringido', 'estandar', 'semipublico'];

  it('cada sala declara uno de los tres, y ninguno queda sin usar', () => {
    const vistos = new Set();
    for (const p of SALAS) {
      expect(NIVELES, `${p.sala} declara «${p.mundo.privacidad}»`)
        .toContain(p.mundo.privacidad);
      vistos.add(p.mundo.privacidad);
    }
    //  Si los tres no aparecen, dos de las variantes son código que no corre.
    expect([...vistos].sort()).toEqual([...NIVELES].sort());
  });

  it('las salas que reciben gente de la calle NO son restringidas', () => {
    //  Y al revés: una sala de atención con lector de acceso le estaría
    //  diciendo al cliente que no puede entrar donde lo van a atender.
    for (const p of SALAS) {
      const tieneMostrador = (p.mobiliario ?? []).some((m) => m.tipo === 'mostrador');
      const tieneBancosDeEspera = (p.mobiliario ?? []).filter((m) => m.tipo === 'banco').length >= 3;
      if (tieneMostrador && tieneBancosDeEspera) {
        expect(p.mundo.privacidad, `${p.sala} atiende público y está restringida`)
          .not.toBe('restringido');
      }
    }
  });

  it('la sala con racks es restringida', () => {
    //  El cuarto de equipos no es un sitio por el que se pasa.
    for (const p of SALAS) {
      if (!(p.mobiliario ?? []).some((m) => m.tipo === 'rack')) continue;
      expect(p.mundo.privacidad, `${p.sala} tiene racks y no está restringida`)
        .toBe('restringido');
    }
  });

  it('el reparto no deja a una sola sala en su nivel', () => {
    //  Un nivel con una sola sala no es un nivel: es una excepción, y una
    //  excepción con nombre de categoría se termina usando para otra cosa.
    const cuenta = {};
    for (const p of SALAS) cuenta[p.mundo.privacidad] = (cuenta[p.mundo.privacidad] ?? 0) + 1;
    for (const [nivel, n] of Object.entries(cuenta)) {
      expect(n, `«${nivel}» lo usa una sola sala`).toBeGreaterThan(1);
    }
  });
});

describe('ningun mueble se pone delante de la puerta', () => {
  //  Cuanto ocupa a lo largo de SU muro cada mueble de pared, leido del
  //  dibujo. Esta repetido a proposito: si `sede.js` cambia estos numeros y
  //  aqui no, la guarda deja de medir lo que el dibujo hace — y eso se ve,
  //  porque entonces afirma de mas o de menos.
  const LARGO = {
    tablero: [-0.12, 2.74],
    panel_fibra: [0, 2.1],
    armario: [0, 1.5],
    estanteria: [0, null],
    pizarra: [-0.1, null],
    videoconferencia: [-0.1, null],
    biblioteca: [0, null]
  };

  const tapadoDe = (p) => {
    const v = p.mundo.puertaLateral;
    if (!v) return [];
    const choques = [];
    for (const mu of p.mobiliario ?? []) {
      const def = LARGO[mu.tipo];
      if (!def) continue;
      //  LO QUE SE MUDO AL FONDO YA NO ESTA EN ESTE MURO. Sin esta linea,
      //  `mu.gy ?? 0` lo colocaba en el 0 del muro lateral —un sitio donde no
      //  esta— y la guarda seguia verde midiendo algo que no ocurre.
      if (mu.muro === 'fondo') continue;
      const desde = (mu.gy ?? 0) + def[0];
      const largo = def[1] ?? ((mu.largo ?? 2) + (def[0] < 0 ? 0.2 : 0));
      const solape = Math.min(desde + largo, v[1]) - Math.max(desde, v[0]);
      if (solape > 0.05) choques.push({ tipo: mu.tipo, solape });
    }
    return choques;
  };

  it('ninguna puerta queda tapada por la mitad o mas', () => {
    //  LA AFIRMACION QUE IMPORTA, y la que la revision pidio con estas
    //  palabras: «las entradas del lado derecho no se distinguen». Eran
    //  SEIS de once, todas las que abren por el muro lateral, que es el
    //  unico que lleva mobiliario colgado. El dato estaba bien —la puerta
    //  existia, se dibujaba y se pasaba por ella— y encima tenia un tablero.
    //
    //  Medio vano es el limite: por debajo la hoja y el marco se siguen
    //  leyendo; por encima, lo que se ve es el mueble.
    const MEDIO = 0.9;
    const mal = [];
    for (const p of SALAS) {
      for (const c of tapadoDe(p)) {
        if (c.solape >= MEDIO) {
          mal.push(`${p.sala}: ${c.tipo} tapa ${c.solape.toFixed(2)} de 1,8`);
        }
      }
    }
    expect(mal, mal.join(' | ')).toEqual([]);
  });

  it('y el compositor aparta lo que puede, no lo borra', () => {
    //  `apartarDelVano` corre el mueble por el muro. Lo que NO puede hacer es
    //  hacerlo desaparecer: una sala que pierde su armario al cambiar de
    //  columna es una sala cuyo contenido depende de donde cayo. Ya paso una
    //  vez —el despeje de puertas del patio borro el mostrador de recepcion—
    //  y por eso esto se mide.
    for (const p of SALAS) {
      const dePlantilla = PLANTILLAS[PLANTILLA_DE.get(p.sala) ?? 'generica'];
      if (!dePlantilla) continue;
      const cuenta = (lista) => {
        const c = {};
        for (const mu of lista ?? []) c[mu.tipo] = (c[mu.tipo] ?? 0) + 1;
        return c;
      };
      expect(cuenta(p.mobiliario), `${p.sala} perdio o gano muebles al colocarse`)
        .toEqual(cuenta(dePlantilla.mobiliario));
    }
  });
});

describe('lo que cuelga de la pared no se queda sobre el cristal', () => {
  //  Cuando el muro lateral pasa a ser el cerramiento acristalado que da al
  //  pasillo, un tablero atornillado ahi no tiene de donde colgar. El
  //  compositor lo muda al muro del fondo. Los que se APOYAN -armario,
  //  biblioteca, estanteria- no se tocan y por eso no estan en esta lista.
  const COLGADOS = new Set(['tablero', 'pizarra', 'videoconferencia', 'panel_fibra']);
  const LARGO_DE = {
    tablero: 2.74, panel_fibra: 2.1,
    pizarra: (mu) => (mu.largo ?? 2) + 0.2,
    videoconferencia: (mu) => (mu.largo ?? 2) + 0.2
  };
  const largoDe = (mu) => {
    const d = LARGO_DE[mu.tipo];
    return typeof d === 'function' ? d(mu) : d;
  };

  const deVidrio = SALAS.filter((p) => p.mundo.antepecho?.izquierda);

  it('hay salas con la cara del pasillo acristalada: si no, esto no mira nada', () => {
    expect(deVidrio.length).toBeGreaterThan(0);
  });

  it('y lo que sigue colgado del cristal es SOLO lo que no cabia en el fondo', () => {
    //  LA AFIRMACION QUE IMPORTA. No se exige que se mude todo -Atencion al
    //  Cliente y Recepcion tienen 6,4 de mural sobre 13 y no hay sitio- sino
    //  que lo que se queda sea exactamente lo que NO CABE. Un compositor que
    //  deje de mudar por vagancia cae aqui.
    const SEPARACION = 0.25;
    const mal = [];
    for (const p of deVidrio) {
      const ocupados = (p.mural?.paneles ?? []).map((q) => [q.gx, q.gx + q.ancho]);
      for (const mu of p.mobiliario ?? []) {
        if (mu.muro === 'fondo') {
          ocupados.push([mu.gx, mu.gx + largoDe(mu)]);
        }
      }
      const pisa = (a, b, c, d) => Math.min(b, d) - Math.max(a, c) > 0.001;
      for (const mu of p.mobiliario ?? []) {
        if (!COLGADOS.has(mu.tipo) || mu.muro === 'fondo') continue;
        const largo = largoDe(mu);
        let cabia = false;
        for (let d = 0.3; d + largo <= p.mundo.ancho - 0.3 + 1e-9; d += 0.05) {
          if (ocupados.some(([a, b]) => pisa(d, d + largo, a - SEPARACION, b + SEPARACION))) continue;
          cabia = true;
          break;
        }
        if (cabia) mal.push(`${p.sala}: ${mu.tipo} sigue en el cristal y SI cabia en el fondo`);
      }
    }
    expect(mal, mal.join(' | ')).toEqual([]);
  });

  it('y lo mudado no se monta encima del mural', () => {
    //  El mural son pantallas: es lo unico del muro del fondo con lo que de
    //  verdad no puede compartir sitio. Sobre el cartel pintado si puede.
    const mal = [];
    for (const p of deVidrio) {
      for (const mu of (p.mobiliario ?? []).filter((m) => m.muro === 'fondo')) {
        const a = mu.gx; const b = mu.gx + largoDe(mu);
        for (const q of p.mural?.paneles ?? []) {
          const sol = Math.min(b, q.gx + q.ancho) - Math.max(a, q.gx);
          if (sol > 0.05) mal.push(`${p.sala}: ${mu.tipo} pisa ${sol.toFixed(2)} del mural`);
        }
      }
    }
    expect(mal, mal.join(' | ')).toEqual([]);
  });
});
