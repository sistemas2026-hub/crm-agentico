import { fail } from '@sveltejs/kit';
import {
  leerCuadrillas,
  crearCuadrilla,
  editarCuadrilla,
  leerJornadaDeCuadrillas,
  leerHistorialDeCuadrillas,
  armarJornada,
  leerZonas,
  crearZona,
  mapearZona,
  leerLocalidades,
  proponerReparto,
  publicarReparto,
  leerPersonasDeCampo,
  crearPersonaDeCampo,
  editarPersonaDeCampo,
  leerConfiguracionDeReparto,
  guardarConfiguracionDeReparto,
  leerHorarioDeCuadrillas,
  guardarHorarioDeCuadrillas,
  leerTiposDeTrabajo,
  clasificarTipoDeTrabajo
} from '$lib/server/v2/cuadrillas.js';
import { leerUbicaciones } from '$lib/server/v2/inventario.js';
import { mensajeDeError } from '$lib/server/v2/mensaje-de-error.js';

/**
 * Cuadrillas — Supervisor NOC.
 *
 * Tercera vista del mismo módulo, no una pantalla suelta: cuelga de
 * /supervisor-noc para que se alcance con las pastillas de arriba, igual que
 * Programación.
 *
 * ABRE EN UN DÍA, SIEMPRE. «La jornada» sin fecha no significa nada —es el
 * mismo criterio que el backend ya impone en programación— así que sin
 * `?dia=` se usa hoy en vez de mostrar «todo».
 */

/** Hoy en formato YYYY-MM-DD, en la zona del servidor. */
function hoy() {
  return new Date().toISOString().slice(0, 10);
}

/** @type {import('./$types').PageServerLoad} */
export async function load({ url, cookies, locals, fetch }) {
  const dia = (url.searchParams.get('dia') ?? '').trim() || hoy();
  const verBajas = url.searchParams.get('bajas') === '1';

  // EL HISTORIAL SE PIDE, NO VIENE SIEMPRE. Es otra pregunta que «armar
  // mañana», y traerlo en cada visita costaría una consulta de hasta tres
  // meses para una pantalla que la mayoría de las veces se abre a asignar.
  // EL REPARTO SE PIDE, NO SE CORRE SOLO. Mirar la pantalla no puede
  // disparar un calculo sobre todas las órdenes pendientes.
  const verReparto = url.searchParams.get('reparto') === '1';

  const verQuien = (url.searchParams.get('quien') ?? '').trim();
  const verCual = (url.searchParams.get('cual') ?? '').trim();
  const desde = (url.searchParams.get('desde') ?? '').trim();
  const hasta = (url.searchParams.get('hasta') ?? '').trim();
  const hayHistorial = Boolean((verQuien || verCual) && desde && hasta);

  // Las cuatro juntas: sin personas no se puede armar una cuadrilla, sin
  // vehículos no se le puede asignar uno, y sin la jornada no se sabe qué
  // hace hoy. Pedirlas en serie sumaría tres esperas que no hacen falta.
  const [cuadrillas, jornada, personas, ubicaciones, historial, zonas, locs,
         reparto, configuracion, tipos, horario] =
    await Promise.all([
      leerCuadrillas({ cookies }, verBajas),
      leerJornadaDeCuadrillas({ cookies }, dia),
      //  PERSONAS DE CAMPO, no cuentas: un auxiliar sin celular no tiene
      //  `Profile` y aun asi integra la cuadrilla. Ver
      //  `campo.cuadrillas.PersonaDeCampo`.
      leerPersonasDeCampo({ cookies }, verBajas),
      leerUbicaciones({ cookies }),
      hayHistorial
        ? leerHistorialDeCuadrillas({ cookies }, {
            desde,
            hasta,
            cuadrilla: verCual,
            profile: verQuien
          })
        : Promise.resolve({ jornadas: [], error: false, motivo: '' }),
      leerZonas({ cookies }),
      // Las localidades viven en el MOTOR, no acá: las arma
      // `localidades.py::sincronizar()` recorriendo el catálogo del
      // proveedor, y su documentación dice que «nunca la escribe una
      // persona». Se ofrecen para elegir, no para teclear.
      leerLocalidades(locals, fetch),
      verReparto
        ? proponerReparto({ cookies }, dia)
        : Promise.resolve({ propuesta: null, error: false, motivo: '' }),
      //  Cómo y a qué hora reparte la empresa. Va en el mismo viaje: sale de
      //  una fila que ya está en la base y no justifica una espera propia.
      leerConfiguracionDeReparto({ cookies }),
      //  Qué labor tiene cada tipo de trabajo. Sin esto no se puede clasificar
      //  nada, y lo que no está clasificado no se reparte.
      leerTiposDeTrabajo({ cookies }),
      //  Cuándo trabajan las cuadrillas (21/10/2026): el Supervisor arma
      //  y despacha con este horario, no con el de atención al cliente.
      leerHorarioDeCuadrillas({ cookies })
    ]);

  const vehiculos = (ubicaciones.ubicaciones ?? []).filter(
    (u) => u.tipo === 'vehiculo'
  );

  return {
    dia,
    verBajas,
    cuadrillas: cuadrillas.cuadrillas,
    jornadas: jornada.jornadas,
    zonas: zonas.zonas,
    reparto: {
      pedido: verReparto,
      propuesta: reparto.propuesta,
      error: reparto.error,
      motivo: reparto.motivo
    },
    localidades: locs.localidades,
    localidadesActualizadoEn: locs.actualizado_en,
    localidadesError: locs.error,
    historial: {
      pedido: hayHistorial,
      desde,
      hasta,
      quien: verQuien,
      cual: verCual,
      jornadas: historial.jornadas,
      error: historial.error,
      motivo: historial.motivo
    },
    tipos: tipos.tipos,
    //  `labores` NO se pasa: la pantalla ya tiene el catálogo y pasarlo
    //  además lo dejaría como dato muerto. El backend lo sigue devolviendo
    //  para quien lo necesite.
    tiposSinClasificar: tipos.sinClasificar,
    reparto_config: configuracion.configuracion,
    repartoConfigError: configuracion.error,
    horario: horario.horario,
    horarioError: horario.error,
    personas: personas.personas,
    //  Las cuentas del equipo que todavia no son persona de campo: se
    //  ofrecen para darlas de alta en un clic, en vez de teclear el nombre
    //  de alguien que el sistema ya conoce.
    cuentasSinPersona: personas.cuentasSinPersona,
    vehiculos,
    // NO SE INVENTA UN CERO CUANDO LA LECTURA FALLÓ. Una empresa sin
    // cuadrillas y una consulta que no respondió se dibujan distinto.
    error: cuadrillas.error || jornada.error || personas.error
  };
}

/** Traduce lo que devuelve el backend a una frase, sin inventar una. */
function mensajeDe(e) {
  //  Buscaba `detail` (DRF) y se perdía `detalle`, que es la clave que usan
  //  los endpoints de campo. El detalle está en `mensaje-de-error.js`.
  return mensajeDeError(e);
}

/**
 * Lo que la persona eligió en un campo del formulario, o `undefined` si no lo
 * tocó y por lo tanto no hay que mandarlo.
 *
 * LO QUE NO SE TOCÓ NO SE MANDA (17/10/2026). El backend escribe cada campo
 * que le llega, y la ficha de cuadrilla mandaba el líder, el vehículo y las
 * notas siempre. Un líder que el selector no ofrecía dejaba el `<select>` sin
 * opción elegida —y un select así no viaja en el formulario—, de modo que
 * volvía como «sin líder» y lo borraba: así perdió el suyo una cuadrilla de
 * Rapilink al marcarle las zonas habituales.
 *
 * Tres casos:
 *   - el campo no vino                      → `undefined`, no se manda;
 *   - vino igual que `<campo>_antes`        → `undefined`, no se manda;
 *   - vino distinto                         → el valor, y vacío es `null`:
 *     «— sin líder —» elegido a propósito sí quita al líder.
 *
 * @param {FormData} f
 * @param {string} campo
 * @returns {string | null | undefined}
 */
function cambioDe(f, campo) {
  if (!f.has(campo)) return undefined;
  const ahora = String(f.get(campo) ?? '').trim();
  const antes = f.get(`${campo}_antes`);
  if (antes !== null && ahora === String(antes).trim()) return undefined;
  return ahora || null;
}

export const actions = {
  cuadrilla: async ({ request, cookies }) => {
    const f = await request.formData();
    const id = String(f.get('cuadrilla_id') ?? '').trim();
    /** @type {Record<string, any>} */
    const cuerpo = {
      nombre: f.get('nombre'),
      // LO HABITUAL (17/10/2026): la lista ENTERA de zonas marcadas, como en
      // la jornada del día; desmarcarlas todas manda una lista vacía.
      zonas_habituales: f.getAll('zona_habitual').map((x) => String(x)).filter(Boolean)
    };
    const labor = String(f.get('labor_habitual') ?? '').trim();
    if (labor) cuerpo.labor_habitual = labor;
    // El líder y el vehículo, SOLO si la persona los cambió. Ver `cambioDe`.
    for (const campo of ['lider', 'vehiculo']) {
      const elegido = cambioDe(f, campo);
      if (elegido !== undefined) cuerpo[campo] = elegido;
    }
    // Las notas, solo si el formulario las trae: la ficha no tiene ese campo,
    // y mandarlas vacías las borraba en cada guardado.
    if (f.has('notas')) cuerpo.notas = String(f.get('notas') ?? '');
    try {
      const r = id
        ? await editarCuadrilla({ cookies }, id, cuerpo)
        : await crearCuadrilla({ cookies }, cuerpo);
      return {
        hecho: id
          ? `${r?.nombre} quedó actualizada.`
          : `${r?.nombre} quedó dada de alta.`
      };
    } catch (e) {
      return fail(409, { error: mensajeDe(e) });
    }
  },

  baja: async ({ request, cookies }) => {
    const f = await request.formData();
    const id = String(f.get('cuadrilla_id') ?? '').trim();
    const activa = String(f.get('activa') ?? '') === '1';
    try {
      const r = await editarCuadrilla({ cookies }, id, { activa });
      return {
        hecho: activa
          ? `${r?.nombre} vuelve a estar activa.`
          : `${r?.nombre} quedó dada de baja. Sus jornadas siguen enteras.`
      };
    } catch (e) {
      return fail(409, { error: mensajeDe(e) });
    }
  },

  /**
   * Publica la propuesta.
   *
   * Recibe las asignaciones que la pantalla mostró, no una fecha: se publica
   * lo que se vio, no lo que el reparto diría ahora.
   */
  publicar: async ({ request, cookies }) => {
    const f = await request.formData();
    /** @type {{ jornada: string, ordenes: string[] }[]} */
    const asignaciones = [];
    for (const par of f.getAll('asignacion')) {
      const [jornada, ...ordenes] = String(par).split('|');
      if (jornada && ordenes.length) asignaciones.push({ jornada, ordenes });
    }
    if (asignaciones.length === 0) {
      return fail(400, { error: 'No hay nada que publicar.' });
    }
    try {
      const r = await publicarReparto({ cookies }, asignaciones);
      const n = r?.publicadas ?? 0;
      const ya = r?.ya_tenian ?? [];
      //  LAS TRES QUE SE ESTABAN CAYENDO ACÁ  --  13/10/2026
      //
      //  `RepartoView.post` nombra cinco cosas y esta capa leía DOS. Las otras
      //  tres se perdían en silencio, y el backend dice por qué las nombra:
      //
      //    sin_nadie_con_cuenta  «Un silencio aca haria creer que se repartio
      //                           todo» -- y era exactamente el silencio que
      //                           producía esta función.
      //    reasignadas           «se nombran porque alguien puede estar
      //                           esperandolas donde estaban»
      //    auxiliares_...        es lo esperado, pero se dice para que nadie
      //                           lo lea como gente perdida
      //
      //  O sea: con dos cuadrillas sin publicar y tres órdenes movidas de
      //  cuadrilla, el mensaje decía «12 órdenes asignadas.» y nada más. Es la
      //  misma falla que `requiere_noc` el 29/09 (CLAUDE.md §6): el backend lo
      //  manda, su prueba pasa, y la capa servidor lo deja caer.
      const sinCuenta = r?.sin_nadie_con_cuenta ?? [];
      const movidas = r?.reasignadas ?? [];
      const auxiliares = r?.auxiliares_sin_asignacion ?? 0;

      const partes = [`${n} ${n === 1 ? 'orden asignada' : 'órdenes asignadas'}.`];
      if (ya.length) {
        partes.push(
          `${ya.length} ya tenía${ya.length === 1 ? '' : 'n'} a alguien y no se tocó: ` +
          `${ya.map((n) => `#${n}`).join(', ')}.`
        );
      }
      if (movidas.length) {
        partes.push(
          //  'cambió' + 'n' da «cambión». El plural es 'cambiaron'.
          `${movidas.length} ${movidas.length === 1 ? 'cambió' : 'cambiaron'} de cuadrilla: ` +
          //  `reasignadas` y `ya_tenian` son NUMEROS de orden (`orden.numero`,
          //  `cuadrillas_views.py:1038` y `:1056`), no textos. Sin el '#' el
          //  mensaje queda «3 cambiaron de cuadrilla: 1001, 1002, 1003.», que
          //  se lee como una cantidad y no como tres identificadores.
          `${movidas.map((n) => `#${n}`).join(', ')}.`
        );
      }
      if (sinCuenta.length) {
        //  Lo más importante del mensaje y lo que faltaba: una cuadrilla en la
        //  que nadie entra al sistema NO recibió nada, y el total de arriba no
        //  lo dice.
        partes.push(
          `Sin publicar por no tener nadie con cuenta: ${sinCuenta.join(', ')}.`
        );
      }
      if (auxiliares) {
        partes.push(
          `${auxiliares} ${auxiliares === 1 ? 'auxiliar' : 'auxiliares'} ` +
          `${auxiliares === 1 ? 'integra' : 'integran'} la cuadrilla sin recibir asignación.`
        );
      }
      return { hecho: partes.join(' ') };
    } catch (e) {
      return fail(409, { error: mensajeDe(e) });
    }
  },

  zona: async ({ request, cookies }) => {
    const f = await request.formData();
    try {
      const r = await crearZona({ cookies }, { nombre: f.get('nombre') });
      return { hecho: `La zona ${r?.nombre} quedó creada.` };
    } catch (e) {
      return fail(409, { error: mensajeDe(e) });
    }
  },

  /**
   * Reemplaza ENTERO el mapeo de una zona.
   *
   * Se manda la lista completa y no un delta: la pantalla tiene el estado
   * entero, y mandar «agregá esta, sacá aquella» obligaría a las dos puntas a
   * estar de acuerdo sobre qué había antes.
   */
  mapeo: async ({ request, cookies }) => {
    const f = await request.formData();
    const id = String(f.get('zona_id') ?? '').trim();
    const localidades = f.getAll('localidad').map((x) => String(x));
    try {
      const r = await mapearZona({ cookies }, id, localidades);
      const n = r?.localidades?.length ?? 0;
      return {
        hecho: `${r?.nombre}: ${n} ${n === 1 ? 'barrio' : 'barrios'}.`
      };
    } catch (e) {
      // 409 es «ese barrio ya está en otra zona», y el mensaje dice en cuál.
      // Se pasa tal cual: sin el nombre hay que salir a buscarlo.
      return fail(409, { error: mensajeDe(e) });
    }
  },

  /**
   * Clasifica un tipo de trabajo.
   *
   * Define qué cuadrillas pueden tomarlo. Vacío es válido: es «volver a sin
   * clasificar», y hace falta para deshacer una clasificación equivocada.
   */
  tipo_labor: async ({ request, cookies }) => {
    const f = await request.formData();
    const id = String(f.get('id') ?? '').trim();
    if (!id) return fail(400, { error: 'Falta el tipo de trabajo.' });
    try {
      const r = await clasificarTipoDeTrabajo(
        { cookies }, id, String(f.get('labor') ?? '')
      );
      return {
        hecho: r?.labor
          ? `${r.nombre}: ${r.labor}.`
          : `${r?.nombre} quedó sin clasificar; sus órdenes no se reparten.`
      };
    } catch (e) {
      return fail(400, { error: mensajeDe(e) });
    }
  },

  /**
   * Cómo y a qué hora reparte la empresa.
   *
   * ENCENDERLO ES UNA DECISIÓN DE OPERACIÓN, no algo que deba pasar porque
   * alguien desplegó una versión — mismo criterio que `RELOJ_HABILITADO` en el
   * motor. Por eso viene apagado de fábrica y se enciende acá.
   */
  reparto_config: async ({ request, cookies }) => {
    const f = await request.formData();
    try {
      /** @type {Record<string, any>} */
      const cuerpo = {
        activo: f.get('activo') === '1',
        hora_local: String(f.get('hora_local') ?? '3'),
        tope_por_cuadrilla: String(f.get('tope_por_cuadrilla') ?? '8'),
        copia_la_jornada: f.get('copia_la_jornada') === '1'
      };
      //  EL CORTE DE RED (19/10/2026), solo si el formulario lo trae, como la
      //  tabla de labores: una pantalla vieja no lo vuelve al de fábrica.
      if (f.has('onus_para_corte_de_red')) {
        cuerpo.onus_para_corte_de_red = String(f.get('onus_para_corte_de_red') ?? '');
      }
      //  LA LABOR DE CADA GRUPO DE CASO (17/10/2026), solo si el formulario
      //  la trae: una pantalla vieja que no tiene esos campos no la borra.
      //  Vacío es «no cuenta», y viaja así.
      const grupos = [
        'falla_de_servicio',
        'trabajo_pedido',
        'instalacion_nueva',
        'obra_de_red'
      ];
      if (grupos.some((g) => f.has(`labor_de_${g}`))) {
        cuerpo.labor_por_grupo = Object.fromEntries(
          grupos
            .filter((g) => f.has(`labor_de_${g}`))
            .map((g) => [g, String(f.get(`labor_de_${g}`) ?? '')])
        );
      }
      //  LOS NOMBRES DE LAS LABORES (20/10/2026), solo si el formulario los
      //  trae. Vacío viaja vacío: es «el de siempre».
      const labores = ['instalacion', 'correctivo', 'trabajos'];
      if (labores.some((l) => f.has(`nombre_labor_${l}`))) {
        cuerpo.nombres_de_labor = Object.fromEntries(
          labores
            .filter((l) => f.has(`nombre_labor_${l}`))
            .map((l) => [l, String(f.get(`nombre_labor_${l}`) ?? '').trim()])
        );
      }
      const r = await guardarConfiguracionDeReparto({ cookies }, cuerpo);
      return {
        hecho: r?.activo
          ? `El ciclo corre todos los días a las ${r.hora_local}:00, ` +
            `con hasta ${r.tope_por_cuadrilla} órdenes por cuadrilla.`
          : 'El ciclo quedó apagado. Las jornadas se arman a mano.'
      };
    } catch (e) {
      return fail(400, { error: mensajeDe(e) });
    }
  },

  /**
   * El horario de las cuadrillas, ENTERO (21/10/2026): la pantalla manda
   * todos los días, y un día sin la casilla «trabaja» viaja cerrado. Los
   * feriados, uno por línea: «AAAA-MM-DD Nombre».
   */
  horario: async ({ request, cookies }) => {
    const f = await request.formData();
    const DIAS = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo'];
    /** @type {Record<string, { abre: string, cierra: string } | null>} */
    const dias = {};
    for (const d of DIAS) {
      dias[d] = f.get(`trabaja_${d}`) === '1'
        ? { abre: String(f.get(`abre_${d}`) ?? ''), cierra: String(f.get(`cierra_${d}`) ?? '') }
        : null;
    }
    const feriados = String(f.get('feriados') ?? '')
      .split('\n')
      .map((l) => l.trim())
      .filter(Boolean)
      .map((l) => {
        const [fecha, ...resto] = l.split(/\s+/);
        return { fecha, nombre: resto.join(' ') };
      });
    try {
      await guardarHorarioDeCuadrillas({ cookies }, {
        zona_horaria: String(f.get('zona_horaria') ?? '').trim(),
        dias,
        feriados,
        hora_de_corte: String(f.get('hora_de_corte') ?? '').trim()
      });
      return { hecho: 'Horario de las cuadrillas guardado. El Supervisor arma y despacha con este.' };
    } catch (e) {
      return fail(400, { error: mensajeDe(e) });
    }
  },

  /**
   * Da de alta a alguien que trabaja en campo.
   *
   * Con `profile` se da de alta una cuenta del equipo; con `nombre`, a un
   * auxiliar que no entra al sistema. Hasta ahora lo segundo no se podía: la
   * lista ofrecía `Profile`, o sea gente con correo y credenciales, y los
   * auxiliares no tienen celular asignado.
   */
  persona_alta: async ({ request, cookies }) => {
    const f = await request.formData();
    try {
      const r = await crearPersonaDeCampo({ cookies }, {
        nombre: String(f.get('nombre') ?? '').trim(),
        profile: String(f.get('profile') ?? '') || undefined,
        rol_habitual: String(f.get('rol_habitual') ?? '').trim() || undefined
      });
      return {
        hecho:
          `${r?.nombre} quedó dado de alta` +
          (r?.tiene_cuenta ? '.' : ', sin cuenta de usuario.'),
        // EL HOMÓNIMO SE AVISA, no se bloquea: dos personas se pueden llamar
        // igual de verdad, y bloquear la segunda obligaría a deformarle el
        // nombre. Quien cargó decide si era un duplicado.
        aviso: r?.homonimos
          ? `Ojo: ya había ${r.homonimos} con ese mismo nombre.`
          : ''
      };
    } catch (e) {
      return fail(400, { error: mensajeDe(e) });
    }
  },

  /**
   * Cambia el nombre, el rol habitual, la cuenta enlazada o la baja.
   *
   * ENLAZAR UNA CUENTA es el caso del auxiliar al que le asignan celular: se
   * le engancha a la MISMA persona, así sus jornadas anteriores siguen siendo
   * suyas. Si naciera una persona nueva, su historial empezaría de cero.
   */
  persona_editar: async ({ request, cookies }) => {
    const f = await request.formData();
    const id = String(f.get('id') ?? '').trim();
    if (!id) return fail(400, { error: 'Falta la persona.' });

    /** @type {Record<string, any>} */
    const cuerpo = {};
    if (f.has('nombre')) cuerpo.nombre = String(f.get('nombre') ?? '').trim();
    if (f.has('rol_habitual'))
      cuerpo.rol_habitual = String(f.get('rol_habitual') ?? '').trim();
    if (f.has('profile')) cuerpo.profile = String(f.get('profile') ?? '') || null;
    // `has` y no el valor: un checkbox sin marcar no manda nada, así que
    // «activa» tiene que llegar explícita para distinguir «dar de baja» de
    // «no se tocó».
    if (f.has('activa')) cuerpo.activa = f.get('activa') === '1';

    try {
      const r = await editarPersonaDeCampo({ cookies }, id, cuerpo);
      return {
        hecho: r?.activa
          ? `${r?.nombre} actualizado.`
          : `${r?.nombre} quedó dado de baja; lo que ya trabajó sigue escrito.`
      };
    } catch (e) {
      // 409 es «esa cuenta ya está en otra persona de campo», y el mensaje lo
      // dice: pasarlo tal cual evita salir a buscar cuál.
      return fail(409, { error: mensajeDe(e) });
    }
  },

  /**
   * Arma el día de una cuadrilla.
   *
   * Manda la jornada ENTERA —labor e integrantes— porque el backend es
   * idempotente por cuadrilla y fecha: reescribe todo con lo que llega. Mandar
   * solo lo que cambió obligaría a leer el estado previo acá y a decidir qué
   * es un cambio, que es justo lo que la idempotencia evita.
   */
  jornada: async ({ request, cookies }) => {
    const f = await request.formData();

    // Vienen como pares paralelos, igual que las líneas del despacho.
    //
    //  SE MANDA `persona`, NO `profile`: el integrante es una persona de
    //  campo, que puede no tener cuenta. El rol se deja vacío cuando no se
    //  elige para que el backend use el habitual de esa persona, en vez de
    //  escribir 'tecnico' sobre lo que ya se sabe de ella.
    const ids = f.getAll('integrante_persona').map((x) => String(x).trim());
    const roles = f.getAll('integrante_rol').map((x) => String(x).trim());
    const integrantes = ids
      .map((persona, i) => ({ persona, rol: roles[i] || '' }))
      .filter((x) => x.persona);

    try {
      const r = await armarJornada({ cookies }, {
        cuadrilla: f.get('cuadrilla'),
        fecha: f.get('fecha'),
        labor: f.get('labor'),
        zonas: f.getAll('zona').map((x) => String(x)).filter(Boolean),
        lider: f.get('lider') || null,
        integrantes,
        notas: f.get('notas') ?? ''
      });
      const cuantos = r?.integrantes?.length ?? 0;
      return {
        hecho:
          `${r?.cuadrilla?.nombre}: ${r?.labor_nombre} el ${r?.fecha}, ` +
          `${cuantos} ${cuantos === 1 ? 'persona' : 'personas'}.`
      };
    } catch (e) {
      // 409 es «esa persona ya está en otra cuadrilla hoy», y el mensaje del
      // backend dice en cuál. Se pasa tal cual: reescribirlo acá perdería el
      // nombre, que es lo único que evita salir a buscarla.
      return fail(409, { error: mensajeDe(e) });
    }
  }
};
