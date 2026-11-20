import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { codigoDesde, huecosDe, textoDelHueco } from './entrenar.js';

/**
 * EL CICLO «se equivocó → lo corrijo → sé si mejoró»  --  02/11/2026
 * ==================================================================
 *
 * Se afirma sobre el EFECTO de cada función, y en las últimas secciones
 * sobre el código fuente de los proxies, que es lo único que este harness
 * puede alcanzar: `vitest.config.js` no compila `.svelte` ni resuelve
 * `$env/dynamic/private`, así que un `+server.js` no se puede importar. Una
 * guarda estática es menos de lo que uno querría y mucho más que nada: los
 * defectos que cierra se ven leyendo esas líneas.
 *
 * El 02/11/2026 el usuario decidió que el simulador de WhatsApp vuelva a
 * fijar `cliente_final`: entrenar se hace en /asistente, y el simulador
 * existe para probar ESE canal. Las guardas de aquel selector y del número
 * que subía al cambiar de agente se quitaron con él -- una prueba de algo
 * que ya no existe no es cobertura, es ruido que alguien va a creerse.
 */


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

describe('cuando guardar falla, el motivo no se pierde', () => {
  //  La primera version mostraba siempre «No se pudo guardar.»: si la
  //  respuesta no traía `error`, o no era JSON, no quedaba con qué
  //  diagnosticar. El código HTTP es lo que distingue «no sos admin» (403)
  //  de «ya existe ese código» (400) de «el motor no está» (502).
  const fuente = readFileSync(
    resolve(process.cwd(), 'src/lib/components/manual/CorregirAgente.svelte'),
    'utf-8'
  );

  it('el mensaje lleva el código HTTP', () => {
    expect(fuente).toContain('No se pudo guardar (HTTP ${resp.status})');
  });

  it('y lee el cuerpo como texto antes de parsearlo', () => {
    //  Con `resp.json()` a secas, una respuesta HTML --un 500 de SvelteKit--
    //  lanza y el cuerpo se pierde entero.
    expect(fuente).toContain('const crudo = await resp.text()');
    expect(fuente).not.toMatch(/await resp\.json\(\)\.catch/);
  });
});

describe('«✎ Corregir» aparece en toda respuesta del agente', () => {
  //  EL DEFECTO QUE CIERRA, encontrado el 02/11/2026 leyendo por qué no se
  //  veía en Conversaciones: el botón se agregó DENTRO del pie de la burbuja
  //  sin sumarse a la condición que decide si ese pie existe. Resultado: solo
  //  aparecía cuando algo MÁS ya había puesto un pie ahí --el estado de
  //  entrega, o el botón de buen ejemplo con casos cargados--. En una
  //  conversación sin casos del manual no se veía nunca.
  //
  //  Guarda estática: el harness no compila `.svelte`. Lo que se afirma es la
  //  condición, que es donde vivía el bug.
  const hilo = readFileSync(
    resolve(process.cwd(), 'src/lib/conversaciones/messages/MessageThread.svelte'),
    'utf-8'
  );

  it('toda respuesta del agente tiene pie, sin depender de nada más', () => {
    expect(hilo).toContain(
      "!!(m.sinEntregar || m.estado_entrega === 'fallido' || m.rol === 'assistant')"
    );
  });

  it('y ya no exige casos del manual ni estado de entrega', () => {
    //  Si alguien repone la condición vieja, esto se pone rojo.
    expect(hilo).not.toMatch(/m\.rol === 'assistant' && \(m\.estado_entrega \|\| casos\.length/);
  });

  it('el botón está dentro de ese pie y le llega el rol de la conversación', () => {
    expect(hilo).toMatch(/<CorregirAgente[\s\S]{0,80}rol=\{rolActivo\}/);
  });

  it('sin rol el botón se ve apagado, no deja escribir y fallar al final', () => {
    const corregir = readFileSync(
      resolve(process.cwd(), 'src/lib/components/manual/CorregirAgente.svelte'),
      'utf-8'
    );
    expect(corregir).toContain('disabled={guardando || !rol}');
  });
});
