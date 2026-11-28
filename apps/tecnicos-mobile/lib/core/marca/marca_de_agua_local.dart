/// LA MARCA DE LA EMPRESA, GUARDADA EN EL TELÉFONO (13/11/2026).
///
/// El técnico toma fotos en sótanos, en postes y en veredas sin señal. Si la
/// vista previa dependiera de preguntarle al servidor en ese momento, la marca
/// aparecería y desaparecería según la cobertura -- y una vista previa que a
/// veces no está enseña a no mirarla. Así que se guarda la última que dijo el
/// servidor y se refresca cuando hay red.
///
/// LO QUE SE GUARDA, Y DÓNDE
/// -------------------------
/// ```
/// <documentos>/marca_de_agua/<org_id>/marca.json
/// <documentos>/marca_de_agua/<org_id>/logo
/// ```
///
/// Por empresa, como todo lo local: un teléfono de cuadrilla pasa de mano en
/// mano y la marca de una empresa no puede aparecer sobre la foto de otra.
/// Nada de esto es dato de un cliente --es lo que la propia empresa decidió
/// mostrar en cada foto--, así que no va al almacenamiento cifrado.
///
/// NUNCA LANZA. Sin red, sin permiso, con el servidor viejo que no conoce la
/// ruta: queda lo que había, y si no había nada, la marca apagada. La vista
/// previa no puede costar una foto.
library;

import 'dart:convert';
import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

import '../api/api_client.dart';
import '../api/api_endpoints.dart';
import 'marca_de_agua.dart';

/// Lo que el teléfono sabe de la marca de su empresa.
@immutable
class MarcaDeLaEmpresa {
  const MarcaDeLaEmpresa({
    required this.configuracion,
    this.empresa = '',
    this.tecnico = '',
    this.logoVersion,
    this.logo,
  });

  static const MarcaDeLaEmpresa apagada =
      MarcaDeLaEmpresa(configuracion: ConfiguracionDeMarca.apagada);

  final ConfiguracionDeMarca configuracion;
  final String empresa;

  /// El nombre de quien usa el teléfono, como lo va a estampar el servidor:
  /// nunca su correo (`nombre_para_la_marca`).
  final String tecnico;
  final String? logoVersion;
  final Uint8List? logo;

  factory MarcaDeLaEmpresa.desdeServidor(Map<String, dynamic> j,
      {Uint8List? logo}) {
    final dynamic c = j['configuracion'];
    return MarcaDeLaEmpresa(
      configuracion: ConfiguracionDeMarca.fromJson(
          c is Map ? Map<String, dynamic>.from(c) : null),
      empresa: (j['empresa'] ?? '').toString(),
      tecnico: (j['tecnico'] ?? '').toString(),
      logoVersion: j['logo_version']?.toString(),
      logo: logo,
    );
  }

  Map<String, dynamic> toJson() => <String, dynamic>{
        'configuracion': configuracion.toJson(),
        'empresa': empresa,
        'tecnico': tecnico,
        'logo_version': logoVersion,
      };

  /// Los datos de una foto concreta, con lo que la empresa y la sesión ya
  /// saben. Lo propio de la foto lo trae quien llama.
  DatosDeLaFoto datosDe({
    required DateTime? fecha,
    required Map<String, dynamic> metadatos,
    bool esCaptura = false,
    bool esFirma = false,
  }) =>
      DatosDeLaFoto(
        empresa: empresa,
        tecnico: tecnico,
        fecha: fecha,
        metadatos: metadatos,
        esCaptura: esCaptura,
        esFirma: esFirma,
      );
}

class MarcaDeAguaLocal {
  MarcaDeAguaLocal({this.api, Future<Directory> Function()? raiz})
      : _raiz = raiz ?? getApplicationDocumentsDirectory;

  /// Reemplazable en pruebas; sin él, el cliente de la app.
  final ApiClient? api;
  final Future<Directory> Function() _raiz;

  Future<Directory> _carpeta(String orgId) async {
    final Directory base = await _raiz();
    final String seguro = orgId.replaceAll(RegExp(r'[^A-Za-z0-9_.\-]'), '_');
    return Directory(p.join(base.path, 'marca_de_agua',
        seguro.isEmpty || seguro == '.' || seguro == '..' ? '_' : seguro));
  }

  /// La última que se guardó para esta empresa, o la apagada.
  Future<MarcaDeLaEmpresa> leer(String orgId) async {
    try {
      final Directory dir = await _carpeta(orgId);
      final File json = File(p.join(dir.path, 'marca.json'));
      if (!await json.exists()) return MarcaDeLaEmpresa.apagada;
      final dynamic j = jsonDecode(await json.readAsString());
      if (j is! Map) return MarcaDeLaEmpresa.apagada;
      final File logo = File(p.join(dir.path, 'logo'));
      return MarcaDeLaEmpresa.desdeServidor(
        Map<String, dynamic>.from(j),
        logo: await logo.exists() ? await logo.readAsBytes() : null,
      );
    } catch (_) {
      return MarcaDeLaEmpresa.apagada;
    }
  }

  /// Le pregunta al servidor y guarda. Devuelve lo que quedó guardado.
  ///
  /// El logo se baja solo cuando cambia su huella: la vista se abre cada vez
  /// que el técnico entra a una orden, y bajar el logo cada vez es gastarle
  /// datos por nada.
  Future<MarcaDeLaEmpresa> refrescar(String orgId) async {
    final MarcaDeLaEmpresa anterior = await leer(orgId);
    try {
      final ApiClient cliente = api ?? ApiClient();
      final Response<dynamic> r = await cliente
          .get<dynamic>(ApiEndpoints.marcaDeAgua)
          .timeout(const Duration(seconds: 8));
      dynamic cuerpo = r.data;
      if (cuerpo is String) cuerpo = jsonDecode(cuerpo);
      if (r.statusCode != 200 || cuerpo is! Map) return anterior;
      final MarcaDeLaEmpresa nueva =
          MarcaDeLaEmpresa.desdeServidor(Map<String, dynamic>.from(cuerpo));

      final Directory dir = await _carpeta(orgId);
      await dir.create(recursive: true);
      final File logo = File(p.join(dir.path, 'logo'));

      Uint8List? bytesLogo = anterior.logo;
      if (nueva.logoVersion == null) {
        bytesLogo = null;
        if (await logo.exists()) await logo.delete();
      } else if (nueva.logoVersion != anterior.logoVersion ||
          anterior.logo == null) {
        final Response<List<int>> rl = await cliente
            .get<List<int>>(
              ApiEndpoints.marcaDeAguaLogo,
              options: Options(responseType: ResponseType.bytes),
            )
            .timeout(const Duration(seconds: 15));
        if (rl.statusCode == 200 && rl.data != null) {
          bytesLogo = Uint8List.fromList(rl.data!);
          await logo.writeAsBytes(bytesLogo, flush: true);
        }
      }

      //  El json se escribe AL FINAL: si el logo no bajó, la huella vieja
      //  queda guardada y la próxima vez se reintenta.
      final MarcaDeLaEmpresa guardada = MarcaDeLaEmpresa(
        configuracion: nueva.configuracion,
        empresa: nueva.empresa,
        tecnico: nueva.tecnico,
        logoVersion: bytesLogo == null && nueva.logoVersion != null
            ? anterior.logoVersion
            : nueva.logoVersion,
        logo: bytesLogo,
      );
      await File(p.join(dir.path, 'marca.json'))
          .writeAsString(jsonEncode(guardada.toJson()), flush: true);
      return guardada;
    } catch (_) {
      return anterior;
    }
  }
}
