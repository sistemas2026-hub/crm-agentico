-- =============================================================================
-- B5: ACCIONES LIGADAS A SU CONVERSACION  (contrato §3.4, §3.7, §9.3, T12, T13)
-- =============================================================================
-- Una accion propuesta no sabia de donde venia. Sin eso no hay forma de
-- revalidarla al aprobar --¿el ticket de que conversacion? ¿sigue abierta?--,
-- ni de impedir que la IA proponga dos veces lo mismo, ni de que venza sola.
-- G3 cerro el agujero mas grande (aprobar ya no ejecuta el legado); esto le da
-- a las acciones NUEVAS lo que les faltaba para poder aprobarse con seguridad.
--
-- QUE SE AGREGA
-- -------------
--   conversation_id      NULLABLE, y solo por el legado (§3.4). Toda accion
--                        nueva la lleva; las 36 viejas se quedan en NULL y
--                        siguen sin poder aprobarse (X24).
--
--   vence_en             creado_en + la vigencia que declara la herramienta
--                        (§3.7). NULLABLE: una herramienta que todavia no
--                        declara vigencia no puede fabricar una fecha, y
--                        fabricarla seria inventar un plazo que nadie decidio.
--                        Sin vence_en no hay vencimiento; con el, aprobar
--                        despues del plazo es imposible.
--
--   clave_equivalencia   hash de (conversation_id, herramienta, argumentos en
--                        forma canonica). El indice unico PARCIAL --solo sobre
--                        'pendiente' y 'ejecutando'-- impide que dos propuestas
--                        equivalentes esten VIVAS a la vez, y a la vez permite
--                        proponer de nuevo lo mismo cuando la anterior ya se
--                        resolvio. Las dos cosas importan: la primera evita dos
--                        tickets por el mismo problema, la segunda deja
--                        reintentar despues de un rechazo.
--
--   estado               el CHECK completo de §3.4. Reemplaza al de G3, que
--                        solo conocia cuatro estados porque eran los unicos
--                        que el codigo escribia.
--
-- QUE NO CAMBIA
-- -------------
-- Ninguna fila. Las 36 de legado siguen 'pendiente', con conversation_id NULL,
-- vence_en NULL y clave_equivalencia NULL -- el indice es parcial y ademas
-- ignora los NULL, asi que no colisionan entre ellas. No se migran ni se
-- adoptan (§11.4).

alter table asistente.acciones_propuestas
  add column if not exists conversation_id uuid
    references asistente.conversations(id) on delete set null,
  add column if not exists vence_en timestamptz,
  add column if not exists clave_equivalencia text;

-- El catalogo completo de §3.4. Va NOT VALID por lo mismo que el de G3: no
-- escanear una tabla de produccion, y aun asi validar todo lo nuevo.
alter table asistente.acciones_propuestas
  drop constraint if exists acciones_propuestas_estado_declarado;
alter table asistente.acciones_propuestas
  add constraint acciones_propuestas_estado_declarado
  check (estado in ('pendiente', 'ejecutando', 'ejecutada_ok', 'ejecutada_fallo',
                    'aprobada', 'rechazada', 'vencida', 'cancelada', 'desconocida'))
  not valid;

-- 'aprobada' sigue en la lista y no es un descuido: es el estado terminal que
-- escribieron las filas de antes de B5. Los caminos nuevos escriben
-- ejecutada_ok / ejecutada_fallo, que dicen ademas COMO termino.

-- Dos propuestas equivalentes no pueden estar vivas a la vez (T12).
create unique index if not exists acciones_propuestas_equivalencia_viva
  on asistente.acciones_propuestas (organization_id, clave_equivalencia)
  where estado in ('pendiente', 'ejecutando');

-- Lo que la pantalla de una conversacion pregunta: sus acciones, las ultimas
-- primero.
create index if not exists acciones_propuestas_conv_idx
  on asistente.acciones_propuestas (organization_id, conversation_id, creado_en desc)
  where conversation_id is not null;

-- Lo que T20 barre: lo que quedo a medias o vencido. Parcial, asi que no crece
-- con el historico.
create index if not exists acciones_propuestas_a_revisar_idx
  on asistente.acciones_propuestas (organization_id, estado, vence_en)
  where estado in ('pendiente', 'ejecutando');

-- El expediente de una accion gana un tipo mas: la propuesta que no se creo
-- porque ya habia una equivalente viva (T12). Se registra sobre la accion QUE
-- SIGUE VIVA --no sobre la que no se creo, que no tiene fila-- y por eso
-- importa: dice que el pedido se repitio, que es justo lo que alguien querria
-- saber al revisarla.
alter table asistente.acciones_eventos
  drop constraint if exists acciones_eventos_tipo_check;
alter table asistente.acciones_eventos
  add constraint acciones_eventos_tipo_check
  check (tipo in ('accion_aprobada', 'accion_rechazada', 'accion_cancelada',
                  'accion_vencida', 'accion_desconocida',
                  'accion_propuesta_duplicada',
                  'accion_aprobacion_rechazada'));
