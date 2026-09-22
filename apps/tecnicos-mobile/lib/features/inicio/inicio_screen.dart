import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/estado/ordenes_jornada.dart';
import '../../core/storage/local_database.dart';
import '../../core/sync/sync_presentacion.dart';
import '../../core/sync/sync_queue_service.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/dexter_empty_state.dart';
import '../materiales/estado_de_jornada.dart';
import '../trabajo/estado_trabajo.dart';
import '../trabajo/seleccion_jornada.dart';
import '../trabajo/trabajo_vista.dart';
import 'resumen_de_inicio.dart';

/// Inicio — la pantalla de decisión de la jornada.
///
/// QUÉ RESPONDE, Y EN QUÉ ORDEN
/// ----------------------------
/// 1. ¿Qué tengo hoy?   → el avance del día y el kit que lleva encima.
/// 2. ¿Qué hago ahora?   → un trabajo, el siguiente, con el botón para entrar.
/// 3. ¿Tengo problemas?  → lo que se rompió y alguien tiene que mirar.
///
/// QUIÉN DECIDE QUÉ
/// ----------------
/// La pantalla **no decide nada**. Cuál es el próximo trabajo, qué cuenta como
/// hecho y qué merece un aviso lo resuelve [ResumenDeInicio], que se prueba
/// sin emulador. Acá solo se dibuja lo que esa lógica ya decidió: una segunda
/// cuenta en el widget es la forma más rápida de que dos pantallas de la misma
/// aplicación digan cosas distintas del mismo día.
///
/// LO QUE SE FUE DE ACÁ, Y POR QUÉ
/// -------------------------------
/// Academia, vehículo y la potencia previa de la OLT ya no se dibujan. No
/// tienen fuente: eran constantes de demostración con aire de dato. Una
/// tarjeta que dice "ABC123 · 75% de combustible" la primera semana y nunca
/// más enseña que la pantalla no se mira, y ese aprendizaje después se lleva
/// puesto al aviso que sí importaba. Cuando exista el endpoint, vuelven con la
/// fuente y la hora del dato al lado.
class InicioScreen extends StatefulWidget {
  const InicioScreen({
    super.key,
    required this.ordenes,
    required this.abrirTrabajo,
    required this.nombreTecnico,
    this.resumenSincronizacion,
    this.onVerTodos,
    this.jornada,
    this.ahora,
  });

  final OrdenesJornada ordenes;
  final Future<void> Function(BuildContext contexto, TrabajoVista trabajo)
  abrirTrabajo;
  final String nombreTecnico;
  final SyncSummary? resumenSincronizacion;
  final VoidCallback? onVerTodos;

  /// La jornada ya leída. Se inyecta en las pruebas; en la aplicación se lee
  /// sola de la base y se vuelve a leer cuando el kit o la cola cambian.
  final EstadoDeJornada? jornada;

  /// El reloj, para que una prueba no dependa de la hora en que se corre.
  final DateTime? ahora;

  @override
  State<InicioScreen> createState() => _InicioScreenState();
}

class _InicioScreenState extends State<InicioScreen> {
  StreamSubscription<LocalDatabaseChangeEvent>? _suscripcion;
  EstadoDeJornada? _jornada;

  @override
  void initState() {
    super.initState();
    widget.ordenes.addListener(_alCambiar);
    widget.ordenes.asegurarCargado();
    _cargarJornada();
    // Registrar un consumo dentro de una orden tiene que verse en el kit del
    // inicio sin volver a entrar a la pantalla. La suscripción se guarda para
    // cancelarla: dejarla viva es una fuga en el teléfono y, en una prueba,
    // un oyente pendiente que impide que el test termine.
    _suscripcion = LocalDatabase.onDataChanged.listen((evento) {
      if (!mounted) return;
      if (evento.tabla == 'local_kit' ||
          evento.tabla == 'local_jornada' ||
          evento.tabla == 'cola_movimientos_material') {
        _cargarJornada();
      }
    });
  }

  @override
  void dispose() {
    _suscripcion?.cancel();
    widget.ordenes.removeListener(_alCambiar);
    super.dispose();
  }

  void _alCambiar() {
    if (mounted) setState(() {});
  }

  Future<void> _cargarJornada() async {
    if (widget.jornada != null) {
      if (mounted) setState(() => _jornada = widget.jornada);
      return;
    }
    final leida = await EstadoDeJornada.leer();
    if (!mounted) return;
    setState(() => _jornada = leida);
  }

  @override
  Widget build(BuildContext context) {
    if (widget.ordenes.cargando) {
      // Un fondo quieto, no un indicador que gira: esto lee SQLite y son
      // milisegundos. Una animación perpetua además deja la pantalla sin
      // reposo, que es lo que cuelga cualquier prueba que espere a que las
      // animaciones terminen.
      return const ColoredBox(color: AppColors.surface);
    }

    final trabajos = widget.ordenes.trabajos;
    final sync = widget.resumenSincronizacion;
    final jornada = _jornada;

    // Los movimientos de material viven en su propia cola, aparte de la de
    // mutaciones: sin sumarlos, "todo enviado" sería falso justo el día que
    // el técnico registró consumo sin señal.
    final resumen = ResumenDeInicio.armar(
      trabajos: trabajos,
      jornada: jornada,
      movimientosSinSubir:
          (sync?.mutacionesPendientes ?? 0) + (jornada?.sinSubir ?? 0),
      evidenciasSinSubir: sync?.evidenciasPendientes ?? 0,
      mutacionesEnConflicto: sync?.mutacionesConflicto ?? 0,
      ahora: widget.ahora,
    );

    final proximos = SeleccionJornada.proximos(
      trabajos,
      desde: widget.ahora ?? DateTime.now(),
    ).where((TrabajoVista t) => t.id != resumen.siguiente?.id).toList();
    final sinFecha = SeleccionJornada.activosSinFecha(trabajos)
        .where((TrabajoVista t) => t.id != resumen.siguiente?.id)
        .toList();

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
              _saludo(sync),
              // Un solo ritmo entre bloques. Antes los tres primeros iban a
              // `md` y los de abajo a `lg`: la mitad superior se veia
              // apretada contra la inferior sin que nada lo justificara.
              if (jornada != null && jornada.hayJornada) ...<Widget>[
                const SizedBox(height: AppSpacing.lg),
                _estadoDeJornada(jornada),
              ],
              const SizedBox(height: AppSpacing.lg),
              _avanceDiario(resumen),
              // Los avisos van arriba, pero **solo cuando existen**: cuando no
              // hay ninguno el bloque no se dibuja, así el día no empieza en
              // rojo por costumbre. Cuando aparece uno, aparece donde se ve,
              // no al final de un scroll largo.
              if (resumen.hayProblemas) ...<Widget>[
                const SizedBox(height: AppSpacing.lg),
                _alertas(resumen.avisos),
              ],
              const SizedBox(height: AppSpacing.lg),
              _proximoTrabajo(resumen, trabajos),
              const SizedBox(height: AppSpacing.lg),
              _proximos(proximos, sinFecha),
              if (resumen.hayKit) ...<Widget>[
                const SizedBox(height: AppSpacing.lg),
                _materiales(resumen),
              ],
              const SizedBox(height: AppSpacing.lg),
              _sincronizacion(sync),
            ],
          ],
        ),
      ),
    );
  }

  // --- 1. Saludo -----------------------------------------------------------

  /// El saludo.
  ///
  /// Sin tarjeta ni avatar, y en tipografía grande, como en el diseño. La
  /// versión anterior lo metía en una caja azul con un círculo de iniciales:
  /// gastaba ochenta píxeles de alto para decir el nombre de quien ya sabe
  /// cómo se llama, y empujaba hacia abajo lo único que importa a esa hora,
  /// que es el trabajo que sigue. El avatar ya está arriba, en el encabezado.
  Widget _saludo(SyncSummary? sync) {
    final hora = (widget.ahora ?? DateTime.now()).hour;
    final momento = hora < 12
        ? 'Buenos días'
        : hora < 19
        ? 'Buenas tardes'
        : 'Buenas noches';

    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: <Widget>[
        Expanded(
          child: FittedBox(
            fit: BoxFit.scaleDown,
            alignment: Alignment.centerLeft,
            child: Text(
              '$momento, ${_primerNombre(widget.nombreTecnico)}',
              style: AppTypography.tituloGrande,
              maxLines: 1,
            ),
          ),
        ),
        const SizedBox(width: AppSpacing.sm),
        _estadoDeEnvio(sync),
      ],
    );
  }

  /// Si lo registrado ya viajó. El número sale de la cola, que es real.
  ///
  /// No se muestra hace cuánto fue el último envío bueno: la cola todavía no
  /// lo guarda, y una antigüedad inventada es justo el dato que alguien usa
  /// para decidir si puede irse.
  Widget _estadoDeEnvio(SyncSummary? sync) {
    final int pendientes = sync == null
        ? 0
        : sync.mutacionesPendientes + sync.evidenciasPendientes + sync.datosDirty;
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
            alDia ? 'Todo enviado' : '$pendientes sin enviar',
            style: AppTypography.etiquetaChica.copyWith(
              color: alDia ? AppColors.exitoTexto : AppColors.onSurfaceVariant,
              fontWeight: FontWeight.w700,
            ),
          ),
        ],
      ),
    );
  }

  // --- 2. En qué estado está la jornada ------------------------------------

  /// En qué está la jornada, según el servidor.
  ///
  /// Sustituye al selector de modos —"En ruta", "Pausa"— que se veía y no
  /// guardaba nada. Un "Pausa" que el supervisor nunca recibe es peor que no
  /// poder marcarlo: el técnico cree haber avisado.
  ///
  /// Las tres frases son distintas a propósito. Una jornada **tomada** es una
  /// intención que viaja en la cola; una **cerrada** tiene un acta con números
  /// congelados. Decirle cerrada a la primera haría que alguien se fuera a su
  /// casa creyendo que entregó.
  Widget _estadoDeJornada(EstadoDeJornada jornada) {
    final (String texto, Color color, IconData icono) = jornada.cerrada
        ? ('Jornada cerrada', AppColors.exitoTexto, Icons.check_circle)
        : jornada.cierreTomado
        ? (
            'Cierre enviado · esperando confirmación',
            AppColors.onSurfaceVariant,
            Icons.hourglass_bottom,
          )
        : ('Jornada en curso', AppColors.exito, Icons.play_circle_fill);

    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.sm,
      ),
      decoration: BoxDecoration(
        color: AppColors.surfaceContainerLowest,
        borderRadius: AppRadius.brTarjeta,
        boxShadow: AppTheme.sombraNivel1,
      ),
      child: Row(
        children: <Widget>[
          Icon(icono, size: 16, color: color),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Text(
              texto,
              style: AppTypography.etiqueta.copyWith(
                color: color,
                fontWeight: FontWeight.w700,
              ),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }

  /// El avance del día, con los números que decidió [ResumenDeInicio].
  Widget _avanceDiario(ResumenDeInicio resumen) {
    final int total = resumen.totalDeTrabajos;
    final double avance = total == 0 ? 0 : resumen.completados / total;

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
              // "1 / 4 OT" en monoespaciada se lee "1 / 4 0T": la O y el
              // cero se confunden, y el tracking amplio separa el rotulo del
              // numero. "de" no tiene ese problema y se entiende igual.
              Text(
                '${resumen.completados} de $total',
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
                '· ${resumen.pendientes} pendientes',
                style: AppTypography.etiquetaChica,
              ),
            ],
          ),
        ],
      ),
    );
  }

  // --- 3. Lo que alguien tiene que mirar -----------------------------------

  /// Los avisos, en el orden y con la gravedad que decidió la lógica.
  ///
  /// El rojo se reserva para lo que no se arregla solo. Una cola esperando
  /// señal sube sola: pintarla de rojo enseña a ignorar los rojos, y el día
  /// que aparezca uno de verdad nadie lo va a mirar.
  Widget _alertas(List<AvisoDeInicio> avisos) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Text(
          'Alertas operativas',
          style: AppTypography.tituloChico,
        ),
        const SizedBox(height: AppSpacing.sm),
        for (final AvisoDeInicio aviso in avisos)
          Padding(
            padding: const EdgeInsets.only(bottom: AppSpacing.sm),
            child: _FilaDeAviso(aviso: aviso),
          ),
      ],
    );
  }

  // --- 4. Qué hago ahora ---------------------------------------------------

  Widget _proximoTrabajo(ResumenDeInicio resumen, List<TrabajoVista> trabajos) {
    final TrabajoVista? siguiente = resumen.siguiente;

    if (siguiente == null) {
      // Dos vacíos distintos, y la diferencia importa: terminar lo que había
      // es una jornada cumplida; no tener nada asignado es un problema de
      // despacho que alguien debería mirar.
      return Container(
        decoration: BoxDecoration(
          color: AppColors.surfaceContainerLowest,
          borderRadius: AppRadius.brTarjeta,
          boxShadow: AppTheme.sombraNivel1,
        ),
        child: resumen.terminoLaJornada
            ? const DexterEmptyState(
                icono: Icons.task_alt,
                titulo: 'Terminaste todos tus trabajos',
                mensaje: 'No te queda ninguno pendiente por hacer hoy.',
              )
            : const DexterEmptyState(
                icono: Icons.event_available,
                titulo: 'No tenés trabajos asignados',
                mensaje: 'Cuando el despacho te asigne uno, aparece acá.',
              ),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Text(
          'Próximo trabajo',
          style: AppTypography.tituloChico,
        ),
        const SizedBox(height: AppSpacing.sm),
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
        _TarjetaDeTrabajo(
          trabajo: siguiente,
          ahora: widget.ahora,
          onAbrir: () async {
            await widget.abrirTrabajo(context, siguiente);
            await widget.ordenes.recargar();
          },
        ),
      ],
    );
  }

  // --- 5. Los que vienen después -------------------------------------------

  Widget _proximos(List<TrabajoVista> proximos, List<TrabajoVista> sinFecha) {
    if (proximos.isEmpty && sinFecha.isEmpty) return const SizedBox.shrink();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Row(
          children: <Widget>[
            Text('Después', style: AppTypography.tituloChico),
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

  // --- 6. El kit que lleva encima ------------------------------------------

  /// Lo que salió de bodega, lo que se usó y lo que queda.
  ///
  /// Los tres números los calculó el dominio y los guardó el espejo de la
  /// jornada. Acá no se resta nada: la misma cuenta hecha dos veces es la
  /// forma segura de que algún día difieran y nadie sepa cuál creer.
  ///
  /// Sin jornada cargada este bloque no existe. No se dibuja un kit en cero:
  /// "0 disponible" y "todavía no sincronizó" se ven igual y significan lo
  /// contrario.
  Widget _materiales(ResumenDeInicio resumen) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Text(
          'Materiales',
          style: AppTypography.tituloChico,
        ),
        const SizedBox(height: AppSpacing.sm),
        Container(
          padding: const EdgeInsets.all(AppSpacing.md),
          decoration: BoxDecoration(
            color: AppColors.surfaceContainerLowest,
            borderRadius: AppRadius.brTarjeta,
            boxShadow: AppTheme.sombraNivel1,
          ),
          child: Row(
            children: <Widget>[
              Expanded(
                child: _Cifra(
                  etiqueta: 'Recibido',
                  valor: resumen.kitRecibido,
                ),
              ),
              Expanded(
                child: _Cifra(
                  etiqueta: 'Consumido',
                  valor: resumen.kitConsumido,
                ),
              ),
              Expanded(
                child: _Cifra(
                  etiqueta: 'En mano',
                  valor: resumen.kitDisponible,
                  color: AppColors.primary,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  // --- 7. La cola ----------------------------------------------------------

  Widget _sincronizacion(SyncSummary? sync) {
    final limpio = sync != null && sync.isClean && !sync.hasConnectionError;

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
                      SyncPresentacion.fraseFranja(sync),
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


}

/// Un aviso, pintado según su gravedad.
class _FilaDeAviso extends StatelessWidget {
  const _FilaDeAviso({required this.aviso});

  final AvisoDeInicio aviso;

  @override
  Widget build(BuildContext context) {
    final bool grave = aviso.gravedad == GravedadDeAviso.alta;
    final Color color = grave ? AppColors.error : AppColors.onSurfaceVariant;

    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: grave
            ? AppColors.errorContainer
            : AppColors.surfaceContainerLowest,
        borderRadius: AppRadius.brTarjeta,
        boxShadow: AppTheme.sombraNivel1,
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Icon(
            grave ? Icons.warning_amber_rounded : Icons.cloud_upload_outlined,
            size: 18,
            color: grave ? AppColors.onErrorContainer : color,
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  aviso.titulo,
                  style: AppTypography.etiquetaGrande.copyWith(
                    color: grave ? AppColors.onErrorContainer : AppColors.onSurface,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  aviso.detalle,
                  style: AppTypography.cuerpoChico.copyWith(
                    color: grave ? AppColors.onErrorContainer : color,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Uno de los tres números del kit.
class _Cifra extends StatelessWidget {
  const _Cifra({required this.etiqueta, required this.valor, this.color});

  final String etiqueta;
  final String valor;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Text(etiqueta, style: AppTypography.etiquetaChica),
        const SizedBox(height: 2),
        Text(
          valor,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: AppTypography.dato.copyWith(
            color: color ?? AppColors.onSurface,
            fontWeight: FontWeight.w700,
          ),
        ),
      ],
    );
  }
}

/// La tarjeta dominante: el trabajo que toca ahora.
class _TarjetaDeTrabajo extends StatelessWidget {
  const _TarjetaDeTrabajo({
    required this.trabajo,
    required this.onAbrir,
    this.ahora,
  });

  final TrabajoVista trabajo;
  final VoidCallback onAbrir;
  final DateTime? ahora;

  /// Si ya se empezó, el botón continúa; si no, empieza. Prometer "continuar"
  /// sobre algo que ni se abrió confunde a quien mira la pantalla de reojo.
  bool get _empezado =>
      trabajo.estado == EstadoTrabajo.enSitio ||
      trabajo.estado == EstadoTrabajo.enCamino;

  @override
  Widget build(BuildContext context) {
    final int? minutos = trabajo.minutosParaVencer(ahora: ahora);

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
          // Cinta superior: estado y, si el servidor dijo cuándo vence, cuánto
          // queda. Sin `sla_vence_en` no se dibuja el reloj: una cuenta
          // inventada es justo lo que hace correr a alguien sin motivo.
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
                Flexible(
                  child: Text(
                    trabajo.estado.etiqueta.toUpperCase(),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: AppTypography.etiqueta.copyWith(
                      color: AppColors.onPrimary,
                      fontWeight: FontWeight.w700,
                    ),
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
                const Spacer(),
                if (minutos != null)
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
                          minutos < 0 ? 'SLA vencido' : 'SLA: $minutos min',
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
                // Qué hay que hacer, si la orden lo dice; si no, para quién.
                //
                // `resumen` es un campo real del backend que hasta ahora no
                // se dibujaba en ninguna pantalla. Es la línea que el diseño
                // pone como título, y tiene sentido: a las siete de la mañana
                // lo primero que decide el día es el problema, no el apellido
                // de quien lo tiene.
                Text(
                  trabajo.resumen.isEmpty
                      ? trabajo.clienteNombre
                      : trabajo.resumen,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: AppTypography.tituloChico.copyWith(
                    fontWeight: FontWeight.w700,
                  ),
                ),
                if (trabajo.resumen.isNotEmpty)
                  Text(
                    trabajo.clienteNombre,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: AppTypography.cuerpo,
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
                          // Cómo se entra al inmueble, si el despacho lo cargó.
                          if (trabajo.detalleAcceso.isNotEmpty)
                            Text(
                              trabajo.detalleAcceso,
                              style: AppTypography.etiquetaChica,
                            ),
                        ],
                      ),
                    ),
                  ],
                ),
                if (_ventana(trabajo).isNotEmpty) ...<Widget>[
                  const SizedBox(height: AppSpacing.md),
                  Container(
                    padding: const EdgeInsets.all(AppSpacing.sm),
                    decoration: BoxDecoration(
                      color: AppColors.surfaceContainerLow,
                      borderRadius: AppRadius.brCampo,
                    ),
                    child: _DatoConIcono(
                      icono: Icons.schedule,
                      etiqueta: 'Ventana',
                      valor: _ventana(trabajo),
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
                      _textoDelBoton(),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
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
                        texto: 'Navegar',
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

  String _textoDelBoton() {
    final String verbo = _empezado ? 'CONTINUAR' : 'EMPEZAR';
    return trabajo.numero == null ? '$verbo ORDEN' : '$verbo OT #${trabajo.numero}';
  }

  /// La franja prometida, si existe; si no, la hora del compromiso. Vacía
  /// cuando el servidor no dijo ninguna de las dos.
  static String _ventana(TrabajoVista trabajo) {
    if (trabajo.ventanaTexto.isNotEmpty) return trabajo.ventanaTexto;
    final DateTime? f = trabajo.compromiso;
    if (f == null) return '';
    return '${f.hour.toString().padLeft(2, '0')}:'
        '${f.minute.toString().padLeft(2, '0')}';
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
          Flexible(
            child: Text(
              texto,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: AppTypography.etiquetaGrande.copyWith(color: color),
            ),
          ),
        ],
      ),
    );
  }
}

/// Una fila de los trabajos que vienen después.
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
