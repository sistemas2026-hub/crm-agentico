/**
 * Configuracion del asistente: el puente entre el CRM y el motor.
 *
 * Server-only. El resto de `$lib/server/v2/` habla con Django; esto habla con
 * crm-agentico (`PRIVATE_ASISTENTE_URL`), que es otro servicio en la misma red
 * interna. El tenant sale del entorno del servidor y nunca del cliente, igual
 * que en `/api/agentes` y `/api/simulador-whatsapp`: quien pide no elige de
 * que empresa es la configuracion que va a leer o escribir.
 *
 * POR QUE `leer` NO LANZA
 * -----------------------
 * El hub de configuracion (`/settings`) hace un `Promise.all` de una docena de
 * cargas. Si esta lanzara cuando el motor esta caido -o cuando ni siquiera hay
 * asistente desplegado, que es el caso de cualquier instalacion del CRM sin
 * este producto- se caeria la pagina entera de configuracion, y el sintoma
 * seria "no puedo entrar a ajustes" en vez de "el asistente no responde".
 *
 * Devuelve `null` y el hub muestra el destino sin valor, que es exactamente lo
 * que ya hace con los ajustes que un miembro no tiene permiso de contar.
 * `guardar`, en cambio, SI lanza: ahi alguien apreto un boton y tiene que
 * enterarse de que no se guardo.
 */
import { env } from '$env/dynamic/private';

function destino() {
  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (!baseUrl || !tenant) return null;
  return { baseUrl, tenant };
}

/**
 * La configuracion editable del asistente, o `null` si no hay asistente
 * configurado o no contesta.
 * @returns {Promise<{ persona: any, modelo: string, roles: string[] } | null>}
 */
export async function leerConfiguracionAsistente() {
  const cfg = destino();
  if (!cfg) return null;
  try {
    const resp = await fetch(
      `${cfg.baseUrl}/configuracion?tenant=${encodeURIComponent(cfg.tenant)}`
    );
    if (!resp.ok) return null;
    return await resp.json();
  } catch {
    return null;
  }
}

/**
 * Guarda la persona. Lanza con un mensaje legible si el motor la rechaza --
 * el validador devuelve el motivo (un tono que no existe, el texto pasado de
 * largo) y ese texto es mas util que "no se pudo guardar".
 * @param {{ nombre_asistente: string, tono: string, longitud_respuesta: string,
 *           instrucciones_adicionales: string }} valores
 */
export async function guardarPersonaAsistente(valores) {
  const cfg = destino();
  if (!cfg) {
    throw new Error('Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT).');
  }

  const resp = await fetch(`${cfg.baseUrl}/configuracion/persona`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...valores, tenant: cfg.tenant })
  });

  const datos = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new Error(datos.error || 'El asistente rechazo el cambio.');
  }
  return datos.persona;
}

/**
 * Guarda que servicios/planes ofrece la empresa -- contexto que se inyecta
 * SIEMPRE en el prompt del agente (nucleo/recuperacion/prompt.py), a
 * diferencia del corpus (RAG, solo si la pregunta matchea).
 * @param {string} descripcion
 */
export async function guardarDescripcionEmpresa(descripcion) {
  const cfg = destino();
  if (!cfg) {
    throw new Error('Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT).');
  }

  const resp = await fetch(`${cfg.baseUrl}/configuracion/identidad`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ descripcion, tenant: cfg.tenant })
  });

  const datos = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new Error(datos.error || 'El asistente rechazo el cambio.');
  }
  return datos.descripcion;
}

/**
 * Guarda el plazo (en dias) para resolver un ticket de visita tecnica --
 * fecha_final se calcula como 'ahora + este numero' en cada llamada
 * (nucleo/modelo/motor.py), nunca una fecha fija. Solo existe si el tenant
 * tiene la herramienta 'agendar_visita_tecnica' en su catalogo.
 * @param {number} dias
 */
export async function guardarPlazoVisitaTecnica(dias) {
  const cfg = destino();
  if (!cfg) {
    throw new Error('Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT).');
  }

  const resp = await fetch(`${cfg.baseUrl}/configuracion/plazo-visita-tecnica`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ dias, tenant: cfg.tenant })
  });

  const datos = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new Error(datos.error || 'El asistente rechazo el cambio.');
  }
  return datos.dias;
}
