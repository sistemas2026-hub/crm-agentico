import 'dart:io';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:uuid/uuid.dart';

/// Dónde vive una fotografía de evidencia mientras espera su turno de subir.
///
/// LA RUTA ES LA IDENTIDAD
/// -----------------------
/// Hasta la v1 el archivo se llamaba `<uuid>.jpg` y vivía en un único
/// `evidencias/` plano, compartido por todas las empresas y todos los técnicos
/// que hubieran usado el teléfono. Peor: ese UUID era uno *distinto* del id de
/// la fila que lo registraba, así que el nombre no servía ni para encontrar su
/// evidencia. El único vínculo entre la foto de la casa de un cliente y su
/// dueño era la columna `archivo_path` — y si esa fila se perdía, quedaba un
/// archivo imposible de atribuir y, por lo tanto, imposible de limpiar.
///
/// Ahora la ruta lleva la identidad adentro:
///
///     evidencias/<org_id>/<profile_id>/<orden_id>/<evidencia_id>.jpg
///
/// Eso da tres cosas que antes no había: se puede borrar todo lo de una cuenta
/// sin consultar la base, un archivo huérfano sigue diciendo de quién era, y
/// el nombre es el id de la evidencia, así que la foto y su fila se encuentran
/// la una a la otra.
class EvidenciaStorageService {
  static const String _evidenciasSubdir = 'evidencias';
  static Directory? _overrideDirectory;

  /// Permite inyectar un directorio en tests unitarios sin depender del canal de plataforma
  static void setOverrideDirectory(Directory? dir) {
    _overrideDirectory = dir;
  }

  /// Retorna el directorio persistente y durable para evidencias offline
  static Future<Directory> getStorageDirectory() async {
    if (_overrideDirectory != null) {
      if (!await _overrideDirectory!.exists()) {
        await _overrideDirectory!.create(recursive: true);
      }
      return _overrideDirectory!;
    }

    final docsDir = await getApplicationDocumentsDirectory();
    final persistentDir = Directory(p.join(docsDir.path, _evidenciasSubdir));
    if (!await persistentDir.exists()) {
      await persistentDir.create(recursive: true);
    }
    return persistentDir;
  }

  /// El directorio de una identidad. Borrarlo entero deja el dispositivo sin
  /// una sola foto de esa cuenta, sin preguntarle nada a la base.
  static Future<Directory> directorioDeIdentidad({
    required String orgId,
    required String profileId,
  }) async {
    final raiz = await getStorageDirectory();
    return Directory(p.join(raiz.path, _seguro(orgId), _seguro(profileId)));
  }

  /// Copia de forma atómica e inmediata el archivo capturado al almacenamiento
  /// persistente privado de Dexter IA para evitar pérdidas por limpieza de /cache.
  ///
  /// [evidenciaId] es el id de la fila que va a registrar esta foto: el
  /// archivo se llama como ella para que el vínculo no dependa solo de la
  /// columna `archivo_path`.
  ///
  /// El archivo de origen se borra al terminar. `image_picker` escribe una
  /// copia recomprimida en el directorio de caché antes de devolver el
  /// `XFile`, y esa copia no la limpiaba nadie: cada fotografía quedaba dos
  /// veces en el teléfono, una de ellas fuera de todo control de identidad.
  static Future<File> persistirArchivoCaptura(
    File tempFile, {
    String? nombreOriginal,
    required String orgId,
    required String profileId,
    required String ordenId,
    required String evidenciaId,
  }) async {
    if (!await tempFile.exists()) {
      throw FileSystemException('El archivo temporal de captura no existe', tempFile.path);
    }

    final raiz = await getStorageDirectory();
    final targetDir = Directory(p.join(
      raiz.path,
      _seguro(orgId),
      _seguro(profileId),
      _seguro(ordenId),
    ));
    if (!await targetDir.exists()) {
      await targetDir.create(recursive: true);
    }

    final extension = p.extension(tempFile.path);
    final extFinal = extension.isNotEmpty ? extension : '.jpg';
    final nombre = evidenciaId.isNotEmpty ? _seguro(evidenciaId) : const Uuid().v4();
    final targetPath = p.join(targetDir.path, '$nombre$extFinal');

    final persistentFile = await tempFile.copy(targetPath);

    // La copia ya está a salvo; el original de caché solo ocupa espacio y
    // duplica el dato. Si no se puede borrar, no es motivo para fallar: la
    // evidencia que importa ya quedó escrita.
    try {
      await tempFile.delete();
    } on FileSystemException {
      // Se ignora a propósito.
    }

    return persistentFile;
  }

  /// Un segmento de ruta que no se puede escapar del directorio.
  ///
  /// Los ids vienen del servidor y son UUID, pero esto arma rutas de archivo:
  /// un valor con `..` o una barra convertiría un borrado por identidad en un
  /// borrado en cualquier parte del disco.
  static String _seguro(String valor) {
    final limpio = valor.replaceAll(RegExp(r'[^A-Za-z0-9_.\-]'), '_');
    if (limpio.isEmpty || limpio == '.' || limpio == '..') return '_';
    return limpio;
  }
}
