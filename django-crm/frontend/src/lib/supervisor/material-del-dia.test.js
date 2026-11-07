import { describe, expect, it } from 'vitest';

import {
  cantidad,
  cuerpoDeConfiguracion,
  equipoQueFalta,
  equiposDeTodas,
  estadoDeCarga,
  lineaDeEquipo,
  lineaDeMaterial,
  loQueHayQueResolver,
  tituloDelMaterial,
  opcionDelSupervisor,
  pastillaDeAvisos,
  porQue,
  resumenDeAvisos,
  resumenDeLineas
} from './material-del-dia.js';

describe('si el Supervisor ya cargó el material (fase 3)', () => {
  it('la hora, sin el acta (29/10/2026: «está de más»), o nada', () => {
    expect(estadoDeCarga({ cargado_en: '2026-10-28T06:07:10-05:00', acta: 'MAT-20261028-1a2b3c4d' })).toBe(
      'Cargado a las 06:07'
    );
    expect(estadoDeCarga({ cargado_en: null, acta: 'MAT-x' })).toBe('');
  });

  it('los avisos en una línea: lo que falta y los equipos con que no sale', () => {
    const falta = 'Le falta material para completar el kit (13 de 14 materiales): sale con lo que hay en bodega.';
    const catv = 'Sale sin ONU CATV: no puede hacer el trabajo que lo necesita.';
    const wifi = 'Sale sin ONU WIFI: no puede hacer el trabajo que lo necesita.';
    const tv = 'Sale sin SPLITER DE TV 1X2: no puede hacer el trabajo que lo necesita.';
    expect(resumenDeAvisos([falta, catv, wifi])).toBe('Falta material · sale sin ONU CATV y ONU WIFI');
    expect(resumenDeAvisos([falta, catv, wifi, tv])).toBe(
      'Falta material · sale sin ONU CATV, ONU WIFI y SPLITER DE TV 1X2'
    );
    expect(resumenDeAvisos([catv])).toBe('Sale sin ONU CATV');
    expect(resumenDeAvisos([falta, 'No tiene líder con cuenta activa: no hay a quién cargarle.'])).toBe(
      'Falta material · 1 aviso más'
    );
    expect(resumenDeAvisos([])).toBe('');
  });

  it('el título dice cuántas ya se cargaron, o que es una propuesta', () => {
    expect(tituloDelMaterial([{ cargado_en: null }, { cargado_en: null }])).toBe(
      'Material del día · propuesta: el Supervisor todavía no cargó nada'
    );
    expect(tituloDelMaterial([{ cargado_en: '2026-10-28T06:07:00-05:00' }, { cargado_en: null }])).toBe(
      'Material del día · el Supervisor ya cargó 1 de 2 cuadrillas'
    );
  });
});

describe('lo que eligió el Supervisor, y por qué', () => {
  it('una persona o el Supervisor con su motivo', () => {
    expect(porQue('lo eligió una persona')).toBe('elegido por una persona');
    expect(porQue('su zona la nombra')).toBe('lo eligió el Supervisor: su zona la nombra');
    expect(porQue('')).toBe('');
  });

  it('la opción del panel dice qué elegiría hoy', () => {
    expect(opcionDelSupervisor('BOG-SOLEDAD')).toBe('Que elija el Supervisor (hoy: BOG-SOLEDAD)');
    expect(opcionDelSupervisor('')).toBe('Que elija el Supervisor (hoy no puede: ver el motivo)');
  });
});

describe('el material del día, como lo lee una persona', () => {
  it('lo que carga, y lo que ya tiene', () => {
    expect(
      lineaDeMaterial({ material: 'Conector UPC', unidad: 'unidades', en_mano: '4', necesita: '6', asignado: '6' })
    ).toBe('Conector UPC: carga 6 unidades (ya tiene 4)');
    expect(
      lineaDeMaterial({ material: 'ONU WIFI', unidad: 'unidades', en_mano: '0', necesita: '1', asignado: '1' })
    ).toBe('ONU WIFI: carga 1 unidad');
  });

  it('lo que falta va en la misma línea, y «no hay en bodega» en vez de «carga 0»', () => {
    expect(
      lineaDeMaterial({ material: 'CABLE COAXIAL', unidad: 'm', en_mano: '0', necesita: '200', asignado: '100', falta: '100' })
    ).toBe('CABLE COAXIAL: carga 100 m (faltan 100 m)');
    expect(
      lineaDeMaterial({ material: 'CHAZO', unidad: 'unidades', en_mano: '0', necesita: '10', asignado: '0', falta: '10' })
    ).toBe('CHAZO: no hay en bodega (faltan 10 unidades)');
    expect(
      lineaDeMaterial({ material: 'TENSOR', unidad: 'unidades', en_mano: '2', necesita: '8', asignado: '5', falta: '3' })
    ).toBe('TENSOR: carga 5 unidades (ya tiene 2 · faltan 3 unidades)');
  });

  it('el rótulo de la lista plegada', () => {
    expect(resumenDeLineas([{ falta: '0' }, { falta: '3' }, { falta: '1' }])).toBe(
      'Ver los 3 materiales del kit · 2 incompletos'
    );
    expect(resumenDeLineas([{ falta: '0' }])).toBe('Ver el material del kit');
  });

  it('si ya tiene el kit completo no dice «carga 0»', () => {
    expect(
      lineaDeMaterial({ material: 'Cable drop', unidad: 'metros', en_mano: '300', necesita: '0', asignado: '0' })
    ).toBe('Cable drop: tiene el kit completo (ya tiene 300)');
  });

  it('las unidades', () => {
    expect([cantidad('1', 'unidades'), cantidad('2', 'unidades'), cantidad('300', 'metros')]).toEqual([
      '1 unidad',
      '2 unidades',
      '300 metros'
    ]);
  });
});

describe('el formulario de configuración', () => {
  it('kits y bodegas, y vacío es «sin»', () => {
    const f = new FormData();
    f.set('kit:correctivo', 'k-1');
    f.set('kit:trabajos', '');
    f.set('bodega:c-1', 'b-1');
    f.set('otra_cosa', 'x');
    // Si cada labor se toma de apoyo (30/10/2026); lo que no es sí o no, no viaja.
    f.set('apoyo:instalacion', 'si');
    f.set('apoyo:trabajos', 'no');
    f.set('apoyo:correctivo', 'tal vez');

    expect(cuerpoDeConfiguracion(f)).toEqual({
      kits: { correctivo: 'k-1', trabajos: null },
      bodegas: { 'c-1': 'b-1' },
      apoyos: { instalacion: true, trabajos: false }
    });
  });
});


const CATV = 'Sale sin ONU CATV: no puede hacer el trabajo que lo necesita.';
const WIFI = 'Sale sin ONU WIFI: no puede hacer el trabajo que lo necesita.';
const FALTA = 'Le falta material para completar el kit (13 de 14 materiales): sale con lo que hay en bodega.';

describe('lo que dice la pastilla de la tarjeta', () => {
  //  EL MURO (07/11/2026). El usuario, con la captura de cuatro tarjetas:
  //  «qué otro arreglo se puede hacer para que no se vea tan maluco». La
  //  línea era «Falta material · sale sin ONU CATV y ONU WIFI», idéntica en
  //  las cuatro, y «Falta material» ya lo dicen las pastillas de arriba.
  it('EL DEFECTO: con equipo nombrado NO repite «Falta material»', () => {
    expect(pastillaDeAvisos([FALTA, CATV, WIFI])).toEqual({
      texto: 'Sin ONU CATV y ONU WIFI',
      propio: true
    });
  });

  it('un solo equipo va en singular, sin la «y» colgando', () => {
    expect(pastillaDeAvisos([FALTA, CATV]).texto).toBe('Sin ONU CATV');
  });

  it('tres equipos se separan con comas y una «y»', () => {
    const tres = ['A', 'B', 'C'].map((x) => `Sale sin ONU ${x}: no puede hacer el trabajo.`);
    expect(pastillaDeAvisos(tres).texto).toBe('Sin ONU A, ONU B y ONU C');
  });

  //  EL CONTROL: sin equipo nombrado hay que decir lo que hay, no quedarse
  //  callado. Una tarjeta sin pastilla se lee como «esta sale completa».
  it('sin equipo nombrado dice que falta material', () => {
    expect(pastillaDeAvisos([FALTA])).toEqual({ texto: 'Falta material', propio: true });
  });

  it('un aviso que no reconoce se cuenta, no se pierde', () => {
    expect(pastillaDeAvisos(['Algo raro pasó.']).texto).toBe('1 aviso más');
  });

  it('sin avisos, nada', () => {
    expect(pastillaDeAvisos([]).texto).toBe('');
    expect(pastillaDeAvisos(undefined).texto).toBe('');
  });

  //  EL SEGUNDO MURO (07/11/2026). El usuario, con la pantalla YA desplegada:
  //  «esto sigue igual». Y era cierto: las cuatro tarjetas seguían diciendo
  //  «Sin ONU CATV y ONU WIFI» palabra por palabra, debajo de un «Sin ONU
  //  CATV: 4 cuadrillas» que ya lo decía. Acortar la frase no quitó la
  //  repetición.
  it('lo que le falta a TODAS no se repite en la tarjeta', () => {
    expect(pastillaDeAvisos([FALTA, CATV, WIFI], ['ONU CATV', 'ONU WIFI'])).toEqual({
      texto: '3 avisos',
      propio: false
    });
  });

  it('pero lo PROPIO sí sale, y el común no lo tapa', () => {
    expect(pastillaDeAvisos([CATV, WIFI], ['ONU CATV'])).toEqual({
      texto: 'Sin ONU WIFI',
      propio: true
    });
  });

  it('sin comunes se comporta como antes', () => {
    expect(pastillaDeAvisos([FALTA, CATV, WIFI], [])).toEqual({
      texto: 'Sin ONU CATV y ONU WIFI',
      propio: true
    });
  });

  it('el rótulo gris cuenta los avisos de esa cuadrilla, y uno va en singular', () => {
    expect(pastillaDeAvisos([CATV], ['ONU CATV'])).toEqual({ texto: '1 aviso', propio: false });
  });
});

describe('los equipos que le faltan a TODAS (07/11/2026)', () => {
  it('solo los que están en todas las que tienen material', () => {
    expect(
      equiposDeTodas([
        { avisos: [FALTA, CATV, WIFI] },
        { avisos: [CATV, WIFI] },
        { avisos: [FALTA, CATV] },
        //  Sin material: no vota. Si votara, el conjunto quedaría vacío y
        //  volvería el muro de la captura.
        { avisos: [] }
      ])
    ).toEqual(['ONU CATV']);
  });

  it('si una se salva, ya no es de todas', () => {
    expect(equiposDeTodas([{ avisos: [CATV] }, { avisos: [FALTA] }])).toEqual([]);
  });

  //  CON UNA SOLA CUADRILLA NO HAY REPETICIÓN POSIBLE: lo suyo es propio y
  //  tiene que seguir saliendo en rojo en su tarjeta.
  it('una sola cuadrilla con material no tiene nada en común con nadie', () => {
    expect(equiposDeTodas([{ avisos: [CATV, WIFI] }])).toEqual([]);
    expect(equiposDeTodas([{ avisos: [CATV] }, { avisos: [] }])).toEqual([]);
    expect(equiposDeTodas([])).toEqual([]);
    expect(equiposDeTodas(undefined)).toEqual([]);
  });

  it('el caso del usuario: las cuatro iguales, y la tarjeta deja de repetirlo', () => {
    const cuatro = [
      { avisos: [FALTA, CATV, WIFI] },
      { avisos: [FALTA, CATV, WIFI] },
      { avisos: [FALTA, CATV, WIFI] },
      { avisos: [FALTA, CATV, WIFI] }
    ];
    const comunes = equiposDeTodas(cuatro);
    expect(comunes).toEqual(['ONU CATV', 'ONU WIFI']);
    for (const m of cuatro) expect(pastillaDeAvisos(m.avisos, comunes).propio).toBe(false);
  });
});

describe('qué equipo falta hoy y a cuántas cuadrillas', () => {
  it('cuenta CUADRILLAS por equipo, de la más a la menos', () => {
    expect(
      equipoQueFalta([
        { avisos: [FALTA, CATV, WIFI] },
        { avisos: [CATV] },
        { avisos: [CATV, WIFI] },
        { avisos: [FALTA] },
        { avisos: [] }
      ])
    ).toEqual([
      { equipo: 'ONU CATV', cuadrillas: 3, todas: false },
      { equipo: 'ONU WIFI', cuadrillas: 2, todas: false }
    ]);
  });

  it('dos avisos del mismo equipo en una cuadrilla siguen siendo UNA', () => {
    expect(equipoQueFalta([{ avisos: [CATV, CATV] }])).toEqual([
      { equipo: 'ONU CATV', cuadrillas: 1, todas: false }
    ]);
  });

  //  CUANDO NO SE SALVA NINGUNA (07/11/2026): la tarjeta ya no lo repite, así
  //  que esta pastilla es la ÚNICA vez que se dice. Tiene que quedar claro
  //  que no es parcial.
  it('marca el equipo que le falta a todas las que tienen material', () => {
    expect(equipoQueFalta([{ avisos: [CATV, WIFI] }, { avisos: [CATV] }, { avisos: [] }])).toEqual([
      { equipo: 'ONU CATV', cuadrillas: 2, todas: true },
      { equipo: 'ONU WIFI', cuadrillas: 1, todas: false }
    ]);
  });

  it('si no falta equipo no inventa una pastilla', () => {
    expect(equipoQueFalta([{ avisos: [FALTA] }, { avisos: [] }])).toEqual([]);
    expect(equipoQueFalta([])).toEqual([]);
    expect(equipoQueFalta(undefined)).toEqual([]);
  });

  //  COMO FRASE desde el 07/11/2026 (tercera vuelta): el renglón vive dentro
  //  del bloque «Para que el día salga completo», que se lee de corrido.
  it('se lee «A 3 cuadrillas les falta ONU CATV», y una sola en singular', () => {
    expect(lineaDeEquipo({ equipo: 'ONU CATV', cuadrillas: 3 })).toBe('A 3 cuadrillas les falta ONU CATV');
    expect(lineaDeEquipo({ equipo: 'ONU WIFI', cuadrillas: 1 })).toBe('A 1 cuadrilla le falta ONU WIFI');
  });

  it('cuando no se salva ninguna lo dice con todas las letras: «las 4»', () => {
    expect(lineaDeEquipo({ equipo: 'ONU CATV', cuadrillas: 4, todas: true })).toBe(
      'A las 4 cuadrillas les falta ONU CATV'
    );
  });

  //  EL BLOQUE (07/11/2026, tercera vuelta). Eran seis pastillas rojas y un
  //  párrafo suelto repartidos por la franja; el usuario eligió sobre la
  //  maqueta juntarlos. El orden importa: primero lo que deja a una cuadrilla
  //  sin poder trabajar, después lo que impide que le llegue el trabajo.
  it('junta el equipo que falta y las apps, en ese orden', () => {
    expect(
      loQueHayQueResolver(
        [
          { equipo: 'ONU CATV', cuadrillas: 5, todas: true },
          { equipo: 'ONU WIFI', cuadrillas: 2 }
        ],
        '4 cuadrillas no abrieron la app: 44 órdenes todavía no están en los teléfonos. Que abran la app para recibirlas.'
      )
    ).toEqual([
      'A las 5 cuadrillas les falta ONU CATV',
      'A 2 cuadrillas les falta ONU WIFI',
      '4 cuadrillas no abrieron la app: 44 órdenes todavía no están en los teléfonos. Que abran la app para recibirlas.'
    ]);
  });

  it('sin nada que resolver no hay bloque: un aviso siempre visible no avisa', () => {
    expect(loQueHayQueResolver([], '')).toEqual([]);
    expect(loQueHayQueResolver(undefined, '')).toEqual([]);
  });

  it('con una sola de las dos cosas, el bloque igual sale', () => {
    expect(loQueHayQueResolver([], 'Alguien no abrió la app.')).toEqual(['Alguien no abrió la app.']);
    expect(loQueHayQueResolver([{ equipo: 'ONU WIFI', cuadrillas: 1 }], '')).toEqual([
      'A 1 cuadrilla le falta ONU WIFI'
    ]);
  });
});
