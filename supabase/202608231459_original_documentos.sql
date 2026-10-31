-- =============================================================================
--  23. El archivo original de cada documento, para que una aprobacion se
--      pueda auditar
-- =============================================================================
--  La migracion 22 agrego que un documento no lo use el asistente hasta que
--  una persona lo apruebe, y registra QUIEN y CUANDO. Le faltaba el QUE: el
--  .docx original no se guardaba en ninguna parte del sistema -- quedaba en
--  la carpeta local de quien lo subio.
--
--  Sin el original, "Fulano aprobo este documento el 14 de agosto" no se
--  puede verificar despues. Se puede reconstruir el TEXTO desde
--  document_chunks, pero no el documento: se pierden las tablas de firma, el
--  registro de cambios, el formato y todo lo que el extractor descarta a
--  proposito (encabezados, pies, boilerplate). Dos archivos distintos pueden
--  producir exactamente los mismos fragmentos y no ser el mismo documento
--  para una auditoria.
--
--  Y el hash por si solo tampoco alcanza: prueba que un archivo que TENES
--  es el que se proceso, pero no te devuelve el archivo si se perdio.
--
--  POR QUE bytea EN POSTGRES Y NO ALMACENAMIENTO DE OBJETOS
--  --------------------------------------------------------
--  De Supabase este proyecto usa deliberadamente solo Postgres (ver
--  DESPLIEGUE.md). Sumar Storage por esto traeria otra credencial, otro
--  backup, otra superficie de fallo y sincronizacion base<->objeto, para
--  ahorrar unos pocos MB: hoy son ~20 documentos de 30 KB a 2 MB. Ademas ya
--  hay precedente de guardar bytes en la base (asistente.media.contenido,
--  para las fotos que mandan los clientes).
--
--  Se guarda aparte de 'media' a proposito: una foto de WhatsApp es
--  contenido transitorio de una conversacion; un manual aprobado es un
--  artefacto versionado y auditable. Mezclarlos mezclaria dos ciclos de vida
--  que no tienen nada que ver.
--
--  El dia que el volumen lo justifique, los bytes se mueven a un
--  almacenamiento de objetos y aca queda la referencia -- la semantica de
--  "esta version fue aprobada" no cambia por eso. Ver DESPLIEGUE.md,
--  seccion de pendientes.
-- =============================================================================

alter table asistente.documents
  add column if not exists original_content bytea,
  add column if not exists nombre_archivo   text,
  add column if not exists mime             text,
  -- Como se FRAGMENTO. El mismo .docx produce fragmentos distintos si cambia
  -- el perfil del chunker: medido en esta sesion, 'exigir_multinivel_sin_
  -- estilo' decide si "1. Objetivo" abre seccion o si el documento colapsa
  -- en bloques cortados por tamaño. Sin registrarlo, no se puede distinguir
  -- "cambio el documento" de "cambiamos nosotros el pipeline y reprocesamos
  -- el mismo documento".
  add column if not exists perfil_fragmentacion jsonb;

comment on column asistente.documents.original_content is
  'El .docx tal como se subio. Es la evidencia de QUE se aprobo: los '
  'fragmentos son una representacion derivada, no la fuente. Null en los '
  'documentos cargados antes de esta migracion cuyo archivo ya no se pudo '
  'recuperar.';

comment on column asistente.documents.perfil_fragmentacion is
  'Con que reglas se partio el documento (perfil del chunker + modelo de '
  'embeddings). Permite distinguir un cambio del documento de un cambio '
  'nuestro del pipeline sobre el mismo documento.';

-- 'hash' ya guardaba el sha256 del archivo desde el esquema original, asi que
-- no hace falta una columna nueva para eso: sirve para integridad y para
-- detectar si alguien vuelve a subir exactamente el mismo archivo.
comment on column asistente.documents.hash is
  'sha256 del archivo original. Con original_content forman el par completo: '
  'el hash prueba integridad, el contenido permite recuperarlo.';
