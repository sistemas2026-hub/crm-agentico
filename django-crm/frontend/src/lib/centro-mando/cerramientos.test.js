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

describe('el vidrio es para la cara publica, y solo para esa', () => {
  const CARAS = ['frente', 'derecha', 'izquierda'];
  const vanoDe = (p, cara) => (cara === 'izquierda' ? p.mundo.puertaLateral
    : cara === 'derecha' ? p.mundo.puertaDerecha : p.mundo.puertaFrente);

  it('cada sala tiene exactamente UNA cara con puerta', () => {
    //  Una cara lleva puerta cuando da a una circulacion. Dos puertas serian
    //  dos accesos al mismo recinto, y cero es una sala a la que no se entra.
    const mal = [];
    for (const p of SALAS) {
      const con = CARAS.filter((c) => p.mundo.antepecho?.[c] && vanoDe(p, c));
      if (con.length !== 1) mal.push(`${p.sala}: ${con.length} caras con puerta (${con.join('+') || '—'})`);
    }
    expect(mal, mal.join(' | ')).toEqual([]);
  });

  it('y ninguna sala queda con dos paredes de vidrio', () => {
    //  LA AFIRMACION QUE IMPORTA, y la que la revision pidio: «la pared de
    //  cristal que esta a la derecha ya debe ser de material». Acristalar una
    //  cara que no da a nadie le daba a cada sala del bloque derecho DOS
    //  paredes de vidrio, una de ellas mirando al borde del edificio.
    //
    //  Se afirma sobre el DATO que decide el dibujo: `construirCerramiento`
    //  levanta pano solo donde hay vano, asi que una cara con peto y sin
    //  puerta es peto opaco y nada mas.
    const mal = [];
    for (const p of SALAS) {
      const vidrio = CARAS.filter((c) => p.mundo.antepecho?.[c] && vanoDe(p, c));
      if (vidrio.length > 1) mal.push(`${p.sala}: vidrio en ${vidrio.join(' y ')}`);
    }
    expect(mal, mal.join(' | ')).toEqual([]);
  });
});

describe('el edificio cierra por sus cuatro lados', () => {
  const ENVOLVENTE = SEDE.plantas.filter((p) => p.arquitectura);
  const huella = SALAS.reduce((a, p) => ({
    ancho: Math.max(a.ancho, p.origen.gx + p.mundo.ancho),
    fondo: Math.max(a.fondo, p.origen.gy + p.mundo.fondo)
  }), { ancho: 0, fondo: 0 });

  it('hay una pieza en cada borde, y el de delante no se olvida', () => {
    //  Tres de los cuatro estaban desde el principio. El DELANTERO quedaba
    //  abierto a proposito -«el muro del frente estaria entre la camara y la
    //  oficina entera»- y era cierto para un muro: el peto a 1,15 cierra el
    //  volumen sin tapar a nadie, igual que el antepecho de sala a 1,2.
    const bordes = {
      fondo: ENVOLVENTE.some((p) => p.origen.gy < 0),
      izquierdo: ENVOLVENTE.some((p) => p.origen.gx < 0),
      derecho: ENVOLVENTE.some((p) => p.origen.gx >= huella.ancho),
      delantero: ENVOLVENTE.some((p) => p.origen.gy >= huella.fondo)
    };
    const faltan = Object.entries(bordes).filter(([, v]) => !v).map(([k]) => k);
    expect(faltan, 'bordes sin cerrar: ' + faltan.join(', ')).toEqual([]);
  });

  it('y lo que cierra el frente no tapa a nadie', () => {
    //  LA AFIRMACION QUE IMPORTA. La tabla de oclusion de P7: a 1,2 no se
    //  esconde a ninguna persona y a 2,2 ya se comen 2,4 celdas de
    //  escritorio. Una envolvente delantera mas alta que el antepecho de una
    //  sala estaria tapando mas que el propio muro de la sala.
    const ALTURA_DE_ANTEPECHO = 1.2;
    const delante = ENVOLVENTE.filter((p) => p.origen.gy >= huella.fondo);
    for (const p of delante) {
      const alto = p.arquitectura.altura ?? p.mundo.alto;
      expect(alto, `la pieza delantera mide ${alto}`).toBeLessThanOrEqual(ALTURA_DE_ANTEPECHO);
    }
  });

  it('y una pieza larga del borde se pinta POR DELANTE de lo que cruza', () => {
    //  `profundidad = gx + gy`, asi que el extremo derecho -origen (35, 0)-
    //  valia 35 mientras las salas que recorre llegan a 89: se dibujaba
    //  detras de ellas. Una pieza de 54 celdas no tiene una sola
    //  profundidad, y la que le sirve al pintor es la de su extremo cercano.
    const maxSala = Math.max(...SALAS.map((p) => p.origen.gx + p.origen.gy));
    const cruzan = ENVOLVENTE.filter(
      (p) => p.origen.gx >= huella.ancho || p.origen.gy >= huella.fondo);
    expect(cruzan.length).toBeGreaterThan(0);
    for (const p of cruzan) {
      expect(p.profundidad ?? (p.origen.gx + p.origen.gy),
        `${p.arquitectura.tipo} se pintaria detras de las salas`).toBeGreaterThanOrEqual(maxSala);
    }
  });
});

describe('dos salas de la sede no pueden ser la misma sala', () => {
  //  POR QUE HACIA FALTA, Y QUE NO VEIA LA OTRA.
  //
  //  `plantillas.test.js` ya exige que cada plantilla tenga tres tipos de
  //  mueble que cualquier otra no tenga. Pero compara PLANTILLAS, y dos
  //  salas que declaran la MISMA plantilla nunca se comparan entre si: el
  //  par no existe en esa matriz.
  //
  //  Asi vivieron Recepcion y Atencion al Cliente, las dos con `atencion`:
  //  identicas pieza por pieza, con dos mostradores, dos maquinas de turnos
  //  y dos salas de espera de cuatro bancos en la misma sede. La guarda de
  //  plantillas estaba en verde y tenia razon —habia una sola plantilla—.
  //
  //  Esta mira lo que de verdad se dibuja: las once salas compuestas.
  const tipos = (p) => new Set((p.mobiliario ?? []).map((m) => m.tipo));

  it('cada sala tiene tres muebles que cualquier otra no tiene', () => {
    const mal = [];
    for (const a of SALAS) {
      for (const b of SALAS) {
        if (a.sala === b.sala) continue;
        const solo = [...tipos(a)].filter((t) => !tipos(b).has(t));
        if (solo.length < 3) {
          mal.push(`${a.sala} sólo tiene ${solo.length} que ${b.sala} no: ${solo.join(',') || '—'}`);
        }
      }
    }
    expect(mal, mal.join(' | ')).toEqual([]);
  });

  it('y ninguna pareja comparte plantilla', () => {
    //  LA CAUSA, no el sintoma. Dos salas pueden diferenciarse hoy por como
    //  las amueble el compositor y volver a ser la misma mañana si comparten
    //  plantilla. Que cada sala tenga la suya es lo que lo impide de raiz.
    const porPlantilla = new Map();
    for (const p of SALAS) {
      const n = PLANTILLA_DE.get(p.sala) ?? 'generica';
      porPlantilla.set(n, [...(porPlantilla.get(n) ?? []), p.sala]);
    }
    const repetidas = [...porPlantilla.entries()]
      .filter(([, cuales]) => cuales.length > 1)
      .map(([n, cuales]) => `${n}: ${cuales.join(' y ')}`);
    expect(repetidas, repetidas.join(' | ')).toEqual([]);
  });
});
