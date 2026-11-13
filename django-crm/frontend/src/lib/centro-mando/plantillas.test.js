/**
 * EL CATÁLOGO DE SALAS Y SUS TAMAÑOS.
 *
 * Las salas grandes se GENERAN, así que lo que hay que vigilar no es que
 * existan: es que lo generado sea una sala y no un dibujo roto. Una silla
 * dentro de una pared, dos sillas en el mismo punto o una sala que crece hacia
 * el fondo no dan error — dan una oficina en la que alguien trabaja donde nadie
 * lo ve.
 */
import { describe, it, expect } from 'vitest';
import { PLANTILLAS, PLANTILLA_DE_RESERVA, plantillaDe } from './plantillas.js';
import DEL_MOTOR from './__fixtures__/plantillas-del-motor.json';

const TODAS = Object.entries(PLANTILLAS);

describe('toda sala del catálogo es dibujable', () => {
  it('ningún puesto cae fuera de su sala', () => {
    // La mutación que mata: ampliar la fila sin ensanchar el mundo. El
    // escritorio quedaría atravesando el muro y la escena lo dibujaría igual.
    for (const [nombre, p] of TODAS) {
      for (const s of p.puestos) {
        expect(s.gx, `${nombre}/${s.id} gx`).toBeGreaterThanOrEqual(0);
        expect(s.gx, `${nombre}/${s.id} gx`).toBeLessThanOrEqual(p.mundo.ancho);
        expect(s.gy, `${nombre}/${s.id} gy`).toBeGreaterThanOrEqual(0);
        expect(s.gy, `${nombre}/${s.id} gy`).toBeLessThanOrEqual(p.mundo.fondo);
      }
    }
  });

  it('ningún puesto se repite de identificador', () => {
    // Dos `p3` serían dos ocupaciones del mismo puesto, que el esquema del
    // motor rechaza: la sala no se podría guardar y nadie sabría por qué.
    for (const [nombre, p] of TODAS) {
      const ids = p.puestos.map((s) => s.id);
      expect(new Set(ids).size, `${nombre}`).toBe(ids.length);
    }
  });

  it('ningún puesto se superpone con otro', () => {
    // Dos escritorios en el mismo punto dibujan uno solo, y la oficina se ve
    // con menos gente de la que tiene.
    for (const [nombre, p] of TODAS) {
      const puntos = p.puestos.map((s) => `${s.gx}|${s.gy}`);
      expect(new Set(puntos).size, `${nombre}`).toBe(puntos.length);
    }
  });

  it('toda sala tiene un puesto principal, y uno solo', () => {
    for (const [nombre, p] of TODAS) {
      expect(p.puestos.filter((s) => s.principal).length, nombre).toBe(1);
    }
  });
});

describe('los tamaños', () => {
  const variantes = TODAS.filter(([n]) => /_\d+$/.test(n));

  it('hay variantes, y su nombre dice cuántos puestos tienen', () => {
    // Si el nombre y el contenido se separan, la empresa elige «10 puestos» y
    // recibe otra cosa sin un error.
    expect(variantes.length).toBeGreaterThan(0);
    for (const [nombre, p] of variantes) {
      expect(p.puestos.length, nombre).toBe(Number(nombre.split('_').pop()));
    }
  });

  it('CRECEN A LO ANCHO Y NUNCA HACIA EL FONDO', () => {
    // No es estética. La separación entre pisos salió de invertir la
    // proyección: un puesto queda tapado por el nivel de arriba cuando
    // `(ALTURA_DE_PISO - z) * 0.8125 <= fondo - gy`. Crecer en fondo esconde
    // los escritorios nuevos bajo el piso de arriba, y la escena los sigue
    // animando donde nadie los ve. `gx` no aparece en esa condición.
    for (const [nombre, p] of variantes) {
      const base = PLANTILLAS[nombre.replace(/_\d+$/, '')];
      expect(p.mundo.fondo, `${nombre} fondo`).toBe(base.mundo.fondo);
      expect(p.mundo.alto, `${nombre} alto`).toBe(base.mundo.alto);
      expect(p.mundo.ancho, `${nombre} ancho`).toBeGreaterThan(base.mundo.ancho);
    }
  });

  it('ningún puesto nuevo va más atrás que los que ya estaban', () => {
    // El otro lado de la misma desigualdad: menos `gy` tapa igual que más
    // fondo.
    for (const [nombre, p] of variantes) {
      const base = PLANTILLAS[nombre.replace(/_\d+$/, '')];
      const minimoBase = Math.min(...base.puestos.map((s) => s.gy));
      expect(Math.min(...p.puestos.map((s) => s.gy)), nombre).toBeGreaterThanOrEqual(minimoBase);
    }
  });

  it('CAMBIAR DE TAMAÑO NO DESENTA A NADIE', () => {
    // Los puestos de la sala chica siguen llamándose igual en la grande. Si
    // `principal` o `p1` cambiaran de nombre, agrandar un departamento dejaría
    // a sus agentes en puestos que ya no existen: el motor los reportaría como
    // «puesto desconocido» y la oficina se vaciaría sola.
    for (const [nombre, p] of variantes) {
      const base = PLANTILLAS[nombre.replace(/_\d+$/, '')];
      const ids = new Set(p.puestos.map((s) => s.id));
      for (const s of base.puestos) expect(ids.has(s.id), `${nombre} perdió ${s.id}`).toBe(true);
    }
  });

  it('la sala de reserva NO tiene tamaños', () => {
    // Es a la que se cae cuando la plantilla pedida no existe. Ofrecer tamaños
    // de una sala de reserva sería ofrecer elegir el error.
    expect(TODAS.filter(([n]) => n.startsWith(`${PLANTILLA_DE_RESERVA}_`))).toEqual([]);
  });

  it('el cartel queda dentro de la sala y no pegado al muro viejo', () => {
    for (const [nombre, p] of variantes) {
      expect(p.cartel.gx, nombre).toBeGreaterThan(p.mundo.ancho * 0.2);
      expect(p.cartel.gx, nombre).toBeLessThan(p.mundo.ancho * 0.8);
    }
  });
});

describe('el catálogo del motor y el del frontend no se separan', () => {
  it('toda plantilla que ofrece el motor existe acá, con sus mismos puestos', () => {
    // Son dos listas en dos lenguajes: el motor sirve NOMBRES y la geometría
    // vive acá. Separadas, el formulario ofrece una sala que la oficina dibuja
    // como «Sala sin plantilla» — degrada visible, pero es un defecto igual.
    // El fixture lo genera `cli/exportar_organizacion.py`.
    for (const pl of DEL_MOTOR) {
      expect(Object.keys(PLANTILLAS), `el motor ofrece ${pl.nombre}`).toContain(pl.nombre);
      expect(PLANTILLAS[pl.nombre].puestos.length, pl.nombre).toBe(pl.puestos);
    }
  });

  it('y toda plantilla de acá la ofrece el motor', () => {
    // La otra dirección: una sala que existe y nadie puede elegir es código
    // que no corre.
    const ofrecidas = new Set(DEL_MOTOR.map((p) => p.nombre));
    for (const nombre of Object.keys(PLANTILLAS)) {
      if (nombre === PLANTILLA_DE_RESERVA) continue; // no se elige: se cae en ella
      expect(ofrecidas, `${nombre} no se puede elegir`).toContain(nombre);
    }
  });
});

describe('plantillaDe', () => {
  it('una plantilla desconocida cae en la de reserva Y lo dice', () => {
    const r = plantillaDe('inventada');
    expect(r.plantilla).toBe(PLANTILLAS[PLANTILLA_DE_RESERVA]);
    expect(r.faltante).toBe('inventada');
  });

  it('una conocida no reporta faltante', () => {
    expect(plantillaDe('tecnica_6').faltante).toBe(null);
  });
});

describe('la mitad agregada se amuebla', () => {
  const variantes = Object.entries(PLANTILLAS).filter(([n]) => /_\d+$/.test(n));

  it('una sala más grande tiene MÁS muebles, no los mismos repartidos', () => {
    // Estirar la fila y correr lo de la derecha deja en medio una franja de
    // suelo pelado del ancho de los puestos nuevos: se lee como un depósito.
    for (const [nombre, p] of variantes) {
      const base = PLANTILLAS[nombre.replace(/_\d+$/, '')];
      expect(p.mobiliario.length, nombre).toBeGreaterThan(base.mobiliario.length);
    }
  });

  it('ningún mueble queda fuera de la sala', () => {
    for (const [nombre, p] of variantes) {
      for (const m of p.mobiliario) {
        if (typeof m.gx !== 'number') continue;
        expect(m.gx, `${nombre}/${m.tipo}`).toBeGreaterThanOrEqual(-0.5);
        expect(m.gx, `${nombre}/${m.tipo}`).toBeLessThanOrEqual(p.mundo.ancho);
      }
    }
  });

  it('lo ÚNICO no se duplica: un dispensador no se vuelve tres', () => {
    // Dos dispensadores en una sala no son más sala. Sólo se repite lo que ya
    // se repite a lo largo de una oficina: estanterías y plantas.
    const unicos = ['dispensador', 'mostrador', 'armario', 'panel_fibra', 'tablero'];
    for (const [nombre, p] of variantes) {
      const base = PLANTILLAS[nombre.replace(/_\d+$/, '')];
      for (const tipo of unicos) {
        const antes = base.mobiliario.filter((m) => m.tipo === tipo).length;
        const ahora = p.mobiliario.filter((m) => m.tipo === tipo).length;
        expect(ahora, `${nombre}/${tipo}`).toBe(antes);
      }
    }
  });

  it('ningún mueble repetido cae encima de otro', () => {
    for (const [nombre, p] of variantes) {
      const puntos = p.mobiliario
        .filter((m) => typeof m.gx === 'number' && typeof m.gy === 'number')
        .map((m) => `${m.tipo}|${m.gx}|${m.gy}`);
      expect(new Set(puntos).size, nombre).toBe(puntos.length);
    }
  });
});

describe('cada área se reconoce por lo que tiene dentro', () => {
  /** Los tipos de mueble de una plantilla, sin contar los que lleva cualquiera. */
  const COMUNES = new Set(['zona', 'luminaria', 'planta', 'dispensador', 'mampara', 'ducto']);
  const senas = (p) =>
    [...new Set(p.mobiliario.map((m) => m.tipo))].filter((t) => !COMUNES.has(t)).sort();

  //  TODAS las plantillas base del catálogo, no una selección. Si alguien
  //  agrega una y no la pone acá, las guardas de este bloque no la miran: es
  //  la trampa de «una prueba que recorre una lista incompleta pasa siempre».
  const BASES = Object.keys(PLANTILLAS)
    .filter((n) => n !== PLANTILLA_DE_RESERVA && !/_\d+$/.test(n));

  it('la lista de áreas que se vigila es la del catálogo entero', () => {
    //  La guarda de la guarda. Con once departamentos y seis plantillas, tres
    //  se veían iguales; al agregar cinco, una lista escrita a mano se habría
    //  quedado vieja sin que nada lo dijera.
    expect(BASES.length).toBe(
      Object.keys(PLANTILLAS).filter((n) => !/_\d+$/.test(n)).length - 1);
    expect(BASES.length).toBeGreaterThanOrEqual(11);
  });

  it('cada área se distingue de CUALQUIER otra, no sólo de alguna', () => {
    //  LA REGLA QUE PEDÍA LA REVISIÓN: «cada sala debe diferenciarse por su
    //  mobiliario, composición y uso del espacio, no solamente por colores y
    //  rótulos».
    //
    //  Y es más estricta que la de más abajo. Aquélla compara el conjunto
    //  entero de señas y falla sólo si dos salas son IDÉNTICAS; ésta exige que
    //  para CADA PAR, cada una tenga al menos tres tipos que la otra no tiene.
    //  Dos salas que compartan todo menos un mueble pasaban la primera y caen
    //  en ésta.
    const tipos = (n) => new Set(PLANTILLAS[n].mobiliario.map((m) => m.tipo));
    for (const a of BASES) {
      for (const b of BASES) {
        if (a === b) continue;
        const soloEnA = [...tipos(a)].filter((t) => !tipos(b).has(t));
        expect(soloEnA.length, `${a} sólo tiene ${soloEnA.length} cosas que ${b} no: ${soloEnA.join(', ')}`)
          .toBeGreaterThanOrEqual(3);
      }
    }
  });

  it('y tampoco comparten el plano: dos salas no miden lo mismo y se amueblan igual', () => {
    //  «No únicamente objetos diferentes sobre la misma distribución». Dos
    //  salas con el mismo tamaño Y el mismo reparto de puestos son la misma
    //  sala con otros adornos, por distinto que sea el mobiliario.
    const huella = (n) => {
      const p = PLANTILLAS[n];
      return `${p.mundo.ancho}x${p.mundo.fondo}|` +
        p.puestos.map((q) => `${q.gx},${q.gy}`).sort().join(';');
    };
    const vistas = new Map();
    for (const n of BASES) {
      const k = huella(n);
      expect(vistas.has(k), `${n} y ${vistas.get(k)} tienen el mismo plano y los puestos en el mismo sitio`)
        .toBe(false);
      vistas.set(k, n);
    }
  });

  it('ninguna sala lleva mural Y videowall: van en el mismo muro', () => {
    //  LOS DOS SE DIBUJAN EN EL MURO DE FONDO Y A LA MISMA ALTURA —el mural en
    //  z 1,45..3,35 y el videowall en 1,15..3,3—, así que juntos se pintan uno
    //  encima del otro. En la captura del NOC se veía una fila de pantallas
    //  con el borde de otra asomando por debajo.
    //
    //  Y LA GUARDA DE SOLAPES DE ABAJO NO PODÍA VERLO: recorre `mobiliario`, y
    //  el mural no vive ahí sino en su propio campo de la plantilla. Es el
    //  mismo error que cometí con los rótulos —medir el par que se me ocurre y
    //  no el que está roto— repetido en otro sitio.
    for (const n of [...BASES, 'generica']) {
      const p = PLANTILLAS[n];
      const tieneVideowall = p.mobiliario.some((m) => m.tipo === 'videowall');
      const tieneMural = Boolean(p.mural?.paneles?.length);
      expect(tieneVideowall && tieneMural, `${n} lleva mural y videowall`).toBe(false);
    }
  });

  it('el videowall está en la sala cuyos puestos son de monitoreo', () => {
    //  LA GUARDA QUE HABRÍA CAZADO MI ERROR, y los datos ya lo decían.
    //
    //  Puse el videowall y los racks en `tecnica` creyendo que era el NOC, y
    //  el material de campo en `operaciones`. La empresa del piloto declara lo
    //  contrario —su «NOC y Redes» pide `operaciones`— y lo descubrí mirando
    //  el navegador: la sala rotulada NOC tenía cajas apiladas.
    //
    //  Lo que no miré fueron los PUESTOS de cada plantilla. En `operaciones`
    //  se llaman «Monitoreo 1, 2, 3» y «Supervisión». Una sala cuyos asientos
    //  son de monitoreo es la que mira pantallas, y eso está escrito en este
    //  mismo archivo desde antes de que yo tocara nada.
    const mira = (n) => PLANTILLAS[n].puestos
      .some((p) => /monitore|supervis/i.test(p.nombre ?? ''));
    const conVideowall = BASES.filter((n) =>
      PLANTILLAS[n].mobiliario.some((m) => m.tipo === 'videowall'));
    expect(conVideowall.length, 'nadie tiene videowall').toBeGreaterThan(0);
    for (const n of conVideowall) {
      expect(mira(n), `${n} tiene videowall y ningún puesto de monitoreo`).toBe(true);
    }
  });

  it('ninguna sala mira pantallas Y alista material a la vez', () => {
    //  Son dos funciones distintas y una sala que tuviera las dos no se
    //  reconocería por ninguna. Es la otra mitad del mismo error.
    for (const n of BASES) {
      const tipos = new Set(PLANTILLAS[n].mobiliario.map((m) => m.tipo));
      const vigila = tipos.has('videowall') || tipos.has('rack');
      const alista = tipos.has('cajas') || tipos.has('bobina');
      expect(vigila && alista, `${n} vigila y alista al mismo tiempo`).toBe(false);
    }
  });

  //  ACÁ VIVÍA «cada área tiene al menos tres piezas que no tiene NINGUNA
  //  otra». La reemplaza la de pares de más arriba, y no es un ablandamiento:
  //
  //  Aquélla la escribí con SIETE plantillas, y era un sustituto de lo que de
  //  verdad importa. Con once, exige que haya ~33 tipos de mueble usados una o
  //  dos veces en todo el catálogo, y eso no mide si una sala se reconoce
  //  frente a otra: obliga a inventar muebles para cumplir un conteo global.
  //  Un dispensador en dos salas no hace que se confundan.
  //
  //  La regla por pares dice exactamente lo que se quiere —que mirando
  //  cualquier sala al lado de cualquier otra haya tres cosas que las separan—
  //  y es MÁS estricta en el caso que importa: cazó que `reuniones` y
  //  `comercial` se diferenciaban en una sola pieza, cosa que la vieja dejaba
  //  pasar.

  it('ningún adorno se repite mecánicamente en toda la sede', () => {
    //  «No duplicar plantas, archivadores y otros adornos de manera
    //  automática», dice la especificación. La maceta llegó a estar en las 19
    //  plantillas y a dibujarse **39 veces** en la sede del piloto: era la
    //  pieza más numerosa de toda la escena, por encima de cualquier equipo.
    //
    //  El tope es por PLANTILLA y no por sede: cuántas salas usen una
    //  plantilla lo decide la empresa, no este archivo.
    for (const n of [...BASES, 'generica']) {
      const macetas = PLANTILLAS[n].mobiliario.filter((m) => m.tipo === 'planta').length;
      expect(macetas, `${n} tiene ${macetas} macetas`).toBeLessThanOrEqual(1);
    }
  });

  it('la mesa de reunión está donde reunirse es la función', () => {
    //  Mesa redonda + alfombra estaba en 16 de 19 plantillas, o sea en **9 de
    //  las 11 salas** del piloto: el otro mueble que hacía que todas se
    //  parecieran. Auditoría recibió una mesa de REVISIÓN —dos sillas
    //  enfrentadas y un expediente abierto— que es otra cosa y se ve distinta.
    const conMesa = BASES.filter((n) =>
      PLANTILLAS[n].mobiliario.some((m) => m.tipo === 'mesa'));
    expect(conMesa, `mesa redonda en ${conMesa.join(', ')}`)
      .toContain('reuniones');
    expect(conMesa.length, `mesa redonda en ${conMesa.length} de ${BASES.length} áreas`)
      .toBeLessThanOrEqual(Math.ceil(BASES.length / 2));
  });

  it('el mueble de documentos no está en casi todas las áreas', () => {
    //  LA PREGUNTA QUE ESTA GUARDA NO SABÍA HACER. La de más abajo comprueba
    //  que no haya DOS áreas amuebladas igual, y pasaba en verde mientras la
    //  estantería de carpetas estaba en **6 de 7 plantillas**: cada área era
    //  distinta de las demás por otras piezas, y aun así todas se veían como
    //  un archivo. «¿Por qué todas las oficinas tienen mueble de documento?».
    //
    //  Afirma sobre la pieza más reconocible del catálogo —cuatro baldas de
    //  carpetas de colores— y no sobre el mobiliario en bloque.
    const todas = [...BASES, 'generica'];
    const conEstante = todas.filter((n) =>
      PLANTILLAS[n].mobiliario.some((m) => m.tipo === 'estanteria'));
    expect(conEstante.length, `estantería en ${conEstante.join(', ')}`)
      .toBeLessThanOrEqual(Math.floor(todas.length / 3));
  });

  it('y donde está, está porque el trabajo son los expedientes', () => {
    const cuantas = (n) =>
      PLANTILLAS[n].mobiliario.filter((m) => m.tipo === 'estanteria').length;
    for (const otra of BASES.filter((n) => n !== 'expedientes')) {
      expect(cuantas('expedientes'), `${otra} tiene tantas como expedientes`)
        .toBeGreaterThan(cuantas(otra));
    }
  });

  it('ninguna sala se queda sin mobiliario propio de su oficio', () => {
    //  Todas tenían estantería y planta, así que una de ventas se veía igual
    //  que una de auditoría. El veredicto del 01/11/2026 fue «solo veo cuartos
    //  separados», y esto es la mitad del motivo: no era que faltaran muebles,
    //  era que eran los MISMOS muebles.
    for (const nombre of BASES) {
      expect(senas(PLANTILLAS[nombre]), `${nombre} sin nada propio`).not.toEqual([]);
    }
  });

  it('y dos áreas distintas no se amueblan igual', () => {
    //  La prueba que importa: si dos plantillas tienen las mismas señas, en la
    //  sede se ven como la misma sala con otro nombre.
    const vistas = new Map();
    for (const nombre of BASES) {
      const clave = senas(PLANTILLAS[nombre]).join('+');
      expect(vistas.has(clave),
        `${nombre} se amuebla igual que ${vistas.get(clave)}: ${clave}`).toBe(false);
      vistas.set(clave, nombre);
    }
  });

  it('la sala de redes es la que más equipo técnico tiene', () => {
    //  Tenía UNA estantería y nada más —menos equipo que la sala de
    //  expedientes— y el panel de fibra se lo llevaba Operaciones de Campo.
    const tecnico = (p) =>
      p.mobiliario.filter((m) => ['panel_fibra', 'tablero', 'ducto'].includes(m.tipo)).length;
    expect(tecnico(PLANTILLAS.tecnica)).toBeGreaterThan(1);
  });

  it('el área comercial tiene tableros: es lo que se mira en ventas', () => {
    expect(PLANTILLAS.comercial.mobiliario.filter((m) => m.tipo === 'tablero').length)
      .toBeGreaterThan(1);
  });

  it('ningún mueble de pared se apila con otro en el mismo tramo', () => {
    //  Los muebles de pared se colocan por `gy` y ocupan `largo`. Tres en el
    //  mismo punto dibujan uno, y la sala muestra menos de lo que tiene: pasó
    //  en `generica` al amueblarla, con un tablero, dos estanterías y un
    //  armario casi en el mismo sitio.
    //  Cuánto ocupa cada uno a lo largo del muro, LEÍDO DEL DIBUJO y no
    //  supuesto: el tablero arranca medio paso antes de su `gy` y mide 2,74;
    //  el panel de fibra, 2,1; el armario, 1,5; la estantería, su `largo`.
    //  Con un número inventado esta prueba acusaría solapes que no existen y
    //  dejaría pasar los que sí.
    const DE_PARED = {
      tablero: { antes: 0.12, largo: 2.74 },
      panel_fibra: { antes: 0, largo: 2.1 },
      armario: { antes: 0, largo: 1.5 },
      estanteria: { antes: 0, largo: null }
    };
    for (const [nombre, p] of Object.entries(PLANTILLAS)) {
      const enLaPared = p.mobiliario
        .filter((m) => DE_PARED[m.tipo])
        .map((m) => {
          const d = DE_PARED[m.tipo];
          const desde = (m.gy ?? 0) - d.antes;
          return { tipo: m.tipo, desde, hasta: desde + (d.largo ?? m.largo ?? 2) };
        })
        .sort((a, b) => a.desde - b.desde);
      for (let i = 1; i < enLaPared.length; i++) {
        expect(enLaPared[i].desde,
          `${nombre}: ${enLaPared[i].tipo} se monta sobre ${enLaPared[i - 1].tipo}`
        ).toBeGreaterThanOrEqual(enLaPared[i - 1].hasta - 0.01);
      }
    }
  });
});

describe('dos muebles de suelo no ocupan el mismo sitio', () => {
  /**
   * Lo que ocupa cada mueble de suelo alrededor de su punto, medido del
   * dibujo. No es exacto —un banco no es un círculo— y es a propósito: una
   * cota generosa caza el solape antes de que se vea, y afinarla pediría
   * replicar la geometría de `oficina.ts` acá, que sería probar la copia.
   */
  //  La luminaria NO entra: va en el techo. Una lámpara sobre un escritorio no
  //  es un choque, es lo que se quiere —y contarla acusaba cuarenta y ocho
  //  solapes que no existen, que es la forma más rápida de que una guarda se
  //  aprenda a ignorar—.
  const RADIO = {
    mostrador: 1.6, mesa: 1.2, banco: 0.7, dispensador: 0.6, planta: 0.5
  };

  it('ninguno cae encima de otro, en ninguna plantilla', () => {
    const choques = [];
    for (const [nombre, p] of Object.entries(PLANTILLAS)) {
      const suelo = p.mobiliario.filter(
        (m) => RADIO[m.tipo] !== undefined && typeof m.gx === 'number');
      for (let i = 0; i < suelo.length; i++) {
        for (let j = i + 1; j < suelo.length; j++) {
          const a = suelo[i];
          const b = suelo[j];
          const minimo = RADIO[a.tipo] + RADIO[b.tipo];
          if (minimo === 0) continue;
          const d = Math.hypot((a.gx ?? 0) - (b.gx ?? 0), (a.gy ?? 0) - (b.gy ?? 0));
          if (d < minimo) {
            choques.push(`${nombre}: ${a.tipo}@${a.gx},${a.gy} y ${b.tipo}@${b.gx},${b.gy} a ${d.toFixed(1)}`);
          }
        }
      }
    }
    expect(choques).toEqual([]);
  });

  it('y ninguno se sienta encima de un puesto', () => {
    //  Un mueble sobre un escritorio tapa a quien trabaja ahí, que es el único
    //  elemento de la sala que no es decoración.
    const choques = [];
    for (const [nombre, p] of Object.entries(PLANTILLAS)) {
      for (const m of p.mobiliario) {
        if (RADIO[m.tipo] === undefined || typeof m.gx !== 'number') continue;
        for (const q of p.puestos) {
          const d = Math.hypot(m.gx - q.gx, (m.gy ?? 0) - q.gy);
          if (d < RADIO[m.tipo] + 1.1) {
            choques.push(`${nombre}: ${m.tipo}@${m.gx},${m.gy} sobre ${q.id} a ${d.toFixed(1)}`);
          }
        }
      }
    }
    expect(choques).toEqual([]);
  });
});
