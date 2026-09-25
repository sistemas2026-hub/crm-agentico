/**
 * La superficie de revisión del legado (G3).
 *
 * La aserción que sostiene todo el gate: NO HAY BOTÓN DE APROBAR. No
 * deshabilitado — ausente. Aprobar es ejecutar, y ejecutar una intención de
 * hace semanas sin revalidación es lo que X24 prohíbe; un botón gris invita a
 * preguntar cómo habilitarlo.
 *
 * El motor además la rechaza con 409 (tests/test_g3_acciones_legado.py), así
 * que la pantalla no es la única defensa. Es que no haya ni por dónde
 * intentarlo.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import {
  lineaDeAccion, queHace, porQueNoSeAprueba, antiguedad, resumenPorTipo
} from './legado.js';

const leer = (rel) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), 'utf-8');

/**
 * El código sin comentarios.
 *
 * Existe por un error propio, cometido cuatro veces en esta fase: afirmar
 * `not.toMatch(/argumentos/)` sobre el archivo entero da ROJO por el
 * comentario que explica que los argumentos NO se piden — y al revés, daría
 * verde con la línea viva comentada al lado. Lo que se afirma es sobre lo que
 * se ejecuta.
 */
const soloCodigo = (fuente) =>
  fuente.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '');

const pagina = leer('../../routes/(app)/acciones-legado/+page.svelte');
const proxyLista = soloCodigo(leer('../../routes/api/acciones-legado/+server.js'));
const proxyCancelar = soloCodigo(
  leer('../../routes/api/acciones-legado/[id]/cancelar/+server.js')
);

const accion = (extra) => ({
  id: 'a1', herramienta: 'crear_ticket', resumen: 'Sin internet desde el martes',
  estado: 'pendiente', es_legado: true, creado_en: '2026-09-01T10:00:00Z', ...extra
});

const AHORA = new Date('2026-09-20T10:00:00Z');

describe('no hay forma de aprobar desde acá', () => {
  it('la pantalla no tiene ningún control que apruebe', () => {
    // Se afirma sobre los CONTROLES, no sobre la palabra: la pantalla dice
    // «no se pueden aprobar» en su texto, y tiene que poder decirlo. Lo que
    // no puede existir es algo en lo que apretar.
    const marcado = pagina
      .slice(pagina.lastIndexOf('</script>'))
      .replace(/<style[\s\S]*?<\/style>/g, '')
      .replace(/<!--[\s\S]*?-->/g, '');

    const botones = marcado.match(/<button[\s\S]*?<\/button>/g) ?? [];
    expect(botones.length).toBeGreaterThan(0);
    for (const boton of botones) {
      expect(boton).not.toMatch(/aprobar/i);
    }
    // Ningún manejador, ni siquiera fuera de un <button>.
    for (const manejador of marcado.match(/on(click|submit)=\{[^}]*\}/g) ?? []) {
      expect(manejador).not.toMatch(/aprobar/i);
    }
    // Y el único verbo que el script llama es cancelar.
    const script = soloCodigo(pagina.slice(0, pagina.lastIndexOf('</script>')));
    expect(script).not.toMatch(/aprobar/i);
    expect(marcado).toMatch(/Cancelar esta acción/);
  });

  it('tampoco hay un proxy que llegue a aprobar', () => {
    expect(proxyLista).not.toMatch(/\/aprobar/);
    expect(proxyCancelar).not.toMatch(/\/aprobar/);
  });

  it('el proxy de cancelar sólo acepta POST, y exige motivo', () => {
    expect(proxyCancelar).toMatch(/export async function POST/);
    expect(proxyCancelar).not.toMatch(/export async function (GET|PUT|DELETE)/);
    expect(proxyCancelar).toMatch(/Falta el motivo/);
  });

  it('quién cancela sale de la sesión, no del navegador', () => {
    // Una cancelación firmada por quien dice el cliente HTTP no prueba nada.
    expect(proxyCancelar).toMatch(/autorDeSesion\(locals\)/);
    expect(proxyCancelar).not.toMatch(/cuerpo\??\.\s*cancelada_por/);
  });

  it('las dos rutas exigen sesión', () => {
    for (const proxy of [proxyLista, proxyCancelar]) {
      expect(proxy).toMatch(/if \(!locals\.user\)/);
    }
  });

  it('la lista no pide los argumentos crudos', () => {
    // El motor ya no los manda; el proxy tampoco los pide ni los reenvía.
    expect(proxyLista).not.toMatch(/argumentos/);
  });
});

describe('cada fila dice lo suficiente para decidir', () => {
  it('traduce la herramienta a lo que haría', () => {
    expect(queHace(accion())).toMatch(/ticket/i);
    expect(queHace({ herramienta: 'promise_payment' })).toMatch(/promesa de pago/i);
  });

  it('una herramienta desconocida no rompe la fila', () => {
    expect(queHace({ herramienta: 'inventada_xyz' })).toContain('inventada_xyz');
    expect(lineaDeAccion({ id: 'x', estado: 'pendiente' }).queHace).toBeTruthy();
  });

  it('dice por qué no se aprueba, y la razón cambia según el tipo', () => {
    const ticket = porQueNoSeAprueba(accion());
    const promesa = porQueNoSeAprueba({ herramienta: 'promise_payment' });
    expect(ticket).not.toBe(promesa);
    expect(ticket).toMatch(/no se puede deshacer|ya existe/i);
    expect(promesa).toMatch(/venci/i);
  });

  it('muestra la antigüedad en palabras', () => {
    expect(antiguedad(accion({ creado_en: '2026-09-01T10:00:00Z' }), AHORA))
      .toBe('hace 19 días');
    expect(antiguedad(accion({ creado_en: '2026-09-20T09:00:00Z' }), AHORA)).toBe('hoy');
    expect(antiguedad(accion({ creado_en: '2026-06-01T10:00:00Z' }), AHORA))
      .toMatch(/meses/);
    expect(antiguedad({ creado_en: null }, AHORA)).toBe('');
  });

  it('la antigüedad NO es lo que la hace inejecutable', () => {
    // Si lo fuera, la regla parecería un plazo que alguien podría estirar. Lo
    // que la hace inejecutable es no tener conversación, y vale igual para
    // una recién creada.
    const reciente = lineaDeAccion(accion({ creado_en: AHORA.toISOString() }), AHORA);
    expect(reciente.esLegado).toBe(true);
    expect(reciente.porQueNo).toBeTruthy();
    expect(reciente.antiguedad).toBe('hoy');
  });

  it('sólo se ofrece cancelar lo que sigue pendiente', () => {
    expect(lineaDeAccion(accion()).puedeCancelarse).toBe(true);
    expect(lineaDeAccion(accion({ estado: 'cancelada' })).puedeCancelarse).toBe(false);
    expect(lineaDeAccion(accion({ estado: 'aprobada' })).puedeCancelarse).toBe(false);
  });

  it('no expone los argumentos aunque llegaran', () => {
    const conPii = accion({ argumentos: { telefono: '573001112233' } });
    expect(JSON.stringify(lineaDeAccion(conPii))).not.toContain('573001112233');
  });
});

describe('el encabezado dice de qué está hecha la lista', () => {
  it('cuenta por tipo, de mayor a menor', () => {
    const muchas = [
      ...Array.from({ length: 34 }, (_, i) => accion({ id: `t${i}` })),
      accion({ id: 'p1', herramienta: 'promise_payment' }),
      accion({ id: 'p2', herramienta: 'promise_payment' })
    ];
    const resumen = resumenPorTipo(muchas);
    expect(resumen[0]).toMatchObject({ herramienta: 'crear_ticket', cuantas: 34 });
    expect(resumen[1]).toMatchObject({ herramienta: 'promise_payment', cuantas: 2 });
    // No son 36 filas iguales: son 34 visitas técnicas y 2 promesas vencidas.
    expect(resumen[0].queHace).not.toBe(resumen[1].queHace);
  });

  it('una lista vacía no rompe nada', () => {
    expect(resumenPorTipo([])).toEqual([]);
    expect(resumenPorTipo()).toEqual([]);
  });
});

describe('la pantalla se relee después de cancelar', () => {
  it('no saca la fila de la lista a mano', () => {
    // Si alguien más la resolvió mientras tanto, la lista tiene que decir la
    // verdad en vez de mostrar el resultado que esta pestaña esperaba.
    const cuerpo = pagina.slice(pagina.indexOf('async function cancelar'));
    expect(cuerpo.slice(0, 900)).toMatch(/await cargar\(\)/);
    expect(cuerpo.slice(0, 900)).not.toMatch(/acciones\s*=\s*acciones\.filter/);
  });
});
