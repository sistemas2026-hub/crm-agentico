import 'dart:convert';

import 'package:campo/features/ejecucion/datos_de_ejecucion.dart';

/// Una ejecución armada a mano, sin base ni sesión.
///
/// PARA QUÉ
/// --------
/// Para poder dibujar la pantalla de ejecución en una prueba o en una captura.
/// Antes leía SQLite y el almacenamiento seguro por su cuenta, así que montarla
/// exigía levantar la base entera — y mezclar eso con pruebas de widget ya
/// colgó la suite de este proyecto una vez.
///
/// Devuelve exactamente la misma forma de datos que la fuente real: las filas
/// son las de la base, con sus columnas en `snake_case` y sus JSON como texto,
/// porque es así como llegan. Si esto los devolviera "más lindos", la pantalla
/// se probaría contra algo que en el teléfono nunca pasa.
class FuenteDeEjecucionFalsa implements FuenteDeEjecucion {
  FuenteDeEjecucionFalsa({
    this.orgId = 'org_rapilink',
    this.profileId = 'prof_carlos',
    this.numero = 4832,
    this.revision = 7,
    List<Map<String, dynamic>>? campos,
    List<Map<String, dynamic>>? requisitos,
    Map<String, dynamic>? valores,
    List<Map<String, dynamic>>? evidencias,
    List<Map<String, dynamic>>? materiales,
    this.sinIdentidad = false,
    this.sinOrden = false,
  })  : campos = campos ?? camposTipicos,
        requisitos = requisitos ?? requisitosTipicos,
        valores = valores ?? <String, dynamic>{},
        evidencias = evidencias ?? <Map<String, dynamic>>[],
        materiales = materiales ?? <Map<String, dynamic>>[];

  final String orgId;
  final String profileId;
  final int numero;
  final int revision;
  final List<Map<String, dynamic>> campos;
  final List<Map<String, dynamic>> requisitos;
  final Map<String, dynamic> valores;
  final List<Map<String, dynamic>> evidencias;
  final List<Map<String, dynamic>> materiales;

  /// Nadie con la sesión iniciada. La pantalla no puede mostrar nada.
  final bool sinIdentidad;

  /// La orden no está en la base del teléfono todavía.
  final bool sinOrden;

  /// Lo que se le pidió escribir. Sirve para comprobar que la pantalla guarda
  /// lo que dice guardar, sin abrir la base.
  final List<Map<String, dynamic>> guardados = <Map<String, dynamic>>[];
  final List<Map<String, dynamic>> transiciones = <Map<String, dynamic>>[];
  int colasProcesadas = 0;
  int resumenesRefrescados = 0;

  static const List<Map<String, dynamic>> camposTipicos =
      <Map<String, dynamic>>[
    <String, dynamic>{
      'clave': 'potencia_rx',
      'etiqueta': 'Potencia óptica en roseta (dBm)',
      'tipo': 'numero',
      'obligatorio': true,
    },
    <String, dynamic>{
      'clave': 'tipo_intervencion',
      'etiqueta': 'Tipo de intervención',
      'tipo': 'opciones',
      'obligatorio': true,
      'opciones': <String>[
        'Reconectorización',
        'Cambio de drop',
        'Cambio de ONT',
      ],
    },
    <String, dynamic>{
      'clave': 'observaciones',
      'etiqueta': 'Observaciones técnicas',
      'tipo': 'texto_largo',
      'obligatorio': false,
    },
  ];

  static const List<Map<String, dynamic>> requisitosTipicos =
      <Map<String, dynamic>>[
    <String, dynamic>{
      'id': 'foto_roseta',
      'descripcion': 'Foto de la roseta terminada',
      'tipo': 'foto',
    },
    <String, dynamic>{
      'id': 'foto_medicion',
      'descripcion': 'Foto de la medición en el power meter',
      'tipo': 'foto',
    },
    <String, dynamic>{
      'id': 'firma_cliente',
      'descripcion': 'Firma del abonado',
      'tipo': 'firma',
    },
  ];

  /// Una evidencia ya capturada, como la guarda la base.
  static Map<String, dynamic> evidencia({
    required String requisitoId,
    String estado = 'confirmada',
  }) =>
      <String, dynamic>{
        'id': 'ev_$requisitoId',
        'requisito_id': requisitoId,
        'archivo_path': '/datos/evidencias/$requisitoId.jpg',
        'subida_estado': estado,
        'mime_type': 'image/jpeg',
      };

  static Map<String, dynamic> material({
    String codigo = 'CON-SC-APC',
    String nombre = 'Conector SC/APC',
    String cantidad = '2',
    String? serie,
  }) =>
      <String, dynamic>{
        'material_codigo': codigo,
        'material_nombre': nombre,
        'cantidad': cantidad,
        'serie': serie ?? '',
        'estado': 'confirmado',
      };

  @override
  Future<DatosDeEjecucion?> cargar(String ordenId) async {
    if (sinIdentidad || sinOrden) return null;
    return DatosDeEjecucion(
      orgId: orgId,
      profileId: profileId,
      orden: <String, dynamic>{
        'id': ordenId,
        'numero': numero,
        'revision': revision,
        'estado': 'en_sitio',
        'cliente_nombre': 'Carlos Gómez Rincón',
        'direccion': 'Cra 45 #12-88, Barrio San José',
        'tipo_nombre': 'Instalación FTTH',
        'tipo_codigo': 'ftth_instalacion',
        'schema_version': 1,
        // Como en la base: JSON en texto, no estructuras de Dart.
        'formulario_campos_json': jsonEncode(campos),
        'formulario_evidencias_json': jsonEncode(requisitos),
      },
      campos: campos,
      requisitosDeEvidencia: requisitos,
      valores: valores,
      evidenciasCapturadas: evidencias,
      materialesUsados: materiales,
    );
  }

  @override
  Future<void> guardarCampo({
    required String orgId,
    required String profileId,
    required String ordenId,
    required String clave,
    required dynamic valor,
  }) async {
    guardados.add(<String, dynamic>{'clave': clave, 'valor': valor});
    valores[clave] = valor;
  }

  @override
  Future<void> encolarEvidencia({
    required String id,
    required String orgId,
    required String profileId,
    required String ordenId,
    required String requisitoId,
    required String archivoPath,
    required String sha256,
    required int tamanoBytes,
    required String mimeType,
    required String registroIdempotencyKey,
    required String confirmacionIdempotencyKey,
  }) async {
    evidencias.add(<String, dynamic>{
      'id': id,
      'requisito_id': requisitoId,
      'archivo_path': archivoPath,
      'subida_estado': 'pendiente',
      'mime_type': mimeType,
    });
  }

  @override
  Future<List<Map<String, dynamic>>> evidenciasDe({
    required String orgId,
    required String profileId,
    required String ordenId,
  }) async =>
      evidencias;

  @override
  Future<List<Map<String, dynamic>>> materialesDe({
    required String orgId,
    required String profileId,
    required String ordenId,
  }) async =>
      materiales;

  @override
  Future<void> transicionar({
    required String orgId,
    required String profileId,
    required String ordenId,
    required String nuevoEstadoLocal,
    required String tipoAccion,
    required int revisionBase,
    required String idempotencyKey,
  }) async {
    transiciones.add(<String, dynamic>{
      'orden': ordenId,
      'estado': nuevoEstadoLocal,
      'accion': tipoAccion,
      'revision_base': revisionBase,
    });
  }

  @override
  void refrescarResumen() => resumenesRefrescados++;

  @override
  void procesarCola() => colasProcesadas++;
}
