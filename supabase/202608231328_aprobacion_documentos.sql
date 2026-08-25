-- =============================================================================
--  22. Aprobacion humana de un documento antes de que el asistente lo use
-- =============================================================================
--  Hasta ahora, un documento subido desde /manual quedaba VIGENTE al
--  instante: se vectorizaba y el asistente podia recuperarlo en la siguiente
--  consulta de un cliente, sin que nadie lo hubiera leido.
--
--  Eso no es un riesgo teorico. Se midio en este proyecto (agosto 2026) que
--  la unica guia de diagnostico existente, G-GO-04, esta escrita para un
--  tecnico en campo: de sus 8 fragmentos, 7 le dirian a un cliente que abra
--  conectores de fibra, mida potencia optica con un Power Meter o reemplace
--  el cable de acometida. Un documento asi, asignado por error al rol de
--  cara al cliente, produce instrucciones peligrosas sin que salte ningun
--  error.
--
--  Es el MISMO criterio que el proyecto ya aplica dos veces:
--    asistente.herramientas_propuestas   una API sondeada no entra al
--                                        catalogo hasta que un ADMIN la aprueba
--    asistente.acciones_propuestas       una escritura no se ejecuta hasta
--                                        que una persona la confirma
--  Ahora tambien: un documento no lo lee el asistente hasta que alguien lo
--  aprueba.
--
--  LA CERRADURA YA EXISTIA, solo faltaba usarla: asistente.match_chunks
--  filtra por d.estado = 'vigente'. Un documento en 'pendiente' es
--  invisible para la recuperacion sin tocar una linea del motor -- la
--  garantia esta en SQL, no en un prompt ni en una condicion del frontend.
--  Ver PRD 7.4: el codigo es la garantia.
--
--  Fail-closed: 'pendiente' no se recupera. Si alguien olvida aprobar, el
--  asistente responde sin ese documento (que es lo que hace hoy igual);
--  nunca al reves.
-- =============================================================================

alter table asistente.documents
  add column if not exists aprobado_por uuid,
  add column if not exists aprobado_en  timestamptz;

comment on column asistente.documents.estado is
  'vigente = el asistente puede recuperarlo (match_chunks filtra por esto). '
  'pendiente = cargado y vectorizado, pero invisible hasta que una persona lo '
  'apruebe. obsoleto = retirado, se conserva para poder reconstruir con que '
  'version se respondio algo.';

comment on column asistente.documents.aprobado_por is
  'Perfil del CRM (public.profile) de quien aprobo el documento para uso del '
  'asistente. Null en los cargados por cli/cargar_corpus.py, que es una '
  'herramienta de operacion y exige credenciales de base -- ahi la revision '
  'la hace quien corre el comando.';

comment on column asistente.documents.aprobado_en is
  'Cuando se aprobo. Junto con aprobado_por deja el rastro de quien "firmo" '
  'que ese contenido puede llegarle a un cliente.';

-- Los documentos que ya estaban cargados siguen vigentes: esta migracion no
-- apaga nada de lo que hoy funciona. El estado 'pendiente' aplica de aca en
-- adelante, y solo a lo que se suba desde la interfaz.
