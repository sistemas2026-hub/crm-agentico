import { describe, it, expect } from 'vitest';
import {
	resultadoDelCierre,
	BLOQUEADO_POR_INTERRUPTOR,
	CAMBIO_LA_CONDICION,
	LECTURA_NO_CONFIABLE,
	SIN_HERRAMIENTA
} from './resultado-del-cierre.js';

// ===========================================================================
//  LOS SEIS ESTADOS, Y LA DIFERENCIA QUE IMPORTA
// ===========================================================================
//  Lo que estas pruebas guardan no es la redacción: es que dos resultados que
//  se parecen no se cuenten igual. "El interruptor está detenido" se arregla
//  levantándolo; "cambió la condición" no se arregla. Si la pantalla los
//  confunde, alguien insiste con un botón que nunca va a funcionar.

describe('los seis estados', () => {
	it('sin revisar es pendiente, y es lo único accionable por decisión', () => {
		const r = resultadoDelCierre({ estado: 'propuesta' });
		expect(r.titulo).toBe('Pendiente por revisión');
		expect(r.accionable).toBe(true);
	});

	it('ejecutada es cerrada correctamente', () => {
		const r = resultadoDelCierre({ estado: 'aceptada', ejecutada: true });
		expect(r.titulo).toBe('Cerrada correctamente');
		expect(r.tono).toBe('ok');
		expect(r.accionable).toBe(false);
	});

	it('aceptada sin intento de cierre NO dice que falló', () => {
		//  Una propuesta de otro tipo: no hay nada que ejecutar. Decir "falló"
		//  ahí inventaría un problema que no existe.
		const r = resultadoDelCierre({ estado: 'aceptada', ejecutada: false, motivo: '' });
		expect(r.titulo).toBe('Aceptada');
		expect(r.tono).toBe('ok');
		expect(r.explicacion).toMatch(/no hay ninguna acción que ejecutar/i);
	});

	it('el interruptor se cuenta como detenido, sin prometer un reintento', () => {
		//  ESTA PRUEBA EXIGIA LO CONTRARIO HASTA EL 29/09/2026: afirmaba
		//  '/reintentar/i', o sea que blindaba una promesa que el sistema no
		//  puede cumplir -- no hay ninguna ruta que vuelva a lanzar el cierre de
		//  una propuesta ya aceptada. Se invierte a proposito, y se afirma sobre
		//  los tres hechos que SI son ciertos.
		const r = resultadoDelCierre({
			estado: 'aceptada',
			ejecutada: false,
			motivo: BLOQUEADO_POR_INTERRUPTOR
		});
		expect(r.titulo).toBe('Bloqueada por el interruptor');
		expect(r.accionable).toBe(true);
		expect(r.explicacion).not.toMatch(/reintent/i);
		//  Y se dice que la decisión no se perdió, que es la duda inmediata.
		expect(r.explicacion).toMatch(/qued[óo] registrada/i);
		expect(r.explicacion).toMatch(/sigue abierto/i);
	});

	it('una condición que cambió NO se presenta como un fallo', () => {
		const r = resultadoDelCierre({
			estado: 'aceptada',
			ejecutada: false,
			motivo: 'EL_PROVEEDOR_NO_LO_REPORTA_CERRADO',
			detalle: 'el proveedor lo reporta como Nuevo'
		});
		expect(r.titulo).toBe('No ejecutada: cambió la condición');
		expect(r.titulo).not.toMatch(/fall/i);
		//  Y NO es accionable: reintentar daría lo mismo.
		expect(r.accionable).toBe(false);
		expect(r.explicacion).toContain('Nuevo');
	});

	it('un fallo de verdad se cuenta como fallo, y sí es accionable', () => {
		const r = resultadoDelCierre({
			estado: 'aceptada',
			ejecutada: false,
			motivo: 'FALLO_AL_CERRAR',
			detalle: 'HTTPError: 400'
		});
		expect(r.titulo).toBe('Aceptada pero el cierre falló');
		expect(r.tono).toBe('critico');
		expect(r.accionable).toBe(true);
		expect(r.explicacion).toMatch(/sigue abierto/i);
	});
});

describe('los dos que se parecen y no son lo mismo', () => {
	it('el interruptor y una condición cambiada dan títulos DISTINTOS', () => {
		const detenido = resultadoDelCierre({
			ejecutada: false,
			motivo: BLOQUEADO_POR_INTERRUPTOR
		});
		const cambio = resultadoDelCierre({ ejecutada: false, motivo: 'CASO_YA_CERRADO' });
		expect(detenido.titulo).not.toBe(cambio.titulo);
		//  Y lo que de verdad los separa: si vale la pena volver a intentar.
		expect(detenido.accionable).toBe(true);
		expect(cambio.accionable).toBe(false);
	});

	it('el interruptor NO está en la lista de condiciones cambiadas', () => {
		//  Si estuviera, se contaría como "ya no corresponde cerrar" -- y la
		//  persona daría por perdido un cierre que solo está esperando.
		expect(CAMBIO_LA_CONDICION.has(BLOQUEADO_POR_INTERRUPTOR)).toBe(false);
	});

	it('cada motivo de validación previa se cuenta como condición cambiada', () => {
		//  La lista es la de operaciones/cierre_de_caso.py. Si allá se agrega un
		//  motivo y aquí no, ese caso caería en "el cierre falló" -- que es la
		//  categoría equivocada y la más alarmante de las tres.
		for (const motivo of [
			'CASO_YA_CERRADO',
			'EL_PROVEEDOR_NO_LO_REPORTA_CERRADO',
			'HAY_RESPUESTA_POSTERIOR_AL_CIERRE',
			'PROPUESTA_NO_ACEPTADA'
		]) {
			expect(resultadoDelCierre({ ejecutada: false, motivo }).titulo).toBe(
				'No ejecutada: cambió la condición'
			);
		}
	});

	// =========================================================================
	//  LA LECTURA DEL PROVEEDOR NO ES UNA CONDICION DEL CASO  --  29/09/2026
	// =========================================================================
	//  Los dos motivos de lectura estaban dentro de CAMBIO_LA_CONDICION, que
	//  dice "algo cambió y ya no corresponde cerrar" y marca NO accionable. Las
	//  dos mitades eran falsas: del caso puede no haber cambiado nada, y sí hay
	//  algo que hacer. Ese día los 237 casos tenían la lectura vencida (175 h
	//  contra un límite de 72), así que el 100% de las aceptaciones caía en el
	//  mensaje equivocado.

	it('la lectura vencida NO se cuenta como condición cambiada', () => {
		expect(CAMBIO_LA_CONDICION.has('LECTURA_EXTERNA_FUERA_DE_FRESCURA')).toBe(false);
		expect(CAMBIO_LA_CONDICION.has('LA_ULTIMA_LECTURA_FALLO')).toBe(false);
	});

	it('los dos motivos de lectura tienen su propio resultado, y es accionable', () => {
		for (const motivo of LECTURA_NO_CONFIABLE) {
			const r = resultadoDelCierre({ ejecutada: false, motivo });

			expect(r.titulo).toBe('Bloqueado: la lectura del proveedor no es confiable');
			//  Lo que de verdad lo separa de "cambió la condición": hay algo que
			//  hacer, y no es mirar el caso.
			expect(r.accionable).toBe(true);
		}
	});

	it('no manda a mirar el caso cuando el problema es la sincronización', () => {
		const r = resultadoDelCierre({
			ejecutada: false,
			motivo: 'LECTURA_EXTERNA_FUERA_DE_FRESCURA',
			detalle: 'la ultima lectura del proveedor tiene 175 h y el limite es 72 h'
		});
		const cambio = resultadoDelCierre({ ejecutada: false, motivo: 'CASO_YA_CERRADO' });

		expect(r.titulo).not.toBe(cambio.titulo);
		expect(r.accionable).not.toBe(cambio.accionable);
		expect(r.explicacion).toMatch(/sincronizaci/i);
		//  El detalle del backend llega hasta la persona: es el unico lugar
		//  donde aparece el numero real de horas.
		expect(r.explicacion).toMatch(/175 h/);
	});

	// =========================================================================
	//  FALTA UNA BANDERA DE CONFIGURACION, NO SE ROMPIO NADA
	// =========================================================================

	it('la herramienta no habilitada es un bloqueo de configuración, no un fallo', () => {
		const r = resultadoDelCierre({ ejecutada: false, motivo: SIN_HERRAMIENTA });
		const fallo = resultadoDelCierre({ ejecutada: false, motivo: 'ALGO_NUEVO' });

		expect(r.titulo).toBe('Bloqueado por configuración');
		expect(r.tono).not.toBe(fallo.tono);
		//  Se puede resolver, pero no lo resuelve quien revisa la propuesta.
		expect(r.accionable).toBe(true);
		expect(r.explicacion).toMatch(/configuraci/i);
	});

	it('los cuatro bloqueos se cuentan distinto entre sí', () => {
		//  La razon de ser de este modulo: cuatro resultados que se parecen y
		//  llevan a cuatro acciones distintas no pueden compartir titulo.
		const titulos = [
			BLOQUEADO_POR_INTERRUPTOR,
			'LECTURA_EXTERNA_FUERA_DE_FRESCURA',
			SIN_HERRAMIENTA,
			'CASO_YA_CERRADO'
		].map((motivo) => resultadoDelCierre({ ejecutada: false, motivo }).titulo);

		expect(new Set(titulos).size).toBe(4);
	});

	// =========================================================================
	//  NINGUN TEXTO PROMETE UN REINTENTO QUE NO EXISTE  --  29/09/2026
	// =========================================================================
	//  El de 'BLOQUEADO_POR_INTERRUPTOR' decía «cuando se levante el
	//  interruptor, se puede reintentar». No hay por dónde: el único llamador
	//  de 'cierre_de_caso.cerrar()' es 'RevisarPropuestaView', y
	//  'supervisor.revisar()' levanta 'YaRevisada' sobre una propuesta que ya
	//  no está en 'propuesta'. Tampoco vuelve sola: 'ESTADOS_QUE_BLOQUEAN'
	//  incluye 'aceptada'.
	//
	//  Se afirma sobre TODOS los resultados y no sobre el que falló, porque lo
	//  que hay que impedir es que la promesa reaparezca en cualquiera de ellos.

	it('ningun resultado le promete a nadie que puede reintentar', () => {
		const motivos = [
			BLOQUEADO_POR_INTERRUPTOR,
			SIN_HERRAMIENTA,
			'LECTURA_EXTERNA_FUERA_DE_FRESCURA',
			'LA_ULTIMA_LECTURA_FALLO',
			'CASO_YA_CERRADO',
			'EL_PROVEEDOR_NO_LO_REPORTA_CERRADO',
			'EL_MOTOR_NO_RESPONDIO',
			'ALGO_NUEVO'
		];

		for (const motivo of motivos) {
			const r = resultadoDelCierre({ ejecutada: false, motivo });
			expect(r.explicacion, motivo).not.toMatch(/reintent/i);
			expect(r.explicacion, motivo).not.toMatch(/volv[eé]r? a intentar/i);
			expect(r.titulo, motivo).not.toMatch(/reintent/i);
		}
	});

	it('tampoco lo prometen los dos estados sin intento de cierre', () => {
		for (const r of [
			resultadoDelCierre({ estado: 'propuesta' }),
			resultadoDelCierre({ estado: 'aceptada', ejecutada: false })
		]) {
			expect(r.explicacion).not.toMatch(/reintent/i);
		}
	});

	it('el bloqueo por interruptor dice que el caso sigue abierto', () => {
		//  Lo que reemplaza a la promesa: el hecho, que sí es verdad y sí le
		//  sirve a quien lee.
		const r = resultadoDelCierre({ ejecutada: false, motivo: BLOQUEADO_POR_INTERRUPTOR });

		expect(r.explicacion).toMatch(/sigue abierto/i);
		expect(r.explicacion).toMatch(/qued[oó] registrada/i);
	});

	it('un motivo desconocido cae en fallo, que es el lado seguro', () => {
		//  Ante la duda se alarma, no se tranquiliza: un motivo que nadie
		//  clasificó merece que alguien lo mire.
		const r = resultadoDelCierre({ ejecutada: false, motivo: 'ALGO_NUEVO' });
		expect(r.titulo).toBe('Aceptada pero el cierre falló');
		expect(r.accionable).toBe(true);
	});
});
