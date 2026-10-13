import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * PUBLICAR EL REPARTO, Y LO QUE EL MENSAJE TIENE QUE DECIR.
 *
 * `RepartoView.post` (`campo/cuadrillas_views.py:1066`) nombra CINCO cosas, y
 * cada comentario del backend explica por qué no alcanza con el total:
 *
 *   publicadas                 cuántas quedaron asignadas
 *   ya_tenian                  «si no, la cuenta no cuadra con lo que se vio»
 *   sin_nadie_con_cuenta       «Un silencio aca haria creer que se repartio todo»
 *   auxiliares_sin_asignacion  «se dice para que nadie lo lea como gente perdida»
 *   reasignadas                «alguien puede estar esperandolas donde estaban»
 *
 * Esta capa leía DOS. Las otras tres se caían en silencio: con dos cuadrillas
 * sin publicar porque nadie en ellas entra al sistema, el mensaje decía
 * «12 órdenes asignadas.» y nada más. Es la misma falla que `requiere_noc` el
 * 29/09/2026 (CLAUDE.md §6) — el backend lo manda, su prueba pasa, y el salto
 * al frontend lo deja caer, con todo verde. `cuadrillas.js` no tenía ninguna
 * prueba, igual que 37 módulos más de `lib/server/v2/`.
 *
 * Lo que se afirma es el EFECTO: que cada una de las cinco APAREZCA en el
 * texto que lee una persona. No que la variable exista — una afirmación así
 * sobrevivió intacta a una inversión completa de la conducta (§6).
 */

const apiRequest = vi.fn();
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: (...a) => apiRequest(...a) }));

const { actions } = await import('./+page.server.js');

/** Un submit de la pantalla: `asignacion` repetida, `jornada|orden|orden`. */
function submitPublicar(pares) {
  const f = new FormData();
  for (const p of pares) f.append('asignacion', p);
  return /** @type {any} */ ({
    request: { formData: async () => f },
    cookies: { get: () => 'token' }
  });
}

const UNA = ['jo-1|o-1|o-2'];

/* `ya_tenian`, `reasignadas` -> NUMEROS de orden (`orden.numero`);
   `sin_nadie_con_cuenta` -> NOMBRES de cuadrilla (`cuadrilla.nombre`);
   `auxiliares_sin_asignacion` -> un entero. Visto en
   `campo/cuadrillas_views.py:1012-1056`. Si acá fueran cadenas ya formateadas,
   la prueba pasaría con un mensaje que en producción diría otra cosa. */

beforeEach(() => {
  apiRequest.mockReset();
});

describe('publicar', () => {
  it('el total solo, cuando no hay nada más que decir', async () => {
    apiRequest.mockResolvedValue({
      publicadas: 2, ya_tenian: [], sin_nadie_con_cuenta: [],
      auxiliares_sin_asignacion: 0, reasignadas: []
    });

    const r = await actions.publicar(submitPublicar(UNA));
    expect(r.hecho).toBe('2 órdenes asignadas.');
  });

  it('una cuadrilla sin nadie con cuenta se NOMBRA: el total no lo dice', async () => {
    apiRequest.mockResolvedValue({
      publicadas: 12, ya_tenian: [], reasignadas: [],
      auxiliares_sin_asignacion: 0,
      sin_nadie_con_cuenta: ['Cuadrilla 3', 'Cuadrilla 4']
    });

    const r = await actions.publicar(submitPublicar(UNA));
    //  LA MUTACIÓN QUE ESTA PRUEBA MATA. Antes el mensaje era «12 órdenes
    //  asignadas.» y dos cuadrillas no habían recibido nada.
    expect(r.hecho).toContain('Cuadrilla 3');
    expect(r.hecho).toContain('Cuadrilla 4');
    expect(r.hecho).toContain('12 órdenes asignadas.');
  });

  it('las que cambiaron de cuadrilla se nombran, no se cuentan y punto', async () => {
    apiRequest.mockResolvedValue({
      publicadas: 5, ya_tenian: [], sin_nadie_con_cuenta: [],
      auxiliares_sin_asignacion: 0,
      reasignadas: [1001, 1002, 1003]
    });

    const r = await actions.publicar(submitPublicar(UNA));
    //  Alguien puede estar esperándolas donde estaban: un número sin los
    //  identificadores no le sirve a quien tiene que avisar.
    expect(r.hecho).toContain('#1001');
    expect(r.hecho).toContain('#1003');
    expect(r.hecho).toContain('3 cambiaron de cuadrilla');
  });

  it('un auxiliar sin asignación se explica, para que no se lea como gente perdida', async () => {
    apiRequest.mockResolvedValue({
      publicadas: 4, ya_tenian: [], sin_nadie_con_cuenta: [],
      reasignadas: [], auxiliares_sin_asignacion: 2
    });

    const r = await actions.publicar(submitPublicar(UNA));
    expect(r.hecho).toContain('2 auxiliares');
    expect(r.hecho).toContain('sin recibir asignación');
  });

  it('las cinco juntas caben en el mismo mensaje', async () => {
    apiRequest.mockResolvedValue({
      publicadas: 9,
      ya_tenian: [900],
      sin_nadie_con_cuenta: ['Cuadrilla 5'],
      auxiliares_sin_asignacion: 1,
      reasignadas: [901, 902]
    });

    const r = await actions.publicar(submitPublicar(UNA));
    //  Ninguna tapa a otra: el día que las cinco pasen a la vez, se ven las
    //  cinco. Un mensaje que elige una sola es el mismo silencio de antes.
    for (const pedazo of ['9 órdenes', '#900', '#901', '#902', 'Cuadrilla 5',
                          '1 auxiliar']) {
      expect(r.hecho).toContain(pedazo);
    }
    //  Y el singular/plural de cada una, que es lo que hace que el texto se
    //  lea como escrito por alguien y no como una plantilla.
    expect(r.hecho).toContain('ya tenía a alguien');
    expect(r.hecho).toContain('integra la cuadrilla');
  });

  it('sin asignaciones no se llama al backend', async () => {
    const r = await actions.publicar(submitPublicar([]));
    expect(r.status).toBe(400);
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it('un par sin órdenes se descarta: publicaría una jornada vacía', async () => {
    const r = await actions.publicar(submitPublicar(['jo-1']));
    expect(r.status).toBe(400);
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it('manda las asignaciones que la pantalla mostró, no una fecha', async () => {
    apiRequest.mockResolvedValue({ publicadas: 3 });
    await actions.publicar(submitPublicar(['jo-1|o-1|o-2', 'jo-2|o-3']));

    const [, opciones] = apiRequest.mock.calls[0];
    //  Entre mirar y publicar entran tickets nuevos: recalcular por fecha
    //  publicaría algo que nadie revisó.
    expect(opciones.body.asignaciones).toEqual([
      { jornada: 'jo-1', ordenes: ['o-1', 'o-2'] },
      { jornada: 'jo-2', ordenes: ['o-3'] }
    ]);
  });

  it('un choque del backend se muestra tal como lo explica', async () => {
    //  `apiRequest` lanza un Error con `.body`, no con `.data`.
    apiRequest.mockRejectedValue(
      Object.assign(new Error('Esa jornada ya se publicó.'),
                    { status: 409, body: { detail: 'Esa jornada ya se publicó.' } })
    );
    const r = await actions.publicar(submitPublicar(UNA));
    expect(r.status).toBe(409);
    expect(r.data.error).toBe('Esa jornada ya se publicó.');
  });

  it('también lee `detalle`, que es la clave de los endpoints de campo', async () => {
    apiRequest.mockRejectedValue(
      Object.assign(new Error('NO_SE_PUDO_ASIGNAR'),
                    { status: 409, body: { error: 'NO_SE_PUDO_ASIGNAR',
                                           detalle: 'Nadie de esa cuadrilla tiene cuenta.' } })
    );
    const r = await actions.publicar(submitPublicar(UNA));
    expect(r.data.error).toBe('Nadie de esa cuadrilla tiene cuenta.');
  });
});

/* ------------------------------------------------------------------ *
 *  EL INTERRUPTOR DEL CICLO DE LA MADRUGADA
 * ------------------------------------------------------------------ */

describe('reparto_config', () => {
  const submitConfig = (campos) => {
    const f = new FormData();
    for (const [k, v] of Object.entries(campos)) f.set(k, v);
    return /** @type {any} */ ({
      request: { formData: async () => f },
      cookies: { get: () => 'token' }
    });
  };

  beforeEach(() => {
    apiRequest.mockReset();
  });

  it('encenderlo manda activo=true, con la hora y el tope', async () => {
    apiRequest.mockResolvedValue({ activo: true, hora_local: 3, tope_por_cuadrilla: 10 });
    const r = await actions.reparto_config(
      submitConfig({ activo: '1', hora_local: '3', tope_por_cuadrilla: '10', copia_la_jornada: '1' })
    );

    const [, opciones] = apiRequest.mock.calls[0];
    expect(opciones.body.activo).toBe(true);
    expect(opciones.body.copia_la_jornada).toBe(true);
    //  El mensaje repite lo que el SERVIDOR guardó, no lo que se mandó: si el
    //  backend ajustara el tope, la pantalla diría el valor real.
    expect(r.hecho).toContain('3:00');
    expect(r.hecho).toContain('10 órdenes por cuadrilla');
  });

  it('una casilla sin marcar es false, no «ausente»', async () => {
    apiRequest.mockResolvedValue({ activo: false });
    const r = await actions.reparto_config(submitConfig({ hora_local: '3' }));

    const [, opciones] = apiRequest.mock.calls[0];
    //  `undefined` dejaría el valor anterior en el backend: apagar el ciclo
    //  tiene que apagarlo, no omitirlo.
    expect(opciones.body.activo).toBe(false);
    expect(opciones.body.copia_la_jornada).toBe(false);
    expect(r.hecho).toContain('apagado');
  });

  it('apagado no promete una hora', async () => {
    apiRequest.mockResolvedValue({ activo: false, hora_local: 3, tope_por_cuadrilla: 8 });
    const r = await actions.reparto_config(submitConfig({ hora_local: '3' }));
    //  Decir «corre a las 3:00» con el ciclo apagado es afirmar algo que no
    //  va a pasar.
    expect(r.hecho).not.toContain('3:00');
  });
});
