import { describe, it, expect } from 'vitest';
import {
  agentesDe,
  ocupacionesSinSilla,
  pisosDe,
  plantaDe,
  salaPorId,
  salasDe
} from './departamentos.js';
import { PLANTILLAS, plantillaDe } from './plantillas.js';
import { TIPOS_DE_MUEBLE } from './escena/oficina';
import PORDEFECTO from './__fixtures__/organizacion-por-defecto.json';

/**
 * LA ORGANIZACIÓN ES UN DATO, Y ESTO LO MIDE.
 *
 * Hasta el 31/10/2026 había seis departamentos escritos en el frontend. La
 * prueba que de verdad importa no es que ahora haya ocho: es que **este archivo
 * no sabe cuántos hay**. Si un día alguien resuelve el departamento de una
 * empresa agregando una fila a `departamentos.js`, lo que se pierde no es
 * elegancia — es que la siguiente empresa vuelva a costar una sesión de código.
 *
 * EL FIXTURE NO ESTÁ COPIADO A MANO, y es deliberado. Lo generó el motor desde
 * `nucleo/config/organizacion.py`, y `tests/test_organizacion_config.py`
 * comprueba que siga siendo idéntico a lo que el motor sirve. Copiar el
 * documento a mano es exactamente el error que dejó a E1 sin probar durante
 * semanas: la prueba de E1 copiaba la consulta en vez de importar el módulo, y
 * así la función podía no funcionar con la prueba en verde.
 *
 * Y las comprobaciones de geometría existen porque sus fallos NO dan error: dos
 * escritorios en la misma celda se dibujan uno dentro del otro y el síntoma se
 * describe como «el mobiliario parpadea».
 */

//  Los nueve roles reales del tenant, con el area que DECLARAN.
const inventario = [
  { nombre: 'supervisor_noc', area: 'Operaciones', cargo: 'Supervisor NOC' },
  { nombre: 'soporte', area: 'Atención al Cliente', cargo: 'Soporte' },
  { nombre: 'cliente_final', area: 'Atención al Cliente', cargo: 'Primera línea' },
  { nombre: 'soporte_tecnico_cliente', area: 'Soporte Técnico', cargo: 'Diagnóstico' },
  { nombre: 'facturacion', area: 'Facturación', cargo: 'Facturación' },
  { nombre: 'facturacion_cliente', area: 'Facturación', cargo: 'Cobranza' },
  { nombre: 'ventas', area: 'Ventas', cargo: 'Comercial' },
  { nombre: 'administracion', area: 'Administración', cargo: 'Administración' },
  { nombre: 'configuracion_guiada', area: 'Administración', cargo: 'Gestión' }
];

const SALAS = salasDe(PORDEFECTO);
const DEPTOS = SALAS.filter((s) => s.tipo === 'departamento');

describe('la estructura sale de la configuración, no de este archivo', () => {
  it('los ocho departamentos de la empresa piloto están', () => {
    expect(DEPTOS.length).toBe(8);
    expect(DEPTOS.map((d) => d.rotulo)).toEqual([
      'NOC y Redes', 'Operaciones de Campo', 'Atención al Cliente',
      'Comercial y Marketing', 'Finanzas y Cartera', 'Administración',
      'Recursos Humanos', 'Auditoría y Cumplimiento'
    ]);
  });

  it('y los tres espacios complementarios NO son departamentos', () => {
    // Una recepción es parte del edificio y no una parte de la organización a
    // la que se le puedan asignar responsabilidades. Contarla como
    // departamento diría que la empresa tiene once.
    const espacios = SALAS.filter((s) => s.tipo === 'espacio');
    expect(espacios.map((e) => e.id)).toEqual(['direccion', 'sala_reuniones', 'recepcion']);
    for (const e of espacios) {
      expect(e.areas, e.id).toEqual([]);
      expect(e.capacidades, e.id).toEqual([]);
    }
  });

  it('una empresa CHICA: cuatro departamentos en una sola planta', () => {
    // El caso que prueba que esto es un producto y no una pantalla para una
    // empresa. Si algo quedara fijo en ocho o en tres pisos, acá se rompe.
    const chica = {
      pisos: [{ nivel: 1, rotulo: 'Planta' }],
      departamentos: ['soporte', 'ventas', 'cartera', 'tecnica_zonal'].map((id) => ({
        id, rotulo: id, piso: 1, plantilla: 'tecnica', areas: [id]
      })),
      espacios: []
    };
    const s = salasDe(chica);
    expect(s.length).toBe(4);
    expect(pisosDe(chica, s).length).toBe(1);
  });

  it('una empresa GRANDE: quince departamentos en cinco niveles', () => {
    const grande = {
      pisos: [1, 2, 3, 4, 5].map((nivel) => ({ nivel, rotulo: `Nivel ${nivel}` })),
      departamentos: Array.from({ length: 15 }, (_, i) => ({
        id: `d${i}`, rotulo: `Departamento ${i}`, piso: (i % 5) + 1,
        plantilla: 'expedientes', areas: [`a${i}`]
      })),
      espacios: []
    };
    const s = salasDe(grande);
    const pisos = pisosDe(grande, s);
    expect(s.length).toBe(15);
    expect(pisos.length).toBe(5);
    //  De arriba hacia abajo, que es como se lee un edificio.
    expect(pisos.map((p) => p.nivel)).toEqual([5, 4, 3, 2, 1]);
    expect(pisos.reduce((n, p) => n + p.salas.length, 0)).toBe(15);
  });

  it('sin organización no se inventa ninguna', () => {
    // Es la decisión que sostiene todo lo demás. Caer a una estructura
    // inventada cuando el motor no responde sería afirmar cómo es una empresa
    // que no se pudo consultar.
    expect(salasDe(null)).toEqual([]);
    expect(salasDe({})).toEqual([]);
    expect(salasDe({ departamentos: [] })).toEqual([]);
    expect(pisosDe(null)).toEqual([]);
  });

  it('entradas basura no tumban la pantalla', () => {
    const roto = { departamentos: [null, {}, { id: 'ok', plantilla: 'tecnica' }], espacios: null };
    const s = salasDe(roto);
    expect(s.length).toBe(1);
    expect(s[0].id).toBe('ok');
  });
});

describe('los pisos', () => {
  it('cada sala del piloto cae en un piso declarado', () => {
    for (const p of pisosDe(PORDEFECTO, SALAS)) {
      expect(p.declarado, `piso ${p.nivel}`).toBe(true);
    }
  });

  it('el reparto del piloto es 3 / 3 / 5', () => {
    const porNivel = Object.fromEntries(
      pisosDe(PORDEFECTO, SALAS).map((p) => [p.nivel, p.salas.length])
    );
    expect(porNivel).toEqual({ 3: 3, 2: 3, 1: 5 });
  });

  it('un piso declarado y VACÍO sigue apareciendo', () => {
    // Un nivel libre es un dato del edificio, no un error que haya que
    // esconder: una empresa que declara cuatro y ocupa tres tiene un piso
    // vacío, y el edificio tiene que poder dibujarlo.
    const org = {
      pisos: [{ nivel: 1 }, { nivel: 2 }],
      departamentos: [{ id: 'x', rotulo: 'X', piso: 1, plantilla: 'tecnica' }]
    };
    const pisos = pisosDe(org);
    expect(pisos.map((p) => p.nivel)).toEqual([2, 1]);
    expect(pisos[0].salas).toEqual([]);
  });

  it('una sala en un piso que nadie declaró aparece MARCADA, no se pierde', () => {
    // El motor lo rechaza al validar, así que llegar hasta acá significa que
    // entró por otro camino. Perderla en silencio dejaría un departamento
    // fuera del edificio sin que nadie pudiera explicar por qué.
    const org = {
      pisos: [{ nivel: 1 }],
      departamentos: [{ id: 'x', rotulo: 'X', piso: 9, plantilla: 'tecnica' }]
    };
    const pisos = pisosDe(org);
    const nueve = pisos.find((p) => p.nivel === 9);
    expect(nueve.declarado).toBe(false);
    expect(nueve.salas.map((s) => s.id)).toEqual(['x']);
  });
});

describe('la plantilla es una ELECCIÓN del catálogo', () => {
  it('cada sala del piloto pide una plantilla que existe', () => {
    for (const s of SALAS) {
      expect(s.plantillaFaltante, `${s.id} pide «${s.plantilla}»`).toBeNull();
    }
  });

  it('dos departamentos pueden compartir plantilla y siguen siendo dos salas', () => {
    // Finanzas, Recursos Humanos y Auditoría usan la misma. Compartir
    // geometría es reutilizar la biblioteca; lo que no pueden compartir es
    // identidad, rótulo ni puestos.
    const mismas = DEPTOS.filter((d) => d.plantilla === 'expedientes');
    expect(mismas.length).toBeGreaterThanOrEqual(3);
    expect(new Set(mismas.map((d) => d.id)).size).toBe(mismas.length);
    expect(new Set(mismas.map((d) => d.planta.puestos[0].id)).size).toBe(mismas.length);
  });

  it('una plantilla desconocida cae en una sala sosa Y LO DICE', () => {
    // Las dos alternativas son peores: no dibujar el departamento abre un
    // hueco que nadie puede explicar, y caer en silencio a otra plantilla
    // afirma que esa sala es un centro de operaciones cuando nadie lo dijo.
    const s = salasDe({ departamentos: [{ id: 'x', rotulo: 'X', plantilla: 'nave_espacial' }] })[0];
    expect(s.plantillaFaltante).toBe('nave_espacial');
    expect(s.planta.mundo).toEqual(PLANTILLAS.generica.mundo);
    expect(s.planta.mural).toBeNull();
  });

  it('un puesto que la plantilla NO tiene se reporta, no desaparece', () => {
    // La empresa escribió que alguien se sienta y no hay silla. Ignorarlo
    // haría desaparecer a un agente declarado sin que nadie lo notara.
    const s = salasDe({
      departamentos: [{
        id: 'x', rotulo: 'X', plantilla: 'reuniones',
        ocupaciones: [{ puesto: 'principal', agente: 'a' }, { puesto: 'p7', agente: 'b' }]
      }]
    })[0];
    expect(s.puestosDesconocidos).toEqual(['p7']);
    expect(s.planta.puestos.some((p) => p.agente === 'b')).toBe(false);
  });

  it('el acento de la configuración gana sobre el de la plantilla', () => {
    const s = salasDe({
      departamentos: [{ id: 'x', rotulo: 'X', plantilla: 'tecnica', acento: '#123456' }]
    })[0];
    expect(s.planta.acento).toBe(0x123456);
  });

  it('un acento mal escrito se descarta en vez de interpretarse', () => {
    for (const malo of ['rojo', '#12345', 'rgb(1,2,3)', '', null]) {
      const s = salasDe({
        departamentos: [{ id: 'x', rotulo: 'X', plantilla: 'tecnica', acento: malo }]
      })[0];
      expect(s.planta.acento, String(malo)).toBe(PLANTILLAS.tecnica.acento);
    }
  });
});

describe('la escena sabe dibujar todo lo que el catálogo pide', () => {
  it('ningún mueble declarado es de un tipo desconocido', () => {
    // Un tipo que la escena no conoce no da error: el mueble simplemente no
    // se dibuja, y la sala sale incompleta sin que nada lo diga.
    const conocidos = new Set(TIPOS_DE_MUEBLE);
    for (const [nombre, p] of Object.entries(PLANTILLAS)) {
      for (const m of p.mobiliario) {
        expect(conocidos.has(m.tipo), `${nombre}: «${m.tipo}» no existe`).toBe(true);
      }
    }
  });
});

describe('la geometría de cada plantilla cierra', () => {
  for (const [nombre, p] of Object.entries(PLANTILLAS)) {
    it(`${nombre}: los puestos caben dentro del recinto`, () => {
      for (const q of p.puestos) {
        expect(q.gx, `${q.id}.gx`).toBeGreaterThan(0);
        expect(q.gy, `${q.id}.gy`).toBeGreaterThan(0);
        expect(q.gx, `${q.id}.gx`).toBeLessThan(p.mundo.ancho);
        expect(q.gy, `${q.id}.gy`).toBeLessThan(p.mundo.fondo);
      }
    });

    it(`${nombre}: ningún puesto se solapa con otro`, () => {
      for (const a of p.puestos) {
        for (const b of p.puestos) {
          if (a === b) continue;
          const d = Math.abs(a.gx - b.gx) + Math.abs(a.gy - b.gy);
          expect(d, `${a.id} y ${b.id} se tocan`).toBeGreaterThan(1.4);
        }
      }
    });

    it(`${nombre}: los identificadores de puesto no se repiten`, () => {
      const ids = p.puestos.map((q) => q.id);
      expect(new Set(ids).size).toBe(ids.length);
    });

    it(`${nombre}: el pasillo está dentro del recinto y no tiene ancho cero`, () => {
      if (!p.pasillo) return;
      expect(p.pasillo.desde).toBeGreaterThanOrEqual(0);
      expect(p.pasillo.hasta).toBeLessThanOrEqual(p.mundo.ancho);
      expect(p.pasillo.hasta).toBeGreaterThan(p.pasillo.desde);
    });

    it(`${nombre}: hay exactamente un puesto principal`, () => {
      expect(p.puestos.filter((q) => q.principal === true).length).toBe(1);
    });
  }
});

describe('los identificadores de puesto no chocan entre salas', () => {
  it('ninguno se repite en toda la empresa', () => {
    // Con once salas y seis plantillas, tres departamentos comparten
    // geometría: sin el prefijo de la sala, seleccionar un puesto de Finanzas
    // seleccionaría el de Auditoría.
    const ids = SALAS.flatMap((s) => s.planta.puestos.map((p) => p.id));
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('y cada uno lleva el identificador de su sala', () => {
    for (const s of SALAS) {
      for (const p of s.planta.puestos) {
        expect(p.id.startsWith(`${s.id}:`), p.id).toBe(true);
        expect(p.local).not.toContain(':');
      }
    }
  });
});

describe('quién pertenece a cada departamento', () => {
  it('los agentes salen por área, no por nombre', () => {
    const noc = salaPorId(SALAS, 'operativo');
    expect(agentesDe(inventario, noc).map((a) => a.nombre)).toEqual(['supervisor_noc']);
  });

  it('acepta todas las escrituras que el departamento DECLARA', () => {
    // Hay dos vocabularios de área y no coinciden: la configuración declara
    // `operativo` y el rol que existe de verdad escribe «Operaciones». Con
    // solo el identificador, esta sala salía vacía en producción.
    const noc = salaPorId(SALAS, 'operativo');
    for (const area of ['operativo', 'Operaciones', 'NOC y Redes', 'OPERATIVO']) {
      expect(agentesDe([{ nombre: 'x', area }], noc).length, area).toBe(1);
    }
  });

  it('y NO adivina las que no declara', () => {
    // Aceptar «operaciones» como `operativo` serviría hoy y el día que una
    // empresa tenga las dos cosas sentaría al agente equivocado, sin un error
    // que lo explique.
    const noc = salaPorId(SALAS, 'operativo');
    for (const area of ['red', 'infraestructura', 'noc', 'Redes']) {
      expect(agentesDe([{ nombre: 'x', area }], noc).length, area).toBe(0);
    }
  });

  it('DOS etiquetas de rol pueden ser UN departamento', () => {
    // «Soporte Técnico» y «Atención al Cliente» son dos áreas en el
    // vocabulario de los roles y una sola puerta de servicio en la empresa.
    // Antes eran dos salas, y eso era consecuencia de deducir la estructura de
    // los agentes.
    const at = salaPorId(SALAS, 'atencion_cliente');
    expect(agentesDe(inventario, at).map((a) => a.nombre).sort())
      .toEqual(['cliente_final', 'soporte', 'soporte_tecnico_cliente']);
  });

  it('cada área real del tenant cae en algún departamento', () => {
    const reales = ['Operaciones', 'Atención al Cliente', 'Soporte Técnico',
                    'Facturación', 'Ventas', 'Administración'];
    for (const area of reales) {
      const encaja = DEPTOS.some((d) => agentesDe([{ nombre: 'x', area }], d).length === 1);
      expect(encaja, `«${area}» no tiene sala`).toBe(true);
    }
  });

  it('y ninguna cae en DOS departamentos a la vez', () => {
    // El mismo agente en dos salas sería el mismo trabajo contado dos veces.
    const reales = ['Operaciones', 'Atención al Cliente', 'Soporte Técnico',
                    'Facturación', 'Ventas', 'Administración'];
    for (const area of reales) {
      const cuantas = DEPTOS.filter((d) => agentesDe([{ nombre: 'x', area }], d).length === 1).length;
      expect(cuantas, `«${area}» cae en ${cuantas} salas`).toBe(1);
    }
  });

  it('un espacio complementario no reclama a nadie', () => {
    const rec = salaPorId(SALAS, 'recepcion');
    expect(agentesDe(inventario, rec)).toEqual([]);
  });

  it('no muta el inventario que recibe', () => {
    const copia = [...inventario];
    agentesDe(inventario, salaPorId(SALAS, 'operativo'));
    expect(inventario.map((a) => a.nombre)).toEqual(copia.map((a) => a.nombre));
  });
});

describe('la planta lista para dibujar', () => {
  const planta = plantaDe(salaPorId(SALAS, 'operativo'), inventario);

  it('sienta al agente DECLARADO en el puesto declarado', () => {
    const principal = planta.puestos.find((p) => p.principal);
    expect(principal.agente).toBe('supervisor_noc');
    expect(principal.nombre).toBe('Supervisor NOC');
  });

  it('los puestos sin agente se dibujan vacíos y lo dicen', () => {
    const libres = planta.puestos.filter((p) => !p.agente);
    expect(libres.length).toBe(3);
    for (const p of libres) {
      expect(p.motivo).toBe('sin agente asignado');
    }
  });

  it('el cartel del muro lleva el rótulo del departamento', () => {
    expect(planta.cartel.rotulo).toBe('NOC y Redes');
  });

  it('el nombre que la configuración declara gana sobre el de la plantilla', () => {
    // Finanzas declara «Cobranza» para un puesto que la plantilla llama
    // «Coordinación». Es lo que permite reutilizar geometría sin heredar
    // rótulos ajenos.
    const cartera = salasDe(PORDEFECTO).find((s) => s.id === 'cartera');
    expect(cartera.planta.puestos.find((p) => p.principal).nombre).toBe('Cobranza');
  });

  it('sin inventario, cada sala se dibuja entera y vacía', () => {
    for (const s of SALAS) {
      const p = plantaDe(s, []);
      expect(p.puestos.length, s.id).toBe(s.planta.puestos.length);
      expect(p.puestos.every((q) => q.agente === null), s.id).toBe(true);
    }
  });

  it('conserva mundo, pasillo y mobiliario de la plantilla', () => {
    const noc = salaPorId(SALAS, 'operativo');
    expect(planta.mundo).toEqual(noc.planta.mundo);
    expect(planta.pasillo).toEqual(noc.planta.pasillo);
    expect(planta.mobiliario.length).toBe(noc.planta.mobiliario.length);
  });

  it('un agente declarado que el inventario NO trae deja el puesto vacío y dice por qué', () => {
    const s = salasDe({
      departamentos: [{
        id: 'x', rotulo: 'X', plantilla: 'tecnica',
        ocupaciones: [{ puesto: 'principal', agente: 'fantasma' }]
      }]
    })[0];
    const p = plantaDe(s, inventario).puestos.find((q) => q.principal);
    expect(p.agente).toBeNull();
    expect(p.area).toBe('agente no encontrado');
    expect(p.motivo).toContain('fantasma');
    expect(p.motivo).toContain('el inventario no lo trae');
  });

  it('una capacidad se resuelve contra el inventario, con su cargo', () => {
    const at = plantaDe(salaPorId(SALAS, 'atencion_cliente'), inventario);
    expect(at.capacidades).toEqual([{ nombre: 'soporte', cargo: 'Soporte', ausente: false }]);
  });

  it('una capacidad que el inventario no trae se marca ausente', () => {
    const s = salasDe({
      departamentos: [{ id: 'x', rotulo: 'X', plantilla: 'tecnica', capacidades: ['fantasma'] }]
    })[0];
    expect(plantaDe(s, inventario).capacidades).toEqual(
      [{ nombre: 'fantasma', cargo: null, ausente: true }]);
  });
});

describe('un departamento SIN NINGÚN AGENTE existe igual', () => {
  //  Es el caso que más importa de los ocho, y el que la estructura deducida de
  //  los agentes no podía representar: un departamento existe porque la empresa
  //  lo tiene, no porque haya un agente que lo represente.
  for (const id of ['campo', 'recursos_humanos', 'auditoria']) {
    it(`${id}: tiene sala, puestos y cartel`, () => {
      const s = salaPorId(SALAS, id);
      const p = plantaDe(s, inventario);
      expect(s).toBeTruthy();
      expect(p.puestos.length).toBeGreaterThan(0);
      expect(p.cartel.rotulo).toBe(s.rotulo);
    });

    it(`${id}: y NO se le inventa ningún personaje`, () => {
      const p = plantaDe(salaPorId(SALAS, id), inventario);
      expect(p.puestos.every((q) => q.agente === null)).toBe(true);
      expect(p.capacidades).toEqual([]);
    });
  }
});

describe('los agentes del piloto: seis se sientan, tres son capacidades', () => {
  //  Se pregunta por la OCUPACIÓN, no por el reparto en el espacio: cada sala
  //  por separado, sin componer ningún edificio. Pedirle la geometría a esta
  //  prueba la ataría a un layout que no tiene nada que ver con lo que afirma.
  const plantas = SALAS.map((s) => plantaDe(s, inventario));
  const sentados = plantas.flatMap((p) => p.puestos.map((q) => q.agente)).filter(Boolean);

  it('se sientan SEIS de los nueve', () => {
    // Tres de los nueve roles no son empleados virtuales: son capacidades que
    // se le asignan a una persona real del CRM. Antes se les dibujaba un
    // escritorio propio.
    expect(sentados.sort()).toEqual([
      'cliente_final', 'configuracion_guiada', 'facturacion_cliente',
      'soporte_tecnico_cliente', 'supervisor_noc', 'ventas'
    ]);
  });

  it('y ninguno de los nueve se pierde: o se sienta, o es capacidad declarada', () => {
    const capacidades = plantas.flatMap((p) => p.capacidades.map((c) => c.nombre));
    const representados = new Set([...sentados, ...capacidades]);
    for (const a of inventario) {
      expect(representados.has(a.nombre), `${a.nombre} no está en ninguna parte`).toBe(true);
    }
  });

  it('ningún agente se sienta DOS veces', () => {
    // Sentado en dos sitios, la misma actividad animaría dos personajes y la
    // empresa se vería con más trabajo del que tiene.
    expect(new Set(sentados).size).toBe(sentados.length);
  });
});

describe('la guarda de este archivo: no vuelve a saber de ninguna empresa', () => {
  it('no exporta ninguna lista de departamentos', async () => {
    // La mutación que esta prueba mata: alguien agrega
    // `export const DEPARTAMENTOS = [...]` «solo para el caso de esta empresa»
    // y la estructura vuelve a estar escrita en el frontend.
    //  `normalizar` se agrego el 31/10/2026 y es la unica excepcion: la
    //  pantalla que organiza la empresa propone ocupantes casando las mismas
    //  areas, y dos normalizaciones distintas casarian distinto. Es una
    //  FUNCION, no una lista -- que es justo lo que esta guarda vigila.
    const mod = await import('./departamentos.js');
    expect(Object.keys(mod).sort()).toEqual([
      'agentesDe', 'normalizar', 'ocupacionesSinSilla', 'pisosDe', 'plantaDe',
      'salaPorId', 'salasDe'
    ]);
    for (const [nombre, valor] of Object.entries(mod)) {
      expect(typeof valor, `${nombre} dejo de ser una funcion`).toBe('function');
    }
  });

  it('el catálogo de plantillas no nombra ningún departamento', () => {
    // Una plantilla se llama por lo que ES —un centro de operaciones, una sala
    // de expedientes—, nunca por quién la usa. «noc» o «cartera» como nombre
    // de plantilla ataría la geometría a una organización concreta.
    const prohibidas = ['noc', 'cartera', 'rrhh', 'auditoria', 'ventas', 'soporte'];
    for (const nombre of Object.keys(PLANTILLAS)) {
      expect(prohibidas, nombre).not.toContain(nombre);
    }
  });

  it('y la guarda se pondría roja si lo hiciera', () => {
    // Sin esto no habría forma de distinguir «no está» de «la comprobación no
    // comprueba nada».
    expect(plantillaDe('cartera').faltante).toBe('cartera');
    expect(plantillaDe('expedientes').faltante).toBeNull();
  });
});

describe('ocupacionesSinSilla', () => {
  //  QUE VIGILA. Cambiar un departamento a una sala mas chica deja al agente de
  //  `p3` sin donde sentarse. La ocupacion NO se borra -a proposito: volver a la
  //  sala grande lo devuelve a su puesto-, pero mientras tanto el agente es
  //  invisible, y el pie decia «5 de 38 puestos ocupados» sin que la diferencia
  //  con el documento guardado la viera nadie.
  const org = (plantilla, ocupaciones) => ({
    departamentos: [{ id: 'auditoria', rotulo: 'Auditoría', piso: 1, plantilla, ocupaciones }]
  });

  it('nombra la sala Y el puesto de la ocupación que no se puede dibujar', () => {
    const salas = salasDe(org('reuniones', [{ puesto: 'p3', agente: 'ventas' }]));
    expect(ocupacionesSinSilla(salas)).toEqual(['Auditoría/p3']);
  });

  it('una ocupación que SÍ tiene silla no se denuncia', () => {
    const salas = salasDe(org('expedientes', [{ puesto: 'p3', agente: 'ventas' }]));
    expect(ocupacionesSinSilla(salas)).toEqual([]);
  });

  it('dice la sala porque el mismo `p3` existe en cinco salas distintas', () => {
    const salas = salasDe({
      departamentos: [
        { id: 'a', rotulo: 'Uno', piso: 1, plantilla: 'reuniones',
          ocupaciones: [{ puesto: 'p3', agente: 'x' }] },
        { id: 'b', rotulo: 'Dos', piso: 1, plantilla: 'reuniones',
          ocupaciones: [{ puesto: 'p3', agente: 'y' }] }
      ]
    });
    expect(ocupacionesSinSilla(salas)).toEqual(['Uno/p3', 'Dos/p3']);
  });

  it('una lista vacía o rota no revienta la pantalla', () => {
    expect(ocupacionesSinSilla([])).toEqual([]);
    expect(ocupacionesSinSilla(null)).toEqual([]);
    expect(ocupacionesSinSilla([null, undefined])).toEqual([]);
  });
});

describe('una persona del equipo ocupa su puesto', () => {
  //  QUE VIGILA. Hasta el 31/10/2026 la oficina sabia dibujar tres cosas -un
  //  agente, un agente declarado y ausente, y un puesto vacio- y una empresa
  //  de internet no esta hecha solo de agentes. Un escritorio con alguien
  //  trabajando se veia EXACTAMENTE IGUAL que uno libre.
  const conPersona = {
    departamentos: [{
      id: 'campo', rotulo: 'Campo', piso: 1, plantilla: 'tecnica',
      ocupaciones: [{ puesto: 'p1', persona: 'Ana Gómez' }]
    }]
  };

  it('no se dibuja como un puesto libre', () => {
    const planta = plantaDe(salasDe(conPersona)[0], []);
    const p1 = planta.puestos.find((p) => p.local === 'p1');
    expect(p1.persona).toBe('Ana Gómez');
    expect(p1.area).not.toBe('puesto libre');
  });

  it('se rotula con su nombre', () => {
    const planta = plantaDe(salasDe(conPersona)[0], []);
    expect(planta.puestos.find((p) => p.local === 'p1').nombre).toBe('Ana Gómez');
  });

  it('NO se resuelve contra el inventario de agentes, así que no puede estar «ausente»', () => {
    // No esta ahi ni tiene por que estarlo: el motor no conoce las cuentas del
    // CRM. Buscarla en el inventario la dejaria para siempre como un agente
    // que falta, que es una acusacion y no un dato.
    const planta = plantaDe(salasDe(conPersona)[0], []);
    const p1 = planta.puestos.find((p) => p.local === 'p1');
    expect(p1.motivo).toBe(null);
    expect(p1.agente).toBe(null);
  });

  it('un puesto con agente sigue sin persona, y al revés', () => {
    // Las dos formas tienen que ser UNA: si un puesto a veces trae `persona` y
    // a veces no trae la clave, quien lea `p.persona` acierta por casualidad.
    const planta = plantaDe(salasDe({
      departamentos: [{ id: 'x', rotulo: 'X', piso: 1, plantilla: 'tecnica',
                        ocupaciones: [{ puesto: 'principal', agente: 'ventas' }] }]
    })[0], [{ nombre: 'ventas', cargo: 'Ventas' }]);
    for (const p of planta.puestos) expect(p).toHaveProperty('persona');
    expect(planta.puestos.find((p) => p.local === 'principal').persona).toBe(null);
  });
});
