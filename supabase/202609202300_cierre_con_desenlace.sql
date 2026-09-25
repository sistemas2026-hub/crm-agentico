-- =============================================================================
--  B6: EL CIERRE DICE POR QUE  (contrato del relevo §3.1, §3.5, T15a/b, T16, T17)
-- =============================================================================
--  Hoy una conversacion se cierra y no queda nada de por que. 'estado' pasa a
--  'cerrada' y se acabo: no se sabe si el cliente confirmo, si vencio el plazo,
--  si una persona la resolvio, ni que le paso al cliente. La bandeja queda
--  limpia y el aprendizaje se pierde entero.
--
--  QUE SE AGREGA A asistente.conversations
--  ---------------------------------------
--    cerrada_por_tipo     'cliente' | 'ia_cliente' | 'plazo' | 'inactividad' |
--                         'operador'. QUIEN la cerro, no por que. Los cinco son
--                         los caminos de cierre de §6 (T15a, T15b, T16, T18,
--                         T17), y cada uno tiene reglas distintas sobre el
--                         desenlace.
--    cerrada_por_usuario_id  el operador, cuando lo hubo. NULL en los cierres
--                         automaticos: ahi no hay a quien atribuirselo, y poner
--                         un id inventado seria peor que no tener ninguno.
--    desenlace_codigo     que le paso al cliente. El catalogo base vive en
--                         codigo (nucleo/relevo/desenlaces.py) y cada empresa
--                         puede extenderlo desde la interfaz; por eso aca NO
--                         hay CHECK de valores: un CHECK enumerado obligaria a
--                         una migracion cada vez que una empresa agrega un
--                         codigo propio, que es exactamente lo que este
--                         proyecto no hace con los datos de empresa.
--    desenlace_categoria_base  la categoria de plataforma a la que ese codigo
--                         pertenecia EN EL MOMENTO DEL CIERRE.
--    desenlace_nota       texto corto del operador. Sin PII por contrato (X19).
--
--  POR QUE SE GUARDA LA CATEGORIA Y NO SOLO EL CODIGO
--  --------------------------------------------------
--  Las metricas de plataforma agrupan por categoria_base (§3.5). Si la
--  categoria se resolviera al LEER, contra la config de hoy, una empresa que
--  renombra o retira un codigo propio reescribiria el pasado: los cierres de
--  hace tres meses cambiarian de categoria, o dejarian de tener ninguna. Es la
--  misma razon por la que 'sincronizaciones_externas.datos_intencion' guarda lo
--  que habia que hacer y no se reconstruye con la config actual (§3.6).
--
--  Un codigo base es su propia categoria, asi que para los doce de plataforma
--  las dos columnas coinciden. La diferencia aparece con los propios:
--  'fibra_poste_17' -> 'red_distribucion'.
--
--  LA REGLA QUE SI SE PUEDE ESCRIBIR EN LA BASE
--  --------------------------------------------
--  Que solo una conversacion CERRADA tenga datos de cierre. Lo contrario
--  --una abierta con desenlace-- no significa nada y no deberia poder existir.
--
--  Lo que NO se exige aca es que toda cerrada tenga desenlace: T15a, T15b y
--  T18 cierran con NULL a proposito (§3.5), y ademas ya hay conversaciones
--  cerradas de antes de esta migracion. Que el cierre MANUAL exija codigo se
--  decide en la transicion, no en la tabla: es una regla sobre quien cierra,
--  no sobre la forma del dato.
--
--  QUE NO CAMBIA
--  -------------
--  Ninguna fila existente. Las cinco columnas son nullable y sin default, asi
--  que el ADD COLUMN es metadata-only (PG11+) y no reescribe la tabla.

alter table asistente.conversations
  add column if not exists cerrada_por_tipo text,
  add column if not exists cerrada_por_usuario_id uuid,
  add column if not exists desenlace_codigo text,
  add column if not exists desenlace_categoria_base text,
  add column if not exists desenlace_nota text;

alter table asistente.conversations
  drop constraint if exists conversations_cerrada_por_tipo_check;
alter table asistente.conversations
  add constraint conversations_cerrada_por_tipo_check
  check (cerrada_por_tipo is null
         or cerrada_por_tipo in ('cliente', 'ia_cliente', 'plazo',
                                 'inactividad', 'operador'));

-- Datos de cierre solo en una conversacion cerrada.
alter table asistente.conversations
  drop constraint if exists conversations_cierre_solo_si_cerrada;
alter table asistente.conversations
  add constraint conversations_cierre_solo_si_cerrada
  check (estado = 'cerrada'
         or (cerrada_por_tipo is null and cerrada_por_usuario_id is null
             and desenlace_codigo is null and desenlace_categoria_base is null
             and desenlace_nota is null));

-- El codigo y su categoria viajan juntos o no viajan. Un desenlace sin
-- categoria no entra a ninguna metrica de plataforma y nadie se entera.
alter table asistente.conversations
  drop constraint if exists conversations_desenlace_con_categoria;
alter table asistente.conversations
  add constraint conversations_desenlace_con_categoria
  check ((desenlace_codigo is null) = (desenlace_categoria_base is null));

-- Un operador es quien cierra a mano; en los cierres automaticos no hay quien.
alter table asistente.conversations
  drop constraint if exists conversations_cerrada_por_usuario_solo_operador;
alter table asistente.conversations
  add constraint conversations_cerrada_por_usuario_solo_operador
  check (cerrada_por_usuario_id is null or cerrada_por_tipo = 'operador');

-- La nota es del operador y es corta (§3.3: hasta 500 caracteres, sin PII).
alter table asistente.conversations
  drop constraint if exists conversations_desenlace_nota_corta;
alter table asistente.conversations
  add constraint conversations_desenlace_nota_corta
  check (desenlace_nota is null or length(desenlace_nota) <= 500);

-- Las metricas leen por categoria y por periodo. Parcial: solo las cerradas
-- con desenlace, que es una fraccion de la tabla.
create index if not exists conversations_desenlace_idx
  on asistente.conversations (organization_id, desenlace_categoria_base, actualizado_en)
  where desenlace_categoria_base is not null;

comment on column asistente.conversations.desenlace_categoria_base is
  'Categoria de plataforma del desenlace EN EL MOMENTO DEL CIERRE. No se '
  'recalcula al leer: la config de la empresa puede cambiar, y el pasado no.';
comment on column asistente.conversations.cerrada_por_tipo is
  'Quien cerro (T15a cliente, T15b ia_cliente, T16 plazo, T18 inactividad, '
  'T17 operador). No es el desenlace: es el camino.';
