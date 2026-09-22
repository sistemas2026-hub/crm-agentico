import 'package:flutter/material.dart';

import '../../core/estado/ordenes_jornada.dart';
import '../../core/mock/field_mock_data.dart';
import '../../core/sync/sync_presentacion.dart';
import '../../core/sync/sync_queue_service.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/dexter_empty_state.dart';
import '../trabajo/seleccion_jornada.dart';
import '../trabajo/trabajo_vista.dart';

/// Inicio — Dashboard de jornada.
///
/// Réplica de la pantalla del proyecto de Stitch, bloque por bloque: saludo y
/// turno, las tres métricas, los chips de verificación, la tarjeta del trabajo
/// en curso con su cinta de estado, los próximos trabajos, el kit y la
/// sincronización.
///
/// Lo que el backend entrega se muestra tal cual. Lo que todavía no existe
/// —turno, cuadrilla, SLA, ventana, terminal, señal previa, kit, vehículo,
/// academia— está en `FieldMockData` con su identificador `CAMPO-DATA-XXX` y
/// solo aparece con el modo demostración encendido.
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
  final Future<void> Function(BuildContext contexto, TrabajoVista trabajo)
  abrirTrabajo;
  final String nombreTecnico;
  final SyncSummary? resumenSincronizacion;
  final VoidCallback? onVerTodos;
  final bool mostrarDatosFuturos;

  @override
  State<InicioScreen> createState() => _InicioScreenState();
}

class _InicioScreenState extends State<InicioScreen> {
  /// CAMPO-DATA-038 · Qué modo de jornada se ve marcado. Vive solo acá: no se
  /// guarda ni viaja a ningún lado.
  int _estadoDeJornada = 0;

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
        color: AppColors.surface,
        child: Center(child: CircularProgressIndicator()),
      );
    }

    final trabajos = widget.ordenes.trabajos;
    final enCurso = SeleccionJornada.enCursoDestacado(trabajos);
    final proximos = SeleccionJornada.proximos(trabajos, desde: DateTime.now());
    final sinFecha = SeleccionJornada.activosSinFecha(trabajos);

    return ColoredBox(
      color: AppColors.surface,
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
            if (widget.ordenes.fallo) ...<Widget>[
              const DexterEmptyState(
                icono: Icons.error_outline,
                titulo: 'No se pudieron leer tus trabajos',
                mensaje: 'Deslizá hacia abajo para volver a intentar.',
                esAdvertencia: true,
              ),
            ] else ...<Widget>[
              _saludo(),
              if (widget.mostrarDatosFuturos) ...<Widget>[
                const SizedBox(height: AppSpacing.md),
                _modoDeJornada(),
              ],
              const SizedBox(height: AppSpacing.md),
              _avanceDiario(trabajos),
              const SizedBox(height: AppSpacing.lg),
              _trabajoEnCurso(enCurso, trabajos),
              const SizedBox(height: AppSpacing.lg),
              _proximos(proximos, sinFecha),
              const SizedBox(height: AppSpacing.lg),
              _widgetsDelTurno(),
            ],
          ],
        ),
      ),
    );
  }

  // --- 1. Saludo y turno ---------------------------------------------------

  Widget _saludo() {
    final hora = DateTime.now().hour;
    final momento = hora < 12
        ? 'Buenos días'
        : hora < 19
        ? 'Buenas tardes'
        : 'Buenas noches';

    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.surfaceContainer,
        borderRadius: AppRadius.brTarjeta,
        boxShadow: AppTheme.sombraNivel1,
      ),
      child: Row(
        children: <Widget>[
          Container(
            width: 48,
            height: 48,
            decoration: BoxDecoration(
              color: AppColors.surfaceContainerHigh,
              borderRadius: BorderRadius.circular(AppRadius.circulo),
            ),
            alignment: Alignment.center,
            child: Stack(
              clipBehavior: Clip.none,
              alignment: Alignment.center,
              children: <Widget>[
                Text(
                  _iniciales(widget.nombreTecnico),
                  style: AppTypography.etiquetaGrande.copyWith(
                    color: AppColors.primary,
                  ),
                ),
                if (widget.mostrarDatosFuturos)
                  Positioned(
                    right: -2,
                    bottom: -2,
                    child: Container(
                      width: 14,
                      height: 14,
                      decoration: BoxDecoration(
                        color: AppColors.exitoFuerte,
                        shape: BoxShape.circle,
                        border: Border.all(
                          color: AppColors.surfaceContainer,
                          width: 2,
                        ),
                      ),
                    ),
                  ),
              ],
            ),
          ),
          const SizedBox(width: AppSpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  '$momento, ${_primerNombre(widget.nombreTecnico)}',
                  style: AppTypography.tituloMedio,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                // CAMPO-DATA-007
                if (widget.mostrarDatosFuturos)
                  Text(
                    FieldMockData.cuadrilla,
                    style: AppTypography.etiqueta,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
              ],
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          _estadoDeEnvio(),
        ],
      ),
    );
  }

  /// Lo que el diseño pone al lado del saludo: si lo registrado ya viajó.
  ///
  /// El número sale de la cola, que es real. La antigüedad ("2m") es
  /// CAMPO-DATA-036: la cola todavía no guarda cuándo fue el último envío
  /// bueno, así que ese dato no se muestra como si lo supiéramos.
  Widget _estadoDeEnvio() {
    final SyncSummary? resumen = widget.resumenSincronizacion;
    final int pendientes = resumen == null
        ? 0
        : resumen.mutacionesPendientes +
            resumen.evidenciasPendientes +
            resumen.datosDirty;
    final bool alDia = pendientes == 0;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.sm, vertical: 4),
      decoration: BoxDecoration(
        color: alDia ? AppColors.exitoFondo : AppColors.surfaceContainerHigh,
        borderRadius: BorderRadius.circular(AppRadius.circulo),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Icon(
            alDia ? Icons.cloud_done : Icons.cloud_upload,
            size: 13,
            color: alDia ? AppColors.exitoTexto : AppColors.onSurfaceVariant,
          ),
          const SizedBox(width: 4),
          Text(
            alDia ? 'Sync OK' : '$pendientes sin enviar',
            style: AppTypography.etiquetaChica.copyWith(
              color: alDia ? AppColors.exitoTexto : AppColors.onSurfaceVariant,
              fontWeight: FontWeight.w700,
            ),
          ),
        ],
      ),
    );
  }

  // --- 2. El modo de trabajo y el avance del día ---------------------------

  /// CAMPO-DATA-038 · En qué está el técnico ahora.
  ///
  /// El selector se ve y responde, pero **no guarda nada**: no hay jornada en
  /// el backend ni cola para marcarla sin señal. Por eso vive en la
  /// demostración: un "Pausa" que el supervisor nunca recibe es peor que no
  /// poder marcarlo.
  Widget _modoDeJornada() {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.surfaceContainerLowest,
        borderRadius: AppRadius.brTarjeta,
        boxShadow: AppTheme.sombraNivel1,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Row(
            children: <Widget>[
              Text(
                'JORNADA EN CURSO',
                style: AppTypography.etiquetaChica.copyWith(
                  color: AppColors.exito,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const Spacer(),
              // CAMPO-DATA-006
              Text(
                'Turno: ${FieldMockData.turno}',
                style: AppTypography.etiquetaChica,
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),
          Row(
            children: <Widget>[
              for (
                int i = 0;
                i < FieldMockData.estadosDeJornada.length;
                i++
              ) ...<Widget>[
                if (i > 0) const SizedBox(width: AppSpacing.xs),
                Expanded(
                  child: _ChipDeEstado(
                    estado: FieldMockData.estadosDeJornada[i],
                    activo: i == _estadoDeJornada,
                    alTocar: () => setState(() => _estadoDeJornada = i),
                  ),
                ),
              ],
            ],
          ),
        ],
      ),
    );
  }

  /// El avance del día. Esto **sí** es real: sale de las órdenes de la jornada.
  Widget _avanceDiario(List<TrabajoVista> trabajos) {
    final int total = trabajos.length;
    final int terminados = SeleccionJornada.terminados(trabajos).length;
    final int pendientes = SeleccionJornada.pendientes(trabajos).length;
    final double avance = total == 0 ? 0 : terminados / total;

    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.surfaceContainerLowest,
        borderRadius: AppRadius.brTarjeta,
        boxShadow: AppTheme.sombraNivel1,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Row(
            children: <Widget>[
              Text(
                'Avance Diario',
                style: AppTypography.etiqueta.copyWith(
                  color: AppColors.onSurface,
                ),
              ),
              const Spacer(),
              Text(
                '$terminados / $total OT',
                style: AppTypography.dato.copyWith(
                  color: AppColors.primary,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),
          ClipRRect(
            borderRadius: BorderRadius.circular(AppRadius.circulo),
            child: LinearProgressIndicator(
              value: avance,
              minHeight: 8,
              backgroundColor: AppColors.surfaceContainerHigh,
              valueColor: const AlwaysStoppedAnimation<Color>(AppColors.exito),
            ),
          ),
          const SizedBox(height: AppSpacing.xs),
          Row(
            children: <Widget>[
              Text(
                '${(avance * 100).round()}%',
                style: AppTypography.etiquetaChica.copyWith(
                  color: AppColors.exito,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(width: AppSpacing.xs),
              Text(
                '· $pendientes pendientes',
                style: AppTypography.etiquetaChica,
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _trabajoEnCurso(TrabajoVista? enCurso, List<TrabajoVista> trabajos) {
    if (enCurso == null) {
      return Container(
        decoration: BoxDecoration(
          color: AppColors.surfaceContainerLowest,
          borderRadius: AppRadius.brTarjeta,
          boxShadow: AppTheme.sombraNivel1,
        ),
        child: const DexterEmptyState(
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
          Padding(
            padding: const EdgeInsets.only(bottom: AppSpacing.sm),
            child: Row(
              children: <Widget>[
                const Icon(
                  Icons.info_outline,
                  size: 14,
                  color: AppColors.error,
                ),
                const SizedBox(width: AppSpacing.xs),
                Expanded(
                  child: Text(
                    'Tenés ${SeleccionJornada.enCurso(trabajos).length} trabajos '
                    'empezados a la vez. Se muestra el más próximo.',
                    style: AppTypography.cuerpoChico.copyWith(
                      color: AppColors.error,
                    ),
                  ),
                ),
              ],
            ),
          ),
        _TarjetaEnCurso(
          trabajo: enCurso,
          mostrarDatosFuturos: widget.mostrarDatosFuturos,
          onAbrir: () async {
            await widget.abrirTrabajo(context, enCurso);
            await widget.ordenes.recargar();
          },
        ),
      ],
    );
  }

  // --- 5. Próximos trabajos ------------------------------------------------

  Widget _proximos(List<TrabajoVista> proximos, List<TrabajoVista> sinFecha) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Row(
          children: <Widget>[
            Text('Próximos Trabajos', style: AppTypography.tituloChico),
            const SizedBox(width: AppSpacing.sm),
            if (proximos.isNotEmpty)
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                decoration: BoxDecoration(
                  color: AppColors.surfaceContainerHigh,
                  borderRadius: BorderRadius.circular(AppRadius.circulo),
                ),
                child: Text(
                  '${proximos.length} pendientes',
                  style: AppTypography.etiquetaChica,
                ),
              ),
            const Spacer(),
            if (widget.onVerTodos != null)
              InkWell(
                onTap: widget.onVerTodos,
                child: Padding(
                  padding: const EdgeInsets.symmetric(
                    horizontal: AppSpacing.xs,
                    vertical: AppSpacing.sm,
                  ),
                  child: Text(
                    'Ver Agenda',
                    style: AppTypography.etiqueta.copyWith(
                      color: AppColors.secondary,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ),
          ],
        ),
        const SizedBox(height: AppSpacing.sm),
        if (proximos.isEmpty && sinFecha.isEmpty)
          Container(
            decoration: BoxDecoration(
              color: AppColors.surfaceContainerLowest,
              borderRadius: AppRadius.brTarjeta,
              boxShadow: AppTheme.sombraNivel1,
            ),
            child: const DexterEmptyState(
              icono: Icons.event_available,
              titulo: 'No te queda nada agendado',
              mensaje: 'Cuando te asignen un trabajo nuevo, aparece acá.',
            ),
          ),
        for (final TrabajoVista trabajo in proximos)
          Padding(
            padding: const EdgeInsets.only(bottom: AppSpacing.sm),
            child: _ItemProximo(
              trabajo: trabajo,
              onVer: () async {
                await widget.abrirTrabajo(context, trabajo);
                await widget.ordenes.recargar();
              },
            ),
          ),
        if (sinFecha.isNotEmpty)
          InkWell(
            onTap: widget.onVerTodos,
            borderRadius: AppRadius.brTarjeta,
            child: Container(
              padding: const EdgeInsets.all(AppSpacing.md),
              decoration: BoxDecoration(
                color: AppColors.surfaceContainerLow,
                borderRadius: AppRadius.brTarjeta,
              ),
              child: Row(
                children: <Widget>[
                  const Icon(
                    Icons.schedule_outlined,
                    size: 16,
                    color: AppColors.onSurfaceVariant,
                  ),
                  const SizedBox(width: AppSpacing.sm),
                  Expanded(
                    child: Text(
                      sinFecha.length == 1
                          ? 'Tenés 1 trabajo sin fecha asignada'
                          : 'Tenés ${sinFecha.length} trabajos sin fecha asignada',
                      style: AppTypography.cuerpo,
                    ),
                  ),
                  const Icon(
                    Icons.chevron_right,
                    size: 18,
                    color: AppColors.secondary,
                  ),
                ],
              ),
            ),
          ),
      ],
    );
  }

  // --- 6. Mi kit (solo demostración) ---------------------------------------

  // --- 5. Telemetría y recursos del turno ----------------------------------

  /// La rejilla 2x2 del diseño. Tres de sus cuatro casillas son de lo que
  /// todavía no existe (kit, vehículo, academia); la cuarta —la cola— es real
  /// y se ve siempre, porque es la que dice si lo registrado ya viajó.
  Widget _widgetsDelTurno() {
    if (!widget.mostrarDatosFuturos) return _sincronizacion();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Text(
          'Telemetría & Recursos de Turno',
          style: AppTypography.etiqueta.copyWith(color: AppColors.onSurface),
        ),
        const SizedBox(height: AppSpacing.sm),
        // Las dos casillas de cada fila miden lo mismo, como en el diseño: la
        // altura la marca la más alta, no un número fijo que se quede corto.
        IntrinsicHeight(
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              // CAMPO-DATA-009 y CAMPO-DATA-025
              Expanded(
                child: _WidgetTurno(
                  icono: Icons.inventory_2,
                  titulo: 'KIT DROP',
                  destacado: '${FieldMockData.kitDisponibles} disp.',
                  colorDestacado: AppColors.primary,
                  lineas: <String>[
                    'Usados: ${FieldMockData.kitConsumidos}',
                    'Carga: ${FieldMockData.kitRecibidos}',
                    'Drop 85m disp.',
                  ],
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              // CAMPO-DATA-008 y CAMPO-DATA-042
              Expanded(
                child: _WidgetTurno(
                  icono: Icons.local_shipping,
                  titulo: 'VEHÍCULO',
                  insignia: 'OK',
                  destacado:
                      '${FieldMockData.vehiculoModelo} '
                      '${FieldMockData.vehiculoPlaca}',
                  lineas: <String>[
                    FieldMockData.vehiculoOdometro,
                    if (FieldMockData.vehiculoPreoperacionalHecho)
                      'Preoperacional ✓',
                  ],
                  medidor: FieldMockData.vehiculoCombustible / 100,
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: AppSpacing.sm),
        IntrinsicHeight(
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              // CAMPO-DATA-018 y CAMPO-DATA-043
              Expanded(
                child: _WidgetTurno(
                  icono: Icons.school,
                  titulo: 'ACADEMIA',
                  destacado:
                      '${FieldMockData.cursosPendientes} Curso Obligatorio',
                  colorDestacado: AppColors.error,
                  lineas: <String>[
                    FieldMockData.cursoObligatorio,
                    FieldMockData.cursoVence,
                  ],
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(child: _motorDeSincronizacion()),
            ],
          ),
        ),
      ],
    );
  }

  /// La casilla de la cola dentro de la rejilla. Todo lo que dice es real: lo
  /// que falta por enviar, si hubo error de red y si la base local está al día.
  Widget _motorDeSincronizacion() {
    final SyncSummary? resumen = widget.resumenSincronizacion;
    final int pendientes = resumen == null
        ? 0
        : resumen.mutacionesPendientes +
            resumen.evidenciasPendientes +
            resumen.datosDirty;
    final bool errorDeRed = resumen?.hasConnectionError ?? false;

    return _WidgetTurno(
      icono: Icons.dns,
      titulo: 'ENGINE SYNC',
      destacado: '$pendientes ${pendientes == 1 ? 'Pendiente' : 'Pendientes'}',
      colorDestacado: pendientes == 0 ? AppColors.exitoTexto : AppColors.primary,
      lineas: <String>[
        errorDeRed ? 'Sin conexión con el servidor' : '0 fallas de red',
        pendientes == 0 ? 'Base local al día' : 'Falta enviar lo registrado',
        // CAMPO-DATA-036 · La hora del último envío bueno todavía no se guarda.
        if (widget.mostrarDatosFuturos)
          'Sync ${FieldMockData.ultimaSincronizacion.toLowerCase()}',
      ],
    );
  }

  Widget _sincronizacion() {
    final resumen = widget.resumenSincronizacion;
    final limpio =
        resumen != null && resumen.isClean && !resumen.hasConnectionError;

    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.surfaceContainer,
        borderRadius: AppRadius.brTarjeta,
        boxShadow: AppTheme.sombraNivel1,
      ),
      child: Column(
        children: <Widget>[
          Row(
            children: <Widget>[
              Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(
                  color: limpio
                      ? AppColors.exito
                      : AppColors.surfaceContainerHigh,
                  borderRadius: BorderRadius.circular(AppRadius.circulo),
                ),
                child: Icon(
                  limpio ? Icons.cloud_done : Icons.cloud_sync_outlined,
                  size: 20,
                  color: limpio ? AppColors.exitoFuerte : AppColors.primary,
                ),
              ),
              const SizedBox(width: AppSpacing.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(
                      limpio ? 'Dexter Cloud Sincronizado' : 'Dexter Cloud',
                      style: AppTypography.cuerpoGrande.copyWith(
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    Text(
                      SyncPresentacion.fraseFranja(resumen),
                      style: AppTypography.cuerpoChico,
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.md),
          _BotonSecundario(
            texto: 'Sincronizar ahora',
            icono: Icons.sync,
            iconoAlPrincipio: true,
            onTap: widget.ordenes.refrescar,
          ),
        ],
      ),
    );
  }

  static String _primerNombre(String nombre) => nombre.trim().split(' ').first;

  static String _iniciales(String nombre) {
    final partes = nombre
        .trim()
        .split(RegExp(r'\s+'))
        .where((String p) => p.isNotEmpty)
        .toList();
    if (partes.isEmpty) return '';
    if (partes.length == 1) return partes.first.substring(0, 1).toUpperCase();
    return (partes.first.substring(0, 1) + partes[1].substring(0, 1))
        .toUpperCase();
  }
}

/// La tarjeta dominante del Home Operacional: el trabajo que está en curso.
class _TarjetaEnCurso extends StatelessWidget {
  const _TarjetaEnCurso({
    required this.trabajo,
    required this.mostrarDatosFuturos,
    required this.onAbrir,
  });

  final TrabajoVista trabajo;
  final bool mostrarDatosFuturos;
  final VoidCallback onAbrir;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: AppColors.surfaceContainerLowest,
        borderRadius: AppRadius.brTarjeta,
        boxShadow: AppTheme.sombraNivel2,
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          // Cinta superior: estado y SLA.
          Container(
            color: AppColors.primary,
            padding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.md,
              vertical: AppSpacing.sm,
            ),
            child: Row(
              children: <Widget>[
                Container(
                  width: 10,
                  height: 10,
                  decoration: const BoxDecoration(
                    color: AppColors.exitoFuerte,
                    shape: BoxShape.circle,
                  ),
                ),
                const SizedBox(width: AppSpacing.sm),
                Text(
                  trabajo.estado.etiqueta.toUpperCase(),
                  style: AppTypography.etiqueta.copyWith(
                    color: AppColors.onPrimary,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                if (trabajo.numero != null) ...<Widget>[
                  const SizedBox(width: 6),
                  Text(
                    '· OT #${trabajo.numero}',
                    style: AppTypography.etiquetaChica.copyWith(
                      color: AppColors.onPrimaryContainer,
                    ),
                  ),
                ],
                // CAMPO-DATA-039 · Hora estimada de llegada.
                if (mostrarDatosFuturos) ...<Widget>[
                  const SizedBox(width: 6),
                  Text(
                    '· ETA ${FieldMockData.etaTrabajoActual}',
                    style: AppTypography.etiquetaChica.copyWith(
                      color: AppColors.onPrimaryContainer,
                    ),
                  ),
                ],
                const Spacer(),
                // CAMPO-DATA-002
                if (mostrarDatosFuturos)
                  Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 6,
                      vertical: 2,
                    ),
                    decoration: const BoxDecoration(
                      color: AppColors.error,
                      borderRadius: AppRadius.brChico,
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: <Widget>[
                        const Icon(
                          Icons.timer,
                          size: 12,
                          color: AppColors.onError,
                        ),
                        const SizedBox(width: 4),
                        Text(
                          'SLA: ${trabajo.futuro.slaRestanteMinutos} min',
                          style: AppTypography.etiquetaChica.copyWith(
                            color: AppColors.onError,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(AppSpacing.md),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Row(
                  children: <Widget>[
                    const Icon(Icons.build, size: 16, color: AppColors.error),
                    const SizedBox(width: 6),
                    Expanded(
                      child: Text(
                        trabajo.tipoNombre.toUpperCase(),
                        style: AppTypography.etiquetaChica.copyWith(
                          color: AppColors.error,
                          fontWeight: FontWeight.w700,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: AppSpacing.xs),
                Row(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: <Widget>[
                    Flexible(
                      child: Text(
                        trabajo.clienteNombre,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: AppTypography.tituloChico.copyWith(
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                    // CAMPO-DATA-040 · El identificador del abonado en el ISP.
                    if (mostrarDatosFuturos) ...<Widget>[
                      const SizedBox(width: 6),
                      Text(
                        '· ${FieldMockData.idAbonado}',
                        style: AppTypography.etiquetaChica,
                      ),
                    ],
                  ],
                ),
                const SizedBox(height: AppSpacing.xs),
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    const Icon(
                      Icons.location_on,
                      size: 18,
                      color: AppColors.primary,
                    ),
                    const SizedBox(width: 6),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: <Widget>[
                          Text(trabajo.direccion, style: AppTypography.cuerpo),
                          // CAMPO-DATA-041 · Cómo se entra al inmueble.
                          if (mostrarDatosFuturos)
                            Text(
                              FieldMockData.detalleAcceso,
                              style: AppTypography.etiquetaChica,
                            ),
                        ],
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: AppSpacing.md),
                // Ventana y terminal.
                Container(
                  padding: const EdgeInsets.all(AppSpacing.sm),
                  decoration: BoxDecoration(
                    color: AppColors.surfaceContainerLow,
                    borderRadius: AppRadius.brCampo,
                  ),
                  child: Row(
                    children: <Widget>[
                      Expanded(
                        child: _DatoConIcono(
                          icono: Icons.schedule,
                          etiqueta: 'Ventana',
                          // CAMPO-DATA-020, y la hora real si no hay demostración.
                          valor: mostrarDatosFuturos
                              ? FieldMockData.ventanaHoraria
                              : _hora(trabajo.compromiso),
                        ),
                      ),
                      if (mostrarDatosFuturos)
                        // CAMPO-DATA-011
                        Expanded(
                          child: _DatoConIcono(
                            icono: Icons.hub,
                            etiqueta: 'Terminal',
                            valor: FieldMockData.terminal,
                          ),
                        ),
                    ],
                  ),
                ),
                // CAMPO-DATA-001
                if (mostrarDatosFuturos) ...<Widget>[
                  const SizedBox(height: AppSpacing.sm),
                  Container(
                    padding: const EdgeInsets.all(AppSpacing.sm),
                    decoration: BoxDecoration(
                      color: AppColors.errorContainer,
                      borderRadius: AppRadius.brCampo,
                    ),
                    child: Row(
                      children: <Widget>[
                        Container(
                          width: 36,
                          height: 36,
                          decoration: BoxDecoration(
                            color: AppColors.onErrorContainer.withValues(
                              alpha: 0.12,
                            ),
                            borderRadius: AppRadius.brCampo,
                          ),
                          child: const Icon(
                            Icons.sensors,
                            size: 20,
                            color: AppColors.onErrorContainer,
                          ),
                        ),
                        const SizedBox(width: AppSpacing.sm),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: <Widget>[
                              Text(
                                'Diagnóstico Central OLT',
                                style: AppTypography.etiquetaChica.copyWith(
                                  color: AppColors.onErrorContainer,
                                  fontWeight: FontWeight.w700,
                                ),
                              ),
                              Text(
                                '${FieldMockData.terminal} · Fuera de norma',
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: AppTypography.etiquetaChica.copyWith(
                                  color: AppColors.onErrorContainer,
                                ),
                              ),
                            ],
                          ),
                        ),
                        Row(
                          crossAxisAlignment: CrossAxisAlignment.baseline,
                          textBaseline: TextBaseline.alphabetic,
                          children: <Widget>[
                            Text(
                              FieldMockData.potenciaRxPrevia.toStringAsFixed(1),
                              style: AppTypography.medicion.copyWith(
                                color: AppColors.error,
                              ),
                            ),
                            const SizedBox(width: 2),
                            Text(
                              'dBm',
                              style: AppTypography.etiquetaChica.copyWith(
                                color: AppColors.onErrorContainer,
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ],
                const SizedBox(height: AppSpacing.md),
                SizedBox(
                  height: 56,
                  child: ElevatedButton.icon(
                    onPressed: onAbrir,
                    icon: const Icon(Icons.flag, size: 20),
                    label: Text(
                      trabajo.numero == null
                          ? 'CONTINUAR ORDEN'
                          : 'CONTINUAR OT #${trabajo.numero}',
                    ),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: AppColors.secondary,
                      foregroundColor: AppColors.onSecondary,
                      textStyle: AppTypography.tituloChico,
                      shape: const RoundedRectangleBorder(
                        borderRadius: AppRadius.brCampo,
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: AppSpacing.sm),
                Row(
                  children: <Widget>[
                    Expanded(
                      child: _AccionRapida(
                        icono: Icons.near_me,
                        texto: 'Navegar Waze/Maps',
                        disponible:
                            trabajo.latitud != null && trabajo.longitud != null,
                      ),
                    ),
                    const SizedBox(width: AppSpacing.sm),
                    Expanded(
                      child: _AccionRapida(
                        icono: Icons.call,
                        texto: 'Llamar Cliente',
                        disponible: trabajo.telefono.isNotEmpty,
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  static String _hora(DateTime? fecha) {
    if (fecha == null) return 'Sin fecha';
    return '${fecha.hour.toString().padLeft(2, '0')}:'
        '${fecha.minute.toString().padLeft(2, '0')}';
  }
}

class _DatoConIcono extends StatelessWidget {
  const _DatoConIcono({
    required this.icono,
    required this.etiqueta,
    required this.valor,
  });

  final IconData icono;
  final String etiqueta;
  final String valor;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: <Widget>[
        Icon(icono, size: 18, color: AppColors.onSurfaceVariant),
        const SizedBox(width: AppSpacing.sm),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text(etiqueta, style: AppTypography.etiquetaChica),
              Text(
                valor,
                style: AppTypography.etiqueta.copyWith(
                  color: AppColors.onSurface,
                  fontWeight: FontWeight.w700,
                ),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ],
          ),
        ),
      ],
    );
  }
}

/// "Navegar GPS" y "Llamar cliente". Todavía no abren nada: falta decidir la
/// dependencia que lanza el mapa y el teléfono. Se ven apagados cuando el dato
/// no existe, para no prometer algo que no puede pasar.
class _AccionRapida extends StatelessWidget {
  const _AccionRapida({
    required this.icono,
    required this.texto,
    required this.disponible,
  });

  final IconData icono;
  final String texto;
  final bool disponible;

  @override
  Widget build(BuildContext context) {
    final color = disponible ? AppColors.primary : AppColors.outline;
    return Container(
      height: 48,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: AppColors.surfaceContainer,
        borderRadius: AppRadius.brCampo,
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: <Widget>[
          Icon(icono, size: 18, color: color),
          const SizedBox(width: 6),
          Text(
            texto,
            style: AppTypography.etiquetaGrande.copyWith(color: color),
          ),
        ],
      ),
    );
  }
}

/// Una fila de "Próximos trabajos".
class _ItemProximo extends StatelessWidget {
  const _ItemProximo({required this.trabajo, required this.onVer});

  final TrabajoVista trabajo;
  final VoidCallback onVer;

  @override
  Widget build(BuildContext context) {
    final (IconData icono, Color color) = switch (trabajo.familia) {
      FamiliaTrabajo.instalacion => (Icons.add_circle, AppColors.primary),
      FamiliaTrabajo.incidencia => (Icons.network_check, AppColors.secondary),
      FamiliaTrabajo.mantenimiento => (
        Icons.build_circle,
        AppColors.onSurfaceVariant,
      ),
      FamiliaTrabajo.otro => (Icons.router, AppColors.onSurfaceVariant),
    };

    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.surfaceContainerLowest,
        borderRadius: AppRadius.brTarjeta,
        boxShadow: AppTheme.sombraNivel1,
      ),
      child: Row(
        children: <Widget>[
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: AppColors.surfaceContainer,
              borderRadius: AppRadius.brCampo,
            ),
            child: Icon(icono, size: 20, color: color),
          ),
          const SizedBox(width: AppSpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Row(
                  children: <Widget>[
                    Text(
                      trabajo.numero == null
                          ? trabajo.familia.etiqueta
                          : '${_prefijo(trabajo.familia)} #${trabajo.numero}',
                      style: AppTypography.etiqueta.copyWith(
                        color: color,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    if (trabajo.compromiso != null) ...<Widget>[
                      const SizedBox(width: 6),
                      Text(
                        '· ${_hora(trabajo.compromiso!)}',
                        style: AppTypography.etiquetaChica,
                      ),
                    ],
                  ],
                ),
                const SizedBox(height: 2),
                Text(
                  trabajo.tipoNombre,
                  style: AppTypography.cuerpoGrande.copyWith(
                    fontWeight: FontWeight.w600,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                Text(
                  trabajo.direccion,
                  style: AppTypography.cuerpoChico,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          InkWell(
            onTap: onVer,
            borderRadius: AppRadius.brCampo,
            child: Container(
              height: 40,
              padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: AppColors.surfaceContainer,
                borderRadius: AppRadius.brCampo,
              ),
              child: Text(
                'Ver',
                style: AppTypography.etiqueta.copyWith(
                  color: AppColors.primary,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  static String _prefijo(FamiliaTrabajo familia) => switch (familia) {
    FamiliaTrabajo.instalacion => 'OT',
    FamiliaTrabajo.incidencia => 'Ticket',
    FamiliaTrabajo.mantenimiento => 'OT',
    FamiliaTrabajo.otro => 'OT',
  };

  static String _hora(DateTime fecha) {
    final h = fecha.hour;
    final sufijo = h < 12 ? 'AM' : 'PM';
    final h12 = h % 12 == 0 ? 12 : h % 12;
    return '${h12.toString().padLeft(2, '0')}:'
        '${fecha.minute.toString().padLeft(2, '0')} $sufijo';
  }
}

/// Botón ancho de acción secundaria, como los del diseño.
class _BotonSecundario extends StatelessWidget {
  const _BotonSecundario({
    required this.texto,
    required this.icono,
    required this.onTap,
    this.iconoAlPrincipio = false,
  });

  final String texto;
  final IconData icono;
  final VoidCallback? onTap;
  final bool iconoAlPrincipio;

  @override
  Widget build(BuildContext context) {
    final color = onTap == null ? AppColors.outline : AppColors.secondary;
    return InkWell(
      onTap: onTap,
      borderRadius: AppRadius.brCampo,
      child: Container(
        height: 48,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: AppColors.surfaceContainerLow,
          borderRadius: AppRadius.brCampo,
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: <Widget>[
            if (iconoAlPrincipio) ...<Widget>[
              Icon(icono, size: 18, color: color),
              const SizedBox(width: 8),
            ],
            Flexible(
              child: Text(
                texto,
                style: AppTypography.etiquetaGrande.copyWith(color: color),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
            if (!iconoAlPrincipio) ...<Widget>[
              const SizedBox(width: 8),
              Icon(icono, size: 18, color: color),
            ],
          ],
        ),
      ),
    );
  }
}

/// CAMPO-DATA-038 · Un modo de jornada, como botón.
class _ChipDeEstado extends StatelessWidget {
  const _ChipDeEstado({
    required this.estado,
    required this.activo,
    required this.alTocar,
  });

  final EstadoJornada estado;
  final bool activo;
  final VoidCallback alTocar;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      selected: activo,
      label: '${estado.nombre}, ${estado.detalle}',
      excludeSemantics: true,
      child: Material(
        color: activo ? AppColors.primary : AppColors.surfaceContainerLow,
        borderRadius: AppRadius.brTarjeta,
        child: InkWell(
          borderRadius: AppRadius.brTarjeta,
          onTap: alTocar,
          child: Container(
            constraints: const BoxConstraints(
              minHeight: AppSpacing.objetivoTactil,
            ),
            padding: const EdgeInsets.symmetric(vertical: 6, horizontal: 4),
            alignment: Alignment.center,
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: <Widget>[
                Text(
                  estado.nombre,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: AppTypography.etiqueta.copyWith(
                    color: activo ? AppColors.onPrimary : AppColors.onSurface,
                    fontWeight: activo ? FontWeight.w700 : FontWeight.w500,
                  ),
                ),
                Text(
                  estado.detalle.toUpperCase(),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: AppTypography.etiquetaChica.copyWith(
                    fontSize: 9,
                    color: activo
                        ? AppColors.primaryFixedDim
                        : AppColors.onSurfaceVariant,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Una casilla de la rejilla de recursos del turno.
class _WidgetTurno extends StatelessWidget {
  const _WidgetTurno({
    required this.icono,
    required this.titulo,
    required this.destacado,
    required this.lineas,
    this.colorDestacado,
    this.insignia,
    this.medidor,
  });

  final IconData icono;
  final String titulo;
  final String destacado;
  final List<String> lineas;
  final Color? colorDestacado;

  /// Una marca corta arriba a la derecha, como el "OK" del vehículo.
  final String? insignia;

  /// Una barra de 0 a 1 debajo del destacado: el combustible del vehículo.
  final double? medidor;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
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
              Icon(icono, size: 16, color: AppColors.secondary),
              const SizedBox(width: 4),
              Expanded(
                child: Text(
                  titulo,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: AppTypography.etiquetaChica.copyWith(
                    color: AppColors.onSurfaceVariant,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
              if (insignia != null)
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 4,
                    vertical: 1,
                  ),
                  decoration: const BoxDecoration(
                    color: AppColors.exitoFondo,
                    borderRadius: AppRadius.brChico,
                  ),
                  child: Text(
                    '✓ ${insignia!}',
                    style: AppTypography.etiquetaChica.copyWith(
                      fontSize: 9,
                      color: AppColors.exitoTexto,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),
          Text(
            destacado,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: AppTypography.etiquetaGrande.copyWith(
              color: colorDestacado ?? AppColors.onSurface,
              fontWeight: FontWeight.w700,
            ),
          ),
          if (medidor != null) ...<Widget>[
            const SizedBox(height: AppSpacing.xs),
            ClipRRect(
              borderRadius: BorderRadius.circular(AppRadius.circulo),
              child: LinearProgressIndicator(
                value: medidor,
                minHeight: 4,
                backgroundColor: AppColors.surfaceContainerHigh,
                valueColor: const AlwaysStoppedAnimation<Color>(
                  AppColors.exito,
                ),
              ),
            ),
          ],
          const SizedBox(height: AppSpacing.xs),
          for (final String linea in lineas)
            Text(
              linea,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: AppTypography.etiquetaChica,
            ),
        ],
      ),
    );
  }
}
