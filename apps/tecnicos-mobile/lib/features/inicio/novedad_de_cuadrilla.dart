import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';

/// LA NOVEDAD DE LA CUADRILLA (30/10/2026). El usuario: «¿cómo el técnico
/// reporta alguna novedad sin tener que escribir en el ticket, por ejemplo se
/// pinchó la llanta?». SPEC/objetivos/novedad-de-cuadrilla.md.
///
/// De un toque: qué pasó y cuánto afecta. Sube con la cola (sin señal también
/// queda avisada en el teléfono), la oficina la ve en Programación, y si es
/// «el resto del día» el Supervisor pasa sus órdenes sin empezar a otra
/// cuadrilla.

/// Qué pasó: la clave del servidor, cómo se dice y su ícono.
const List<(String, String, IconData)> tiposDeNovedad = <(String, String, IconData)>[
  ('llanta', 'Se pinchó una llanta', Icons.tire_repair),
  ('vehiculo', 'El vehículo se varó', Icons.car_crash),
  ('accidente', 'Accidente', Icons.medical_services_outlined),
  ('clima', 'Lluvia o clima', Icons.thunderstorm_outlined),
  ('sin_material', 'Se quedó sin material', Icons.inventory_2_outlined),
  ('otra', 'Otra novedad', Icons.report_outlined),
];

/// Cuánto afecta. Lo dice el técnico.
const List<(String, String)> cuantoAfecta = <(String, String)>[
  ('media_hora', '30 minutos'),
  ('una_hora', '1 hora'),
  ('resto_del_dia', 'El resto del día'),
];

const Map<String, Duration> _duracion = <String, Duration>{
  'media_hora': Duration(minutes: 30),
  'una_hora': Duration(hours: 1),
};

/// Una novedad como la guarda el teléfono (`cola_novedades`).
class NovedadLocal {
  const NovedadLocal({
    required this.id,
    required this.tipo,
    required this.afecta,
    required this.avisadaEn,
    this.texto = '',
    this.estado = 'pendiente',
    this.resuelta = false,
  });

  final String id;
  final String tipo;
  final String afecta;
  final DateTime avisadaEn;
  final String texto;

  /// pendiente | enviada | fallida
  final String estado;
  final bool resuelta;

  static NovedadLocal? desdeFila(Map<String, dynamic> f) {
    final DateTime? avisada = DateTime.tryParse(f['avisada_en']?.toString() ?? '');
    if (avisada == null) return null;
    return NovedadLocal(
      id: f['id'].toString(),
      tipo: f['tipo']?.toString() ?? 'otra',
      afecta: f['afecta']?.toString() ?? 'resto_del_dia',
      avisadaEn: avisada.toLocal(),
      texto: f['texto']?.toString() ?? '',
      estado: f['estado']?.toString() ?? 'pendiente',
      resuelta: (f['resuelta'] as int? ?? 0) == 1,
    );
  }

  /// No cerrada y, si es corta, dentro de su tiempo: la misma regla que el
  /// servidor (`NovedadDeCuadrilla.vigente`).
  bool vigente(DateTime ahora) {
    if (resuelta) return false;
    final Duration? d = _duracion[afecta];
    return d == null || ahora.isBefore(avisadaEn.add(d));
  }

  String get queFue => tiposDeNovedad
      .firstWhere(((String, String, IconData) t) => t.$1 == tipo,
          orElse: () => tiposDeNovedad.last)
      .$2;

  IconData get icono => tiposDeNovedad
      .firstWhere(((String, String, IconData) t) => t.$1 == tipo,
          orElse: () => tiposDeNovedad.last)
      .$3;

  /// «desde las 10:12 · hasta las 10:42», o «desde las 10:12 · el resto del día».
  String get cuando {
    String hm(DateTime d) =>
        '${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}';
    final Duration? d = _duracion[afecta];
    return d == null
        ? 'desde las ${hm(avisadaEn)} · el resto del día'
        : 'desde las ${hm(avisadaEn)} · hasta las ${hm(avisadaEn.add(d))}';
  }
}

/// La hoja para avisar. Devuelve (tipo, afecta, texto), o null si se cerró.
class HojaDeNovedad extends StatefulWidget {
  const HojaDeNovedad({super.key});

  @override
  State<HojaDeNovedad> createState() => _HojaDeNovedadState();
}

class _HojaDeNovedadState extends State<HojaDeNovedad> {
  String? _tipo;
  String? _afecta;
  final TextEditingController _texto = TextEditingController();

  @override
  void dispose() {
    _texto.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final bool listo = _tipo != null && _afecta != null;
    return Padding(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.margen,
        AppSpacing.md,
        AppSpacing.margen,
        AppSpacing.md + MediaQuery.of(context).viewInsets.bottom,
      ),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Text('¿Qué pasó?', style: AppTypography.tituloChico),
            const SizedBox(height: AppSpacing.sm),
            Wrap(
              spacing: AppSpacing.xs,
              runSpacing: AppSpacing.xs,
              children: <Widget>[
                for (final (String, String, IconData) t in tiposDeNovedad)
                  ChoiceChip(
                    key: ValueKey<String>('tipo-${t.$1}'),
                    avatar: Icon(t.$3, size: 18),
                    label: Text(t.$2),
                    selected: _tipo == t.$1,
                    onSelected: (_) => setState(() => _tipo = t.$1),
                  ),
              ],
            ),
            const SizedBox(height: AppSpacing.md),
            Text('¿Cuánto te afecta?', style: AppTypography.tituloChico),
            const SizedBox(height: AppSpacing.sm),
            Wrap(
              spacing: AppSpacing.xs,
              runSpacing: AppSpacing.xs,
              children: <Widget>[
                for (final (String, String) a in cuantoAfecta)
                  ChoiceChip(
                    key: ValueKey<String>('afecta-${a.$1}'),
                    label: Text(a.$2),
                    selected: _afecta == a.$1,
                    onSelected: (_) => setState(() => _afecta = a.$1),
                  ),
              ],
            ),
            if (_afecta == 'resto_del_dia') ...<Widget>[
              const SizedBox(height: AppSpacing.xs),
              Text(
                'Tus órdenes sin empezar pasan a otra cuadrilla.',
                style: AppTypography.etiquetaChica.copyWith(color: AppColors.onSurfaceVariant),
              ),
            ],
            const SizedBox(height: AppSpacing.md),
            TextField(
              key: const ValueKey<String>('texto-de-la-novedad'),
              controller: _texto,
              maxLength: 280,
              maxLines: 2,
              decoration: const InputDecoration(
                labelText: 'Algo más (opcional)',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: AppSpacing.sm),
            FilledButton.icon(
              key: const ValueKey<String>('avisar-novedad'),
              onPressed: listo
                  ? () => Navigator.of(context).pop((_tipo!, _afecta!, _texto.text.trim()))
                  : null,
              icon: const Icon(Icons.campaign_outlined),
              label: const Text('Avisar a la oficina'),
            ),
          ],
        ),
      ),
    );
  }
}

/// La franja de Inicio mientras la novedad dura.
class FranjaDeNovedad extends StatelessWidget {
  const FranjaDeNovedad({super.key, required this.novedad, this.onYaSegui});

  final NovedadLocal novedad;
  final VoidCallback? onYaSegui;

  @override
  Widget build(BuildContext context) {
    final String subida = switch (novedad.estado) {
      'enviada' => 'La oficina ya la tiene',
      'fallida' => 'No se pudo avisar: llamá a la oficina',
      _ => 'Sin enviar: sube cuando haya señal',
    };
    return Container(
      key: const ValueKey<String>('franja-de-novedad'),
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.errorContainer,
        borderRadius: AppRadius.brTarjeta,
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Icon(novedad.icono, color: AppColors.onErrorContainer),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  novedad.queFue,
                  style: AppTypography.cuerpo.copyWith(
                    color: AppColors.onErrorContainer,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                Text(
                  novedad.cuando,
                  style: AppTypography.cuerpoChico.copyWith(color: AppColors.onErrorContainer),
                ),
                Text(
                  subida,
                  style: AppTypography.etiquetaChica.copyWith(color: AppColors.onErrorContainer),
                ),
              ],
            ),
          ),
          if (onYaSegui != null)
            TextButton(
              key: const ValueKey<String>('ya-segui'),
              onPressed: onYaSegui,
              child: const Text('Ya seguí'),
            ),
        ],
      ),
    );
  }
}
