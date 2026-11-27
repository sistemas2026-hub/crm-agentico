import { apiRequest } from '$lib/api-helpers.js';

/**
 * Lo que cada empresa pone en el contrato que el técnico firma con el cliente
 * desde la app (13/11/2026). Ver campo/contrato_views.py.
 *
 * LOS SERVIDORES: el usuario, «zona es el servidor, así que debe mostrar los
 * dos y ahí se elige». Cada uno es el número de ZONA de WispHub (el de
 * /api/zonas/, no el de /api/router/: son catálogos con números distintos
 * aunque se llamen igual) y el nombre que verá el técnico.
 */

/** Cuántas filas de servidor ofrece el formulario. */
export const FILAS_DE_SERVIDOR = 6;

/** @param {{ cookies: any }} ctx */
export async function leerContrato(ctx) {
  try {
    return { configuracion: await apiRequest('/campo/contrato/configuracion/', {}, ctx), error: false };
  } catch {
    return { configuracion: null, error: true };
  }
}

/**
 * Del formulario al cuerpo del PUT.
 *
 * UNA FILA VACÍA SE IGNORA; UNA A MEDIAS NO. Si hay número sin nombre (o al
 * revés) se manda igual y el backend la rechaza con su mensaje: perderla en
 * silencio dejaría a la empresa creyendo que cargó un servidor que no está.
 *
 * El número llega como texto y el backend exige un entero; uno con letras se
 * manda tal cual para que el 400 diga qué está mal, en vez de convertirse en
 * NaN y desaparecer.
 *
 * @param {FormData} f
 */
export function cuerpoDeContrato(f) {
  /** @type {{ id_zona: number | string, nombre: string, vlan?: number | string }[]} */
  const servidores = [];
  for (let i = 0; i < FILAS_DE_SERVIDOR; i++) {
    const id = String(f.get(`servidor_id_${i}`) ?? '').trim();
    const nombre = String(f.get(`servidor_nombre_${i}`) ?? '').trim();
    //  LA VLAN DEL SERVIDOR (26/11/2026), para activar la ONU. Vacía no viaja;
    //  con letras viaja como texto para que el backend diga qué está mal.
    const vlan = String(f.get(`servidor_vlan_${i}`) ?? '').trim();
    if (!id && !nombre) continue;
    servidores.push({
      id_zona: /^\d+$/.test(id) ? Number(id) : id, nombre,
      ...(vlan ? { vlan: /^\d+$/.test(vlan) ? Number(vlan) : vlan } : {})
    });
  }
  //  CÓMO ESCRIBE LA EMPRESA LOS DATOS DEL CLIENTE (25/11/2026).
  //
  //  Una casilla sin marcar NO VIAJA en un formulario: «no está» es «apagada».
  //  Por eso se mandan siempre las dos como sí/no de verdad; mandarlas solo
  //  cuando están marcadas dejaría una costumbre imposible de apagar.
  //
  //  Los dígitos, igual que el número de zona: uno con letras viaja como texto
  //  para que el backend diga qué está mal, en vez de volverse NaN o 0.
  const digitos = String(f.get('digitos_del_telefono') ?? '').trim();
  //  LAS ABREVIATURAS DE LA DIRECCIÓN (25/11/2026): un renglón por regla,
  //  «CLL, CL, CALL = CALLE». Un renglón sin «=» se manda igual, sin cómo
  //  queda, para que el backend diga qué falta en vez de perderlo callado.
  const abreviaturas = String(f.get('abreviaturas_de_direccion') ?? '')
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean)
    .map((l) => {
      const [formas, queda = ''] = l.split('=');
      return {
        como_lo_escriben: formas.split(/[,;]/).map((x) => x.trim()).filter(Boolean),
        como_queda: queda.trim()
      };
    });
  return {
    nit: String(f.get('nit') ?? '').trim(),
    servidores,
    texto_condiciones: String(f.get('texto_condiciones') ?? ''),
    abreviaturas_de_direccion: abreviaturas,
    datos_en_mayusculas: f.get('datos_en_mayusculas') != null,
    barrio_en_la_direccion: f.get('barrio_en_la_direccion') != null,
    //  Igual que las dos de arriba, y acá importa más: es el interruptor de
    //  crear clientes en el proveedor. Si desmarcarlo no viajara como `false`,
    //  no habría forma de apagarlo desde la pantalla.
    crear_en_el_isp: f.get('crear_en_el_isp') != null,
    activar_onu: f.get('activar_onu') != null,
    //  26/11/2026: la instalación la valida una persona, y el cliente firma el
    //  contrato del proveedor. Casilla sin marcar = false, como las de arriba.
    validar_antes_de_activar: f.get('validar_antes_de_activar') != null,
    firma_en_el_proveedor: f.get('firma_en_el_proveedor') != null,
    digitos_del_telefono: digitos === '' ? 0 : /^\d+$/.test(digitos) ? Number(digitos) : digitos
  };
}

/** @param {{ cookies: any }} ctx @param {Record<string, any>} cuerpo */
export async function guardarContrato(ctx, cuerpo) {
  return apiRequest('/campo/contrato/configuracion/', { method: 'PUT', body: cuerpo }, ctx);
}
