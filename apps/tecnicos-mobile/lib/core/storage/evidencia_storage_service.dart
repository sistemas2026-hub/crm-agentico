import 'dart:io';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:uuid/uuid.dart';

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

  /// Copia de forma atómica e inmediata el archivo capturado al almacenamiento
  /// persistente privado de Dexter IA para evitar pérdidas por limpieza de /cache.
  static Future<File> persistirArchivoCaptura(
    File tempFile, {
    String? nombreOriginal,
  }) async {
    if (!await tempFile.exists()) {
      throw FileSystemException('El archivo temporal de captura no existe', tempFile.path);
    }

    final targetDir = await getStorageDirectory();
    final extension = p.extension(tempFile.path);
    final extFinal = extension.isNotEmpty ? extension : '.jpg';
    final uuid = const Uuid().v4();
    final safeName = nombreOriginal != null && nombreOriginal.isNotEmpty
        ? '${uuid}_${p.basenameWithoutExtension(nombreOriginal)}$extFinal'
        : '$uuid$extFinal';

    final targetPath = p.join(targetDir.path, safeName);
    final persistentFile = await tempFile.copy(targetPath);

    return persistentFile;
  }
}
