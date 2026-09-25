<script>
  import { Calendar, Link, AlertCircle } from '@lucide/svelte';
  import { formatDate } from '$lib/utils/formatting.js';

  /**
   * @typedef {Object} Task
   * @property {string} id
   * @property {string} title
   * @property {string} status
   * @property {string} priority
   * @property {string|null} [due_date]
   * @property {boolean} [is_overdue]
   * @property {Array<{id: string, user_details?: {email?: string}, email?: string}>} [assigned_to]
   * @property {{id: string, name: string, type: string}|null} [related_entity]
   */

  /** @type {{ item: Task, onclick?: () => void, ondragstart?: (e: DragEvent) => void, ondragend?: () => void }} */
  let { item, onclick, ondragstart, ondragend } = $props();

  // Priority label strip colors keyed by priority
  const priorityLabelBg = {
    High: 'bg-rose-500',
    Medium: 'bg-amber-400',
    Low: 'bg-sky-400'
  };

  const entityLabels = {
    account: 'Account',
    lead: 'Lead',
    opportunity: 'Opportunity',
    case: 'Ticket'
  };

  // Computed values
  const title = $derived(item.title || 'Untitled Task');
  const priority = $derived(item.priority);
  const dueDate = $derived(item.due_date);
  const isOverdue = $derived(item.is_overdue || false);
  const assignees = $derived(item.assigned_to || []);
  const relatedEntity = $derived(item.related_entity);
  const labelBg = $derived(priority ? priorityLabelBg[priority] : null);

  /**
   * Get assignee initials
   * @param {any} assignee
   */
  function getAssigneeInitials(assignee) {
    const email = assignee?.user_details?.email || assignee?.email || '';
    if (!email) return '?';
    return email.charAt(0).toUpperCase();
  }

  /**
   * Get assignee display name
   * @param {any} assignee
   */
  function getAssigneeName(assignee) {
    return assignee?.user_details?.email || assignee?.email || 'Unknown';
  }

  // Generate consistent avatar color from email
  function getAvatarColor(email) {
    const colors = [
      'bg-violet-500',
      'bg-cyan-500',
      'bg-emerald-500',
      'bg-amber-500',
      'bg-rose-500',
      'bg-indigo-500'
    ];
    const hash = email.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0);
    return colors[hash % colors.length];
  }

  /**
   * @param {KeyboardEvent} e
   */
  function handleKeydown(e) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onclick?.();
    }
  }
</script>

<div
  class="task-card group cursor-pointer rounded-lg border border-black/[0.04] bg-white p-2.5 text-left shadow-[0_1px_0_rgba(9,30,66,0.12)] hover:border-black/10 dark:border-white/[0.06] dark:bg-white/[0.05] dark:hover:border-white/[0.1]"
  draggable="true"
  {onclick}
  onkeydown={handleKeydown}
  {ondragstart}
  {ondragend}
  role="button"
  tabindex="0"
>
  <!-- Priority label strip -->
  {#if labelBg}
    <div
      class="mb-1.5 inline-flex h-1.5 w-10 rounded-sm {labelBg}"
      title="{priority} priority"
    ></div>
  {/if}

  <!-- Title -->
  <h4 class="text-[14px] leading-snug font-normal text-gray-900 dark:text-gray-100">
    {title}
  </h4>

  <!-- Related entity (subtle) -->
  {#if relatedEntity}
    <div class="mt-1.5 flex items-center gap-1 text-[12px] text-gray-500 dark:text-gray-400">
      <Link class="h-3 w-3 shrink-0" />
      <span class="truncate">
        {entityLabels[relatedEntity.type] || relatedEntity.type}: {relatedEntity.name}
      </span>
    </div>
  {/if}

  <!-- Footer: due date + assignees -->
  {#if dueDate || assignees.length > 0}
    <div class="mt-2 flex items-center justify-between gap-2">
      <div class="flex items-center gap-1.5">
        {#if dueDate}
          <span
            class="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium
              {isOverdue
              ? 'bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300'
              : 'text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-white/[0.06]'}"
          >
            {#if isOverdue}
              <AlertCircle class="h-3 w-3" />
            {:else}
              <Calendar class="h-3 w-3" />
            {/if}
            {formatDate(dueDate)}
          </span>
        {/if}
      </div>

      {#if assignees.length > 0}
        <div class="flex items-center -space-x-1.5">
          {#each assignees.slice(0, 3) as assignee, i (assignee.id)}
            <div
              class="relative flex h-6 w-6 items-center justify-center rounded-full {getAvatarColor(
                getAssigneeName(assignee)
              )} text-[10px] font-semibold text-white ring-2 ring-white dark:ring-[#262626]"
              style="z-index: {3 - i}"
              title={getAssigneeName(assignee)}
            >
              {getAssigneeInitials(assignee)}
            </div>
          {/each}
          {#if assignees.length > 3}
            <div
              class="relative flex h-6 w-6 items-center justify-center rounded-full bg-gray-200 text-[10px] font-semibold text-gray-700 ring-2 ring-white dark:bg-gray-700 dark:text-gray-200 dark:ring-[#262626]"
              style="z-index: 0"
            >
              +{assignees.length - 3}
            </div>
          {/if}
        </div>
      {/if}
    </div>
  {/if}
</div>

<style>
  .task-card:active {
    cursor: grabbing;
  }
  .task-card:focus-visible {
    outline: 2px solid rgb(34 211 238);
    outline-offset: 2px;
  }
</style>
