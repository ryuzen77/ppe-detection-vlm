<script lang="ts">
  import type { ReportPeriod, ReportRange } from '../../lib/api/types'
  import { REPORTS as TEXT } from '../../lib/messages'
  import ChevronLeft from '@lucide/svelte/icons/chevron-left'
  import ChevronRight from '@lucide/svelte/icons/chevron-right'

  let { 
    period = $bindable(), 
    date = $bindable(), 
    range,
    loading = false 
  }: { 
    period: ReportPeriod
    date: string
    range: ReportRange | null
    loading?: boolean
  } = $props()

  function offsetDate(base: string, days: number) {
    const d = new Date(base + 'T00:00:00')
    d.setDate(d.getDate() + days)
    const y = d.getFullYear()
    const m = String(d.getMonth() + 1).padStart(2, '0')
    const day = String(d.getDate()).padStart(2, '0')
    return `${y}-${m}-${day}`
  }

  function goPrev() {
    if (range) date = offsetDate(range.from, -1)
  }

  function goNext() {
    if (range) date = offsetDate(range.to, 1)
  }

  function goToday() {
    date = ''
  }

  const periods: ReportPeriod[] = ['day', 'week', 'month']
</script>

<div class="selector" role="group" aria-label={TEXT.period.ariaLabel}>
  <div class="segmented">
    {#each periods as p (p)}
      <button class:active={period === p} aria-pressed={period === p} disabled={loading}
              onclick={() => { period = p; date = '' }}>
        {TEXT.period.options[p]}
      </button>
    {/each}
  </div>

  <div class="nav">
    <button class="btn icon" onclick={goPrev} disabled={loading || !range} title={TEXT.period.prev}>
      <ChevronLeft size={16} aria-hidden="true" />
    </button>
    <span class="range-text" aria-live="polite">
      {#if range}
        {#if range.from === range.to}
          {TEXT.period.formatDate(range.from)}
        {:else}
          {TEXT.period.formatRange(range.from, range.to)}
        {/if}
      {:else}
        ...
      {/if}
    </span>
    <button class="btn icon" onclick={goNext} disabled={loading || !range} title={TEXT.period.next}>
      <ChevronRight size={16} aria-hidden="true" />
    </button>
    {#if date !== ''}
      <button class="btn today" onclick={goToday} disabled={loading}>{TEXT.period.today}</button>
    {/if}
  </div>
</div>

<style>
  .selector {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
    margin-bottom: var(--space-4);
  }
  .segmented {
    display: inline-flex;
    padding: 2px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-md);
    background: var(--surface-2);
  }
  .segmented button {
    padding: 6px 16px;
    border: 0;
    border-radius: var(--radius-sm);
    background: transparent;
    font-size: var(--text-sm);
    font-weight: 500;
    color: var(--text-muted);
    cursor: pointer;
    transition: all 0.2s ease;
  }
  .segmented button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  .segmented button.active {
    background: var(--accent-soft);
    color: var(--text);
  }
  .nav {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }
  .range-text {
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text);
    min-width: 200px;
    text-align: center;
  }
  .btn.icon {
    padding: 6px;
    border-radius: 50%;
  }
  .btn.today {
    margin-left: var(--space-2);
    font-size: var(--text-xs);
    padding: 4px 8px;
  }
</style>
