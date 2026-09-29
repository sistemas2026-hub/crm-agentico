/* ===========================================================================
   COMO SE LE CUENTA A UNA PERSONA QUE PASO CON EL CIERRE
   ===========================================================================
   Seis estados, y la diferencia entre ellos es lo que decide si alguien tiene
   que hacer algo:

     Pendiente por revisión          nadie decidió todavía
     Aceptada                        decidido, sin acción que ejecutar
     Cerrada correctamente           el caso quedó cerrado en Dexter
     Aceptada pero cierre falló      la decisión vale; el cierre no ocurrió
     Bloqueada por el interruptor    el sistema está detenido a propósito
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
	'LECTURA_EXTERNA_FUERA_DE_FRESCURA',
	'LA_ULTIMA_LECTURA_FALLO',
	'HAY_RESPUESTA_POSTERIOR_AL_CIERRE',
	'CASO_NO_ENCONTRADO',
	'CASO_DE_OTRA_ORGANIZACION',
	'PROPUESTA_NO_ACEPTADA',
	'ORIGEN_NO_ES_UN_CASO'
]);

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
			//  Se dice que se puede reintentar, porque es cierto y es lo único
			//  que la persona puede hacer al respecto.
			explicacion:
				'La autonomía está detenida, así que el cierre no se ejecutó. ' +
				'Tu decisión quedó registrada: cuando se levante el interruptor, se puede reintentar.',
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
