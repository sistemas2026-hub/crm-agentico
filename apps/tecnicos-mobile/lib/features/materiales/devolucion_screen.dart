import 'dart:async';

import 'package:flutter/material.dart';
import 'package:uuid/uuid.dart';

import '../../core/storage/local_database.dart';
import '../../core/storage/secure_storage_service.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_radius.dart';
import '../../core/theme/app_typography.dart';
import 'estado_de_jornada.dart';

/// Devolver lo que sobró y cerrar la jornada.
///
/// NINGÚN NÚMERO DE ESTA PANTALLA SE CALCULA ACÁ
/// ---------------------------------------------
/// Lo esperado, lo devuelto y las diferencias los calcula el dominio, que es
/// el mismo que después firma el acta. La pantalla los muestra y encola lo que
/// el técnico hace. Si hiciera su propia cuenta, el día que las dos difieran
/// nadie sabría cuál creer — y una de las dos estaría en un papel firmado.
///
/// Lo único que el teléfono suma por su cuenta es lo que todavía no subió,
/// para que el técnico no vea un saldo de hace dos horas.
///
/// DEVOLVER NO CORRIGE: AGREGA
/// ---------------------------
/// Una devolución es un movimiento nuevo, igual que un consumo. No edita ni
/// anula lo anterior. Por eso acá no hay ningún botón que modifique un
/// registro viejo: lo que pasó, pasó.
class DevolucionScreen extends StatefulWidget {
  const DevolucionScreen({super.key, this.baseLocal, this.estado});

  final LocalDatabase? baseLocal;

  /// Se inyecta en pruebas; en la aplicación se lee de la base.
  final EstadoDeJornada? estado;

  @override
  State<DevolucionScreen> createState() => _DevolucionScreenState();
}

class _DevolucionScreenState extends State<DevolucionScreen> {
  late final LocalDatabase _db = widget.baseLocal ?? LocalDatabase();
  StreamSubscription<LocalDatabaseChangeEvent>? _suscripcion;
  EstadoDeJornada? _estado;
  bool _cargando = true;

  @override
  void dispose() {
    _suscripcion?.cancel();
    super.dispose();
  }

  @override
  void initState() {
    super.initState();
    _cargar();
    // La suscripcion se guarda para poder cancelarla en dispose.
    //
    // Sin eso queda viva despues de que la pantalla se fue: es una fuga en el
    // telefono, y en una prueba deja al arbol con un oyente pendiente que
    // impide que el test termine.
    _suscripcion = LocalDatabase.onDataChanged.listen((evento) {
      if (!mounted) return;
      if (evento.tabla == 'local_jornada' ||
          evento.tabla == 'cola_movimientos_material') {
        _cargar();
      }
    });
  }

  Future<void> _cargar() async {
    if (widget.estado != null) {
      setState(() {
        _estado = widget.estado;
        _cargando = false;
      });
      return;
    }
    final estado = await EstadoDeJornada.leer(baseLocal: _db);
    if (!mounted) return;
    setState(() {
      _estado = estado;
      _cargando = false;
    });
  }

  Future<void> _devolver(MaterialDeJornada material) async {
    final almacenamiento = SecureStorageService();
    final orgId = await almacenamiento.getOrgId();
    final profileId = await almacenamiento.getProfileId();
    if (orgId == null || profileId == null) return;

    await _db.encolarMovimientoMaterial(
      id: const Uuid().v4(),
      orgId: orgId,
      profileId: profileId,
      materialCodigo: material.codigo,
      materialNombre: material.nombre,
      tipo: 'devolucion',
      cantidad: material.porDevolver.toString(),
      serie: material.serie ?? '',
    );
    await _cargar();
  }

  @override
  Widget build(BuildContext context) {
    if (_cargando) return const ColoredBox(color: AppColors.surface);

    final estado = _estado ?? const EstadoDeJornada.vacio();
    if (!estado.hayJornada) {
      return const ColoredBox(
        color: AppColors.surface,
        child: Center(
          child: Padding(
            padding: EdgeInsets.all(32),
            child: Text(
              'Todavía no hay una jornada que cerrar. Aparece cuando tengas '
              'material entregado y haya señal para sincronizar.',
              textAlign: TextAlign.center,
            ),
          ),
        ),
      );
    }

    return ColoredBox(
      color: AppColors.surface,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
        children: <Widget>[
          _resumen(estado),
          const SizedBox(height: 16),
          Text('Material a devolver', style: AppTypography.tituloChico),
          const SizedBox(height: 8),
          for (final material in estado.materiales) _fila(material),
          if (estado.transferencias.isNotEmpty) ...<Widget>[
            const SizedBox(height: 16),
            _transferencias(estado),
          ],
          const SizedBox(height: 16),
          _cierre(estado),
        ],
      ),
    );
  }

  Widget _resumen(EstadoDeJornada estado) => Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: AppColors.surfaceContainerLow,
          borderRadius: AppRadius.brTarjeta,
          border: Border.all(color: AppColors.outlineVariant),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Text('Kit de hoy', style: AppTypography.tituloChico),
            const SizedBox(height: 10),
            _renglon('Recibido', estado.recibido),
            _renglon('Consumido', estado.consumido),
            _renglon('A devolver', estado.aDevolver),
            _renglon('Devuelto', estado.devuelto),
            _renglon(
              'Diferencias',
              estado.diferencias.toString(),
              resaltado: estado.diferencias > 0,
            ),
            const Divider(height: 20),
            Row(
              children: <Widget>[
                Icon(
                  estado.sinSubir == 0 ? Icons.cloud_done_outlined : Icons.upload,
                  size: 16,
                  color: AppColors.onSurfaceVariant,
                ),
                const SizedBox(width: 8),
                Text(
                  estado.sinSubir == 0
                      ? 'Todo enviado'
                      : '${estado.sinSubir} pendiente(s) de sincronizar',
                  style: AppTypography.cuerpoChico.copyWith(
                    color: AppColors.onSurfaceVariant,
                  ),
                ),
              ],
            ),
          ],
        ),
      );

  Widget _renglon(String etiqueta, String valor, {bool resaltado = false}) =>
      Padding(
        padding: const EdgeInsets.symmetric(vertical: 3),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: <Widget>[
            Text(etiqueta, style: AppTypography.cuerpo),
            Text(
              valor,
              style: AppTypography.dato.copyWith(
                color: resaltado ? AppColors.error : AppColors.onSurface,
              ),
            ),
          ],
        ),
      );

  Widget _fila(MaterialDeJornada material) {
    final cuadra = material.diferencia == 0;
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.surfaceContainerLowest,
        borderRadius: AppRadius.brTarjeta,
        border: Border.all(
          color: cuadra ? AppColors.outlineVariant : AppColors.error,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(material.nombre, style: AppTypography.cuerpoGrande),
          // Un equipo con número nunca se muestra solo como cantidad: lo que
          // hay que ubicar es ESE aparato, no "una unidad".
          if (material.serie != null)
            Text('Serie ${material.serie}',
                style: AppTypography.datoChico.copyWith(
                  color: AppColors.onSurfaceVariant,
                )),
          const SizedBox(height: 6),
          Row(
            children: <Widget>[
              Expanded(
                child: Text(
                  'Esperado ${material.esperado} · Devuelto ${material.devuelto}',
                  style: AppTypography.cuerpoChico,
                ),
              ),
              if (cuadra)
                Row(children: <Widget>[
                  const Icon(Icons.check_circle, size: 16, color: AppColors.exito),
                  const SizedBox(width: 4),
                  Text('Correcto',
                      style: AppTypography.cuerpoChico
                          .copyWith(color: AppColors.exito)),
                ])
              else
                Row(children: <Widget>[
                  const Icon(Icons.warning_amber_rounded,
                      size: 16, color: AppColors.error),
                  const SizedBox(width: 4),
                  Text('Diferencia',
                      style: AppTypography.cuerpoChico
                          .copyWith(color: AppColors.error)),
                ]),
            ],
          ),
          if (material.porDevolver > 0) ...<Widget>[
            const SizedBox(height: 10),
            SizedBox(
              width: double.infinity,
              height: 40,
              child: OutlinedButton(
                onPressed: () => _devolver(material),
                child: Text('Devolver ${material.porDevolver} ${material.unidad}'),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _transferencias(EstadoDeJornada estado) => Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: AppColors.surfaceContainer,
          borderRadius: AppRadius.brTarjeta,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Text('Entregado a otro técnico', style: AppTypography.etiquetaGrande),
            const SizedBox(height: 4),
            // Explica un saldo que no baja: hasta que el otro acepte, el
            // material sigue siendo de quien lo entregó.
            Text(
              'Sigue contando como tuyo hasta que lo acepten.',
              style: AppTypography.cuerpoChico.copyWith(
                color: AppColors.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: 8),
            for (final t in estado.transferencias)
              Text('· ${t.material} x${t.cantidad} → ${t.recibe} '
                  '(pendiente de aceptación)',
                  style: AppTypography.cuerpoChico),
          ],
        ),
      );

  Widget _cierre(EstadoDeJornada estado) {
    if (estado.cerrada) {
      return Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: AppColors.exitoFondo,
          borderRadius: AppRadius.brTarjeta,
        ),
        child: Row(children: <Widget>[
          const Icon(Icons.check_circle, color: AppColors.exitoFuerte),
          const SizedBox(width: 10),
          Expanded(
            child: Text('Jornada cerrada. El acta quedó firmada con estos '
                'números.',
                style: AppTypography.cuerpo
                    .copyWith(color: AppColors.exitoTexto)),
          ),
        ]),
      );
    }

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surfaceContainerLow,
        borderRadius: AppRadius.brTarjeta,
        border: Border.all(color: AppColors.outlineVariant),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text('Cerrar la jornada', style: AppTypography.tituloChico),
          const SizedBox(height: 8),
          if (estado.motivos.isEmpty)
            Text(
              'Todo cuadra. Podés cerrar cuando entregues el material en '
              'bodega.',
              style: AppTypography.cuerpoChico,
            )
          else ...<Widget>[
            // Lo que falta, en frases. Un código de error no le dice a nadie
            // qué tiene que hacer para poder irse a su casa.
            Text('Falta resolver esto:', style: AppTypography.cuerpoChico),
            const SizedBox(height: 6),
            for (final motivo in estado.motivos)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 2),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    const Icon(Icons.error_outline,
                        size: 16, color: AppColors.error),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(motivo,
                          style: AppTypography.cuerpoChico
                              .copyWith(color: AppColors.error)),
                    ),
                  ],
                ),
              ),
          ],
          const SizedBox(height: 12),
          SizedBox(
            width: double.infinity,
            height: 48,
            child: FilledButton(
              // La señal NO entra en esta decisión: lo que bloquea es que la
              // jornada se contradiga, no que el teléfono no tenga red.
              onPressed: estado.puedeCerrar ? () {} : null,
              child: const Text('Cerrar jornada'),
            ),
          ),
          if (estado.sinSubir > 0)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(
                'Hay ${estado.sinSubir} registro(s) que todavía no subieron. '
                'Suben solos; no hace falta esperar.',
                style: AppTypography.cuerpoChico.copyWith(
                  color: AppColors.onSurfaceVariant,
                ),
              ),
            ),
        ],
      ),
    );
  }
}
