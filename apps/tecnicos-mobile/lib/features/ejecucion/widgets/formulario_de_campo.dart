import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../../demo/field_mock_data.dart';
import '../../../core/theme/app_theme.dart';
import '../campo_del_formulario.dart';

/// El formulario de campo: el aspecto del diseño, el contenido del backend.
///
/// Las preguntas **no viven acá**. Llegan con la orden en
/// `formulario_campos_json` y cambian por tipo de trabajo, por empresa y por
/// versión del esquema. Este widget solo decide cómo se dibuja cada tipo de
/// campo y avisa cuando el técnico responde; quién guarda, valida y encola
/// sigue siendo la pantalla de ejecución.
///
/// Por eso el diseño de Stitch se copió como *forma*, no como contenido: sus
/// tres preguntas de ejemplo no están escritas en ningún lado de este archivo.
class FormularioDeCampo extends StatelessWidget {
  const FormularioDeCampo({
    super.key,
    required this.campos,
    required this.valores,
    required this.controladores,
    required this.alCambiar,
    this.mostrarDatosFuturos = FieldMockData.modoDemo,
  });

  /// Los campos **ya interpretados**.
  ///
  /// No se reciben crudos a propósito. Leer el esquema acá adentro fue lo que
  /// produjo dos lecturas distintas del mismo campo: este widget buscaba las
  /// opciones en `opciones` mientras el servidor las manda en
  /// `reglas.options`, y un campo de selección obligatorio salía con "Sin
  /// opciones definidas". Quien arma esta lista es `CampoDelFormulario`.
  final List<CampoDelFormulario> campos;

  /// Lo respondido hasta ahora (base del servidor + lo escrito sin enviar).
  final Map<String, dynamic> valores;

  /// Un controlador por campo de texto, creado por la pantalla para que el
  /// cursor no se reinicie en cada redibujo.
  final Map<String, TextEditingController> controladores;

  /// Se llama con la clave del campo y el valor nuevo. La persistencia es
  /// inmediata: la hace quien recibe este aviso.
  final void Function(String clave, dynamic valor) alCambiar;

  final bool mostrarDatosFuturos;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.lg),
      decoration: BoxDecoration(
        color: AppColors.surfaceContainerLowest,
        borderRadius: AppRadius.brTarjeta,
        boxShadow: AppTheme.sombraNivel1,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text('Formulario de Validación', style: AppTypography.tituloChico),
                    Text(
                      'Parámetros técnicos obligatorios de campo',
                      style: AppTypography.cuerpoChico,
                    ),
                  ],
                ),
              ),
              const Icon(Icons.tune, size: 20, color: AppColors.outline),
            ],
          ),
          const SizedBox(height: AppSpacing.lg),
          if (campos.isEmpty)
            Text(
              'Esta orden no trae formulario de campo. Registrá la evidencia '
              'fotográfica y cerrala.',
              style: AppTypography.cuerpoChico,
            )
          else
            ..._camposNumerados(context),
        ],
      ),
    );
  }

  /// El diseño numera las preguntas que se contestan eligiendo, y deja sin
  /// número el interruptor y la medición. Si el número saliera del índice del
  /// arreglo, un booleano en el medio haría saltar la cuenta a la vista.
  List<Widget> _camposNumerados(BuildContext context) {
    final List<Widget> salida = <Widget>[];
    var numero = 0;

    for (var i = 0; i < campos.length; i++) {
      final CampoDelFormulario campo = campos[i];
      final bool llevaNumero =
          !campo.esBooleano && !campo.unidad.toLowerCase().contains('dbm');
      if (llevaNumero) numero++;

      if (i > 0) salida.add(const SizedBox(height: AppSpacing.lg));
      salida.add(_campo(context, campo, llevaNumero ? numero : null));
    }

    return salida;
  }

  Widget _campo(BuildContext context, CampoDelFormulario campo, int? numero) {
    final String clave = campo.id;
    final String etiqueta = campo.titulo;
    final String tipo = campo.tipo;
    final bool obligatorio = campo.obligatorio;
    final String? unidad = campo.unidad.isEmpty ? null : campo.unidad;
    final String? ayuda = campo.ayuda.isEmpty ? null : campo.ayuda;

    switch (tipo) {
      case 'seleccion':
        return _bloque(
          numero: numero,
          etiqueta: etiqueta,
          obligatorio: obligatorio,
          ayuda: ayuda,
          contenido: _opciones(
            campo.opciones,
            clave,
            campo.valor?.toString(),
            campo.motivoDelError,
          ),
        );

      case 'booleano':
        return _interruptor(clave, etiqueta, obligatorio, ayuda);

      default:
        final bool esMedicionOptica = (unidad ?? '').toLowerCase().contains('dbm');
        return _bloque(
          numero: numero,
          etiqueta: etiqueta,
          obligatorio: obligatorio,
          ayuda: ayuda,
          // CAMPO-DATA-032 · Con qué longitud de onda se mide. Todavía no hay
          // catálogo de red que lo diga.
          alDerecha: esMedicionOptica && mostrarDatosFuturos
              ? FieldMockData.longitudOndaMedicion
              : null,
          contenido: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              _entrada(clave, tipo, unidad),
              if (esMedicionOptica && mostrarDatosFuturos) ...<Widget>[
                const SizedBox(height: AppSpacing.xs),
                _referenciaDeUmbral(valores[clave]),
              ],
            ],
          ),
        );
    }
  }

  /// La forma común: número, etiqueta y debajo la respuesta.
  Widget _bloque({
    required int? numero,
    required String etiqueta,
    required bool obligatorio,
    required Widget contenido,
    String? ayuda,
    String? alDerecha,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Expanded(
              child: Text.rich(
                TextSpan(
                  children: <InlineSpan>[
                    TextSpan(text: numero == null ? etiqueta : '$numero. $etiqueta'),
                    if (obligatorio)
                      const TextSpan(
                        text: ' *',
                        style: TextStyle(color: AppColors.error),
                      ),
                  ],
                ),
                style: AppTypography.etiqueta.copyWith(color: AppColors.onSurface),
              ),
            ),
            if (alDerecha != null) ...<Widget>[
              const SizedBox(width: AppSpacing.sm),
              Text(
                alDerecha,
                style: AppTypography.etiquetaChica.copyWith(
                  color: AppColors.secondary,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ],
        ),
        const SizedBox(height: AppSpacing.sm),
        contenido,
        if (ayuda != null && ayuda.isNotEmpty) ...<Widget>[
          const SizedBox(height: AppSpacing.xs),
          Text(ayuda, style: AppTypography.etiquetaChica),
        ],
      ],
    );
  }

  /// CAMPO-DATA-033 · El umbral de aceptación, como referencia.
  ///
  /// Compara y dice, nada más: no valida la respuesta, no bloquea el cierre de
  /// la orden y no cambia el valor. El umbral todavía es un número de ejemplo
  /// —cada empresa define el suyo—, así que decidir con él sería decidir con un
  /// dato inventado.
  Widget _referenciaDeUmbral(dynamic valor) {
    final double? lectura = valor is num
        ? valor.toDouble()
        : double.tryParse(valor?.toString() ?? '');
    final bool dentro = lectura != null &&
        lectura >= FieldMockData.umbralOptimoMin &&
        lectura <= FieldMockData.umbralOptimoMax;

    final Color color = lectura == null
        ? AppColors.onSurfaceVariant
        : (dentro ? AppColors.exito : AppColors.error);

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Icon(
          lectura == null
              ? Icons.straighten
              : (dentro ? Icons.check_circle : Icons.error_outline),
          size: 14,
          color: color,
        ),
        const SizedBox(width: AppSpacing.xs),
        Expanded(
          child: Text(
            lectura == null
                ? 'Referencia: ${FieldMockData.umbralAceptacionTexto}'
                : dentro
                    ? 'Lectura dentro de ${FieldMockData.umbralAceptacionTexto}'
                    : 'Lectura fuera de ${FieldMockData.umbralAceptacionTexto}',
            style: AppTypography.etiquetaChica.copyWith(color: color),
          ),
        ),
      ],
    );
  }

  /// Las opciones, como botones grandes: con guantes y al sol, una lista
  /// desplegable obliga a apuntar dos veces a un texto chico.
  Widget _opciones(
    List<String> opciones,
    String clave,
    String? valorActual,
    String motivoDelError,
  ) {
    if (opciones.isEmpty) {
      // Antes decía "Sin opciones definidas", que le habla al programador.
      // Quien lee esto está en la calle y necesita saber dos cosas: que no es
      // culpa suya y a quién avisar.
      return Container(
        width: double.infinity,
        padding: const EdgeInsets.all(AppSpacing.sm),
        decoration: const BoxDecoration(
          color: AppColors.errorContainer,
          borderRadius: AppRadius.brCampo,
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            const Icon(Icons.error_outline,
                size: 16, color: AppColors.onErrorContainer),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: Text(
                motivoDelError.isEmpty
                    ? 'Este campo llegó sin opciones para elegir.'
                    : motivoDelError,
                style: AppTypography.cuerpoChico
                    .copyWith(color: AppColors.onErrorContainer),
              ),
            ),
          ],
        ),
      );
    }

    final int columnas = opciones.length <= 3 ? opciones.length : 2;
    final List<Widget> filas = <Widget>[];

    for (var i = 0; i < opciones.length; i += columnas) {
      final List<dynamic> grupo =
          opciones.sublist(i, math.min(i + columnas, opciones.length));
      filas.add(
        Row(
          children: <Widget>[
            for (var j = 0; j < columnas; j++) ...<Widget>[
              if (j > 0) const SizedBox(width: AppSpacing.xs),
              Expanded(
                child: j < grupo.length
                    ? _BotonOpcion(
                        key: Key('opcion-$clave-${grupo[j]}'),
                        texto: grupo[j].toString(),
                        seleccionado: grupo[j].toString() == valorActual,
                        alTocar: () => alCambiar(clave, grupo[j].toString()),
                      )
                    : const SizedBox.shrink(),
              ),
            ],
          ],
        ),
      );
      if (i + columnas < opciones.length) {
        filas.add(const SizedBox(height: AppSpacing.xs));
      }
    }

    return Column(children: filas);
  }

  /// Un sí/no, con su bloque condicional debajo.
  Widget _interruptor(String clave, String etiqueta, bool obligatorio, String? ayuda) {
    final bool encendido = valores[clave] == true;

    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: const BoxDecoration(
        color: AppColors.surfaceContainerLow,
        borderRadius: AppRadius.brTarjeta,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(
                      '$etiqueta${obligatorio ? ' *' : ''}',
                      style: AppTypography.etiqueta.copyWith(color: AppColors.onSurface),
                    ),
                    if (ayuda != null && ayuda.isNotEmpty)
                      Text(ayuda, style: AppTypography.etiquetaChica),
                  ],
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              _Interruptor(
                key: Key('interruptor-$clave'),
                encendido: encendido,
                alCambiar: (bool valor) => alCambiar(clave, valor),
              ),
            ],
          ),
          // CAMPO-DATA-026 · La sugerencia de reemplazo todavía no existe: no
          // hay inventario que cruzar. Se muestra cuando el técnico dice que sí
          // —esa parte es real— y nunca se guarda con la respuesta.
          if (encendido && mostrarDatosFuturos) ...<Widget>[
            const SizedBox(height: AppSpacing.md),
            Text(
              'EQUIPO SUGERIDO PARA REEMPLAZO',
              style: AppTypography.etiquetaChica.copyWith(
                color: AppColors.primary,
                fontWeight: FontWeight.w700,
                letterSpacing: 0.6,
              ),
            ),
            const SizedBox(height: AppSpacing.xs),
            Container(
              padding: const EdgeInsets.all(AppSpacing.md),
              decoration: const BoxDecoration(
                color: AppColors.surfaceContainer,
                borderRadius: AppRadius.brTarjeta,
              ),
              child: Row(
                children: <Widget>[
                  const Icon(Icons.memory, size: 18, color: AppColors.secondary),
                  const SizedBox(width: AppSpacing.sm),
                  Expanded(
                    child: Text(
                      FieldMockData.equipoSugerido,
                      style: AppTypography.etiqueta.copyWith(color: AppColors.onSurface),
                    ),
                  ),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                    decoration: const BoxDecoration(
                      color: AppColors.exitoFondo,
                      borderRadius: AppRadius.brChico,
                    ),
                    child: Text(
                      FieldMockData.equipoSugeridoStock,
                      style: AppTypography.etiquetaChica.copyWith(
                        color: AppColors.exitoTexto,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }

  /// Texto y números. La lectura óptica se escribe grande y centrada porque es
  /// el dato que el técnico compara contra el umbral mientras lo mide.
  Widget _entrada(String clave, String tipo, String? unidad) {
    final bool esNumero = tipo == 'numero' || tipo == 'decimal' || tipo == 'integer';
    final bool esMedicionOptica = (unidad ?? '').toLowerCase().contains('dbm');

    final Widget caja = Container(
      height: esNumero ? AppSpacing.objetivoTactilAmplio : AppSpacing.objetivoTactil,
      decoration: const BoxDecoration(
        color: AppColors.surfaceContainer,
        borderRadius: AppRadius.brTarjeta,
      ),
      child: Stack(
        alignment: Alignment.center,
        children: <Widget>[
          TextField(
            controller: controladores[clave],
            keyboardType: esNumero
                ? const TextInputType.numberWithOptions(decimal: true, signed: true)
                : TextInputType.text,
            textAlign: esNumero ? TextAlign.center : TextAlign.start,
            style: esNumero
                ? AppTypography.medicion.copyWith(color: AppColors.onSurface)
                : AppTypography.cuerpo.copyWith(color: AppColors.onSurface),
            decoration: InputDecoration(
              border: InputBorder.none,
              isDense: true,
              contentPadding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.md,
                vertical: AppSpacing.sm,
              ),
              hintText: esNumero ? '-00.0' : null,
            ),
            onChanged: (String val) {
              dynamic valor = val;
              if (esNumero && val.isNotEmpty) {
                valor = num.tryParse(val) ?? val;
              }
              alCambiar(clave, valor);
            },
          ),
          if (esNumero && unidad != null && unidad.isNotEmpty)
            Positioned(
              right: AppSpacing.md,
              bottom: AppSpacing.sm,
              child: Text(
                unidad,
                style: AppTypography.etiquetaChica.copyWith(color: AppColors.outline),
              ),
            ),
        ],
      ),
    );

    // CAMPO-DATA-027 · El medidor por Bluetooth no está integrado. El botón se
    // ve para mostrar a dónde va el producto, pero no escribe la lectura: una
    // medición inventada quedaría firmada por el técnico.
    if (!(esMedicionOptica && mostrarDatosFuturos)) return caja;

    return Row(
      children: <Widget>[
        Expanded(child: caja),
        const SizedBox(width: AppSpacing.xs),
        _BotonMedir(clave: clave),
      ],
    );
  }
}

class _BotonOpcion extends StatelessWidget {
  const _BotonOpcion({
    super.key,
    required this.texto,
    required this.seleccionado,
    required this.alTocar,
  });

  final String texto;
  final bool seleccionado;
  final VoidCallback alTocar;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: seleccionado ? AppColors.primary : AppColors.surfaceContainer,
      borderRadius: AppRadius.brTarjeta,
      child: InkWell(
        borderRadius: AppRadius.brTarjeta,
        onTap: alTocar,
        child: Container(
          height: AppSpacing.objetivoTactil,
          alignment: Alignment.center,
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.sm),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              if (seleccionado) ...<Widget>[
                const Icon(Icons.check, size: 16, color: AppColors.onPrimary),
                const SizedBox(width: AppSpacing.xs),
              ],
              Flexible(
                child: Text(
                  texto,
                  textAlign: TextAlign.center,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: AppTypography.etiqueta.copyWith(
                    color: seleccionado ? AppColors.onPrimary : AppColors.onSurface,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Interruptor extends StatelessWidget {
  const _Interruptor({super.key, required this.encendido, required this.alCambiar});

  final bool encendido;
  final ValueChanged<bool> alCambiar;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      toggled: encendido,
      button: true,
      child: GestureDetector(
        onTap: () => alCambiar(!encendido),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 150),
          width: 56,
          height: 32,
          padding: const EdgeInsets.all(AppSpacing.xs),
          decoration: BoxDecoration(
            color: encendido ? AppColors.secondary : AppColors.surfaceVariant,
            borderRadius: BorderRadius.circular(AppRadius.circulo),
          ),
          child: Align(
            alignment: encendido ? Alignment.centerRight : Alignment.centerLeft,
            child: Container(
              width: 24,
              height: 24,
              decoration: const BoxDecoration(
                color: AppColors.onSecondary,
                shape: BoxShape.circle,
                boxShadow: AppTheme.sombraNivel1,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _BotonMedir extends StatelessWidget {
  const _BotonMedir({required this.clave});

  final String clave;

  @override
  Widget build(BuildContext context) {
    return Material(
      key: Key('medidor-$clave'),
      color: AppColors.secondaryContainer,
      borderRadius: AppRadius.brTarjeta,
      child: InkWell(
        borderRadius: AppRadius.brTarjeta,
        onTap: () {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text(FieldMockData.medidorPendiente)),
          );
        },
        child: Container(
          height: AppSpacing.objetivoTactilAmplio,
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
          alignment: Alignment.center,
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              const Icon(
                Icons.bluetooth_searching,
                size: 20,
                color: AppColors.onSecondaryContainer,
              ),
              const SizedBox(width: AppSpacing.xs),
              Text(
                FieldMockData.medidorBluetooth,
                style: AppTypography.etiqueta.copyWith(
                  color: AppColors.onSecondaryContainer,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
