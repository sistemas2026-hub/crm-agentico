import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../../core/widgets/dexter_bloques.dart';
import 'hoja_de_reporte.dart';

/// La historia de la intervención, leída y nada más.
///
/// ESTA PANTALLA NO DECIDE NADA
/// ----------------------------
/// Cada evento llega del backend con su `etiqueta`, su `severidad` y su
/// `detalle` ya resueltos. Acá no hay un `if (tipo == 'bloqueo_campo')`: lo
/// único que se traduce es **severidad → estilo**, y eso es presentación, que es
/// lo que sí le toca a la aplicación.
///
/// Es la decisión 8 del objetivo, y el motivo de que sea así está medido: si el
/// backend mandara `color` e `icono`, dos frontends tendrían que compartir el
/// mismo diccionario visual, y un cambio de paleta —modo oscuro, contraste—
/// pasaría a ser un cambio de servidor.
///
/// Consecuencia práctica, y es la promesa entera: si mañana aparece un
/// `medicion_extraordinaria` que esta app nunca vio, se dibuja igual.
///
/// NO HAY BOTONES DE ACCIÓN, A PROPÓSITO
/// -------------------------------------
/// La Fase 1 es lectura. Un botón «Registrar avance» que abriera un formulario
/// incapaz de guardar sería peor que no tenerlo: el técnico lo llenaría en la
/// calle y lo perdería. Los botones entran cuando exista la cola de escritura.
class SeguimientoDeLaIntervencion extends StatefulWidget {
  const SeguimientoDeLaIntervencion({
    super.key,
    required this.seguimiento,
    required this.cargando,
    this.actualizado = true,
    this.alReportar,
    this.pendientesDeSubir = 0,
  });

  /// Lo que devolvió el backend, o `null` si **nunca se descargó** en este
  /// teléfono.
  ///
  /// `null` y «sin eventos» son dos cosas distintas y se dicen distinto: una
  /// línea de tiempo vacía se lee como «este trabajo no tiene historia», y lo
  /// que pasa en realidad es «no pude preguntar».
  final Map<String, dynamic>? seguimiento;

  final bool cargando;

  /// `false` cuando se está mostrando el espejo porque la última descarga
  /// falló. Lo que se muestra sigue siendo cierto; lo que no se puede afirmar
  /// es que esté al día.
  final bool actualizado;

  /// Qué hacer con un reporte que el técnico terminó de escribir.
  ///
  /// Se inyecta para que la sección se pueda probar sin base ni red. Si es
  /// `null`, la sección queda en **solo lectura** y no ofrece ningún botón —que
  /// es exactamente lo que hacía la Fase 1.
  final void Function(
    String momento,
    Map<String, dynamic> respuestas, {
    bool requiereNoc,
    bool detener,
  })?
  alReportar;

  /// Cuántos reportes de esta orden esperan subir. Se muestra porque un reporte
  /// guardado y sin subir es un hecho que el técnico tiene que poder ver: si no,
  /// no sabe si el NOC se enteró.
  final int pendientesDeSubir;

  @override
  State<SeguimientoDeLaIntervencion> createState() =>
      _SeguimientoDeLaIntervencionState();
}

class _SeguimientoDeLaIntervencionState
    extends State<SeguimientoDeLaIntervencion> {
  /// El momento cuya hoja está abierta, o `null` si no hay ninguna.
  String? _abierto;

  Map<String, dynamic>? get seguimiento => widget.seguimiento;
  bool get cargando => widget.cargando;
  bool get actualizado => widget.actualizado;

  @override
  Widget build(BuildContext context) {
    return DexterBloque(
      titulo: 'Seguimiento de la intervención',
      icono: Icons.timeline,
      children: _cuerpo(),
    );
  }

  List<Widget> _cuerpo() {
    if (cargando && seguimiento == null) {
      return <Widget>[
        Text(
          'Buscando la historia de este trabajo…',
          style: AppTypography.cuerpoChico,
        ),
      ];
    }

    // NUNCA se descargó. Se dice así, en vez de dibujar una historia vacía.
    if (seguimiento == null) {
      return <Widget>[
        Text(
          'El seguimiento todavía no está disponible en este dispositivo.',
          style: AppTypography.cuerpo,
        ),
        const SizedBox(height: AppSpacing.xs),
        Text(
          'Se descarga al abrir la orden con señal. Que no esté acá no quiere '
          'decir que el trabajo no tenga reportes.',
          style: AppTypography.cuerpoChico,
        ),
      ];
    }

    final List<dynamic> eventos =
        (seguimiento!['eventos'] as List<dynamic>?) ?? const <dynamic>[];

    return <Widget>[
      ..._resumen(),
      if (!actualizado) ...<Widget>[
        const SizedBox(height: AppSpacing.xs),
        Text(
          'No se pudo actualizar ahora: esto es lo último que se supo.',
          style: AppTypography.cuerpoChico,
        ),
      ],
      ..._acciones(),
      const SizedBox(height: AppSpacing.sm),
      if (eventos.isEmpty)
        Text(
          'Todavía no hay reportes de campo en esta orden.',
          style: AppTypography.cuerpoChico,
        )
      else
        for (final dynamic crudo in eventos)
          if (crudo is Map) _evento(Map<String, dynamic>.from(crudo)),
    ];
  }

  /// Los botones, y la hoja del que esté abierto.
  ///
  /// SOLO SE OFRECE LO QUE LA MÁQUINA PERMITE
  /// ----------------------------------------
  /// La lista no sale de lo que sea cómodo mostrar: sale de `formularios`, que es
  /// lo que el backend declaró para este tipo de trabajo, y de
  /// `momentos_registrados`, que dice qué ya ocurrió. Un INICIO no se ofrece dos
  /// veces porque el servidor lo rechazaría, y un botón que lleva a un rechazo es
  /// peor que no tenerlo: el técnico escribe el reporte en la calle y lo pierde.
  ///
  /// Si no hay a quién entregar el reporte (`alReportar == null`), no hay
  /// botones. Así la sección sigue sirviendo como pantalla de lectura.
  List<Widget> _acciones() {
    if (widget.alReportar == null) {
      return const <Widget>[];
    }

    final Map<String, dynamic> formularios =
        _mapa(seguimiento!['formularios']) ?? <String, dynamic>{};
    final List<dynamic> yaOcurrio =
        (seguimiento!['momentos_registrados'] as List<dynamic>?) ??
        const <dynamic>[];
    final bool huboInicio = yaOcurrio.contains('inicio_campo');

    final List<Widget> botones = <Widget>[];
    for (final (String momento, String texto) opcion in <(String, String)>[
      ('inicio', 'Registrar inicio'),
      ('avance', 'Registrar avance'),
      ('bloqueo', 'Reportar bloqueo'),
      ('cierre', 'Cerrar intervención'),
    ]) {
      final String momento = opcion.$1;
      // El tipo de trabajo tiene que declarar ese momento.
      if (!formularios.containsKey(momento)) {
        continue;
      }
      // El INICIO solo antes del primer INICIO.
      if (momento == 'inicio' && huboInicio) {
        continue;
      }
      botones.add(
        DexterAccionRapida(
          texto: opcion.$2,
          icono: _icono(momento),
          alTocar: () =>
              setState(() => _abierto = _abierto == momento ? null : momento),
        ),
      );
    }

    return <Widget>[
      if (widget.pendientesDeSubir > 0) ...<Widget>[
        const SizedBox(height: AppSpacing.xs),
        Text(
          widget.pendientesDeSubir == 1
              ? '1 reporte escrito acá todavía no subió.'
              : '${widget.pendientesDeSubir} reportes escritos acá todavía no '
                    'subieron.',
          style: AppTypography.etiquetaChica,
        ),
      ],
      if (botones.isNotEmpty) ...<Widget>[
        const SizedBox(height: AppSpacing.sm),
        Wrap(
          spacing: AppSpacing.xs,
          runSpacing: AppSpacing.xs,
          children: botones,
        ),
      ],
      if (_abierto != null) ...<Widget>[
        const SizedBox(height: AppSpacing.sm),
        HojaDeReporte(
          momento: _abierto!,
          titulo: _tituloDelMomento(_abierto!),
          campos: _camposDe(formularios, _abierto!),
          alGuardar:
              (
                Map<String, dynamic> respuestas, {
                bool requiereNoc = false,
                bool detener = true,
              }) {
                widget.alReportar!(
                  _abierto!,
                  respuestas,
                  requiereNoc: requiereNoc,
                  detener: detener,
                );
                setState(() => _abierto = null);
              },
        ),
      ],
    ];
  }

  /// Los campos crudos que el backend declaró para ese momento.
  ///
  /// Se pasan TAL CUAL a la hoja, que los interpreta con el mismo lector que el
  /// resto de la aplicación. Acá no se mira qué campos son.
  List<Map<String, dynamic>> _camposDe(
    Map<String, dynamic> formularios,
    String momento,
  ) {
    final Map<String, dynamic>? form = _mapa(formularios[momento]);
    final List<dynamic> campos =
        (form?['campos'] as List<dynamic>?) ?? const <dynamic>[];
    return <Map<String, dynamic>>[
      for (final dynamic c in campos)
        if (c is Map) Map<String, dynamic>.from(c),
    ];
  }

  static String _tituloDelMomento(String momento) {
    switch (momento) {
      case 'inicio':
        return 'Registrar el inicio';
      case 'bloqueo':
        return 'Reportar un bloqueo';
      case 'cierre':
        return 'Cerrar la intervención';
      default:
        return 'Registrar un avance';
    }
  }

  static IconData _icono(String momento) {
    switch (momento) {
      case 'inicio':
        return Icons.play_arrow;
      case 'bloqueo':
        return Icons.pause_circle_outline;
      case 'cierre':
        return Icons.check_circle_outline;
      default:
        return Icons.add_comment_outlined;
    }
  }

  /// El último reporte y la salud, los dos tal como los nombró el backend.
  List<Widget> _resumen() {
    final Map<String, dynamic>? ultimo = _mapa(seguimiento!['ultimo_reporte']);
    final Map<String, dynamic>? salud = _mapa(seguimiento!['salud']);
    final int? sincronizado = seguimiento!['sincronizado_en'] as int?;

    return <Widget>[
      Wrap(
        spacing: AppSpacing.xs,
        runSpacing: AppSpacing.xs,
        children: <Widget>[
          // La etiqueta de la salud viene del servidor porque el TEXTO es el
          // veredicto: «sin sincronización reciente» no es lo mismo que «no
          // reportó». Acá solo se elige cómo se ve.
          if (salud != null && (salud['etiqueta'] ?? '').toString().isNotEmpty)
            _pastilla(
              (salud['etiqueta']).toString(),
              _severidadDeSalud((salud['tipo'] ?? '').toString()),
            ),
          if (ultimo != null)
            DexterPastilla.neutra(texto: _textoDelUltimo(ultimo)),
        ],
      ),
      if (sincronizado != null) ...<Widget>[
        const SizedBox(height: AppSpacing.xs),
        Text(
          'Última sincronización: ${_hora(DateTime.fromMillisecondsSinceEpoch(sincronizado))}',
          style: AppTypography.etiquetaChica,
        ),
      ],
    ];
  }

  Widget _evento(Map<String, dynamic> evento) {
    final String etiqueta = (evento['etiqueta'] ?? evento['tipo'] ?? '—')
        .toString();
    final String severidad = (evento['severidad'] ?? 'info').toString();
    final String quien = (evento['quien'] ?? '').toString();
    final DateTime? recibido = _fecha(evento['recibido_en']);
    final DateTime? enElTelefono = _fecha(evento['capturado_en_dispositivo']);
    final List<dynamic> detalle =
        (evento['detalle'] as List<dynamic>?) ?? const <dynamic>[];
    final Map<String, dynamic> datos =
        _mapa(evento['datos']) ?? <String, dynamic>{};

    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: Container(
        padding: const EdgeInsets.all(AppSpacing.sm),
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
                _pastilla(etiqueta, severidad),
                const Spacer(),
                if (recibido != null)
                  Text(_hora(recibido), style: AppTypography.etiquetaChica),
              ],
            ),
            if (quien.isNotEmpty) ...<Widget>[
              const SizedBox(height: 2),
              Text(quien, style: AppTypography.etiquetaChica),
            ],

            // El detalle de un reporte, leído con el esquema que tenía cuando se
            // capturó. Los títulos vienen de ahí: esta pantalla no sabe qué
            // campos existen ni necesita saberlo.
            for (final dynamic fila in detalle)
              if (fila is Map) ...<Widget>[
                const SizedBox(height: AppSpacing.xs),
                _dato(
                  (fila['titulo'] ?? fila['id'] ?? '').toString(),
                  _valorLegible(fila['valor']),
                ),
              ],

            // Los hechos del sistema traen `datos` en vez de `detalle`: el
            // backend expone solo las claves que decidió mostrar.
            for (final String clave in datos.keys)
              if (datos[clave] != null) ...<Widget>[
                const SizedBox(height: AppSpacing.xs),
                _dato(_humanizar(clave), _valorLegible(datos[clave])),
              ],

            // Las dos horas, cuando difieren. Es la decisión del objetivo hecha
            // visible: lo que gobierna el seguimiento es la llegada al
            // servidor, y la del teléfono está para reconstruir la historia.
            if (enElTelefono != null && recibido != null) ...<Widget>[
              const SizedBox(height: AppSpacing.xs),
              Text(
                _demora(enElTelefono, recibido),
                style: AppTypography.etiquetaChica,
              ),
            ],
          ],
        ),
      ),
    );
  }

  /// Una fila «título: valor», con la tipografía del diseño.
  ///
  /// El título lo pone el esquema del tipo de trabajo, no esta pantalla: por eso
  /// se dibuja tal como llegó, sin traducirlo ni acortarlo.
  Widget _dato(String titulo, String valor) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Expanded(
          flex: 2,
          child: Text(titulo, style: AppTypography.etiquetaChica),
        ),
        const SizedBox(width: AppSpacing.xs),
        Expanded(flex: 3, child: Text(valor, style: AppTypography.cuerpoChico)),
      ],
    );
  }

  // --- Lo único que esta pantalla traduce ---------------------------------

  /// Severidad → estilo. El único mapeo que vive en la aplicación.
  Widget _pastilla(String texto, String severidad) {
    switch (severidad) {
      case 'problema':
        return DexterPastilla.critica(texto: texto);
      case 'atencion':
        return DexterPastilla.alerta(texto: texto);
      case 'en_regla':
        return DexterPastilla.enRegla(texto: texto);
      default:
        // Una severidad que esta versión no conoce se dibuja neutra en vez de
        // romperse. Degradar es parte del contrato: el backend puede agregar
        // valores sin esperar a que se publique la app.
        return DexterPastilla.neutra(texto: texto);
    }
  }

  /// La salud del seguimiento usa los nombres de su propio servicio.
  String _severidadDeSalud(String tipo) {
    switch (tipo) {
      case 'vencido':
        return 'problema';
      case 'pausado_noc':
      case 'sin_contacto_reciente':
        return 'atencion';
      case 'al_dia':
        return 'en_regla';
      default:
        return 'info';
    }
  }

  String _textoDelUltimo(Map<String, dynamic> ultimo) {
    final String etiqueta = (ultimo['etiqueta'] ?? '').toString();
    final Object? minutos = ultimo['minutos_desde_que_lo_recibimos'];
    if (minutos is int) {
      return '$etiqueta · hace $minutos min';
    }
    return etiqueta.isEmpty ? 'Sin reportes' : etiqueta;
  }

  String _demora(DateTime enElTelefono, DateTime recibido) {
    final int minutos = recibido.difference(enElTelefono).inMinutes;
    if (minutos < 2) {
      return 'Escrito y recibido a la misma hora';
    }
    final String cuanto = minutos >= 60
        ? '${minutos ~/ 60} h ${minutos % 60} min'
        : '$minutos min';
    return 'Escrito en el teléfono a las ${_hora(enElTelefono)} · '
        'demora de sincronización: $cuanto';
  }

  // --- Ayudas de formato --------------------------------------------------

  static Map<String, dynamic>? _mapa(Object? valor) =>
      valor is Map ? Map<String, dynamic>.from(valor) : null;

  static DateTime? _fecha(Object? valor) {
    if (valor is! String || valor.isEmpty) {
      return null;
    }
    return DateTime.tryParse(valor)?.toLocal();
  }

  static String _hora(DateTime cuando) {
    final String hh = cuando.hour.toString().padLeft(2, '0');
    final String mm = cuando.minute.toString().padLeft(2, '0');
    return '$hh:$mm';
  }

  static String _valorLegible(Object? valor) {
    if (valor == null) {
      return '—';
    }
    if (valor is bool) {
      return valor ? 'Sí' : 'No';
    }
    return valor.toString();
  }

  /// `que_se_hizo` → `Que se hizo`. Para las claves de los hechos del sistema,
  /// que no traen título propio.
  static String _humanizar(String clave) {
    final String conEspacios = clave.replaceAll('_', ' ');
    if (conEspacios.isEmpty) {
      return clave;
    }
    return conEspacios[0].toUpperCase() + conEspacios.substring(1);
  }
}
