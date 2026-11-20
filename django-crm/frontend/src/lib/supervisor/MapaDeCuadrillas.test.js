import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { render } from 'svelte/server';

import MapaDeCuadrillas from './MapaDeCuadrillas.svelte';
import { seDibujaElMapa } from './dia-publicado.js';
import { opcionesDelIcono, tecnicoDePie } from './icono-de-cuadrilla.js';

/**
 * EL MAPA DE CUADRILLAS (31/10/2026).
 *
 * Se mide lo que se dibuja en el servidor: la cabecera, la cuenta de quién
 * reporta, la advertencia de lo que un punto significa y quién quedó sin
 * señal. Leaflet solo corre en el navegador (`onMount`), así que los pines no
 * entran acá — por eso lo que se afirma es lo que el supervisor LEE alrededor
 * del mapa, que es donde está el riesgo de que un punto se lea como un hecho
 * sobre una persona.
 */
const posicion = (extra = {}) => ({
  latitud: 10.9185, longitud: -74.7668, precision_m: 8, bateria: 72,
  minutos: 3, fresca: true, precision_pobre: false,
  medida_en: '2026-10-31T11:20:00-05:00', de: 'Mario Vásquez', ...extra
});
const cuadrilla = (extra = {}) => ({
  jornada: 'j-1', cuadrilla: 'Cuadrilla #5', ordenes: [], posicion: posicion(), ...extra
});
const html = (cuadrillas) => render(MapaDeCuadrillas, { props: { cuadrillas } }).body;

describe('el mapa de cuadrillas', () => {
  it('cuenta cuántas reportan, sobre el total', () => {
    const h = html([
      cuadrilla(),
      cuadrilla({ jornada: 'j-2', cuadrilla: 'Cuadrilla #3', posicion: null }),
      cuadrilla({ jornada: 'j-3', cuadrilla: 'Cuadrilla #1', posicion: null })
    ]);

    expect(h).toContain('1 de 3 reportando');
  });

  it('nombra a las que están sin señal, en vez de dejarlas invisibles', () => {
    const h = html([
      cuadrilla(),
      cuadrilla({ jornada: 'j-2', cuadrilla: 'Cuadrilla #3', posicion: null })
    ]);

    expect(h).toContain('Sin señal:');
    expect(h).toContain('Cuadrilla #3');
    expect(h).not.toMatch(/Sin señal:[^<]*Cuadrilla #5/);
  });

  it('con todas reportando no dice que falte ninguna', () => {
    expect(html([cuadrilla()])).not.toContain('Sin señal:');
  });

  it('ninguna capa pide clave: CARTO sirve las imágenes tachadas', () => {
    //  EL DEFECTO DEL 05/11/2026: CARTO pasó a exigir clave y empezó a
    //  servir cada tile con «API KEY REQUIRED» encima. El mapa quedó
    //  ilegible y ninguna prueba lo vio, porque ninguna miraba de dónde
    //  salen las imágenes. Esri no pide clave --es el proveedor del
    //  satélite, que ya andaba--.
    const fuente = readFileSync(
      'src/lib/supervisor/MapaDeCuadrillas.svelte', 'utf8');
    const urls = fuente.match(/url: '([^']+)'/g) ?? [];

    expect(urls.length).toBe(2);
    for (const u of urls) {
      expect(u).not.toMatch(/cartocdn|mapbox|api[_-]?key|apikey|access_?token/i);
      expect(u).toContain('arcgisonline.com');
    }
  });

  it('ofrece Mapa y Satélite, y arranca en Mapa', () => {
    const h = html([cuadrilla()]);

    expect(h).toContain('>Mapa<');
    expect(h).toContain('>Satélite<');
    //  Y SE VE: un selector escondido pasa un `toContain` y no sirve a
    //  nadie. Se mira la etiqueta entera, no un patrón con el orden de los
    //  atributos adentro -- ese orden lo decide Svelte y ya me engañó una vez.
    const etiqueta = h.match(/<div[^>]*mp-capas[^>]*>/)?.[0] ?? '';
    expect(etiqueta).not.toBe('');
    expect(etiqueta).not.toContain('hidden');
    //  Svelte pone su sufijo PRIMERO: `class="svelte-… on"`.
    expect(h).toMatch(/class="[^"]*\bon"[^>]*>Mapa</);
    expect(h).not.toMatch(/class="[^"]*\bon"[^>]*>Satélite</);
  });

  it('lo que significa un punto queda a un clic, y la línea lo anuncia', () => {
    //  05/11/2026: estaba siempre a la vista y el usuario lo leyó como
    //  ruido encima del seguimiento. Ahora va plegado — pero la línea que
    //  se ve lo nombra, así que nadie tiene que adivinar que está ahí.
    const h = html([cuadrilla()]);

    const resumen = h.match(/<summary[^>]*>([^<]*)</)?.[1] ?? '';
    expect(resumen).toContain('qué significa un punto');
    //  Y el texto completo sigue estando, a un clic.
    expect(h).toContain('no que la persona esté ahí');
    expect(h).toContain('es dónde estuvo, no dónde está');
  });

  it('la línea plegada cuenta lo que falta, sin obligar a abrirla', () => {
    const h = html([
      cuadrilla(),
      cuadrilla({ jornada: 'j-2', cuadrilla: 'Cuadrilla #3', posicion: null })
    ]);

    expect(h.match(/<summary[^>]*>([^<]*)</)?.[1] ?? '').toContain('1 sin señal');
  });

  it('sin ninguna cuadrilla DICE que no hay a quién ubicar, y dibuja la caja', () => {
    //  01/11/2026: el mapa vivía dentro del bloque de cuadrillas, así que un
    //  día sin cuadrillas armadas no lo dibujaba — y desde afuera eso no se
    //  distingue de un mapa roto. Ahora se ve siempre y dice por qué está
    //  vacío.
    for (const vacio of [[], undefined]) {
      const h = html(vacio);
      expect(h).toContain('0 de 0 reportando');
      expect(h).toContain('class="mp-caja');
      expect(h).toContain('No hay cuadrillas armadas para este día');
    }
  });

  it('con cuadrillas NO dice que no haya ninguna', () => {
    expect(html([cuadrilla()])).not.toContain('No hay cuadrillas armadas');
  });
});

describe('el panel de abajo: cuándo se miró y quién reportó', () => {
  it('dice la HORA de la última verificación, no solo que hubo una', () => {
    //  Pedido del usuario: «ver el log de cuándo verificó las ubicaciones,
    //  con su fecha y hora». Una hora sin segundos no sirve acá: la pantalla
    //  pregunta cada 15 s y cuatro verificaciones seguidas mostrarían la
    //  misma cifra, que es indistinguible de una pantalla congelada.
    const h = render(MapaDeCuadrillas, {
      props: {
        cuadrillas: [cuadrilla()],
        verificadoEn: Date.parse('2026-10-31T16:42:07-05:00')
      }
    }).body;

    expect(h).toContain('Ubicaciones verificadas');
    expect(h).toContain('16:42:07');
  });

  it('sin haber verificado todavía NO inventa una hora', () => {
    //  Lo peligroso sería poner la hora de ahora: diría «verificado 16:42»
    //  cuando la primera consulta ni salió, y una pantalla que nunca
    //  respondió se vería al día.
    const h = html([cuadrilla()]);

    expect(h).toContain('Verificando ubicaciones');
    expect(h).not.toContain('Ubicaciones verificadas');
  });

  it('cada cuadrilla trae SU hora: son dos relojes distintos', () => {
    //  EL PUNTO DE TODO EL PANEL. Si se congela el de arriba, el problema es
    //  esta pantalla; si se congela el de una fila, es ese teléfono. Con un
    //  solo número los dos fallos se ven iguales y se llama a la persona
    //  equivocada.
    const h = render(MapaDeCuadrillas, {
      props: {
        cuadrillas: [cuadrilla()],
        verificadoEn: Date.parse('2026-10-31T16:42:07-05:00')
      }
    }).body;

    //  El de la pantalla.
    expect(h).toContain('16:42:07');
    //  Y el del teléfono, que es otro instante: 11:20, de `posicion()`.
    expect(h).toContain('11:20');
  });

  it('la que no reportó SALE en la lista, y su botón no promete nada', () => {
    //  Sin pin en el mapa y sin fila acá, una cuadrilla sin señal
    //  desaparecería de la pantalla: nadie echa de menos lo que no ve.
    const h = html([
      cuadrilla(),
      cuadrilla({ jornada: 'j-2', cuadrilla: 'Cuadrilla #3', posicion: null })
    ]);

    expect(h).toContain('Cuadrilla #3');
    //  Su botón va deshabilitado: uno que no responde al clic, sin
    //  explicación, se lee como pantalla rota.
    const suBoton = h.match(/<button[^>]*>(?:(?!<\/button>)[\s\S])*?Cuadrilla #3[\s\S]*?<\/button>/)?.[0] ?? '';
    expect(suBoton).not.toBe('');
    expect(suBoton).toContain('disabled');
    expect(suBoton).toContain('sin señal');
  });

  it('la que sí reportó tiene su botón HABILITADO para acercar', () => {
    //  El otro borde: si todo saliera deshabilitado, el test de arriba
    //  pasaría igual y el botón no serviría para nada.
    const h = html([cuadrilla()]);

    const suBoton = h.match(/<button[^>]*>(?:(?!<\/button>)[\s\S])*?Cuadrilla #5[\s\S]*?<\/button>/)?.[0] ?? '';
    expect(suBoton).not.toBe('');
    expect(suBoton).not.toContain('disabled');
    //  Y dice a qué sirve, para quien no adivine que la fila es un botón.
    expect(suBoton).toContain('Acercar el mapa a Cuadrilla #5');
  });

  it('sin cuadrillas no dibuja un panel vacío', () => {
    const h = html([]);

    expect(h).not.toContain('Verificando ubicaciones');
    expect(h).not.toContain('Ubicaciones verificadas');
  });
});

describe('la ruta se VE, no solo existe', () => {
  //  EL DEFECTO DEL 06/11/2026. Las dos puntas estaban dibujadas y la línea
  //  entre ellas también, pero era un trazo marrón al 45% de opacidad: sobre
  //  el mapa claro se leía y sobre el satélite --una foto aérea de un
  //  barrio-- desaparecía. El usuario mandó la captura con el técnico, la
  //  casa, y nada en medio.
  //
  //  Leaflet solo corre en el navegador, así que esto no puede mirar píxeles.
  //  Lee el código del dibujo, que es donde vive la decisión, y afirma lo que
  //  la hace visible: que haya un trazo blanco debajo y que el de arriba sea
  //  opaco. Es una guarda de contraste, no de píxeles -- y lo dice.
  const fuente = readFileSync(
    'src/lib/supervisor/MapaDeCuadrillas.svelte', 'utf8');
  const dibujo = fuente.slice(
    fuente.indexOf('if (q.une'), fuente.indexOf('if (!c.posicion)'));

  it('lleva un halo blanco debajo, que la recorta contra cualquier fondo', () => {
    expect(dibujo).toContain("color: '#fff'");
    //  Más ancho que el trazo de color: si fuera igual o menor, no asomaría.
    const blanco = Number(dibujo.match(/color: '#fff', weight: (\d+)/)?.[1] ?? 0);
    const encima = Number(dibujo.match(/color: '#b45309', weight: (\d+)/)?.[1] ?? 0);
    expect(blanco).toBeGreaterThan(encima);
    expect(encima).toBeGreaterThan(0);
  });

  it('el trazo de color va OPACO: una ruta a medio tono se lee como aproximada', () => {
    //  Y esta no lo es: une dos puntos medidos. El 0.45 de antes decía lo
    //  contrario de lo que el dato merece.
    expect(dibujo).toMatch(/color: '#b45309'[^}]*opacity: 1\b/);
    expect(dibujo).not.toContain('opacity: 0.45');
  });

  it('sigue siendo punteada: no es la ruta por la calle', () => {
    //  Es una recta entre dos puntos, no el camino que va a manejar. Una
    //  línea llena se leería como un recorrido calculado.
    expect(dibujo).toContain('dashArray');
  });

  it('y SOLO se dibuja con las dos puntas', () => {
    //  La regla que no cambia: con una sola sería una ruta hacia un lugar que
    //  nadie midió. Ver `destino-de-la-orden.js`.
    expect(dibujo).toContain('q.une && q.vehiculo && q.destino');
  });
});

describe('cuándo se dibuja el mapa', () => {
  it('solo si lo que se mira es hoy', () => {
    expect(seDibujaElMapa('2026-11-01', '2026-11-01')).toBe(true);
  });

  it('un día pasado NO lo dibuja: no hay posiciones de ese día', () => {
    expect(seDibujaElMapa('2026-10-25', '2026-11-01')).toBe(false);
  });

  it('un día futuro tampoco', () => {
    expect(seDibujaElMapa('2026-11-05', '2026-11-01')).toBe(false);
  });

  it('si la carga falló y los dos quedan vacíos, tampoco: no es que sea hoy', () => {
    //  Cuando el load no pudo leer, `dia` y `hoy` vienen los dos en ''. Sin
    //  la guarda, '' === '' daba true y el mapa se dibujaba sobre nada.
    expect(seDibujaElMapa('', '')).toBe(false);
    expect(seDibujaElMapa(null, null)).toBe(false);
  });

  it('sin saber cuál es hoy no se dibuja, en vez de adivinar', () => {
    //  EL DEFECTO DEL 01/11/2026: la pantalla comparaba contra una zona
    //  horaria escrita a mano y el mapa no aparecía nunca.
    for (const sinHoy of ['', null, undefined]) {
      expect(seDibujaElMapa('2026-11-01', sinHoy)).toBe(false);
    }
  });
});


describe('el técnico en el mapa', () => {
  it('el color dice lo mismo que decía el punto: lleno es de ahora', () => {
    const fresca = tecnicoDePie('#1f7a3d', true);
    const vieja = tecnicoDePie('#6b7280', false);

    //  TIÑE EL CHALECO ENTERO, su frente y su costado, no una franja suelta.
    expect(fresca.match(/#1f7a3d/g)?.length ?? 0).toBeGreaterThanOrEqual(2);
    expect(fresca).toContain('opacity:1');
    //  Lo viejo se ve viejo: es dónde estuvo, no dónde está.
    expect(vieja).toContain('opacity:0.5');
  });

  it('es un dibujo, no una imagen: nítido en cualquier zoom', () => {
    const svg = tecnicoDePie('#1f7a3d', true);
    expect(svg.startsWith('<svg')).toBe(true);
    expect(svg).toContain('viewBox="0 0 34 46"');
    expect(svg).not.toContain('<img');
    //  LO QUE LO HACE VISIBLE sobre el satélite, que es el motivo del
    //  cambio: el halo blanco que lo recorta y el casco, que no aparece en
    //  una foto aérea de un barrio.
    expect(svg).toContain('stroke="#fff"');
    expect(svg).toContain('#f2b705');
  });

  it('el punto cae en los pies, no en el centro del dibujo', () => {
    //  Si se ancla al medio, el vehículo queda corrido respecto de la calle
    //  y el supervisor lo lee como que está en otro lado.
    const o = opcionesDelIcono('#1f7a3d', true);
    expect(o.iconAnchor).toEqual([17, 42]);
    expect(o.iconSize).toEqual([34, 46]);
    expect(o.className).toBe('mp-vehiculo');
  });
});
