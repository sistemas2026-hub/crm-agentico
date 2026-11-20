import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';
import { tenantDeLaSesion } from '$lib/server/v2/tenant.js';
import { leerAreas } from '$lib/server/v2/areas.js';
import { leerAccionesDeAgentes } from '$lib/server/v2/acciones-de-agente.js';

/**
 * Lo que la oficina virtual necesita saber ANTES de dibujarse: quién existe.
 *
 * Dos cosas y nada más —el inventario de agentes y las áreas configuradas— y
 * las dos degradan: si el motor no responde, la sala se dibuja igual con el
 * puesto vacío y lo dice. Una pantalla de operación que desaparece cuando falla
 * una consulta es peor que una que admite que le falta un dato; es el mismo
 * criterio del centro de mando que ya está en producción.
 *
 * SOLO VIAJA LO QUE SE USA
 * El panorama del motor trae mucho más por agente —carga, conversaciones, qué
 * está haciendo—. Acá se recorta a tres campos: nombre, área y cargo. No es
 * ahorro de ancho de banda: es que lo que no llega al navegador no se puede
 * filtrar por accidente, y esta pantalla solo necesita saber quién se sienta
 * dónde. La actividad llega después por el flujo incremental, que ya tiene su
 * propia lista blanca.
 *
 * LA EMPRESA SALE DE LA SESIÓN
 * `tenantDeLaSesion`, en el servidor y nunca del cliente. Mismo patrón que el
 * resto: que el navegador pudiera elegir de qué empresa es la oficina
 * convertiría esta pantalla en un visor de operaciones ajenas.
 *
 * @type {import('./$types').PageServerLoad}
 */
export async function load(event) {
  //  El rol de quien mira (12/11/2026): la ficha de un puesto ofrece el
  //  tablero del Supervisor solo a quien su servidor deja pasar.
  return { ...(await leerOficina(event)), rol: event.locals.profile?.role ?? null };
}

/** @param {{ locals: App.Locals, fetch: typeof globalThis.fetch }} event */
async function leerOficina({ locals, fetch }) {
  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = await tenantDeLaSesion(locals, fetch);
  if (!baseUrl || !tenant) {
    return {
      agentes: [],
      areas: [],
      organizacion: null,
      acciones: null,
      //  DOS CAUSAS DISTINTAS, DOS MENSAJES. Decirle «falta
      //  PRIVATE_ASISTENTE_URL» a quien abre la oficina de una empresa que no
      //  tiene asistente es nombrarle una variable de entorno que no puede
      //  tocar y, peor, culpar al despliegue de algo que es un hecho del
      //  producto. Pasó el 31/10/2026: la pantalla decía eso y mandó a buscar
      //  un problema de configuración donde lo que había era una empresa sin
      //  asistente.
      error: !baseUrl
        ? 'No hay un asistente desplegado para esta instalación.'
        : 'Esta empresa todavía no tiene un asistente configurado.'
    };
  }

  //  QUE PUEDE HACER HOY CADA AGENTE. Degrada a `null`: la oficina se dibuja
  //  igual sin esto, y la ficha dice que no lo pudo leer en vez de mostrar una
  //  lista vacia, que se leeria como «no puede hacer nada».
  //
  //  EN PARALELO DE VERDAD (12/11/2026). El comentario decia «va en paralelo»
  //  y las tres lecturas iban una detras de otra: la pantalla esperaba la
  //  suma de las tres. Ahora salen juntas y espera a la mas lenta.
  const [{ areas }, acciones, centro] = await Promise.all([
    leerAreas(locals, fetch),
    leerAccionesDeAgentes(locals, fetch),
    fetch(`${baseUrl}/centro-mando?tenant=${encodeURIComponent(tenant)}&ventana=10`, {
      headers: headersMotor()
    }).then(
      (resp) => ({ resp, err: null }),
      (err) => ({ resp: null, err })
    )
  ]);

  try {
    if (centro.err) throw centro.err;
    const resp = /** @type {Response} */ (centro.resp);
    const datos = await resp.json();
    if (!resp.ok) {
      return {
        agentes: [],
        areas: areas.map((/** @type {any} */ a) => a?.nombre ?? a).filter(Boolean),
        organizacion: null,
        acciones,
        error: datos.error || 'No se pudo leer el inventario de agentes'
      };
    }
    return {
      agentes: (datos.agentes || []).map((/** @type {any} */ a) => ({
        nombre: a.nombre,
        area: a.area ?? null,
        cargo: a.cargo ?? null,
        //  A quién atiende este agente. Viaja como INFORMACIÓN para la ficha,
        //  no como criterio de quién se sienta: medido el 30/10/2026, su valor
        //  por defecto en el esquema es `colaborador`, así que los tres roles
        //  que no lo declaran salen idénticos a los dos que sí. Separa 4 de 5,
        //  no distingue a un agente ejecutable de una capacidad asignada a una
        //  persona. Quién ocupa cada puesto se declara en la organización.
        orientado_a: a.orientado_a ?? null
      })),
      areas: areas.map((/** @type {any} */ a) => a?.nombre ?? a).filter(Boolean),
      //  LA ESTRUCTURA DE LA EMPRESA, tal como el motor la sirve: sus pisos,
      //  sus departamentos, sus espacios y de donde salio (`origen`).
      //
      //  Viaja entera y sin recortar, al contrario que `agentes`. No es una
      //  excepcion a <<solo viaja lo que se usa>>: aqui TODO se usa, porque
      //  esto es justamente lo que la pantalla tiene que dibujar. Lo que se
      //  recorta de los agentes es su actividad, que llega por el flujo
      //  incremental con su propia lista blanca.
      //
      //  `null` cuando no se pudo leer, y eso NO se rellena con nada. Esta
      //  pantalla dibujaba seis departamentos escritos en el frontend; si
      //  ahora cayera a una estructura inventada cuando el motor no responde,
      //  estaria afirmando como es una empresa que no pudo consultar.
      organizacion: datos.organizacion ?? null,
      acciones,
      error: null
    };
  } catch (/** @type {any} */ err) {
    return {
      agentes: [],
      areas: areas.map((/** @type {any} */ a) => a?.nombre ?? a).filter(Boolean),
      organizacion: null,
      acciones: null,
      error: err?.message || 'No se pudo contactar al asistente'
    };
  }
}
