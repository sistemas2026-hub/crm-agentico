import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';

import '../../core/storage/local_database.dart';
import '../../core/storage/secure_storage_service.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/dexter_bloques.dart';

/// Lo que le avisaron al técnico mientras no estaba mirando.
///
/// POR QUE ESTA PANTALLA EXISTE
/// ----------------------------
/// Medido el 04/10/2026: la aplicación no tenía **ninguna** forma de decirle
/// nada. No hay push y la cola solo corre cuando alguien toca la pantalla. Por
/// eso una devolución se avisaba por fuera del sistema, a mano.
///
/// Y la plataforma ya tenía el mecanismo: `/api/notifications/` es el único
/// despachador —el mismo que alimenta la campanita de la web— y campo era la
/// única parte que no lo usaba.
///
/// LO QUE ESTA PANTALLA NO RESUELVE, Y HAY QUE DECIRLO
/// ---------------------------------------------------
/// Que el técnico se entere **sin abrir la app**. Para eso hace falta push.
/// Esto le da el registro completo —qué pasó, cuándo, qué hay que rehacer— y
/// que no dependa de que alguien le escriba. El golpecito en el hombro es otra
/// capa.
class NotificacionesScreen extends StatefulWidget {
  const NotificacionesScreen({
    super.key,
    this.baseLocal,
    this.alAbrirOrden,
    this.ocultarSiVacio = false,
    this.margenSuperior = 0,
  });

  /// Inyectable para las pruebas: sin esto habría que montar una base real solo
  /// para dibujar una lista.
  final LocalDatabase? baseLocal;

  /// Qué hacer al tocar una que apunta a una orden. `null` deja la lista en
  /// lectura, que es lo correcto cuando quien la monta no sabe navegar.
  final void Function(String ordenId)? alAbrirOrden;

  /// Si no dibujar nada cuando no hay avisos.
  ///
  /// Embebida en Inicio va en `true`: un bloque que dice "No hay avisos" todos
  /// los días enseña a no mirar esa parte de la pantalla, y ese aprendizaje
  /// después se lleva puesto el aviso que sí importaba. Suelta va en `false`,
  /// porque entonces la pantalla entera quedaría en blanco sin explicar nada.
  final bool ocultarSiVacio;

  /// El aire de arriba, que solo corresponde cuando el bloque se dibuja.
  ///
  /// Lo pone el bloque y no quien lo monta a propósito: desde afuera no se
  /// puede saber si hay avisos sin volver a leer la base, y un `SizedBox`
  /// puesto por si acaso deja un hueco los días sin nada.
  final double margenSuperior;

  @override
  State<NotificacionesScreen> createState() => _NotificacionesScreenState();
}

class _NotificacionesScreenState extends State<NotificacionesScreen> {
  late final LocalDatabase _base = widget.baseLocal ?? LocalDatabase();

  List<Map<String, dynamic>> _filas = <Map<String, dynamic>>[];
  bool _cargando = true;
  String? _orgId;
  String? _profileId;

  StreamSubscription<LocalDatabaseChangeEvent>? _suscripcion;

  @override
  void initState() {
    super.initState();
    _traer();
    // Un aviso que llega por push mientras la pantalla está abierta tiene que
    // aparecer sin que nadie la refresque. Lo mismo cuando la cola baja los de
    // la plataforma: las dos cosas escriben `local_notificaciones`.
    _suscripcion = LocalDatabase.onDataChanged.listen((evento) {
      if (evento.tabla == 'local_notificaciones') _traer();
    });
  }

  @override
  void dispose() {
    _suscripcion?.cancel();
    super.dispose();
  }

  Future<void> _traer() async {
    try {
      final SecureStorageService almacen = SecureStorageService();
      _orgId = await almacen.getOrgId();
      _profileId = await almacen.getProfileId();
      if (_orgId == null || _profileId == null) {
        if (mounted) setState(() => _cargando = false);
        return;
      }
      final filas = await _base.leerNotificaciones(
        orgId: _orgId!,
        profileId: _profileId!,
      );
      if (!mounted) return;
      setState(() {
        _filas = filas;
        _cargando = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _cargando = false);
    }
  }

  Future<void> _leer(Map<String, dynamic> fila) async {
    final String id = (fila['id'] ?? '').toString();
    if (_orgId == null || _profileId == null || id.isEmpty) return;

    // Se marca ACÁ y en el acto. Sin señal queda marcado igual: el técnico ya
    // la leyó, y el servidor se entera cuando se pueda.
    if (fila['leida_en'] == null) {
      await _base.marcarNotificacionLeida(
        id: id,
        orgId: _orgId!,
        profileId: _profileId!,
      );
      await _traer();
    }

    final String enlace = (fila['enlace'] ?? '').toString();
    // `/ot/<id>` es el único formato que escribe el backend hoy. Si llegara otro
    // no se intenta adivinar: se deja la notificación leída y nada más.
    if (widget.alAbrirOrden != null && enlace.startsWith('/ot/')) {
      widget.alAbrirOrden!(enlace.substring(4));
    }
  }

  @override
  Widget build(BuildContext context) {
    // Mientras carga tampoco se dibuja: un bloque que aparece vacío y
    // desaparece medio segundo después empuja todo lo de abajo.
    if (widget.ocultarSiVacio && (_cargando || _filas.isEmpty)) {
      return const SizedBox.shrink();
    }

    final Widget bloque = DexterBloque(
      titulo: 'Avisos',
      icono: Icons.notifications_none,
      children: _cuerpo(),
    );
    if (widget.margenSuperior <= 0) return bloque;
    return Padding(
      padding: EdgeInsets.only(top: widget.margenSuperior),
      child: bloque,
    );
  }

  List<Widget> _cuerpo() {
    if (_cargando) {
      return <Widget>[
        Text('Buscando…', style: AppTypography.cuerpoChico),
      ];
    }
    if (_filas.isEmpty) {
      return <Widget>[
        Text('No hay avisos.', style: AppTypography.cuerpo),
        const SizedBox(height: AppSpacing.xs),
        Text(
          'Acá aparece cuando el supervisor devuelve un trabajo. Se actualiza '
          'al sincronizar.',
          style: AppTypography.etiquetaChica,
        ),
      ];
    }

    return <Widget>[
      for (final Map<String, dynamic> f in _filas) _unAviso(f),
    ];
  }

  Widget _unAviso(Map<String, dynamic> fila) {
    final bool sinLeer = fila['leida_en'] == null;
    final Map<String, dynamic> datos = _datos(fila['datos_json']);
    final String titulo = (fila['titulo'] ?? '').toString();
    final List<dynamic> rehacer =
        (datos['rehacer'] as List<dynamic>?) ?? const <dynamic>[];
    final String observacion = (datos['observacion'] ?? '').toString();

    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: InkWell(
        onTap: () => _leer(fila),
        child: Container(
          padding: const EdgeInsets.all(AppSpacing.sm),
          decoration: BoxDecoration(
            // Sin leer se distingue por el fondo y no solo por un punto: a
            // pleno sol un punto de 8 px no se ve.
            color: sinLeer
                ? AppColors.primaryFixed
                : AppColors.surfaceContainerLowest,
            borderRadius: AppRadius.brTarjeta,
            boxShadow: AppTheme.sombraNivel1,
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Row(
                children: <Widget>[
                  if (sinLeer) ...<Widget>[
                    DexterPastilla.alerta(texto: 'Nuevo'),
                    const SizedBox(width: AppSpacing.xs),
                  ],
                  Expanded(
                    child: Text(
                      _queEs(fila['verbo']?.toString() ?? '', titulo, datos),
                      style: AppTypography.cuerpo,
                    ),
                  ),
                ],
              ),
              if (observacion.isNotEmpty) ...<Widget>[
                const SizedBox(height: 2),
                Text('«$observacion»', style: AppTypography.cuerpoChico),
              ],
              if (rehacer.isNotEmpty) ...<Widget>[
                const SizedBox(height: 2),
                Text(
                  'Hay que volver a tomar: ${rehacer.join(', ')}',
                  style: AppTypography.etiquetaChica,
                ),
              ],
              const SizedBox(height: 2),
              Text(_cuando(fila['creada_en']), style: AppTypography.etiquetaChica),
            ],
          ),
        ),
      ),
    );
  }

  /// El verbo del backend, en palabras.
  ///
  /// La traducción vive acá y no en el servidor porque es presentación: el mismo
  /// `trabajo_devuelto` lo lee la web con sus palabras y el teléfono con las
  /// suyas. Un verbo que esta versión no conoce se muestra con el nombre de la
  /// entidad, en vez de esconderse.
  static String _queEs(
    String verbo,
    String titulo, [
    Map<String, dynamic> datos = const <String, dynamic>{},
  ]) {
    switch (verbo) {
      case 'trabajo_devuelto':
        // SE ARMA CON EL NUMERO, NO CON EL TITULO QUE VINO.
        //
        // Los dos caminos traen titulos distintos: la sincronizacion manda
        // `entity_name` («OT #1844») y el push manda el asunto del aviso («OT
        // #1844 devuelta»). Pegarle «Te devolvieron la» delante al segundo
        // produce «Te devolvieron la OT #1844 devuelta». Se vio en el emulador,
        // no leyendo el codigo.
        //
        // Con `orden_numero` la frase sale igual por los dos caminos, porque
        // depende del DATO y no de una cadena que alguien compuso para otra
        // cosa.
        final Object? numero = datos['orden_numero'];
        if (numero != null) return 'Te devolvieron la OT #$numero';
        return 'Te devolvieron la $titulo';
      default:
        return titulo.isEmpty ? 'Aviso' : titulo;
    }
  }

  static Map<String, dynamic> _datos(Object? crudo) {
    if (crudo is! String || crudo.isEmpty) return <String, dynamic>{};
    try {
      final Object? d = jsonDecode(crudo);
      return d is Map ? Map<String, dynamic>.from(d) : <String, dynamic>{};
    } catch (_) {
      return <String, dynamic>{};
    }
  }

  static String _cuando(Object? iso) {
    final DateTime? f = DateTime.tryParse(iso?.toString() ?? '')?.toLocal();
    if (f == null) return '';
    final String dia = f.day.toString().padLeft(2, '0');
    final String mes = f.month.toString().padLeft(2, '0');
    final String hora = f.hour.toString().padLeft(2, '0');
    final String min = f.minute.toString().padLeft(2, '0');
    return '$dia/$mes · $hora:$min';
  }
}
