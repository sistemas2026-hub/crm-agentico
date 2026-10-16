import { describe, it, expect } from 'vitest';
import { areaDelCaso, resumenPorArea, responsablesSinArea, responsablesDeArea, SIN_AREA }
  from './tickets-resumen.js';

/**
 * EL DEFECTO QUE ESTO FIJA  --  medido en produccion el 06/10/2026
 * ----------------------------------------------------------------
 * La pantalla mostraba «Tickets: 47 · Soporte Técnico: 25» y parecia que 22
 * tickets no tenian area. El total venia del servidor y el desglose se
 * calculaba en el navegador sobre una pagina de 25.
 *
 * Por eso el caso central de este archivo es exactamente ese: COUNT > LIMIT.
 * Se afirma sobre el EFECTO --que el desglose corresponda al conjunto
 * completo-- y no sobre de donde salieron los numeros.
 */

const AREAS = [
  { nombre: 'cartera', etiqueta: 'Cartera' },
  { nombre: 'soporte_tecnico', etiqueta: 'Soporte Técnico' },
  { nombre: 'administracion', etiqueta: 'Administración' }
];

/** El mapa persona -> area, como lo sirve el motor. */
const MAPA = {
  'p-soporte': 'soporte_tecnico',
  'p-cartera-1': 'cartera',
  'p-cartera-2': 'cartera'
};

const fila = (assigned_to, total, extra = {}) => ({
  assigned_to, total, urgentes: 0, sin_respuesta: 0, en_progreso: 0, ...extra
});

const de = (filas, nombre) => filas.find((a) => a.nombre === nombre);

describe('el caso de produccion: 47 abiertos, pagina de 25', () => {
  //  Los 47 tenian UN responsable, el mismo, con area soporte_tecnico.
  const desglose = [fila('p-soporte', 47, { urgentes: 3, sin_respuesta: 12, en_progreso: 5 })];

  it('Soporte Técnico dice 47, no 25', () => {
    const r = resumenPorArea(desglose, AREAS, MAPA);
    expect(de(r, 'soporte_tecnico').total).toBe(47);
  });

  it('y las otras dos areas, 0', () => {
    const r = resumenPorArea(desglose, AREAS, MAPA);
    expect(de(r, 'cartera').total).toBe(0);
    expect(de(r, 'administracion').total).toBe(0);
  });

  it('las areas suman el total: 47 = 47 + 0 + 0', () => {
    const r = resumenPorArea(desglose, AREAS, MAPA);
    expect(r.reduce((t, a) => t + a.total, 0)).toBe(47);
  });

  it('no aparece "Sin área asignada" porque no hay ninguno', () => {
    const r = resumenPorArea(desglose, AREAS, MAPA);
    expect(de(r, SIN_AREA)).toBeUndefined();
  });

  it('las demas metricas tambien salen del conjunto completo', () => {
    const s = de(resumenPorArea(desglose, AREAS, MAPA), 'soporte_tecnico');
    expect([s.urgentes, s.sin_respuesta, s.en_progreso]).toEqual([3, 12, 5]);
  });
});

describe('varias areas y varias paginas', () => {
  //  260 abiertos repartidos en cuatro responsables: diez paginas de 25.
  //  Ninguna pagina contiene a los cuatro, y el desglose igual tiene que dar
  //  el total -- es lo que la version anterior no podia hacer.
  const desglose = [
    fila('p-soporte', 120, { urgentes: 10 }),
    fila('p-cartera-1', 80, { urgentes: 4 }),
    fila('p-cartera-2', 40, { urgentes: 1 }),
    fila(null, 20)
  ];
  const r = resumenPorArea(desglose, AREAS, MAPA);

  it('cada area suma a TODOS sus responsables', () => {
    expect(de(r, 'soporte_tecnico').total).toBe(120);
    expect(de(r, 'cartera').total).toBe(120);   // 80 + 40
    expect(de(r, 'administracion').total).toBe(0);
  });

  it('los urgentes tambien se suman entre responsables', () => {
    expect(de(r, 'cartera').urgentes).toBe(5);  // 4 + 1
  });

  it('los sin responsable van a "Sin área asignada"', () => {
    expect(de(r, SIN_AREA).total).toBe(20);
    expect(de(r, SIN_AREA).sin_asignar).toBe(20);
  });

  it('el total del desglose es 260, no 25', () => {
    expect(r.reduce((t, a) => t + a.total, 0)).toBe(260);
  });
});

describe('responsables sin area configurada', () => {
  const desglose = [fila('p-soporte', 5), fila('p-desconocido', 7)];

  it('sus tickets caen en "Sin área", no desaparecen', () => {
    const r = resumenPorArea(desglose, AREAS, MAPA);
    expect(de(r, SIN_AREA).total).toBe(7);
  });

  it('pero NO cuentan como "sin asignar": tienen responsable', () => {
    //  Son dos problemas distintos. "Nadie lo tiene" se arregla asignando;
    //  "su area no esta configurada" se arregla en /agentes. Confundirlos
    //  esconde el que hay que arreglar.
    const r = resumenPorArea(desglose, AREAS, MAPA);
    expect(de(r, SIN_AREA).sin_asignar).toBe(0);
  });

  it('y se pueden nombrar, para avisar', () => {
    expect(responsablesSinArea(desglose, MAPA)).toEqual(['p-desconocido']);
  });

  it('sin desglose no se inventa una lista', () => {
    expect(responsablesSinArea(null, MAPA)).toEqual([]);
  });
});

describe('cuando NO se pudo contar', () => {
  it('devuelve null, no un desglose en ceros', () => {
    //  El error que este modulo existe para no repetir: un cero que dice lo
    //  que no sabe. Si esto devolviera [], la pantalla mostraria "0 tickets en
    //  todas las areas" cuando lo cierto es "no se pudo contar".
    expect(resumenPorArea(null, AREAS, MAPA)).toBeNull();
    expect(resumenPorArea(undefined, AREAS, MAPA)).toBeNull();
    expect(resumenPorArea('no soy una lista', AREAS, MAPA)).toBeNull();
  });

  it('un desglose VACIO si es un cero real', () => {
    const r = resumenPorArea([], AREAS, MAPA);
    expect(r).not.toBeNull();
    expect(r.every((a) => a.total === 0)).toBe(true);
    expect(r).toHaveLength(3);   // las tres areas, sin "Sin área"
  });
});

describe('las areas del equipo se muestran aunque esten vacias', () => {
  it('un area en cero no se esconde: que este vacia es informacion', () => {
    const r = resumenPorArea([fila('p-soporte', 3)], AREAS, MAPA);
    expect(r.map((a) => a.nombre)).toEqual(
      ['cartera', 'soporte_tecnico', 'administracion']);
  });

  it('y conserva la etiqueta que vino de la configuracion', () => {
    const r = resumenPorArea([fila('p-soporte', 3)], AREAS, MAPA);
    expect(de(r, 'soporte_tecnico').etiqueta).toBe('Soporte Técnico');
  });
});

describe('un ticket con dos responsables de areas distintas', () => {
  //  El backend agrupa por responsable, asi que un caso compartido aparece en
  //  los dos. No es doble conteo: el ticket de verdad involucra a dos areas.
  //  Lo que NO puede pasar es que eso se lea como "el total es 2".
  it('cuenta en las dos areas, y el total sigue siendo del backend', () => {
    const r = resumenPorArea([fila('p-soporte', 1), fila('p-cartera-1', 1)], AREAS, MAPA);
    expect(de(r, 'soporte_tecnico').total).toBe(1);
    expect(de(r, 'cartera').total).toBe(1);
    //  La suma da 2 para UN ticket: por eso el total de la cabecera sale de
    //  'open_count' y no de sumar las areas.
    expect(r.reduce((t, a) => t + a.total, 0)).toBe(2);
  });
});


/**
 * EL SEGUNDO DEFECTO, medido en produccion el 07/10/2026
 * -------------------------------------------------------
 * La cabecera de Soporte Tecnico decia «91 en total» y la tabla estaba
 * VACIA. El total ya salia del servidor (lo arreglado el 06/10), pero las
 * FILAS seguian siendo la pagina de 25 mas reciente de toda la cola, que el
 * navegador recortaba por area despues. Ese dia: 138 abiertos, las 25 mas
 * recientes TODAS de cartera, y Soporte Tecnico se quedaba sin ninguna.
 *
 * Ese dia el area no era un campo del CRM: era una propiedad de la persona
 * asignada, y filtrar por area era filtrar por sus responsables. Desde el
 * 16/10/2026 el caso trae su area escrita y el API filtra por ella ('area');
 * esta lista viaja aparte, como 'area_responsables', solo para los casos que
 * todavia no la tienen escrita -- ver el tercer defecto, mas abajo.
 */
describe('los responsables de un area, para pedirle al servidor solo su cola', () => {
  it('devuelve a todos los del area y a nadie mas', () => {
    expect(responsablesDeArea('cartera', MAPA).sort())
      .toEqual(['p-cartera-1', 'p-cartera-2']);
    expect(responsablesDeArea('soporte_tecnico', MAPA)).toEqual(['p-soporte']);
  });

  it('un area sin gente devuelve vacio: la mitad vieja no aplica, y la escrita sigue', () => {
    //  Sin 'area_responsables' el API igual filtra por el area escrita en el
    //  caso. Lo que no puede pasar es que una lista vacia se mande como
    //  'assigned_to': eso no filtraba nada y traia la cola entera.
    expect(responsablesDeArea('administracion', MAPA)).toEqual([]);
  });

  it('"Sin área asignada" no se puede pedir por responsable', () => {
    //  Son los casos SIN responsable, o con uno cuya area nadie configuro.
    //  No hay id que mandar, asi que esa cola sigue recortandose del lado del
    //  navegador -- limite conocido y declarado.
    expect(responsablesDeArea(SIN_AREA, MAPA)).toEqual([]);
    expect(responsablesDeArea('', MAPA)).toEqual([]);
  });

  it('sin mapa de areas no inventa responsables', () => {
    expect(responsablesDeArea('cartera', {})).toEqual([]);
    expect(responsablesDeArea('cartera')).toEqual([]);
  });

  it('EL EFECTO: con los responsables del area, la pagina que se pide es la suya', () => {
    //  La reproduccion del 07/10: la cola tiene mucho mas que una pagina y lo
    //  mas reciente es de OTRA area. Se afirma sobre lo que se le pediria al
    //  servidor, que es lo unico que decide que filas llegan. Lo que la
    //  pantalla manda de verdad lo fija routes/(app)/tickets/page-server.test.js.
    const pedido = new URLSearchParams();
    for (const p of responsablesDeArea('soporte_tecnico', MAPA)) pedido.append('area_responsables', p);
    expect(pedido.getAll('area_responsables')).toEqual(['p-soporte']);
    //  y NO se le pide por los de cartera, que son los que llenaban la pagina
    expect(pedido.getAll('area_responsables')).not.toContain('p-cartera-1');
  });

  it('una persona en dos areas no se duplica en el filtro', () => {
    const r = responsablesDeArea('cartera', { ...MAPA, 'p-cartera-1': 'cartera' });
    expect(r.filter((x) => x === 'p-cartera-1')).toHaveLength(1);
  });
});


/**
 * EL TERCER DEFECTO, medido en local el 16/10/2026
 * -------------------------------------------------
 * La pantalla deducia el area de cada caso de la PERSONA asignada:
 *
 *     Case.area = soporte_tecnico       65
 *     pantalla "Soporte Técnico"        64
 *     pantalla "Sin área asignada"       6
 *
 * El que faltaba tenia area 'soporte_tecnico' y estaba asignado a alguien sin
 * area en el motor. Y al reves, lo grave: un ticket de ventas asignado a un
 * tecnico salia como Soporte Tecnico. El caso trae su area escrita desde
 * cdaa9b27 ('Case.area'); lo que faltaba era leerla.
 *
 * Se afirma con el mismo par de mitades del Supervisor: el area ESCRITA
 * manda; la de la persona solo decide cuando no la hay.
 */
describe('el area de un caso es la escrita en el caso', () => {
  it('con area escrita, esa manda aunque la persona sea de otra', () => {
    expect(areaDelCaso('ventas', 'p-soporte', MAPA)).toBe('ventas');
    expect(areaDelCaso('soporte_tecnico', 'p-cartera-1', MAPA)).toBe('soporte_tecnico');
  });

  it('con area escrita y responsable sin area configurada: la escrita', () => {
    //  El ticket que faltaba: 'LOS en rojo', soporte, asignado a alguien
    //  que el motor no conoce.
    expect(areaDelCaso('soporte_tecnico', 'p-desconocido', MAPA)).toBe('soporte_tecnico');
  });

  it('sin area escrita, la de la persona (el criterio de ayer)', () => {
    expect(areaDelCaso('', 'p-cartera-1', MAPA)).toBe('cartera');
    expect(areaDelCaso(undefined, 'p-soporte', MAPA)).toBe('soporte_tecnico');
    expect(areaDelCaso(null, 'p-soporte', MAPA)).toBe('soporte_tecnico');
  });

  it('sin ninguna de las dos, "Sin área asignada"', () => {
    expect(areaDelCaso('', null, MAPA)).toBe(SIN_AREA);
    expect(areaDelCaso('', 'p-desconocido', MAPA)).toBe(SIN_AREA);
    expect(areaDelCaso('', 'p-soporte', {})).toBe(SIN_AREA);
  });
});

describe('las tarjetas suman por el area escrita en el caso', () => {
  //  La reproduccion del 16/10: el tecnico con 64 de soporte, el caso de
  //  soporte asignado a alguien sin area, 3 de ventas asignados a alguien de
  //  ventas (area que la config no declara) y 2 viejos sin area del tecnico.
  const desglose = [
    fila('p-soporte', 64, { area: 'soporte_tecnico' }),
    fila('p-desconocido', 1, { area: 'soporte_tecnico' }),
    fila('p-soporte', 2, { area: '' }),
    fila('p-soporte', 3, { area: 'ventas' }),
    fila(null, 2, { area: 'soporte_tecnico' })
  ];
  const r = resumenPorArea(desglose, AREAS, MAPA);

  it('Soporte Técnico dice 69: los 64, el del responsable sin area, los 2 viejos y los 2 sueltos', () => {
    expect(de(r, 'soporte_tecnico').total).toBe(69);
  });

  it('un caso de ventas asignado al tecnico NO cuenta como soporte', () => {
    expect(de(r, 'ventas').total).toBe(3);
  });

  it('un area escrita que la config no declara se muestra con su nombre, no se esconde', () => {
    expect(de(r, 'ventas')).toMatchObject({ nombre: 'ventas', etiqueta: 'ventas' });
    //  y despues de las declaradas, que conservan su orden
    expect(r.map((a) => a.nombre)).toEqual(
      ['cartera', 'soporte_tecnico', 'administracion', 'ventas']);
  });

  it('"Sin área asignada" no aparece: todos tienen de donde sacar el area', () => {
    expect(de(r, SIN_AREA)).toBeUndefined();
  });

  it('los sueltos CON area escrita son "sin asignar" de su area, no de "Sin área"', () => {
    expect(de(r, 'soporte_tecnico').sin_asignar).toBe(2);
  });

  it('un desglose viejo, sin el campo area, sigue sumando por responsable', () => {
    //  El frontend nuevo contra un backend viejo: la mitad vieja a secas.
    const viejo = [fila('p-soporte', 47), fila('p-cartera-1', 5)];
    const v = resumenPorArea(viejo, AREAS, MAPA);
    expect(de(v, 'soporte_tecnico').total).toBe(47);
    expect(de(v, 'cartera').total).toBe(5);
  });
});

describe('el aviso de responsables sin area mira solo los casos sin area escrita', () => {
  it('quien tiene casos con area escrita no se avisa: ya cuentan en su tarjeta', () => {
    const desglose = [fila('p-desconocido', 1, { area: 'soporte_tecnico' })];
    expect(responsablesSinArea(desglose, MAPA)).toEqual([]);
  });

  it('quien tiene casos SIN area escrita y sin area configurada, si', () => {
    const desglose = [
      fila('p-desconocido', 1, { area: 'soporte_tecnico' }),
      fila('p-desconocido', 4, { area: '' })
    ];
    expect(responsablesSinArea(desglose, MAPA)).toEqual(['p-desconocido']);
  });
});
