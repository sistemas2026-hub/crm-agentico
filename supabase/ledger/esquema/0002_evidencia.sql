-- =============================================================================
--  ESQUEMA DEL LEDGER  --  version 2: la evidencia de cada adopcion
-- =============================================================================
--
--  Una fila 'baseline' o 'baseline_humano' dice que una migracion se dio por
--  aplicada SIN ejecutarla. La version 1 guardaba archivo, hash, momento, rol y
--  motivo, pero no contra que manifiesto se decidio, contra que servidor, ni
--  quien declaro autorizarlo. Desde esta version cada fila adoptada lleva
--  'evidencia' (jsonb) con eso. Formato y razones:
--  supabase/ledger/analisis/EVIDENCIA_DE_ADOPCION.md
--
--  UN LEDGER V1 CON FILAS ADOPTADAS NO SE ACTUALIZA. Esas filas no tienen
--  evidencia y no se puede fabricar despues: el servidor, el manifiesto y la
--  persona de aquel momento no se pueden medir hoy. Este paso termina con
--  SQLSTATE LG001 sin cambiar nada, y el migrador sale con exit 8.
-- =============================================================================

do $$
declare
  n bigint;
begin
  select count(*) into n from asistente.migraciones_aplicadas where origen <> 'aplicada';
  if n > 0 then
    raise exception using
      errcode = 'LG001',
      message = format('el ledger tiene %s fila(s) adoptadas (baseline o baseline_humano) '
                       'escritas por la version 1 del esquema, sin evidencia', n),
      hint = 'No se fabrica evidencia historica. Ver '
             'supabase/ledger/analisis/EVIDENCIA_DE_ADOPCION.md';
  end if;
end $$;

alter table asistente.migraciones_aplicadas add column evidencia jsonb;

alter table asistente.migraciones_aplicadas
  add constraint ma_evidencia_objeto
    check (evidencia is null or jsonb_typeof(evidencia) = 'object'),
  -- Toda adopcion la lleva, con sus cinco partes. 'autorizacion' puede ser null
  -- en una baseline automatica; en una humana, no (constraint siguiente).
  add constraint ma_evidencia_adopcion
    check (origen = 'aplicada'
           or (evidencia is not null
               and evidencia ?& array['formato', 'manifiesto', 'entorno',
                                      'verificacion', 'operacion'])),
  add constraint ma_evidencia_autorizacion
    check (origen <> 'baseline_humano'
           or length(btrim(coalesce(evidencia #>> '{autorizacion,declarada_por}', ''))) >= 3);

comment on column asistente.migraciones_aplicadas.evidencia is
  'Solo en filas adoptadas: manifiesto usado (sha256, git blob, referencia), '
  'servidor medido dentro del lock (version y extensiones), comprobaciones, '
  'efectos sin comprobar, rol de la sesion y autorizacion DECLARADA por el '
  'operador (la herramienta no la autentica). Null en filas aplicadas.';
