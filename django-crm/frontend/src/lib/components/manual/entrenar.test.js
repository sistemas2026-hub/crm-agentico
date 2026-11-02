import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { codigoDesde, huecosDe, siguienteNumero, textoDelHueco } from './entrenar.js';

/**
 * EL CICLO «se equivocó → lo corrijo → sé si mejoró»  --  02/11/2026
 * ==================================================================
 *
 * Se afirma sobre el EFECTO de cada función, y en la última sección sobre el
 * código fuente del proxy, que es lo único que este harness puede alcanzar:
 * `vitest.config.js` no compila `.svelte` ni resuelve `$env/dynamic/private`,
 * así que un `+server.js` no se puede importar. Una guarda estática sobre ese
 * archivo es menos de lo que uno querría y mucho más que nada: el defecto que
 * cierra —el rol volviendo a quedar fijo en `cliente_final`— es exactamente
 * el que se ve leyendo esa línea.
 */

describe('siguienteNumero · cambiar de agente abre otra conversación', () => {
  //  La sesión del motor ES el número. Una conversación abierta restaura su
  //  `rol_efectivo` y PISA el rol que mande la pantalla (api.py:875), así que
  //  sin número nuevo el selector mostraría un agente y hablaría con otro.
  it('sube en uno, conservando el largo', () => {
    expect(siguienteNumero('3001234567')).toBe('3001234568');
  });

  it('arrastra el acarreo sin perder dígitos', () => {
    expect(siguienteNumero('3001239999')).toBe('3001240000');
  });

  it('ignora lo que no sea dígito', () => {
    expect(siguienteNumero('+57 300 123-4567')).toBe('573001234568');
  });

  it('sin número usable devuelve uno válido, nunca vacío', () => {
    //  Vacío haría que el motor abriera una sesión sin identificador y el
    //  simulador quedaría hablando solo.
    expect(siguienteNumero('')).toBe('3001234567');
    expect(siguienteNumero('   ')).toBe('3001234567');
    expect(siguienteNumero(null)).toBe('3001234567');
    expect(siguienteNumero('abc')).toBe('3001234567');
  });

  it('nunca devuelve el mismo número que entró', () => {
    //  La garantía entera de esta función en una línea.
    for (const n of ['3001234567', '1', '999', '3159999999']) {
      expect(siguienteNumero(n)).not.toBe(n);
    }
  });
});

describe('codigoDesde · el código de la habilidad sale del nombre', () => {
  const ahora = () => 1762000000000;

  it('convierte el nombre a un código legible', () => {
    expect(codigoDesde('Cambiar la contraseña del wifi', ahora)).toMatch(
      /^cambiar_la_contrasena_del_wifi_[a-z0-9]{4}$/
    );
  });

  it('saca los acentos y la eñe, que el código no los lleva', () => {
    expect(codigoDesde('Instalación ÑANDÚ', ahora)).toMatch(/^instalacion_nandu_/);
  });

  it('nunca queda vacío ni empieza o termina en guión bajo', () => {
    for (const entrada of ['', '   ', '!!!', '— · —', null]) {
      const codigo = codigoDesde(entrada, ahora);
      expect(codigo).toMatch(/^correccion_[a-z0-9]{4}$/);
    }
  });

  it('dos nombres iguales en momentos distintos no chocan', () => {
    //  El motor rechaza el código repetido con un error que desde una
    //  burbuja no es accionable; el sufijo es lo que lo evita.
    const a = codigoDesde('Reiniciar la ONT', () => 1762000000000);
    const b = codigoDesde('Reiniciar la ONT', () => 1762000999999);
    expect(a).not.toBe(b);
  });

  it('recorta un nombre largo sin pasarse del campo', () => {
    //  `codigo` se guarda con [:60] del lado del motor; la base queda en 40
    //  más el sufijo, así que nunca se trunca algo ya generado.
    const codigo = codigoDesde('a'.repeat(200), ahora);
    expect(codigo.length).toBeLessThanOrEqual(45);
  });
});

describe('textoDelHueco · la señal en palabras', () => {
  it('distingue la que responde «¿mejoró?» de las otras dos', () => {
    //  `habilidad_insuficiente` significa "ya se le enseñó algo y escaló
    //  igual". Es la única que dice que una corrección NO alcanzó, y por eso
    //  no puede leerse igual que "escaló por X".
    const texto = textoDelHueco({
      senal: 'habilidad_insuficiente',
      codigo_habilidad: 'cambiar_wifi',
      motivo: 'sin_procedimiento'
    });
    expect(texto).toContain('cambiar_wifi');
    expect(texto).toContain('escaló igual');
  });

  it('dice cuando el agente admitió no saber', () => {
    expect(textoDelHueco({ senal: 'sin_procedimiento' })).toBe(
      'dijo no tener el procedimiento'
    );
  });

  it('para una escalada repetida nombra el motivo, legible', () => {
    expect(textoDelHueco({ senal: 'escalada_repetida', motivo: 'falla_de_servicio' })).toBe(
      'escaló por falla de servicio'
    );
  });

  it('sin datos no inventa ni rompe', () => {
    expect(textoDelHueco({})).toBe('escaló por el mismo motivo');
    expect(textoDelHueco(null)).toBe('escaló por el mismo motivo');
  });
});

describe('huecosDe · cada agente ve lo suyo', () => {
  const porRol = { ventas: [{ senal: 'sin_procedimiento' }], soporte: [] };

  it('devuelve los del rol pedido', () => {
    expect(huecosDe(porRol, 'ventas')).toHaveLength(1);
  });

  it('un rol sin huecos devuelve vacío, no los de otro', () => {
    expect(huecosDe(porRol, 'soporte')).toEqual([]);
    expect(huecosDe(porRol, 'facturacion')).toEqual([]);
  });

  it('sin datos devuelve vacío en vez de romper la pantalla', () => {
    expect(huecosDe(null, 'ventas')).toEqual([]);
    expect(huecosDe(undefined, 'ventas')).toEqual([]);
  });
});

describe('el simulador no vuelve a fijar el agente', () => {
  //  GUARDA ESTÁTICA, y se dice que lo es. El proxy no se puede importar acá
  //  (`$env/dynamic/private`), así que se lee su fuente. Lo que cierra es el
  //  defecto concreto que existía hasta el 02/11/2026: `rol: 'cliente_final'`
  //  escrito en el cuerpo del POST, que hacía imposible probar desde ninguna
  //  pantalla un agente recién creado.
  const fuente = readFileSync(
    resolve(process.cwd(), 'src/routes/api/simulador-whatsapp/+server.js'),
    'utf-8'
  );

  it('el rol que se le manda al motor sale del pedido, no de una constante', () => {
    expect(fuente).toContain('rol: rolElegido');
    expect(fuente).not.toContain("rol: 'cliente_final'");
  });

  it('y vacío sigue cayendo en cliente_final, que es su caso normal', () => {
    //  El simulador existe para probar el canal de WhatsApp: quitarle ese
    //  default lo rompería para su uso de siempre.
    expect(fuente).toMatch(/rolElegido\s*=\s*String\(rol \|\| ''\)\.trim\(\) \|\| 'cliente_final'/);
  });
});

describe('el asistente no se bloquea por un perfil que el CRM no resuelve', () => {
  //  GUARDA ESTÁTICA, y se dice que lo es: `+server.js` importa
  //  `$env/dynamic/private` y este harness no lo resuelve.
  //
  //  EL DEFECTO QUE CIERRA, medido en producción el 02/11/2026: `/profile/`
  //  del CRM devuelve 403 «Organization context is required» con el mismo JWT
  //  que el resto de las rutas acepta, y el proxy cortaba ahí con un 502. Era
  //  la razón por la que esta pantalla no se usaba. No es nuevo ni es de acá:
  //  `lib/server/v2/inventario.js:185` documenta el mismo 403 en otra ruta.
  //
  //  Con un agente elegido el `profile_id` ni se manda --es excluyente con
  //  `rol` del lado del motor-- así que pedirlo era frenar por un dato que no
  //  se iba a usar.
  const fuente = readFileSync(
    resolve(process.cwd(), 'src/routes/api/asistente/+server.js'),
    'utf-8'
  );

  it('con agente elegido manda rol, y sin agente manda profile_id', () => {
    expect(fuente).toContain("...(rolPedido ? { rol: rolPedido } : { profile_id: profileId })");
  });

  it('el fallo de /profile/ solo corta cuando NO hay agente elegido', () => {
    //  Si alguien saca el `if (!rolPedido)`, vuelve a cortar siempre.
    const bloque = fuente.slice(fuente.indexOf('apiRequest'));
    expect(bloque).toMatch(/catch[\s\S]{0,120}if \(!rolPedido\) \{/);
  });

  it('sin agente elegido y sin perfil, NO sigue', () => {
    //  La otra mitad: el profile_id es lo que decide a qué datos llega el
    //  turno. Dejarlo pasar vacío sería peor que el 502.
    expect(fuente).toContain('if (!profileId && !rolPedido)');
  });

  it('el nombre cae a la sesión, nunca al cliente', () => {
    expect(fuente).toContain("(locals.user.name || locals.user.email || '').trim()");
    //  Si viniera del navegador, cualquiera firmaría con el nombre de otro.
    expect(fuente).not.toMatch(/nombreColaborador\s*=\s*(cuerpo|body)\./);
  });

  it('elegir agente sigue siendo solo de ADMIN', () => {
    expect(fuente).toContain("locals.profile?.role === 'ADMIN'");
    expect(fuente).toMatch(/if \(rolPedido && !esAdmin\)/);
  });
});
