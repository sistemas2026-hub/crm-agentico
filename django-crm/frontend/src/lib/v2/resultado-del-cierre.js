/* ===========================================================================
   COMO SE LE CUENTA A UNA PERSONA QUE PASO CON EL CIERRE
   ===========================================================================
   Ocho estados, y la diferencia entre ellos es lo que decide si alguien tiene
   que hacer algo:

     Pendiente por revisión          nadie decidió todavía
     Aceptada                        decidido, sin acción que ejecutar
     Cerrada correctamente           el caso quedó cerrado en Dexter
     Aceptada pero cierre falló      la decisión vale; el cierre no ocurrió
     Bloqueada por el interruptor    el sistema está detenido a propósito
     Bloqueado: lectura no confiable el dato del proveedor está vencido o falló
     Bloqueado por configuración     falta habilitar la herramienta de cierre
     No ejecutada: cambió la condición   el mundo cambió entre decidir y cerrar

   POR QUE UN MODULO Y NO UN TERNARIO EN LA PANTALLA
   ------------------------------------------------
   Porque los dos últimos se parecen y no son lo mismo. "Está detenido" se
   arregla levantando el interruptor; "cambió la condición" no se arregla --
   significa que ya no corresponde cerrar. Confundirlos haría que alguien
   insista con un botón que nunca va a funcionar, o que dé por perdido un
   cierre que solo espera.

   El backend manda `motivo` como CLAVE y no como prosa justamente para que
   esta traducción sea posible sin adivinar leyendo un texto.

   NINGUNO DE ESTOS TEXTOS PROMETE UN REINTENTO  --  29/09/2026
   -----------------------------------------------------------
   Porque no existe. Medido: el único llamador de `cierre_de_caso.cerrar()` es
   `RevisarPropuestaView`, y `supervisor.revisar()` levanta `YaRevisada` sobre
   una propuesta que ya no está en `propuesta`. Y no se recupera sola:
   `ESTADOS_QUE_BLOQUEAN` incluye `aceptada`, así que el detector tampoco la
   vuelve a proponer. Una propuesta aceptada cuyo cierre falló queda como
   histórico, y esta pantalla tiene que decirlo así.

   `accionable` NO mueve ningún botón: hoy la pantalla solo lee `tono`,
   `titulo` y `explicacion`. Se conserva porque distingue «hay algo que alguien
   puede hacer» (levantar el interruptor, restablecer la sincronización,
   habilitar la herramienta) de «no hay nada que hacer» -- pero eso que se
   puede hacer NUNCA es reintentar esta propuesta.
   =========================================================================== */

/** El interruptor de autonomía frenó la ejecución. */
export const BLOQUEADO_POR_INTERRUPTOR = 'BLOQUEADO_POR_INTERRUPTOR';

/**
 * Los motivos que significan "el mundo cambió entre la propuesta y el cierre".
 *
 * Son las claves que `operaciones/cierre_de_caso.py` devuelve cuando una de las
 * validaciones previas no pasó. NO se listan aquí para validar nada: se listan
 * para poder decir "cambió la condición" en vez de "falló", que es otra cosa.
 */
export const CAMBIO_LA_CONDICION = new Set([
	'CASO_YA_CERRADO',
	'EL_PROVEEDOR_NO_LO_REPORTA_CERRADO',
	'SIN_FECHA_DE_CIERRE_DEL_PROVEEDOR',
	'HAY_RESPUESTA_POSTERIOR_AL_CIERRE',
	'CASO_NO_ENCONTRADO',
	'CASO_DE_OTRA_ORGANIZACION',
	'PROPUESTA_NO_ACEPTADA',
	'ORIGEN_NO_ES_UN_CASO'
]);

/**
 * Los motivos que NO hablan del caso, sino de la lectura que tenemos de él.
 *
 * POR QUE SE SEPARARON DE «CAMBIO LA CONDICION»  --  29/09/2026
 * ------------------------------------------------------------
 * Estaban adentro, y por eso la pantalla decía «algo cambió y ya no
 * corresponde cerrar» y lo marcaba NO accionable. Las dos mitades de esa frase
 * eran falsas: del caso puede no haber cambiado nada, y sí hay algo que hacer
 * -- volver a sincronizar.
 *
 * No es una distinción teórica. Ese día, la lectura más reciente de CUALQUIER
 * caso tenía 175 h contra un límite de 72: los 237 casos estaban fuera de la
 * ventana, así que el 100% de las aceptaciones caía en un mensaje que mandaba
 * a mirar el caso equivocado. Lo que estaba detenido era la sincronización
 * WispHub -> Dexter, desde el 22/09.
 */
export const LECTURA_NO_CONFIABLE = new Set([
	'LECTURA_EXTERNA_FUERA_DE_FRESCURA',
	'LA_ULTIMA_LECTURA_FALLO'
]);

/**
 * El cierre existe, pero la herramienta no está habilitada para este camino.
 *
 * Lo devuelve el motor (`nucleo/seguimiento/cierre_por_propuesta.py`) y el CRM
 * lo pasa tal cual. Antes caía en «el cierre falló», en tono crítico, que le
 * decía a quien revisa que algo se rompió cuando lo que falta es una bandera
 * de configuración que administra otra persona.
 */
export const SIN_HERRAMIENTA = 'SIN_HERRAMIENTA_DE_CIERRE';

/**
 * Como se le cuenta a una persona el resultado de su decisión.
 *
 * @param {{estado?: string, ejecutada?: boolean, motivo?: string, detalle?: string}} r
 * @returns {{titulo: string, tono: 'ok'|'alerta'|'critico'|'neutro', explicacion: string, accionable: boolean}}
 */
export function resultadoDelCierre(r) {
	const estado = String(r?.estado ?? '').toLowerCase();
	const motivo = String(r?.motivo ?? '');

	if (estado === 'propuesta') {
		return {
			titulo: 'Pendiente por revisión',
			tono: 'neutro',
			explicacion: 'Nadie decidió todavía.',
			accionable: true
		};
	}

	if (r?.ejecutada) {
		return {
			titulo: 'Cerrada correctamente',
			tono: 'ok',
			explicacion: 'El caso quedó cerrado en Dexter.',
			accionable: false
		};
	}

	//  Sin motivo no hubo intento de cierre: es una propuesta revisada de
	//  cualquier otro tipo, donde no hay nada que ejecutar. Decir "falló" ahí
	//  inventaría un problema.
	if (!motivo) {
		return {
			titulo: 'Aceptada',
			tono: 'ok',
			explicacion: 'La decisión quedó registrada y auditada. No hay ninguna acción que ejecutar.',
			accionable: false
		};
	}

	if (motivo === BLOQUEADO_POR_INTERRUPTOR) {
		return {
			titulo: 'Bloqueada por el interruptor',
			tono: 'alerta',
			//  NO se promete reintentar. Se decía «cuando se levante el
			//  interruptor, se puede reintentar» y no hay por dónde: el único
			//  llamador de 'cierre_de_caso.cerrar()' es 'RevisarPropuestaView', y
			//  'supervisor.revisar()' levanta 'YaRevisada' sobre cualquier
			//  propuesta que ya no esté en 'propuesta'. Tampoco vuelve sola:
			//  'ESTADOS_QUE_BLOQUEAN' incluye 'aceptada', así que el detector no
			//  la repropone. Decirle a alguien que insista con un botón que no
			//  existe es peor que decirle que no hay nada que hacer.
			//  Se enuncian los tres hechos y ninguno mas: que no se ejecuto, que
			//  la decision quedo, y que el caso sigue abierto. Sin la palabra
			//  "reintentar" -- ni para prometerla ni para negarla: nombrarla
			//  invita a buscar el boton, y no hay boton.
			explicacion:
				'La autonomía está detenida, así que el cierre no se ejecutó. Tu decisión ' +
				'quedó registrada y el caso sigue abierto.',
			accionable: true
		};
	}

	if (LECTURA_NO_CONFIABLE.has(motivo)) {
		return {
			titulo: 'Bloqueado: la lectura del proveedor no es confiable',
			tono: 'alerta',
			explicacion:
				'No se cierra un caso con una lectura vencida o fallida del proveedor. ' +
				'Del caso puede no haber cambiado nada: lo que hay que revisar es la ' +
				'sincronización. ' +
				(r?.detalle || 'Tu decisión quedó registrada.'),
			//  Accionable, y por un camino distinto al de los demás: no se
			//  arregla mirando el caso sino restableciendo la sincronización.
			accionable: true
		};
	}

	if (motivo === SIN_HERRAMIENTA) {
		return {
			titulo: 'Bloqueado por configuración',
			tono: 'alerta',
			explicacion:
				'La herramienta de cierre no está habilitada para este camino, así que no se ' +
				'ejecutó nada. Tu decisión quedó registrada: lo resuelve quien administra la ' +
				'configuración del asistente, no quien revisa la propuesta.',
			accionable: true
		};
	}

	if (CAMBIO_LA_CONDICION.has(motivo)) {
		return {
			titulo: 'No ejecutada: cambió la condición',
			tono: 'alerta',
			explicacion:
				'Entre la propuesta y tu decisión, algo cambió y ya no corresponde cerrar. ' +
				(r?.detalle || 'El caso quedó como estaba.'),
			//  NO es accionable: reintentar daría el mismo resultado. Lo que
			//  corresponde es mirar el caso.
			accionable: false
		};
	}

	return {
		titulo: 'Aceptada pero el cierre falló',
		tono: 'critico',
		explicacion:
			'Tu decisión quedó registrada y el caso sigue abierto. ' +
			(r?.detalle || 'El motivo quedó en la bitácora.'),
		accionable: true
	};
}
