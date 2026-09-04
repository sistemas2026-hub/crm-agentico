/**
 * v2 enums, mirrored 1:1 from the Django models so the API swap is a
 * field mapping, not a translation.
 *
 *   STAGES, OPPORTUNITY_TYPES, SOURCES  → backend/common/utils.py
 *   LEAD_STATUS, LEAD_SOURCE            → backend/common/utils.py
 *   STATUS_CHOICE, PRIORITY_CHOICE,
 *   CASE_TYPE                           → backend/common/utils.py (cases)
 *   INVOICE_STATUS                      → backend/invoices/models.py
 *   aging_status                        → Opportunity.get_aging_status()
 *                                         returns 'green' | 'yellow' | 'red'
 *
 * TONE is the only place colour is decided. Six tones, and Ember is not one
 * of them. Ember belongs to actions, never to status.
 *   ink   → neutral, structural
 *   slate → nothing to do here (includes aging "green": on pace is the
 *           absence of a problem, not an achievement)
 *   clay  → attention, past expected_days
 *   rust  → overdue, stalled, urgent, lost
 *   moss  → won, paid, completed
 */

export const STAGES = [
  'PROSPECTING',
  'QUALIFICATION',
  'PROPOSAL',
  'NEGOTIATION',
  'CLOSED_WON',
  'CLOSED_LOST'
];

/** The four stages a deal moves through before it closes. Drives the meter. */
export const OPEN_STAGES = STAGES.slice(0, 4);

export const STAGE_LABEL = {
  PROSPECTING: 'Prospección',
  QUALIFICATION: 'Calificación',
  PROPOSAL: 'Propuesta',
  NEGOTIATION: 'Negociación',
  CLOSED_WON: 'Ganada',
  CLOSED_LOST: 'Perdida'
};

export const STAGE_TONE = {
  PROSPECTING: 'slate',
  QUALIFICATION: 'slate',
  PROPOSAL: 'ink',
  NEGOTIATION: 'ink',
  CLOSED_WON: 'moss',
  CLOSED_LOST: 'rust'
};

export const OPPORTUNITY_TYPE_LABEL = {
  NEW_BUSINESS: 'Nuevo negocio',
  EXISTING_BUSINESS: 'Negocio existente',
  RENEWAL: 'Renovación',
  UPSELL: 'Venta adicional',
  CROSS_SELL: 'Venta cruzada'
};

/** Opportunity.aging_status. The API returns these three strings verbatim. */
export const AGING_TONE = { green: 'slate', yellow: 'clay', red: 'rust' };
export const AGING_LABEL = { green: 'A tiempo', yellow: 'Atrasada', red: 'Estancada' };

export const LEAD_STATUS_TONE = {
  assigned: 'slate',
  'in process': 'ink',
  converted: 'moss',
  recycled: 'slate',
  closed: 'rust'
};

/**
 * common.utils LEAD_STATUS / LEAD_SOURCE / INDCHOICES: the stored values,
 * verbatim, lowercase and misspellings included. "compaign" is the value in
 * the database; correcting it here would produce a form that writes a value
 * the column rejects.
 *
 * Labels are separate because these are stored the way somebody typed them in
 * 2015 and SHOUTING an industry at a person is not a design decision.
 */
export const LEAD_STATUSES = ['assigned', 'in process', 'converted', 'recycled', 'closed'];

export const LEAD_STATUS_LABEL = {
  assigned: 'Asignado',
  'in process': 'En proceso',
  converted: 'Convertido',
  recycled: 'Reciclado',
  closed: 'Cerrado'
};

/**
 * The statuses the leads LIST can display. `LeadListView` excludes `converted`
 * outright and splits `closed` into a `close_leads` block the frontend never
 * reads, so offering either as a filter option gives a permanently empty page
 * that reads as "you have none" rather than "this page cannot show them".
 * The full set stays in LEAD_STATUSES for the detail page's status select.
 */
export const LEAD_LIST_STATUSES = ['assigned', 'in process', 'recycled'];

export const LEAD_SOURCES = [
  'call',
  'email',
  'existing customer',
  'partner',
  'public relations',
  'compaign',
  'other'
];

export const LEAD_SOURCE_LABEL = {
  call: 'Llamada',
  email: 'Correo',
  'existing customer': 'Cliente existente',
  partner: 'Socio',
  'public relations': 'Relaciones públicas',
  compaign: 'Campaña',
  other: 'Otro'
};

/**
 * Mirrors `leads/workflow.py::IRREVERSIBLE_STATUSES`. A converted lead can be
 * neither re-converted (which would build a second opportunity) nor moved
 * back out (which would orphan the account, contact and opportunity that
 * conversion created). `LeadCreateSerializer.validate_status` refuses both.
 *
 * "closed" is deliberately absent: reopening a closed lead creates nothing and
 * destroys nothing, so it stays an ordinary edit.
 */
export const LEAD_IRREVERSIBLE_STATUSES = ['converted'];

export const INDUSTRIES = [
  'ADVERTISING',
  'AGRICULTURE',
  'APPAREL & ACCESSORIES',
  'AUTOMOTIVE',
  'BANKING',
  'BIOTECHNOLOGY',
  'BUILDING MATERIALS & EQUIPMENT',
  'CHEMICAL',
  'COMPUTER',
  'EDUCATION',
  'ELECTRONICS',
  'ENERGY',
  'ENTERTAINMENT & LEISURE',
  'FINANCE',
  'FOOD & BEVERAGE',
  'GROCERY',
  'HEALTHCARE',
  'INSURANCE',
  'LEGAL',
  'MANUFACTURING',
  'PUBLISHING',
  'REAL ESTATE',
  'SERVICE',
  'SOFTWARE',
  'SPORTS',
  'TECHNOLOGY',
  'TELECOMMUNICATIONS',
  'TELEVISION',
  'TRANSPORTATION',
  'VENTURE CAPITAL'
];

/** Display text for each INDUSTRIES value. The value sent to the API is unchanged. */
export const INDUSTRY_LABEL = {
  ADVERTISING: 'Publicidad',
  AGRICULTURE: 'Agricultura',
  'APPAREL & ACCESSORIES': 'Ropa y accesorios',
  AUTOMOTIVE: 'Automotriz',
  BANKING: 'Banca',
  BIOTECHNOLOGY: 'Biotecnología',
  'BUILDING MATERIALS & EQUIPMENT': 'Materiales y equipos de construcción',
  CHEMICAL: 'Química',
  COMPUTER: 'Informática',
  EDUCATION: 'Educación',
  ELECTRONICS: 'Electrónica',
  ENERGY: 'Energía',
  'ENTERTAINMENT & LEISURE': 'Entretenimiento y ocio',
  FINANCE: 'Finanzas',
  'FOOD & BEVERAGE': 'Alimentos y bebidas',
  GROCERY: 'Supermercado',
  HEALTHCARE: 'Salud',
  INSURANCE: 'Seguros',
  LEGAL: 'Legal',
  MANUFACTURING: 'Manufactura',
  PUBLISHING: 'Editorial',
  'REAL ESTATE': 'Bienes raíces',
  SERVICE: 'Servicios',
  SOFTWARE: 'Software',
  SPORTS: 'Deportes',
  TECHNOLOGY: 'Tecnología',
  TELECOMMUNICATIONS: 'Telecomunicaciones',
  TELEVISION: 'Televisión',
  TRANSPORTATION: 'Transporte',
  'VENTURE CAPITAL': 'Capital de riesgo'
};

export const industryLabel = (v) => (!v ? '' : (INDUSTRY_LABEL[v] ?? v));

export const PRIORITY_TONE = { Urgent: 'rust', High: 'clay', Normal: 'slate', Low: 'slate' };
export const CASE_PRIORITY_LABEL = { Urgent: 'Urgente', High: 'Alta', Normal: 'Normal', Low: 'Baja' };

export const CASE_STATUS_TONE = {
  New: 'ink',
  Assigned: 'ink',
  Pending: 'clay',
  Closed: 'moss',
  Rejected: 'rust',
  Duplicate: 'slate'
};
export const CASE_STATUS_LABEL = {
  New: 'Nuevo',
  Assigned: 'Asignado',
  Pending: 'Pendiente',
  Closed: 'Cerrado',
  Rejected: 'Rechazado',
  Duplicate: 'Duplicado'
};
export const CASE_TYPE_LABEL = { Question: 'Pregunta', Incident: 'Incidente', Problem: 'Problema' };

export const INVOICE_STATUS_TONE = {
  Draft: 'slate',
  Sent: 'ink',
  Viewed: 'ink',
  Paid: 'moss',
  Partially_Paid: 'clay',
  Overdue: 'rust',
  Pending: 'clay',
  Cancelled: 'slate'
};

/** INVOICE_STATUS uses an underscore on the wire; never show it to a person. */
export const INVOICE_STATUS_LABEL = {
  Draft: 'Borrador',
  Sent: 'Enviada',
  Viewed: 'Vista',
  Paid: 'Pagada',
  Partially_Paid: 'Parcialmente pagada',
  Overdue: 'Vencida',
  Pending: 'Pendiente',
  Cancelled: 'Cancelada'
};
export const invoiceStatusLabel = (s) =>
  INVOICE_STATUS_LABEL[s] ?? String(s ?? '').replace(/_/g, ' ');

/**
 * tasks.Task.STATUS_CHOICES / PRIORITY_CHOICES.
 *
 * Note the trap: a Task's priority is Low/Medium/High, while a Case's is
 * Low/Normal/High/Urgent. They are different enums on different models and
 * "Medium" is not a valid case priority. Keeping them in separate maps means
 * a mismatch is a missing key you can see, not a silently unstyled pill.
 */
export const TASK_STATUS = ['New', 'In Progress', 'Completed'];
export const TASK_STATUS_TONE = { New: 'slate', 'In Progress': 'ink', Completed: 'moss' };
export const TASK_STATUS_LABEL = { New: 'Nueva', 'In Progress': 'En progreso', Completed: 'Completada' };

export const TASK_PRIORITY = ['Low', 'Medium', 'High'];
export const TASK_PRIORITY_TONE = { Low: 'slate', Medium: 'slate', High: 'clay' };
export const TASK_PRIORITY_LABEL = { Low: 'Baja', Medium: 'Media', High: 'Alta' };

/**
 * cases.Solution.STATUS_CHOICES, plus the separate is_published flag.
 *
 * Status and published are two different facts: an article can be approved
 * and still unpublished. v1 showed only one of them, so "approved" articles
 * customers could not see looked live. Both are surfaced here.
 */
export const SOLUTION_STATUS = ['draft', 'reviewed', 'approved'];
export const SOLUTION_STATUS_LABEL = { draft: 'Borrador', reviewed: 'Revisado', approved: 'Aprobado' };
export const SOLUTION_STATUS_TONE = { draft: 'slate', reviewed: 'clay', approved: 'moss' };

/**
 * opportunity.SalesGoal, GOAL_TYPES and PERIOD_TYPES from common/utils.py.
 *
 * The status values are the four SalesGoal.status returns, and the labels say
 * what they mean rather than repeating the wire value: "behind" alone does not
 * tell you behind on what. They are pace judgements, not percentages.
 */
export const GOAL_TYPE_LABEL = { REVENUE: 'Ingresos', DEALS_CLOSED: 'Negociaciones cerradas' };

export const PERIOD_TYPE_LABEL = {
  MONTHLY: 'Mensual',
  QUARTERLY: 'Trimestral',
  YEARLY: 'Anual',
  CUSTOM: 'Personalizado'
};

export const GOAL_STATUS_LABEL = {
  completed: 'Meta cumplida',
  on_track: 'A tiempo',
  at_risk: 'Atrasándose',
  behind: 'Atrasada'
};

export const GOAL_STATUS_TONE = {
  completed: 'moss',
  on_track: 'slate',
  at_risk: 'clay',
  behind: 'rust'
};

/** cases.approvals: APPROVAL_STATE_CHOICES. */
export const APPROVAL_STATE_LABEL = {
  pending: 'Esperando',
  approved: 'Aprobado',
  rejected: 'Rechazado',
  cancelled: 'Retirado'
};

export const APPROVAL_STATE_TONE = {
  pending: 'clay',
  approved: 'moss',
  rejected: 'rust',
  cancelled: 'slate'
};

/**
 * invoices.ESTIMATE_STATUS, its own enum, not the invoice one. There is no
 * Paid estimate and no Accepted invoice; keeping the maps apart makes a
 * mix-up show up as a missing key instead of an unstyled pill.
 *
 * Accepted is moss because the customer said yes. Whether it has been turned
 * into an invoice yet is a separate fact, and the list shows it separately.
 * A green pill on money nobody has billed is exactly the wrong reassurance.
 */
export const ESTIMATE_STATUS_TONE = {
  Draft: 'slate',
  Sent: 'ink',
  Viewed: 'ink',
  Accepted: 'moss',
  Declined: 'rust',
  Expired: 'clay'
};

export const ESTIMATE_STATUS_LABEL = {
  Draft: 'Borrador',
  Sent: 'Enviada',
  Viewed: 'Vista',
  Accepted: 'Aceptada',
  Declined: 'Rechazada',
  Expired: 'Vencida'
};

/** invoices.RECURRING_FREQUENCIES; CUSTOM carries its interval in custom_days. */
export const RECURRING_FREQUENCY_LABEL = {
  WEEKLY: 'Semanal',
  BIWEEKLY: 'Cada 2 semanas',
  MONTHLY: 'Mensual',
  QUARTERLY: 'Trimestral',
  SEMI_ANNUALLY: 'Cada 6 meses',
  YEARLY: 'Anual',
  CUSTOM: 'Personalizado'
};

export const PAYMENT_TERMS_LABEL = {
  DUE_ON_RECEIPT: 'A la recepción',
  NET_15: 'A 15 días',
  NET_30: 'A 30 días',
  NET_45: 'A 45 días',
  NET_60: 'A 60 días',
  CUSTOM: 'Personalizado'
};

/**
 * common.Profile.role. Two values, and that is the whole set. ADMIN and USER.
 * Role is server-derived from the profile; nothing the browser sends decides
 * it. This map exists to label a value the API gave us, never to offer one.
 */
export const ROLE_LABEL = { ADMIN: 'Administrador', USER: 'Miembro' };
export const ROLE_TONE = { ADMIN: 'clay', USER: 'slate' };

/* ── ticket handling configuration ──────────────────────────────────────── */

/**
 * cases.RoutingRule.STRATEGY_CHOICES. The model's own labels read like field
 * documentation ("Round-robin within target_assignees"); these read like the
 * sentence the rule performs, because they sit next to the target list that
 * completes them.
 */
export const ROUTING_STRATEGY_LABEL = {
  direct: 'Siempre a',
  round_robin: 'Por turnos entre',
  least_busy: 'A quien tenga menos abiertos, de',
  by_team: 'Cualquiera en'
};

/** Standalone names for the strategy select. `ROUTING_STRATEGY_LABEL` above
 *  is a sentence fragment that runs into the target names on the rule card,
 *  so it cannot double as an option label. */
export const ROUTING_STRATEGY_NAME = {
  direct: 'Directo',
  round_robin: 'Por turnos',
  least_busy: 'Menos ocupado',
  by_team: 'Por equipo'
};

/** Fields a routing condition can test, in the words the rest of the app uses. */
export const CONDITION_FIELD_LABEL = {
  priority: 'Prioridad',
  case_type: 'Tipo',
  account: 'Cuenta',
  tags: 'Etiquetas',
  from_email_domain: 'Dominio del remitente',
  mailbox_id: 'Casilla de correo'
};

export const CONDITION_OP_LABEL = {
  eq: 'es',
  in: 'es uno de',
  contains: 'incluye',
  regex: 'coincide con'
};

/** cases.EscalationPolicy.ACTION_CHOICES. */
export const ESCALATION_ACTION_LABEL = {
  notify: 'Notificar',
  reassign: 'Reasignar a',
  notify_and_reassign: 'Notificar y reasignar a'
};

/** cases.EscalationPolicy priorities, worst first. This is the display order
 *  the escalation page sorts by, not the model's `ordering = ("priority",)`,
 *  which sorts the CharField alphabetically and puts Low between High and
 *  Normal. Imported by both the page and `lib/server/v2/escalation.js`. */
export const ESCALATION_PRIORITIES = ['Urgent', 'High', 'Normal', 'Low'];

/** cases.InboundMailbox.PROVIDER_CHOICES, only SES ships today. */
export const MAILBOX_PROVIDER_LABEL = {
  ses: 'Amazon SES',
  mailgun: 'Mailgun',
  postmark: 'Postmark',
  imap: 'IMAP'
};

/* ── vocabulary ─────────────────────────────────────────────────────────── */

/** common.CustomFieldDefinition.FIELD_TYPE_CHOICES. */
export const FIELD_TYPE_LABEL = {
  text: 'Texto',
  textarea: 'Texto largo',
  number: 'Número',
  dropdown: 'Lista desplegable',
  date: 'Fecha',
  checkbox: 'Casilla de verificación'
};

/** The statuses a reopened ticket may come back as.
 *
 * `ReopenPolicySerializer.NON_TERMINAL_STATUSES` in
 * `backend/cases/serializer.py` is the authority and rejects anything else.
 * Reopening into a terminal status would close the ticket again on arrival,
 * so the model's own choice list, which also carries Closed, Rejected and
 * Duplicate, is not the list to offer.
 */
export const REOPEN_TO_STATUSES = ['New', 'Assigned', 'Pending'];

/** Plural forms for the target model, for reading in a heading. */
export const TARGET_MODEL_LABEL = {
  Account: 'Cuentas',
  Case: 'Tickets',
  Contact: 'Contactos',
  Estimate: 'Cotizaciones',
  Invoice: 'Facturas',
  Lead: 'Prospectos',
  Opportunity: 'Negociaciones',
  RecurringInvoice: 'Facturas recurrentes',
  Task: 'Tareas'
};

export const MACRO_SCOPE_LABEL = { org: 'Todos', personal: 'Solo vos' };

/* ── board ──────────────────────────────────────────────────────────────── */

/**
 * tasks.BoardTask.PRIORITY_CHOICES. Lowercase, and a different set from
 * TASK_PRIORITY (Low/Medium/High) and PRIORITY_TONE (Urgent/High/Normal/Low).
 * Three enums for one word across three models; keep them apart.
 */
export const BOARD_PRIORITY_LABEL = {
  low: 'Baja',
  medium: 'Media',
  high: 'Alta',
  urgent: 'Urgente'
};
export const BOARD_PRIORITY_TONE = {
  low: 'slate',
  medium: 'slate',
  high: 'clay',
  urgent: 'rust'
};

/** tasks.BoardMember.ROLE_CHOICES, board-local, unrelated to Profile.role. */
export const BOARD_ROLE_LABEL = { owner: 'Propietario', admin: 'Administrador', member: 'Miembro' };

/**
 * Option lists for the list-page filters. Values are what goes on the wire;
 * labels are derived where they differ.
 *
 * CASE_PRIORITIES is not TASK_PRIORITY. A Case is Low/Normal/High/Urgent and a
 * Task is Low/Medium/High: "Medium" is not a valid case priority and "Normal"
 * is not a valid task priority. See the note at TASK_STATUS above.
 */
export const CASE_PRIORITIES = ['Low', 'Normal', 'High', 'Urgent'];
export const CASE_TYPES = ['Question', 'Incident', 'Problem'];
export const CASE_STATUSES = ['New', 'Assigned', 'Pending', 'Closed', 'Rejected', 'Duplicate'];
export const INVOICE_STATUSES = [
  'Draft',
  'Sent',
  'Viewed',
  'Paid',
  'Partially_Paid',
  'Overdue',
  'Pending',
  'Cancelled'
];
export const ESTIMATE_STATUSES = ['Draft', 'Sent', 'Viewed', 'Accepted', 'Declined', 'Expired'];
export const DOCUMENT_STATUSES = ['active', 'inactive'];
