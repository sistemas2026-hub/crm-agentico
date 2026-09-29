import { describe, it, expect } from 'vitest';
import {
	resultadoDelCierre,
	BLOQUEADO_POR_INTERRUPTOR,
	CAMBIO_LA_CONDICION
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

	it('el interruptor se cuenta como detenido, y se dice que se puede reintentar', () => {
		const r = resultadoDelCierre({
			estado: 'aceptada',
			ejecutada: false,
			motivo: BLOQUEADO_POR_INTERRUPTOR
		});
		expect(r.titulo).toBe('Bloqueada por el interruptor');
		expect(r.accionable).toBe(true);
		expect(r.explicacion).toMatch(/reintentar/i);
		//  Y se dice que la decisión no se perdió, que es la duda inmediata.
		expect(r.explicacion).toMatch(/qued[óo] registrada/i);
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
			'LECTURA_EXTERNA_FUERA_DE_FRESCURA',
			'HAY_RESPUESTA_POSTERIOR_AL_CIERRE',
			'PROPUESTA_NO_ACEPTADA'
		]) {
			expect(resultadoDelCierre({ ejecutada: false, motivo }).titulo).toBe(
				'No ejecutada: cambió la condición'
			);
		}
	});

	it('un motivo desconocido cae en fallo, que es el lado seguro', () => {
		//  Ante la duda se alarma, no se tranquiliza: un motivo que nadie
		//  clasificó merece que alguien lo mire.
		const r = resultadoDelCierre({ ejecutada: false, motivo: 'ALGO_NUEVO' });
		expect(r.titulo).toBe('Aceptada pero el cierre falló');
		expect(r.accionable).toBe(true);
	});
});
