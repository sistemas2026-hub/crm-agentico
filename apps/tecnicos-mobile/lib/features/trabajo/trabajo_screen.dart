import 'package:flutter/material.dart';

import '../../core/estado/ordenes_jornada.dart';
import '../../core/mock/field_mock_data.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/dexter_empty_state.dart';
import 'estado_trabajo.dart';
import 'trabajo_vista.dart';
import 'widgets/tarjeta_trabajo.dart';

/// La lista de trabajos del técnico.
///
/// Las órdenes no las carga esta pantalla: las comparte con Inicio a través de
/// [OrdenesJornada]. Acá viven solo las decisiones de esta pantalla — qué
/// pestaña está elegida, qué filtro, y dónde quedó el scroll.
class TrabajoScreen extends StatefulWidget {
  const TrabajoScreen({
    super.key,
    required this.ordenes,
    required this.abrirTrabajo,
    this.mostrarDatosFuturos = FieldMockData.modoDemo,
  });

  final OrdenesJornada ordenes;

  /// Abre el trabajo y devuelve el control cuando el técnico vuelve.
  final Future<void> Function(BuildContext contexto, TrabajoVista trabajo) abrirTrabajo;

  final bool mostrarDatosFuturos;

  @override
  State<TrabajoScreen> createState() => _TrabajoScreenState();
}

class _TrabajoScreenState extends State<TrabajoScreen> {
  PestanaTrabajo _pestana = PestanaTrabajo.todos;
  SegmentoEntidad _segmento = SegmentoEntidad.ordenes;

  /// Lo que el técnico escribió en el buscador. Filtra de verdad, y sobre lo
  /// que ya está en el teléfono: sin señal también busca.
  final TextEditingController _busqueda = TextEditingController();

  @override
  void initState() {
    super.initState();
    widget.ordenes.addListener(_alCambiar);
    // La primera pantalla que se abre dispara la carga; la segunda encuentra
    // los datos ya cargados.
    widget.ordenes.asegurarCargado();
  }

  @override
  void dispose() {
    widget.ordenes.removeListener(_alCambiar);
    _busqueda.dispose();
    super.dispose();
  }

  void _alCambiar() {
    if (mounted) setState(() {});
  }

  /// Lo que se ve: el segmento, el filtro de estado y la búsqueda, en ese
  /// orden. Ninguno de los tres toca la base: filtran la lista que ya está.
  List<TrabajoVista> _visibles() {
    final ahora = DateTime.now();
    final texto = _busqueda.text.trim().toLowerCase();

    return widget.ordenes.trabajos
        .where(_segmento.incluye)
        .where((TrabajoVista t) =>
            perteneceA(_pestana, t.estado, t.compromiso, ahora: ahora))
        .where((TrabajoVista t) => texto.isEmpty || _coincide(t, texto))
        .toList();
  }

  /// Busca por lo que el técnico tiene a mano para reconocer un trabajo: el
  /// número, el cliente, la dirección y el tipo.
  static bool _coincide(TrabajoVista t, String texto) {
    final campos = <String>[
      t.numero?.toString() ?? '',
      t.clienteNombre,
      t.direccion,
      t.tipoNombre,
    ];
    return campos.any((String c) => c.toLowerCase().contains(texto));
  }

  @override
  Widget build(BuildContext context) {
    if (widget.ordenes.cargando) {
      return const ColoredBox(
        color: AppColors.fondo,
        child: Center(child: CircularProgressIndicator()),
      );
    }

    final visibles = _visibles();

    return ColoredBox(
      color: AppColors.fondo,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          _franjaLocal(),
          _encabezado(),
          _segmentos(),
          _buscador(),
          _filtros(),
          Expanded(
            child: RefreshIndicator(
              onRefresh: widget.ordenes.refrescar,
              child: widget.ordenes.fallo
                  ? ListView(
                      children: const <Widget>[
                        SizedBox(height: AppSpacing.xl),
                        DexterEmptyState(
                          icono: Icons.error_outline,
                          titulo: 'No se pudieron leer tus trabajos',
                          mensaje: 'Deslizá hacia abajo para volver a intentar.',
                          esAdvertencia: true,
                        ),
                      ],
                    )
                  : visibles.isEmpty
                      ? ListView(
                          children: <Widget>[
                            const SizedBox(height: AppSpacing.xl),
                            DexterEmptyState(
                              icono: _iconoVacio,
                              titulo: _tituloVacio,
                              mensaje: _mensajeVacio,
                            ),
                          ],
                        )
                      : ListView.builder(
                          key: PageStorageKey<String>('trabajos_${_pestana.name}'),
                          padding: const EdgeInsets.fromLTRB(
                            AppSpacing.margen,
                            AppSpacing.md,
                            AppSpacing.margen,
                            AppSpacing.xl,
                          ),
                          itemCount: visibles.length + 1,
                          itemBuilder: (BuildContext contexto, int i) {
                            // CAMPO-DATA-036 · El pie del diseño. La marca del
                            // último envío bueno todavía no la guarda la cola.
                            if (i == visibles.length) {
                              return _pieDeSincronizacion();
                            }
                            final trabajo = visibles[i];
                            return TarjetaTrabajo(
                              trabajo: trabajo,
                              mostrarDatosFuturos: widget.mostrarDatosFuturos,
                              onTap: () async {
                                await widget.abrirTrabajo(contexto, trabajo);
                                // Al volver, los datos pueden haber cambiado;
                                // la pestaña, el filtro y el scroll no.
                                await widget.ordenes.recargar();
                              },
                            );
                          },
                        ),
            ),
          ),
        ],
      ),
    );
  }

  /// El pie de la lista: cuándo se habló con el servidor por última vez.
  Widget _pieDeSincronizacion() {
    return Padding(
      padding: const EdgeInsets.only(top: AppSpacing.lg),
      child: Column(
        children: <Widget>[
          const Icon(Icons.check_circle, size: 20, color: AppColors.exito),
          const SizedBox(height: AppSpacing.xs),
          Text(
            'No hay más órdenes asignadas en este ciclo de despacho',
            textAlign: TextAlign.center,
            style: AppTypography.etiquetaChica,
          ),
          if (widget.mostrarDatosFuturos) ...<Widget>[
            const SizedBox(height: AppSpacing.xs),
            // CAMPO-DATA-036 · Cuándo se refrescó la cuadrilla.
            Text(
              'Último refresco de cuadrilla: '
              '${FieldMockData.ultimaSincronizacion.toLowerCase()}',
              textAlign: TextAlign.center,
              style: AppTypography.etiquetaChica.copyWith(
                color: AppColors.outline,
              ),
            ),
          ],
        ],
      ),
    );
  }

  /// La franja del diseño: cuántas órdenes hay en el teléfono y si lo que se
  /// registró ya viajó. Las dos cosas son reales.
  Widget _franjaLocal() {
    final int guardadas = widget.ordenes.trabajos.length;

    return Container(
      color: AppColors.surfaceContainerLow,
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.margen,
        vertical: 6,
      ),
      child: Row(
        children: <Widget>[
          const Icon(Icons.offline_pin, size: 14, color: AppColors.exitoTexto),
          const SizedBox(width: 6),
          Expanded(
            child: Text(
              '$guardadas ${guardadas == 1 ? 'OT sincronizada' : 'OTs sincronizadas'} '
              'localmente',
              style: AppTypography.etiquetaChica,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ),
          if (widget.mostrarDatosFuturos)
            // CAMPO-DATA-036 · Cuándo fue el último envío bueno.
            Text(
              'Sync ${FieldMockData.ultimaSincronizacion.toLowerCase()}',
              style: AppTypography.etiquetaChica.copyWith(
                color: AppColors.exitoTexto,
                fontWeight: FontWeight.w700,
              ),
            ),
        ],
      ),
    );
  }

  /// "Mi Trabajo" y cuántas órdenes tiene la jornada. Dato real.
  Widget _encabezado() {
    final int total = widget.ordenes.trabajos.length;

    return Padding(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.margen,
        AppSpacing.md,
        AppSpacing.margen,
        AppSpacing.sm,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text('Mi Trabajo', style: AppTypography.tituloGrande),
          Text(
            total == 1
                ? '1 orden asignada para la jornada de hoy'
                : '$total órdenes asignadas para la jornada de hoy',
            style: AppTypography.cuerpoChico,
          ),
        ],
      ),
    );
  }

  /// El buscador del diseño. El lector de código de barras todavía no existe:
  /// se ve en la demostración y avisa que falta, en vez de fingir que escanea.
  Widget _buscador() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.margen,
        0,
        AppSpacing.margen,
        AppSpacing.sm,
      ),
      child: Row(
        children: <Widget>[
          Expanded(
            child: Container(
              height: AppSpacing.objetivoTactil,
              decoration: const BoxDecoration(
                color: AppColors.surfaceContainerLowest,
                borderRadius: AppRadius.brTarjeta,
              ),
              child: TextField(
                controller: _busqueda,
                onChanged: (_) => setState(() {}),
                style: AppTypography.cuerpo,
                decoration: InputDecoration(
                  border: InputBorder.none,
                  isDense: true,
                  hintText: 'Buscar por cliente, dirección u OT',
                  hintStyle: AppTypography.cuerpoChico,
                  prefixIcon: const Icon(Icons.search, size: 18, color: AppColors.outline),
                  suffixIcon: _busqueda.text.isEmpty
                      ? null
                      : IconButton(
                          icon: const Icon(Icons.close, size: 18),
                          onPressed: () => setState(_busqueda.clear),
                        ),
                ),
              ),
            ),
          ),
          if (widget.mostrarDatosFuturos) ...<Widget>[
            const SizedBox(width: AppSpacing.sm),
            // CAMPO-DATA-044 · Lector de código en el equipo del cliente.
            _BotonCuadrado(
              icono: Icons.qr_code_scanner,
              etiquetaSemantica: 'Escanear equipo',
              alTocar: () => ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text(FieldMockData.escanerPendiente)),
              ),
            ),
          ],
        ],
      ),
    );
  }

  /// El control segmentado del diseño: de qué se está hablando. No es lo
  /// mismo una OT que un ticket que una instalación, y la aplicación no los
  /// mezcla en un mismo contador.
  Widget _segmentos() {
    int cuantos(SegmentoEntidad segmento) =>
        widget.ordenes.trabajos.where(segmento.incluye).length;

    return Container(
      margin: const EdgeInsets.fromLTRB(
        AppSpacing.margen,
        0,
        AppSpacing.margen,
        AppSpacing.sm,
      ),
      padding: const EdgeInsets.all(AppSpacing.xs),
      decoration: const BoxDecoration(
        color: AppColors.surfaceContainer,
        borderRadius: AppRadius.brTarjeta,
      ),
      child: Row(
        children: <Widget>[
          for (final SegmentoEntidad segmento in SegmentoEntidad.values)
            Expanded(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 2),
                child: _Pestana(
                  texto: segmento.etiqueta,
                  cantidad: cuantos(segmento),
                  activa: segmento == _segmento,
                  colorContador: segmento == _segmento
                      ? AppColors.primary
                      : AppColors.surfaceContainerHighest,
                  onTap: () => setState(() => _segmento = segmento),
                ),
              ),
            ),
        ],
      ),
    );
  }

  /// Los filtros de estado, en fila, y debajo la cinta que explica de qué
  /// entidad se habla. El diseño la pone ahí a propósito: confundir una OT con
  /// un ticket es la confusión que más cuesta en campo.
  Widget _filtros() {
    int cuantos(PestanaTrabajo filtro) {
      final ahora = DateTime.now();
      return widget.ordenes.trabajos
          .where(_segmento.incluye)
          .where((TrabajoVista t) =>
              perteneceA(filtro, t.estado, t.compromiso, ahora: ahora))
          .length;
    }

    return Container(
      decoration: const BoxDecoration(
        color: AppColors.surface,
        border: Border(bottom: BorderSide(color: AppColors.surfaceContainerHigh)),
      ),
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: AppSpacing.margen),
            child: Row(
              children: <Widget>[
                for (final PestanaTrabajo filtro in PestanaTrabajo.values) ...<Widget>[
                  if (filtro != PestanaTrabajo.values.first)
                    const SizedBox(width: AppSpacing.sm),
                  _ChipFiltro(
                    texto: filtro == PestanaTrabajo.todos
                        ? filtro.etiqueta
                        : '${filtro.etiqueta} (${cuantos(filtro)})',
                    activo: _pestana == filtro,
                    onTap: () => setState(() => _pestana = filtro),
                  ),
                ],
              ],
            ),
          ),
          const SizedBox(height: AppSpacing.sm),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: AppSpacing.margen),
            child: _cintaDeArquitectura(),
          ),
        ],
      ),
    );
  }

  /// Qué significa lo que se está mirando. Texto fijo, no un dato.
  Widget _cintaDeArquitectura() {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.sm),
      decoration: const BoxDecoration(
        color: AppColors.surfaceContainerLow,
        borderRadius: AppRadius.brCampo,
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          const Icon(Icons.account_tree, size: 14, color: AppColors.secondary),
          const SizedBox(width: 6),
          Expanded(
            child: Text.rich(
              TextSpan(
                children: <InlineSpan>[
                  TextSpan(
                    text: 'Arquitectura de Campo · ',
                    style: AppTypography.etiquetaChica.copyWith(
                      color: AppColors.onSurface,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  TextSpan(text: _segmento.explicacion),
                ],
              ),
              style: AppTypography.etiquetaChica,
            ),
          ),
        ],
      ),
    );
  }


  IconData get _iconoVacio => switch (_pestana) {
        PestanaTrabajo.todos => Icons.inbox_outlined,
        PestanaTrabajo.pendientes => Icons.inbox_outlined,
        PestanaTrabajo.enProceso => Icons.play_circle_outline,
        PestanaTrabajo.finalizadas => Icons.done_all,
        PestanaTrabajo.conNovedad => Icons.report_outlined,
      };

  String get _tituloVacio {
    if (_busqueda.text.trim().isNotEmpty) {
      return 'Sin resultados para "${_busqueda.text.trim()}"';
    }
    return switch (_pestana) {
      PestanaTrabajo.todos => _segmento == SegmentoEntidad.ordenes
          ? 'No tenés trabajos asignados'
          : 'No hay ${_segmento.etiqueta.toLowerCase()} en tu jornada',
      PestanaTrabajo.pendientes => 'No tenés trabajos pendientes',
      PestanaTrabajo.enProceso => 'No tenés ningún trabajo empezado',
      PestanaTrabajo.finalizadas => 'Todavía no terminaste ninguno',
      PestanaTrabajo.conNovedad => 'Ninguno con novedad',
    };
  }

  String? get _mensajeVacio {
    if (_busqueda.text.trim().isNotEmpty) {
      return 'Se busca por cliente, dirección, tipo y número de OT, sobre lo '
          'que ya está en el teléfono.';
    }
    return switch (_pestana) {
      PestanaTrabajo.todos => 'Deslizá hacia abajo para actualizar.',
      PestanaTrabajo.pendientes => 'Deslizá hacia abajo para actualizar.',
      PestanaTrabajo.enProceso =>
        'Cuando marques que vas en camino, el trabajo aparece acá.',
      PestanaTrabajo.finalizadas => null,
      PestanaTrabajo.conNovedad =>
        'Acá aparece lo devuelto para corregir o cancelado.',
    };
  }
}

class _Pestana extends StatelessWidget {
  const _Pestana({
    required this.texto,
    required this.cantidad,
    required this.activa,
    required this.colorContador,
    required this.onTap,
  });

  final String texto;
  final int cantidad;
  final bool activa;
  final Color colorContador;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final color = activa ? AppColors.primary : AppColors.onSurfaceVariant;

    return Semantics(
      button: true,
      selected: activa,
      label: '$texto, $cantidad',
      excludeSemantics: true,
      child: InkWell(
        onTap: onTap,
        borderRadius: AppRadius.brCampo,
        child: Container(
          constraints: const BoxConstraints(minHeight: AppSpacing.objetivoTactil),
          alignment: Alignment.center,
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.sm),
          decoration: BoxDecoration(
            color: activa ? AppColors.surfaceContainerLowest : Colors.transparent,
            borderRadius: AppRadius.brCampo,
            boxShadow: activa ? AppTheme.sombraNivel1 : null,
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Flexible(
                child: Text(
                  texto,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: AppTypography.etiqueta.copyWith(
                    color: color,
                    fontWeight: activa ? FontWeight.w700 : FontWeight.w500,
                  ),
                ),
              ),
              const SizedBox(width: 6),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
                decoration: BoxDecoration(
                  color: colorContador,
                  borderRadius: BorderRadius.circular(AppRadius.circulo),
                ),
                child: Text(
                  '$cantidad',
                  style: AppTypography.etiquetaChica.copyWith(
                    fontSize: 11,
                    color: colorContador == AppColors.surfaceContainerHighest
                        ? AppColors.onSurfaceVariant
                        : AppColors.onPrimary,
                    fontWeight: FontWeight.w700,
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

/// Pastilla de filtro por clase de trabajo.
class _ChipFiltro extends StatelessWidget {
  const _ChipFiltro({
    required this.texto,
    required this.activo,
    required this.onTap,
  });

  final String texto;
  final bool activo;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      selected: activo,
      label: 'Filtrar por $texto',
      excludeSemantics: true,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(AppRadius.circulo),
        child: Container(
          height: 40,
          alignment: Alignment.center,
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
          decoration: BoxDecoration(
            color: activo ? AppColors.primary : AppColors.surfaceContainerHigh,
            borderRadius: BorderRadius.circular(AppRadius.circulo),
            boxShadow: activo ? AppTheme.sombraNivel1 : null,
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Text(
                texto,
                style: AppTypography.etiquetaChica.copyWith(
                  color: activo ? AppColors.onPrimary : AppColors.onSurface,
                  fontWeight: FontWeight.w600,
                ),
              ),
              if (activo) ...<Widget>[
                const SizedBox(width: 6),
                Container(
                  width: 6,
                  height: 6,
                  decoration: const BoxDecoration(
                    color: AppColors.onPrimary,
                    shape: BoxShape.circle,
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

enum SegmentoEntidad {
  ordenes('Órdenes'),
  instalaciones('Instalaciones'),
  tickets('Tickets');

  const SegmentoEntidad(this.etiqueta);

  final String etiqueta;

  bool incluye(TrabajoVista trabajo) => switch (this) {
        SegmentoEntidad.ordenes => true,
        SegmentoEntidad.instalaciones =>
          trabajo.familia == FamiliaTrabajo.instalacion,
        SegmentoEntidad.tickets => trabajo.familia == FamiliaTrabajo.incidencia,
      };

  String get explicacion => switch (this) {
        SegmentoEntidad.ordenes =>
          'OT = Orden de Trabajo asignada para ejecución física en terreno.',
        SegmentoEntidad.instalaciones =>
          'Instalación = alta nueva de servicio; genera la OT que se ejecuta.',
        SegmentoEntidad.tickets =>
          'Ticket = reporte del cliente o del NOC; puede derivar en una OT.',
      };
}

/// Un botón cuadrado de acción, del alto de un campo.
class _BotonCuadrado extends StatelessWidget {
  const _BotonCuadrado({
    required this.icono,
    required this.etiquetaSemantica,
    required this.alTocar,
  });

  final IconData icono;
  final String etiquetaSemantica;
  final VoidCallback alTocar;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: etiquetaSemantica,
      child: Material(
        color: AppColors.surfaceContainerLowest,
        borderRadius: AppRadius.brTarjeta,
        child: InkWell(
          borderRadius: AppRadius.brTarjeta,
          onTap: alTocar,
          child: const SizedBox(
            width: AppSpacing.objetivoTactil,
            height: AppSpacing.objetivoTactil,
            child: Icon(Icons.qr_code_scanner, size: 20, color: AppColors.primary),
          ),
        ),
      ),
    );
  }
}
