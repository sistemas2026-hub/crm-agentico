import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * LA LISTA DE TAREAS DELEGADAS LLEGA HASTA LA PANTALLA.
 *
 * POR QUÉ ESTA PRUEBA EXISTE, Y POR QUÉ NO ALCANZA LA DEL BACKEND
 * ---------------------------------------------------------------
 * `operaciones/tests/test_la_pantalla_dice_que_esta_delegado.py` ya mide que la
 * vista devuelve `delegaciones` con las dos precondiciones resueltas, y corre
 * contra Postgres real. Lo que NO puede ver es este salto: CLAUDE.md §6 lo
 * cuenta con dos cicatrices del 29/09/2026 —`requiere_noc` viajaba bien desde
 * el backend, con su prueba pasando, y la capa servidor del frontend lo dejaba
 * caer—. Esta ruta es exactamente ese salto.
 *
 * Es una ruta de paso y por eso la prueba es corta: afirma que el objeto viaja
 * COMPLETO. Un `json({ configurado, efectivo, ... })` que enumerara campos
 * —que es cómo se escriben la mayoría de estas rutas— dejaría `delegaciones`
 * afuera sin dar ningún error, y la pantalla mostraría «0 de 0 tareas
 * delegadas» con total aplomo.
 *
 * LO QUE NO CUBRE: no compila el `.svelte`, así que no ve qué dibuja la
 * pantalla. Cubre hasta la respuesta de la ruta, que es donde se perdieron los
 * dos campos de la historia.
 */

const apiRequest = vi.fn();
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: (...a) => apiRequest(...a) }));

const { GET } = await import('./+server.js');

/**
 * LA FORMA REAL DEL BACKEND, no una inventada.
 * `operaciones/views.py::AutonomiaSupervisorView.get` -> Response({...}) y
 * `_delegaciones` para cada entrada.
 */
const RESPUESTA = {
  configurado: 3,
  efectivo: 1,
  recortado: true,
  motivo: 'freno puesto a mano',
  interruptor_permite: false,
  techo_de_la_etapa: 3,
  niveles: [{ nivel: 1, etiqueta: 'Recomendar' }],
  historial: [],
  delegaciones: [
    {
      clave: 'pasar_a_despacho_segun_las_reglas',
      nombre: 'Pasar casos a Despacho solo, según las cinco reglas',
      que_hace: 'Después de leer un ticket…',
      que_no_hace: 'NO crea la orden de trabajo…',
      exige_nivel: 3,
      delegada: true,
      delegada_en: '2026-10-20T14:00:00+00:00',
      con_estas_palabras: 'pasá solo los que las reglas dejen pasar',
      nivel_alcanza: false,
      la_despierta_algo: { si: false, por_que: 'nada la va a correr sola todavía…' }
    },
    {
      clave: 'revisar_solo_con_cada_actualizacion',
      nombre: 'Revisar solo, una vez por hora',
      que_hace: 'Mira lo que cambió…',
      que_no_hace: 'No actúa…',
      exige_nivel: 1,
      delegada: false,
      delegada_en: null,
      con_estas_palabras: '',
      nivel_alcanza: true,
      la_despierta_algo: { si: true, por_que: '' }
    }
  ]
};

const JEFA = {
  user: { id: 'u1' },
  profile: { role: 'ADMIN' }
};

function pedir(locals = JEFA) {
  //  EL CAST ES PARA 'svelte-check', no para vitest: el `RequestEvent` real
  //  tiene once propiedades mas y un `Cookies` completo, y ninguna la usa esta
  //  ruta. El archivo vecino (`chat/server.test.js`) arrastra ese mismo error
  //  ocho veces; preferible no sumar una novena.
  return GET(/** @type {any} */ ({ cookies: {}, locals }));
}

describe('la ruta de alcance', () => {
  beforeEach(() => {
    apiRequest.mockReset();
    apiRequest.mockResolvedValue(RESPUESTA);
  });

  it('deja pasar las delegaciones con sus dos precondiciones', async () => {
    const cuerpo = await (await pedir()).json();

    //  EL EFECTO, no la presencia de la clave: lo que la pantalla usa para
    //  decidir el color del punto son estos tres campos, y los tres tienen que
    //  llegar con su valor.
    const [primera, segunda] = cuerpo.delegaciones;
    expect(primera.delegada).toBe(true);
    expect(primera.nivel_alcanza).toBe(false);
    expect(primera.la_despierta_algo.si).toBe(false);
    expect(primera.la_despierta_algo.por_que).toBeTruthy();
    expect(primera.con_estas_palabras).toBe('pasá solo los que las reglas dejen pasar');

    //  Y la que NO está delegada también viaja: media utilidad de la pantalla
    //  está en ver lo que falta encender.
    expect(segunda.delegada).toBe(false);
    expect(cuerpo.delegaciones).toHaveLength(2);
  });

  it('no pierde ninguna clave del backend', async () => {
    const cuerpo = await (await pedir()).json();
    //  Comparación de conjuntos y no campo por campo: un endpoint que mañana
    //  agregue un dato y una ruta que enumere campos se separan en silencio.
    expect(Object.keys(cuerpo).sort()).toEqual(Object.keys(RESPUESTA).sort());
  });

  it('a quien no es de gestión no le dice nada', async () => {
    const r = await pedir({ user: { id: 'u2' }, profile: { role: 'USER' } });
    expect(r.status).toBe(403);
    //  Y el backend no se llama: la puerta corta antes.
    expect(apiRequest).not.toHaveBeenCalled();
  });
});
