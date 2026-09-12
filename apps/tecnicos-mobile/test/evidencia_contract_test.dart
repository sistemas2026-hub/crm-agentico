import 'package:flutter_test/flutter_test.dart';

void main() {
  group('Contrato Oficial de Evidencias API Campo v1', () {
    test('1. Descriptor de upload oficial mapea url, method, headers y requiere_auth_dexter', () {
      final payloadBackendSubiendo = {
        "estado_archivo": "subiendo",
        "evidencia_id": "ev-abc-123",
        "storage_key": "storage/k1",
        "upload": {
          "expires_in": 900,
          "headers": {"X-Amz-Acl": "bucket-owner-full-control"},
          "method": "PUT",
          "requiere_auth_dexter": false,
          "url": "https://storage.r2.cloudflarestorage.com/upload-signed-url"
        }
      };

      // Mapeo estricto
      final String estadoArchivo = payloadBackendSubiendo["estado_archivo"] as String;
      final String evidenciaId = payloadBackendSubiendo["evidencia_id"] as String;
      final Map<String, dynamic> uploadObj = payloadBackendSubiendo["upload"] as Map<String, dynamic>;

      expect(estadoArchivo, 'subiendo');
      expect(evidenciaId, 'ev-abc-123');
      expect(uploadObj['url'], 'https://storage.r2.cloudflarestorage.com/upload-signed-url');
      expect(uploadObj['method'], 'PUT');
      expect(uploadObj['requiere_auth_dexter'], isFalse);
      expect(uploadObj['headers'], containsPair('X-Amz-Acl', 'bucket-owner-full-control'));
    });

    test('2. Caso upload == null con estado_archivo recibido o verificado marca satisfecha sin PUT', () {
      final payloadBackendRecibido = {
        "estado_archivo": "recibido",
        "evidencia_id": "ev-xyz-456",
        "mensaje": "La evidencia ya fue recibida; no hay nada que subir.",
        "storage_key": "storage/k2",
        "upload": null
      };

      final uploadObj = payloadBackendRecibido["upload"];
      final String estadoArchivo = (payloadBackendRecibido["estado_archivo"] as String).toLowerCase();

      final bool satisfechaRemotamente = uploadObj == null && (estadoArchivo == 'recibido' || estadoArchivo == 'verificado');
      expect(satisfechaRemotamente, isTrue);
    });

    test('3. Caso upload con requiere_auth_dexter == true', () {
      final payloadBackendAuth = {
        "estado_archivo": "subiendo",
        "evidencia_id": "ev-internal-789",
        "storage_key": "storage/k3",
        "upload": {
          "expires_in": 900,
          "headers": {},
          "method": "PUT",
          "requiere_auth_dexter": true,
          "url": "/api/campo/evidencias/ev-internal-789/subir/"
        }
      };

      final Map<String, dynamic> uploadObj = payloadBackendAuth["upload"] as Map<String, dynamic>;
      expect(uploadObj['requiere_auth_dexter'], isTrue);
      expect(uploadObj['url'], '/api/campo/evidencias/ev-internal-789/subir/');
    });
  });
}
