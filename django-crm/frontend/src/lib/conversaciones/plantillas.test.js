/**
 * Lo que el operador ve antes de enviar es lo que el cliente va a recibir.
 *
 * El texto de una plantilla lo aprueba Meta y no se corrige después de
 * enviada: la vista previa es la única oportunidad de mirarlo. Si reparte los
 * valores distinto del envío, el operador aprueba una cosa y el cliente lee
 * otra — y nadie lo nota hasta que alguien recibe el nombre de otra persona.
 *
 * Por eso casi todas las aserciones de acá son sobre el EFECTO (qué texto
 * sale, qué dice cada rótulo) y no sobre si la función existe.
 */
import { describe, it, expect } from 'vitest';
import {
  vistaPrevia, etiquetasDe, cuantosValores, sePuedeEnviar, motivoDeBloqueo
} from './plantillas.js';

/** La ficha tal como la devuelve el motor (nucleo/canales/whatsapp.py). */
const ficha = (extra) => ({
  nombre: 'prueba', estado: 'APPROVED', idioma: 'es', categoria: 'UTILITY',
  encabezado: '', cuerpo: '', formato_variables: '',
  variables_encabezado: [], variables_cuerpo: [], variables: 0, ...extra
});

const soloCuerpo = ficha({
  cuerpo: 'Hola {{1}}, tu factura de {{2}} vence mañana.',
  formato_variables: 'posicional', variables_cuerpo: ['1', '2'], variables: 2
});

const soloEncabezado = ficha({
  encabezado: 'Aviso para {{1}}', cuerpo: 'Revisá tu servicio.',
  formato_variables: 'posicional', variables_encabezado: ['1'], variables: 1
});

const ambos = ficha({
  encabezado: 'Aviso para {{1}}', cuerpo: 'Hola {{1}}, tu factura de {{2}}.',
  formato_variables: 'posicional',
  variables_encabezado: ['1'], variables_cuerpo: ['1', '2'], variables: 3
});

const nombrada = ficha({
  encabezado: 'Aviso para {{full_name}}', cuerpo: 'Hola {{customer_name}}, debés {{amount}}.',
  formato_variables: 'nombrado',
  variables_encabezado: ['full_name'], variables_cuerpo: ['customer_name', 'amount'],
  variables: 3
});

const sinVariables = ficha({ cuerpo: 'Ya te estamos atendiendo.' });

describe('la vista previa muestra el texto completo, encabezado incluido', () => {
  it('el cuerpo posicional se llena', () => {
    expect(vistaPrevia(soloCuerpo, ['Ana', '$80.000']))
      .toBe('Hola Ana, tu factura de $80.000 vence mañana.');
  });

  it('el encabezado también se llena, no se pega crudo', () => {
    const texto = vistaPrevia(soloEncabezado, ['Ana Gómez']);
    expect(texto).toBe('Aviso para Ana Gómez\n\nRevisá tu servicio.');
    // La regresión exacta que se arregló: antes el encabezado se concatenaba
    // sin tocar y el operador veía «Aviso para {{1}}» con el campo ya lleno.
    expect(texto).not.toContain('{{');
  });

  it('con encabezado y cuerpo, cada {{1}} recibe SU valor', () => {
    // La trampa: los dos componentes numeran desde 1 por su cuenta.
    const texto = vistaPrevia(ambos, ['ANA GÓMEZ', 'Ana', '$80.000']);
    expect(texto).toBe('Aviso para ANA GÓMEZ\n\nHola Ana, tu factura de $80.000.');
  });

  it('los parámetros nombrados se llenan por nombre', () => {
    const texto = vistaPrevia(nombrada, ['ANA GÓMEZ', 'Ana', '$80.000']);
    expect(texto).toBe('Aviso para ANA GÓMEZ\n\nHola Ana, debés $80.000.');
  });

  it('una plantilla sin variables se muestra tal cual', () => {
    expect(vistaPrevia(sinVariables, [])).toBe('Ya te estamos atendiendo.');
  });

  it('un campo todavía vacío deja el hueco a la vista', () => {
    // Más honesto que un espacio en blanco donde va a ir el nombre.
    expect(vistaPrevia(soloCuerpo, ['', '$80.000']))
      .toBe('Hola {{1}}, tu factura de $80.000 vence mañana.');
  });

  it('sin plantilla no hay previa', () => {
    expect(vistaPrevia(null, [])).toBe('');
  });
});

describe('el reparto de la previa es el mismo que el del envío', () => {
  // El backend reparte primero el encabezado y después el cuerpo
  // (whatsapp.componentes_de_plantilla). Acá se comprueba que la previa hace
  // lo mismo: el primer valor de la lista va al encabezado.
  it('el primer valor es el del encabezado, no el del cuerpo', () => {
    const texto = vistaPrevia(ambos, ['PRIMERO', 'SEGUNDO', 'TERCERO']);
    expect(texto.startsWith('Aviso para PRIMERO')).toBe(true);
    expect(texto).toContain('Hola SEGUNDO');
    expect(texto).toContain('de TERCERO');
  });

  it('cuenta los valores de los dos componentes', () => {
    expect(cuantosValores(ambos)).toBe(3);
    expect(cuantosValores(soloEncabezado)).toBe(1);
    expect(cuantosValores(sinVariables)).toBe(0);
  });
});

describe('los rótulos dicen la verdad', () => {
  it('un posicional del cuerpo dice qué hueco reemplaza', () => {
    const [primero, segundo] = etiquetasDe(soloCuerpo);
    expect(primero.titulo).toBe('Dato 1');
    expect(primero.reemplaza).toBe('{{1}}');
    expect(segundo.reemplaza).toBe('{{2}}');
  });

  it('un nombrado se rotula con su nombre, que ES la etiqueta', () => {
    const rotulos = etiquetasDe(nombrada);
    expect(rotulos.map((r) => r.titulo))
      .toEqual(['full_name', 'customer_name', 'amount']);
    expect(rotulos.map((r) => r.reemplaza))
      .toEqual(['{{full_name}}', '{{customer_name}}', '{{amount}}']);
    // Y NO el «Dato N» genérico, que era lo que se mostraba antes.
    expect(rotulos.some((r) => /^Dato \d/.test(r.titulo))).toBe(false);
  });

  it('cuando hay dos partes, cada campo dice de cuál es', () => {
    // Sin esto, dos campos seguidos dirían «reemplaza {{1}}» y no habría
    // forma de saber cuál es cuál.
    const rotulos = etiquetasDe(ambos);
    expect(rotulos.map((r) => r.donde)).toEqual(['encabezado', 'cuerpo', 'cuerpo']);
    const primeros = rotulos.filter((r) => r.reemplaza === '{{1}}');
    expect(primeros).toHaveLength(2);
    expect(primeros[0].donde).not.toBe(primeros[1].donde);
  });

  it('cuando todo es cuerpo, no se repite la parte en cada campo', () => {
    expect(etiquetasDe(soloCuerpo).every((r) => r.donde === '')).toBe(true);
  });

  it('hay un rótulo por valor que se pide, ni uno más', () => {
    for (const p of [soloCuerpo, soloEncabezado, ambos, nombrada, sinVariables]) {
      expect(etiquetasDe(p)).toHaveLength(cuantosValores(p));
    }
  });
});

describe('no se ofrece un envío que va a fallar', () => {
  it('faltando un campo, no se puede enviar', () => {
    expect(sePuedeEnviar(soloCuerpo, ['Ana', ''])).toBe(false);
    expect(sePuedeEnviar(soloCuerpo, ['Ana', '   '])).toBe(false);
  });

  it('con todo lleno, sí', () => {
    expect(sePuedeEnviar(soloCuerpo, ['Ana', '$80.000'])).toBe(true);
    expect(sePuedeEnviar(sinVariables, [])).toBe(true);
  });

  it('una plantilla mixta no se puede enviar aunque esté completa', () => {
    // El backend la rechaza con 400: ofrecer el botón sería ofrecer un envío
    // que va a fallar.
    const mixta = ficha({
      cuerpo: 'Hola {{1}}, debés {{amount}}.', formato_variables: 'mixto', variables: 0
    });
    expect(sePuedeEnviar(mixta, [])).toBe(false);
    expect(motivoDeBloqueo(mixta)).toMatch(/mezcla/i);
  });

  it('una plantilla normal no muestra ningún motivo de bloqueo', () => {
    expect(motivoDeBloqueo(soloCuerpo)).toBe('');
    expect(motivoDeBloqueo(null)).toBe('');
  });
});

// =============================================================================
//  El cableado, leído del código
// =============================================================================
//  vitest corre en `node` sin el plugin de Svelte: no puede compilar un
//  `.svelte`. Y la lógica de arriba puede estar perfecta mientras la pantalla
//  sigue usando la vieja — que es exactamente lo que pasaba hasta hoy.
//
//  Las aserciones son sobre el MARCADO VISIBLE, no sobre el archivo entero:
//  buscar una cadena en todo el texto da verde con la copia vieja todavía viva
//  en un comentario o en una función muerta. Ese error ya se cometió tres
//  veces en esta fase.

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const leer = (rel) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), 'utf-8');
const pagina = leer('../../routes/(app)/conversaciones/[id]/+page.svelte');
const composer = leer('./composer/MessageComposer.svelte');

/** Sólo lo que el navegador dibuja: sin <script>, sin <style>, sin comentarios. */
const soloMarcado = (fuente) => {
  const i = fuente.lastIndexOf('</script>');
  return fuente
    .slice(i < 0 ? 0 : i)
    .replace(/<style[\s\S]*?<\/style>/g, '')
    .replace(/<!--[\s\S]*?-->/g, '');
};

describe('la pantalla usa esta lógica y no una copia', () => {
  it('la previa sale de vistaPrevia(), no se arma en la página', () => {
    expect(pagina).toMatch(/vistaPreviaPlantilla\s*=\s*\$derived\(vistaPrevia\(/);
    // La copia vieja reemplazaba {{i+1}} a mano sobre el cuerpo. Si volviera,
    // la previa y el envío podrían separarse otra vez sin que nada avise.
    expect(pagina).not.toMatch(/replaceAll\(`\{\{\$\{i \+ 1\}\}\}`/);
  });

  it('cuántos campos se piden sale de los huecos de los dos componentes', () => {
    expect(pagina).toMatch(/cuantosValores\(p\)/);
    // Antes: `length: p.variables ?? 0`, que ignoraba el encabezado porque el
    // backend tampoco lo contaba.
    expect(pagina).not.toMatch(/length:\s*p\.variables/);
  });

  it('los campos se dibujan con los rótulos resueltos, no con el índice', () => {
    const marcado = soloMarcado(composer);
    expect(marcado).toMatch(/#each etiquetasPlantilla as etiqueta/);
    expect(marcado).toMatch(/etiqueta\.reemplaza/);
    // El rótulo viejo afirmaba que el campo i reemplaza {{i+1}}: falso para
    // un nombrado y falso para cualquier campo del encabezado.
    expect(marcado).not.toMatch(/Dato \{i \+ 1\}/);
    expect(marcado).not.toMatch(/#each valoresPlantilla as _/);
  });

  it('el motivo de bloqueo se muestra, no sólo se calcula', () => {
    expect(soloMarcado(composer)).toMatch(/\{plantillaBloqueada\}/);
  });
});
