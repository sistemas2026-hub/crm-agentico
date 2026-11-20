/**
 * Probar una instrucción de foto contra la foto que ya falló.
 *
 * POR QUÉ EXISTE (06/11/2026)
 * ---------------------------
 * La instrucción de cada foto —«Tenía que mostrar: Pantalla del medidor con la
 * lectura legible»— se editaba a ciegas en `/supervisor-noc/plantillas`, y
 * había que esperar a que una orden NUEVA la usara para saber si servía.
 *
 * El usuario intentó afinarlas pegándolas en el chat de `/asistente` y el
 * agente le contestó como si fuera un cliente. No es un error del chat: ese
 * camino manda `proposito=asistente_interno`, que usa otra instrucción —1123
 * caracteres contra 2652— **sin las reglas que producen el veredicto**.
 * Afinar ahí sería medir un prompt que en producción no corre.
 *
 * Esto pasa por el mismo camino, el mismo propósito y el mismo envoltorio que
 * producción, sobre la foto que ya está en la orden.
 *
 * EL CUERPO PASA DE LARGO, pero no a ciegas: el token del backend vive en una
 * cookie del servidor y el navegador no lo tiene, así que el proxy es la
 * única vía. El permiso lo decide el backend (gestión, el mismo que guardar la
 * plantilla) y acá se repite el gate de rol, igual que el resto del
 * Supervisor NOC: dos capas, como el resto del proyecto.
 *
 * NO GUARDA NADA. Ni la instrucción ni el análisis — eso lo garantiza el
 * backend, y es lo que hace seguro probar: un ensayo no puede dejar un
 * veredicto falso en la revisión de una orden real.
 */

import { env } from '$env/dynamic/private';
import { env as publicEnv } from '$env/dynamic/public';

const API_BASE_URL = `${env.PRIVATE_DJANGO_API_URL || publicEnv.PUBLIC_DJANGO_API_URL}/api`;

/** El mismo conjunto que campo/permissions.py::ROLES_GESTION. */
const ROLES_GESTION = new Set(['ADMIN', 'SUPERVISOR', 'OPERACIONES']);
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** @type {import('./$types').RequestHandler} */
export async function POST({ params, cookies, locals, request }) {
  if (!locals.user) return new Response(null, { status: 401 });
  if (!ROLES_GESTION.has(locals.profile?.role)) return new Response(null, { status: 403 });
  //  Lo que va en la URL del backend se valida antes: un id que no es UUID no
  //  puede convertirse en otra ruta.
  if (!UUID_RE.test(params.id)) return new Response(null, { status: 404 });

  const accessToken = cookies.get('jwt_access');
  if (!accessToken) return new Response(null, { status: 401 });

  let cuerpo;
  try {
    cuerpo = await request.json();
  } catch {
    return new Response(JSON.stringify({ error: 'CUERPO_INVALIDO' }), {
      status: 400,
      headers: { 'content-type': 'application/json' }
    });
  }

  const upstream = await fetch(
    `${API_BASE_URL}/campo/evidencias/${params.id}/probar-instruccion/`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${accessToken}`,
        'content-type': 'application/json'
      },
      //  SOLO el campo que esta ruta acepta. Reenviar el cuerpo entero dejaría
      //  que el navegador le mande al backend lo que se le ocurra.
      body: JSON.stringify({ instrucciones: cuerpo?.instrucciones ?? '' }),
      signal: request.signal
    }
  );

  //  El estado se respeta tal cual: un 400 del backend —texto vacío, demasiado
  //  largo— es información para quien escribe, no un error del proxy.
  const texto = await upstream.text();
  return new Response(texto, {
    status: upstream.status,
    headers: { 'content-type': 'application/json' }
  });
}
