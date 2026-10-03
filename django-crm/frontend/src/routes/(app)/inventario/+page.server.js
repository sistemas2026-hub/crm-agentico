import { fail } from '@sveltejs/kit';
import {
  leerExistencias,
  leerCatalogo,
  leerUbicaciones,
  leerSerie,
  leerPersonas,
  registrarEntrada,
  despachar,
  recibirDevolucion,
  // Fase 2
  leerLibre,
  leerReservas,
  reservar,
  liberarReserva,
  trasladar,
  leerConteos,
  abrirConteo,
  anotarConteo,
  cerrarConteo,
  // Fase 3
  leerProveedores,
  crearProveedor,
  registrarCompra,
  leerValorizacion,
  leerReporte,
  // Plantillas de kit
  leerPlantillas,
  crearPlantilla,
  editarPlantilla,
  desactivarPlantilla,
  // El maestro del catálogo
  leerMateriales,
  crearMaterial,
  editarMaterial,
  subirImagenMaterial,
  quitarImagenMaterial,
} from '$lib/server/v2/inventario.js';

/**
 * El inventario de la empresa.
 *
 * LAS TRES LECTURAS VAN EN PARALELO porque ninguna depende de la otra, y la
 * pantalla no sirve con dos de tres: sin catálogo no se puede despachar, sin
 * ubicaciones no se sabe de dónde, sin existencias no se sabe cuánto hay.
 *
 * Y NINGUNA INVENTA UN CERO: cada lectura devuelve `error` aparte de su forma
 * vacía. Una bodega que dice «0 conectores» porque la API falló manda a un
 * técnico a la calle sin material, y eso no se distingue de una bodega vacía si
 * la pantalla no lo dice.
 *
 * @type {import('./$types').PageServerLoad}
 */
export async function load({ url, cookies }) {
  // `apiRequest` lee el token de aca. `locals` no tiene cookies en un load.
  const ctx = { cookies };
  const serie = (url.searchParams.get('serie') ?? '').trim();
  const ver = (url.searchParams.get('ver') ?? 'existencias').trim();
  const ubicacionPedida = (url.searchParams.get('ubicacion') ?? '').trim();

  const [existencias, catalogo, ubicaciones, personas] = await Promise.all([
    leerExistencias(ctx),
    leerCatalogo(ctx),
    leerUbicaciones(ctx),
    leerPersonas(ctx),
  ]);

  // La ubicación de trabajo: la pedida, o la primera interna. Las pestañas de
  // reservas, conteo y valorización son SIEMPRE sobre una ubicación concreta —
  // un «reservado» global no se puede despachar desde ningún lado.
  const internas = (ubicaciones.ubicaciones ?? []).filter(
    (u) => u.tipo === 'bodega' || u.tipo === 'vehiculo'
  );
  const elegida = ubicacionPedida || internas[0]?.id || '';

  // LO QUE SE CARGA BAJO PEDIDO, y por qué no todo siempre: cargar la
  // valorización y los tres reportes en cada visita costaría cinco consultas más
  // para pintar pestañas que nadie abrió.
  /** @type {Record<string, any>} */
  const extra = {};
  if (ver === 'reservas' && elegida) {
    const [libre, reservas] = await Promise.all([
      leerLibre(ctx, elegida),
      leerReservas(ctx, elegida, url.searchParams.get('todas') === '1'),
    ]);
    extra.libre = libre.materiales;
    extra.reservas = reservas.reservas;
    extra.errorExtra = libre.error || reservas.error;
  } else if (ver === 'despacho') {
    // Solo acá: son la ayuda para armar una entrega, y cargarlas en las otras
    // nueve pestañas costaría una consulta que nadie mira.
    const p = await leerPlantillas(ctx, true);
    extra.plantillas = p.plantillas;
    extra.errorExtra = p.error;
  } else if (ver === 'materiales') {
    const m = await leerMateriales(ctx);
    extra.catalogo = m.materiales;
    extra.errorExtra = m.error;
  } else if (ver === 'conteo') {
    const conteos = await leerConteos(ctx);
    extra.conteos = conteos.conteos;
    extra.errorExtra = conteos.error;
  } else if (ver === 'compras') {
    const [provs, val] = await Promise.all([
      leerProveedores(ctx),
      elegida ? leerValorizacion(ctx, elegida) : Promise.resolve(null),
    ]);
    extra.proveedores = provs.proveedores;
    extra.valorizacion = val;
    extra.errorExtra = provs.error || Boolean(val?.error);
  } else if (ver === 'reportes') {
    const cual = (url.searchParams.get('de') ?? 'consumo').trim();
    const desde = (url.searchParams.get('desde') ?? '').trim();
    const hasta = (url.searchParams.get('hasta') ?? '').trim();
    const rep = await leerReporte(ctx, cual, desde, hasta);
    extra.reporte = { de: cual, filas: rep.filas, desde, hasta };
    extra.errorExtra = rep.error;
  }

  const consulta = serie ? await leerSerie(ctx, serie) : null;

  return {
    metricas: contar(existencias),
    existencias: existencias.ubicaciones,
    materiales: catalogo.materiales,
    ubicaciones: ubicaciones.ubicaciones,
    personas: personas.personas,
    ubicacionElegida: elegida,
    ver,
    serieConsultada: serie,
    consulta,
    ...extra,
    // Un solo lugar decide si la pantalla puede confiar en lo que muestra.
    noSePudoLeer:
      existencias.error || catalogo.error || ubicaciones.error || personas.error,
  };
}

/**
 * Las líneas de material de un formulario multilínea.
 *
 * Los campos llegan repetidos --tres `material`, tres `cantidad`, tres `serie`--
 * y `getAll` los devuelve en orden, así que la posición es lo que las une. Se
 * descartan las que no dicen de qué material son: una fila vacía que el operador
 * agregó y no llenó no es una línea, y mandarla haría fallar el lote entero.
 *
 * @param {FormData} f
 */
function leerLineas(f) {
  const materiales = f.getAll('material');
  const cantidades = f.getAll('cantidad');
  const series = f.getAll('serie');
  const esperados = f.getAll('esperado');
  const costos = f.getAll('costo_unitario');
  const lineas = [];
  for (let i = 0; i < materiales.length; i += 1) {
    const material = String(materiales[i] ?? '').trim();
    if (!material) continue;
    const esperado = String(esperados[i] ?? '').trim();
    lineas.push({
      material,
      cantidad: cantidades[i] ?? '',
      serie: String(series[i] ?? '').trim(),
      // Solo viaja si quien recibe lo declaró. Sin esto el backend NO adivina un
      // faltante: devolver parte de lo que se tiene es legítimo.
      ...(esperado ? { esperado } : {}),
      // Y el costo solo lo usa la compra. `null` cuando no se sabe: cero diría
      // que el material es gratis, que es distinto de no conocer su precio.
      ...(String(costos[i] ?? '').trim()
        ? { costo_unitario: String(costos[i]).trim() }
        : {})
    });
  }
  return lineas;
}

/**
 * Los indicadores de la cabecera, calculados de lo que ya se leyó.
 *
 * NINGUNO SE INVENTA, Y SI LA LECTURA FALLÓ NO HAY NÚMERO. Cuando `existencias`
 * viene con error, sus listas están vacías: contar sobre eso daría «0 ubicaciones,
 * 0 alertas», que es la peor respuesta posible — un cero tranquilizador sobre un
 * dato que no se pudo leer. En ese caso se devuelve `null` y la pantalla muestra
 * `—`.
 *
 * El diseño pide un cuarto indicador, «equipos en tránsito», que no sale de acá:
 * haría falta contar los activos serializados que están en la custodia de un
 * técnico, y esa consulta todavía no existe en la API.
 *
 * @param {any} existencias
 */
function contar(existencias) {
  if (existencias?.error) return { ubicaciones: null, materiales: null, negativos: null };

  const bloques = existencias?.ubicaciones ?? [];
  const materiales = new Set();
  let negativos = 0;
  for (const bloque of bloques) {
    for (const m of bloque.materiales ?? []) {
      materiales.add(m.material_id);
      if (Number(m.existencia) < 0) negativos += 1;
    }
  }
  return { ubicaciones: bloques.length, materiales: materiales.size, negativos };
}

/**
 * Las tres acciones que mueven material. Cada una devuelve el mensaje del
 * backend tal cual: el 409 del despacho imposible dice DÓNDE está el aparato, y
 * reescribirlo con un «no se pudo» perdería justo el dato que resuelve el caso.
 *
 * @type {import('./$types').Actions}
 */
export const actions = {
  entrada: async ({ request, cookies }) => {
    const f = await request.formData();
    try {
      await registrarEntrada({ cookies }, {
        material: f.get('material'),
        cantidad: f.get('cantidad'),
        serie: f.get('serie') ?? '',
        ubicacion_destino: f.get('ubicacion_destino'),
        origen_ref: f.get('origen_ref') ?? '',
      });
      return { hecho: 'La entrada quedó registrada.' };
    } catch (e) {
      return fail(400, { error: mensajeDe(e) });
    }
  },

  despacho: async ({ request, cookies }) => {
    const f = await request.formData();
    // VARIAS LÍNEAS EN UN DESPACHO, que es como se entrega un kit de verdad: el
    // técnico se lleva conectores, metros de fibra y una ONT en el mismo acta.
    // El servicio del backend ya recibía una lista; la pantalla mandaba una sola
    // línea y obligaba a repetir el acta, que además es la clave idempotente --
    // el segundo despacho con la misma acta habría devuelto el primero sin
    // agregar nada.
    const lineas = leerLineas(f);
    if (lineas.length === 0) {
      return fail(400, { error: 'Un despacho sin líneas no es un despacho.' });
    }
    try {
      const r = await despachar({ cookies }, {
        ubicacion_origen: f.get('ubicacion_origen'),
        profile_destino: f.get('profile_destino'),
        acta: f.get('acta') ?? '',
        lineas,
      });
      return { hecho: `Despachado. Acta: ${r?.acta || r?.entrega}` };
    } catch (e) {
      return fail(409, { error: mensajeDe(e) });
    }
  },

  devolucion: async ({ request, cookies }) => {
    const f = await request.formData();
    const lineas = leerLineas(f);
    if (lineas.length === 0) {
      return fail(400, { error: 'Hace falta decir qué material volvió.' });
    }
    try {
      const r = await recibirDevolucion({ cookies }, {
        profile_origen: f.get('profile_origen'),
        ubicacion_destino: f.get('ubicacion_destino'),
        notas: f.get('notas') ?? '',
        referencia: f.get('referencia') ?? '',
        lineas,
      });
      const abiertas = r?.incidencias ?? [];
      if (abiertas.length) {
        // La diferencia se DICE. Un 201 silencioso sobre una devolución que no
        // cuadra es esconder justo lo que hay que mirar.
        return {
          hecho: 'La devolución quedó registrada.',
          incidencias: abiertas,
        };
      }
      return { hecho: 'La devolución quedó registrada.' };
    } catch (e) {
      return fail(409, { error: mensajeDe(e) });
    }
  },

  // --- Fase 2 -------------------------------------------------------------

  reservar: async ({ request, cookies }) => {
    const f = await request.formData();
    try {
      const r = await reservar({ cookies }, {
        ubicacion: f.get('ubicacion'),
        material: f.get('material'),
        cantidad: f.get('cantidad'),
        serie: f.get('serie') ?? '',
        // Para que trabajo se aparta. Vacio es el caso normal --una reserva
        // contra la bodega-- y por eso se manda '' en vez de omitirlo: el
        // backend distingue "no viene" de "viene vacio" sin ambiguedad.
        orden_numero: f.get('orden_numero') ?? '',
        vence_en: f.get('vence_en') || null,
        motivo: f.get('motivo') ?? '',
      });
      return { hecho: `Reservado. Quedan ${r?.libre_ahora} libres.` };
    } catch (e) {
      // 409: el dato está bien, el material no alcanza. El mensaje del backend
      // trae los tres números (hay, comprometido, libre) y por eso viaja entero.
      return fail(409, { error: mensajeDe(e) });
    }
  },

  liberar: async ({ request, cookies }) => {
    const f = await request.formData();
    try {
      const r = await liberarReserva(
        { cookies }, String(f.get('reserva')), String(f.get('motivo') ?? '')
      );
      return { hecho: `Reserva liberada. Quedan ${r?.libre_ahora} libres.` };
    } catch (e) {
      return fail(400, { error: mensajeDe(e) });
    }
  },

  traslado: async ({ request, cookies }) => {
    const f = await request.formData();
    try {
      const lineas = leerLineas(f);
      if (lineas.length === 0) {
        return fail(400, { error: 'Un traslado sin líneas no mueve nada.' });
      }
      await trasladar({ cookies }, {
        ubicacion_origen: f.get('ubicacion_origen'),
        ubicacion_destino: f.get('ubicacion_destino'),
        motivo: f.get('motivo') ?? '',
        referencia: f.get('referencia') ?? '',
        lineas,
      });
      return { hecho: 'El traslado quedó registrado.' };
    } catch (e) {
      return fail(409, { error: mensajeDe(e) });
    }
  },

  abrirConteo: async ({ request, cookies }) => {
    const f = await request.formData();
    try {
      const r = await abrirConteo({ cookies }, String(f.get('ubicacion')));
      return { hecho: 'Conteo abierto. Anotá lo que vayas contando.', conteo: r?.id };
    } catch (e) {
      return fail(409, { error: mensajeDe(e) });
    }
  },

  anotarConteo: async ({ request, cookies }) => {
    const f = await request.formData();
    try {
      await anotarConteo({ cookies }, String(f.get('conteo')), {
        material: f.get('material'),
        cantidad: f.get('cantidad'),
        motivo: f.get('motivo') ?? '',
      });
      return { hecho: 'Anotado.', conteo: String(f.get('conteo')) };
    } catch (e) {
      return fail(409, { error: mensajeDe(e) });
    }
  },

  cerrarConteo: async ({ request, cookies }) => {
    const f = await request.formData();
    try {
      const r = await cerrarConteo({ cookies }, String(f.get('conteo')));
      return {
        hecho: `Conteo cerrado. ${r?.ajustes ?? 0} ajuste(s) escritos.`,
        // Las líneas viajan enteras, las que cuadraron incluidas: un conteo que
        // solo muestra diferencias no deja ver cuánto se revisó.
        lineasConteo: r?.lineas ?? [],
      };
    } catch (e) {
      return fail(409, { error: mensajeDe(e) });
    }
  },

  // --- Fase 3 -------------------------------------------------------------

  proveedor: async ({ request, cookies }) => {
    const f = await request.formData();
    try {
      const r = await crearProveedor({ cookies }, {
        nombre: f.get('nombre'),
        identificacion: f.get('identificacion') ?? '',
        contacto: f.get('contacto') ?? '',
      });
      return {
        hecho: r?.creado
          ? `Proveedor «${r.nombre}» creado.`
          : `«${r?.nombre}» ya existía: se usa el que había.`,
      };
    } catch (e) {
      return fail(400, { error: mensajeDe(e) });
    }
  },

  material: async ({ request, cookies }) => {
    const f = await request.formData();
    const id = String(f.get('material_id') ?? '').trim();
    // El formulario manda los campos bloqueados igual; el servidor los acepta
    // mientras no cambien y los rechaza si cambian. La regla vive allá, no acá:
    // deshabilitar un campo en la pantalla no protege de un PATCH a mano.
    const cuerpo = {
      codigo: f.get('codigo'),
      nombre: f.get('nombre'),
      clase: f.get('clase'),
      unidad: f.get('unidad'),
      categoria: f.get('categoria') ?? ''
    };
    try {
      const r = id
        ? await editarMaterial({ cookies }, id, cuerpo)
        : await crearMaterial({ cookies }, cuerpo);
      return {
        hecho: id
          ? `El material ${r?.codigo} quedó actualizado.`
          : `El material ${r?.codigo} quedó dado de alta.`
      };
    } catch (e) {
      return fail(409, { error: mensajeDe(e) });
    }
  },

  materialImagen: async ({ request, cookies }) => {
    const f = await request.formData();
    const id = String(f.get('material_id') ?? '').trim();
    const archivo = f.get('imagen');
    try {
      if (!archivo || typeof archivo === 'string' || archivo.size === 0) {
        // Sin archivo, el botón es el de quitar: el mismo formulario sirve para
        // las dos cosas y así no hay dos rutas para una foto.
        await quitarImagenMaterial({ cookies }, id);
        return { hecho: 'La foto se quitó. El material queda como estaba.' };
      }
      const datos = new FormData();
      datos.append('imagen', archivo);
      await subirImagenMaterial({ cookies }, id, datos);
      return { hecho: 'La foto quedó guardada.' };
    } catch (e) {
      return fail(409, { error: mensajeDe(e) });
    }
  },

  materialEstado: async ({ request, cookies }) => {
    const f = await request.formData();
    const activo = String(f.get('activo')) === 'true';
    try {
      const r = await editarMaterial({ cookies }, String(f.get('material_id')), {
        activo
      });
      return {
        hecho: activo
          ? `${r?.codigo} vuelve a ofrecerse en las operaciones.`
          : `${r?.codigo} ya no se ofrece en operaciones nuevas. No se borró: sigue explicando los movimientos que lo usaron.`
      };
    } catch (e) {
      return fail(409, { error: mensajeDe(e) });
    }
  },

  plantilla: async ({ request, cookies }) => {
    const f = await request.formData();
    const id = String(f.get('plantilla') ?? '').trim();
    // Las líneas llegan con el mismo formato que las de un despacho, así que
    // las lee la misma función. La plantilla ignora `serie`: no fija aparatos.
    const lineas = leerLineas(f).map((l) => ({
      material: l.material,
      cantidad: l.cantidad
    }));
    const cuerpo = {
      nombre: f.get('nombre'),
      descripcion: f.get('descripcion') ?? '',
      lineas
    };
    try {
      const r = id
        ? await editarPlantilla({ cookies }, id, cuerpo)
        : await crearPlantilla({ cookies }, cuerpo);
      return { hecho: `La plantilla «${r?.nombre}» quedó guardada.` };
    } catch (e) {
      return fail(409, { error: mensajeDe(e) });
    }
  },

  plantillaBaja: async ({ request, cookies }) => {
    const f = await request.formData();
    try {
      await desactivarPlantilla({ cookies }, String(f.get('plantilla')));
      return {
        hecho: 'La plantilla ya no se ofrece. No se borró: sigue explicando los despachos que la usaron.'
      };
    } catch (e) {
      return fail(400, { error: mensajeDe(e) });
    }
  },

  compra: async ({ request, cookies }) => {
    const f = await request.formData();
    try {
      const lineas = leerLineas(f);
      if (lineas.length === 0) {
        return fail(400, { error: 'Una compra sin líneas no es una compra.' });
      }
      await registrarCompra({ cookies }, {
        ubicacion_destino: f.get('ubicacion_destino'),
        proveedor: f.get('proveedor') || null,
        referencia: f.get('referencia') ?? '',
        moneda: f.get('moneda') || 'COP',
        lineas,
      });
      return { hecho: 'La compra quedó registrada y el material entró.' };
    } catch (e) {
      return fail(409, { error: mensajeDe(e) });
    }
  },
};

/**
 * El texto que el backend mandó, no una reescritura.
 *
 * `apiRequest` mete el cuerpo del error en el mensaje cuando puede; si no,
 * queda el genérico. Preferir el del backend importa porque ahí está el dato
 * útil: «la serie X figura en la Custodia de Juan» resuelve el caso, y
 * «no se pudo despachar» obliga a investigar de cero.
 *
 * @param {any} e
 */
function mensajeDe(e) {
  const crudo = String(e?.body?.detail ?? e?.message ?? e ?? '');
  const limpio = crudo.replace(/^Error \d+:\s*/, '').trim();
  return limpio || 'No se pudo completar la operación.';
}
