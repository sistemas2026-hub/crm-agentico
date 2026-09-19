import 'package:flutter/material.dart';

import '../../core/estado/ordenes_jornada.dart';
import '../../core/mock/field_mock_data.dart';
import '../../core/sync/sync_presentacion.dart';
import '../../core/sync/sync_queue_service.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/dexter_card.dart';
import '../../core/widgets/dexter_empty_state.dart';
import '../../core/widgets/dexter_metric_tile.dart';
import '../../core/widgets/dexter_sync_badge.dart';
import '../trabajo/seleccion_jornada.dart';
import '../trabajo/trabajo_vista.dart';
import '../trabajo/widgets/tarjeta_trabajo.dart';

/// El resumen de la jornada.
///
/// Contesta seis preguntas y ninguna más: qué tengo, qué terminé, qué me
/// falta, qué estoy haciendo ahora, qué viene después y si quedó algo sin
/// enviar. Todo eso sale de las mismas órdenes que muestra Trabajo —la lista
/// es compartida— y de la misma cola de sincronización que ya lee el
/// contenedor.
class InicioScreen extends StatefulWidget {
  const InicioScreen({
    super.key,
    required this.ordenes,
    required this.abrirTrabajo,
    required this.nombreTecnico,
    this.resumenSincronizacion,
    this.onVerTodos,
    this.mostrarDatosFuturos = FieldMockData.modoDemo,
  });

  final OrdenesJornada ordenes;
  final Future<void> Function(BuildContext contexto, TrabajoVista trabajo) abrirTrabajo;

  /// Nombre real de quien tiene la sesión abierta.
  final String nombreTecnico;

  /// Estado de la cola, tal como lo tiene el contenedor. No se vuelve a
  /// consultar el servicio desde acá.
  final SyncSummary? resumenSincronizacion;

  /// Llevar a la pestaña Trabajo.
  final VoidCallback? onVerTodos;

  final bool mostrarDatosFuturos;

  @override
  State<InicioScreen> createState() => _InicioScreenState();
}

class _InicioScreenState extends State<InicioScreen> {
  @override
  void initState() {
    super.initState();
    widget.ordenes.addListener(_alCambiar);
    widget.ordenes.asegurarCargado();
  }

  @override
  void dispose() {
    widget.ordenes.removeListener(_alCambiar);
    super.dispose();
  }

  void _alCambiar() {
    if (mounted) setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    if (widget.ordenes.cargando) {
      return const ColoredBox(
        color: AppColors.fondo,
        child: Center(child: CircularProgressIndicator()),
      );
    }

    final trabajos = widget.ordenes.trabajos;
    final enCurso = SeleccionJornada.enCursoDestacado(trabajos);
    final proximos = SeleccionJornada.proximos(trabajos, desde: DateTime.now());
    final sinFecha = SeleccionJornada.activosSinFecha(trabajos);

    return ColoredBox(
      color: AppColors.fondo,
      child: RefreshIndicator(
        onRefresh: widget.ordenes.refrescar,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(
            AppSpacing.margen,
            AppSpacing.lg,
            AppSpacing.margen,
            AppSpacing.xl,
          ),
          children: <Widget>[
            _saludo(),
            const SizedBox(height: AppSpacing.lg),
            if (widget.ordenes.fallo) ...<Widget>[
              const DexterEmptyState(
                icono: Icons.error_outline,
                titulo: 'No se pudieron leer tus trabajos',
                mensaje: 'Deslizá hacia abajo para volver a intentar.',
                esAdvertencia: true,
              ),
            ] else ...<Widget>[
              _metricas(trabajos),
              const SizedBox(height: AppSpacing.lg),
              _seccion('Trabajo en curso'),
              _trabajoEnCurso(enCurso, trabajos),
              const SizedBox(height: AppSpacing.lg),
              _seccion('Próximos trabajos', accion: widget.onVerTodos),
              _proximos(proximos, sinFecha),
            ],
            const SizedBox(height: AppSpacing.lg),
            if (widget.mostrarDatosFuturos) ...<Widget>[
              _seccion('Mi kit'),
              _kit(),
              const SizedBox(height: AppSpacing.lg),
            ],
            _seccion('Sincronización'),
            _sincronizacion(),
          ],
        ),
      ),
    );
  }

  Widget _saludo() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Text('Hola, ${widget.nombreTecnico}', style: AppTypography.tituloGrande),
        const SizedBox(height: AppSpacing.xs),
        if (widget.mostrarDatosFuturos)
          // CAMPO-DATA-006 y CAMPO-DATA-007: turno y cuadrilla.
          Text(
            '${FieldMockData.turno} · ${FieldMockData.cuadrilla}',
            style: AppTypography.etiqueta,
          )
        else
          Text(_fechaDeHoy(), style: AppTypography.etiqueta),
      ],
    );
  }

  Widget _metricas(List<TrabajoVista> trabajos) {
    final pendientes = SeleccionJornada.pendientes(trabajos).length;
    final terminados = SeleccionJornada.terminados(trabajos).length;

    return DexterCard(
      child: Row(
        children: <Widget>[
          Expanded(
            child: DexterMetricTile(
              etiqueta: 'Asignados',
              valor: '${trabajos.length}',
              icono: Icons.assignment_outlined,
              compacto: true,
            ),
          ),
          Expanded(
            child: DexterMetricTile(
              etiqueta: 'Terminados',
              valor: '$terminados',
              icono: Icons.check_circle_outline,
              compacto: true,
              tono: DexterMetricTone.exito,
            ),
          ),
          Expanded(
            child: DexterMetricTile(
              etiqueta: 'Sin empezar',
              valor: '$pendientes',
              icono: Icons.schedule,
              compacto: true,
              tono: pendientes == 0
                  ? DexterMetricTone.exito
                  : DexterMetricTone.precaucion,
            ),
          ),
        ],
      ),
    );
  }

  Widget _trabajoEnCurso(TrabajoVista? enCurso, List<TrabajoVista> trabajos) {
    if (enCurso == null) {
      // Sin ninguno empezado no se muestra el primero de la lista como si lo
      // fuera: eso le haría creer al técnico que ya arrancó algo.
      return const DexterCard(
        child: DexterEmptyState(
          icono: Icons.play_circle_outline,
          titulo: 'No tenés ningún trabajo empezado',
          mensaje: 'Abrí uno de los próximos y marcá que vas en camino.',
        ),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        if (SeleccionJornada.hayVariosEnCurso(trabajos))
          // No debería pasar: el técnico está en un lugar a la vez. Se avisa en
          // vez de corregirlo por cuenta propia.
          Padding(
            padding: const EdgeInsets.only(bottom: AppSpacing.sm),
            child: Row(
              children: <Widget>[
                const Icon(Icons.info_outline, size: 14, color: AppColors.precaucion),
                const SizedBox(width: AppSpacing.xs),
                Expanded(
                  child: Text(
                    'Tenés ${SeleccionJornada.enCurso(trabajos).length} trabajos '
                    'empezados a la vez. Se muestra el más próximo.',
                    style: AppTypography.cuerpoChico.copyWith(
                      color: AppColors.precaucion,
                    ),
                  ),
                ),
              ],
            ),
          ),
        TarjetaTrabajo(
          trabajo: enCurso,
          mostrarDatosFuturos: widget.mostrarDatosFuturos,
          onTap: () async {
            await widget.abrirTrabajo(context, enCurso);
            await widget.ordenes.recargar();
          },
        ),
        if (widget.mostrarDatosFuturos) _telemetria(enCurso),
      ],
    );
  }

  /// CAMPO-DATA-001 y CAMPO-DATA-011: la señal y los identificadores de red.
  /// Nada de esto llega hoy del backend; el día que llegue, esta tarjeta
  /// cambia de fuente y no de forma.
  Widget _telemetria(TrabajoVista trabajo) {
    return Padding(
      padding: const EdgeInsets.only(top: AppSpacing.sm),
      child: DexterCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Text('SEÑAL DEL CLIENTE', style: AppTypography.etiquetaChica),
            const SizedBox(height: AppSpacing.sm),
            Row(
              children: <Widget>[
                Expanded(
                  child: DexterMetricTile(
                    etiqueta: 'Potencia RX',
                    valor: trabajo.futuro.potenciaRxDbm.toStringAsFixed(1),
                    unidad: 'dBm',
                    tono: DexterMetricTone.precaucion,
                  ),
                ),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Text('CTO ${FieldMockData.cto}', style: AppTypography.etiqueta),
                      const SizedBox(height: AppSpacing.xs),
                      Text(FieldMockData.puertoPon, style: AppTypography.etiqueta),
                      const SizedBox(height: AppSpacing.xs),
                      Text(
                        'ONT ${FieldMockData.serialOnt}',
                        style: AppTypography.etiquetaChica,
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _proximos(List<TrabajoVista> proximos, List<TrabajoVista> sinFecha) {
    if (proximos.isEmpty && sinFecha.isEmpty) {
      return const DexterCard(
        child: DexterEmptyState(
          icono: Icons.event_available,
          titulo: 'No te queda nada agendado',
          mensaje: 'Cuando te asignen un trabajo nuevo, aparece acá.',
        ),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        for (final TrabajoVista trabajo in proximos)
          TarjetaTrabajo(
            trabajo: trabajo,
            mostrarDatosFuturos: widget.mostrarDatosFuturos,
            onTap: () async {
              await widget.abrirTrabajo(context, trabajo);
              await widget.ordenes.recargar();
            },
          ),
        if (sinFecha.isNotEmpty)
          // Estos trabajos existen y hay que hacerlos, pero no tienen fecha:
          // no se les inventa una hora para que entren en la agenda.
          DexterCard(
            onTap: widget.onVerTodos,
            child: Row(
              children: <Widget>[
                const Icon(Icons.schedule_outlined,
                    size: 16, color: AppColors.textoSecundario),
                const SizedBox(width: AppSpacing.sm),
                Expanded(
                  child: Text(
                    sinFecha.length == 1
                        ? 'Tenés 1 trabajo sin fecha asignada'
                        : 'Tenés ${sinFecha.length} trabajos sin fecha asignada',
                    style: AppTypography.cuerpo,
                  ),
                ),
                const Icon(Icons.chevron_right, size: 18, color: AppColors.azulAccion),
              ],
            ),
          ),
      ],
    );
  }

  /// CAMPO-DATA-009: el kit del día. Se conecta en la Fase 8, con el módulo
  /// de materiales.
  Widget _kit() {
    return DexterCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(FieldMockData.kitOrigen, style: AppTypography.etiquetaChica),
          const SizedBox(height: AppSpacing.sm),
          Row(
            children: <Widget>[
              const Expanded(
                child: DexterMetricTile(
                  etiqueta: 'Recibidos',
                  valor: '${FieldMockData.kitRecibidos}',
                  compacto: true,
                ),
              ),
              const Expanded(
                child: DexterMetricTile(
                  etiqueta: 'Consumidos',
                  valor: '${FieldMockData.kitConsumidos}',
                  compacto: true,
                  tono: DexterMetricTone.info,
                ),
              ),
              const Expanded(
                child: DexterMetricTile(
                  etiqueta: 'Disponibles',
                  valor: '${FieldMockData.kitDisponibles}',
                  compacto: true,
                  tono: DexterMetricTone.exito,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _sincronizacion() {
    final resumen = widget.resumenSincronizacion;
    return DexterCard(
      child: Row(
        children: <Widget>[
          Expanded(
            child: Text(
              SyncPresentacion.fraseFranja(resumen),
              style: AppTypography.cuerpo,
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          DexterSyncBadge(
            estado: SyncPresentacion.estado(resumen),
            detalle: SyncPresentacion.detalle(resumen),
          ),
        ],
      ),
    );
  }

  Widget _seccion(String titulo, {VoidCallback? accion}) {
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: Row(
        children: <Widget>[
          Expanded(child: Text(titulo, style: AppTypography.tituloChico)),
          if (accion != null)
            TextButton(onPressed: accion, child: const Text('Ver todos')),
        ],
      ),
    );
  }

  static String _fechaDeHoy() {
    const dias = <String>[
      'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo',
    ];
    const meses = <String>[
      'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
      'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre',
    ];
    final hoy = DateTime.now();
    return '${dias[hoy.weekday - 1]} ${hoy.day} de ${meses[hoy.month - 1]}';
  }
}
