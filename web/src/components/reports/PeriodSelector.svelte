<script lang="ts">
  import type { ReportPeriod, ReportRange } from '../../lib/api/types'
  import { REPORTS as TEXT } from '../../lib/messages'
  import { localDateIso } from '../../lib/attendance'
  import { clampToToday, hasNextPeriod, offsetDate, formatReportRange } from '../../lib/reports'
  import ChevronLeft from '@lucide/svelte/icons/chevron-left'
  import ChevronRight from '@lucide/svelte/icons/chevron-right'
  import { onDestroy } from 'svelte'
  import { CLOCK } from '../../lib/settings'

  let {
    period = $bindable(),
    date = $bindable(),
    range,
    loading = false,
  }: {
    period: ReportPeriod
    date: string
    range: ReportRange | null
    loading?: boolean
  } = $props()

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
  // Diperbarui berkala: halaman yang dibiarkan terbuka melewati tengah malam (tinjauan Codex T95)
  let today = $state(localDateIso())
  const dayTimer = setInterval(() => (today = localDateIso()), CLOCK.tickMs)
  onDestroy(() => clearInterval(dayTimer))
  const canNext = $derived(hasNextPeriod(range?.to, today))
</script>

<div class="selector" role="group" aria-label={TEXT.period.ariaLabel}>
  <div class="segmented">
    {#each periods as p (p)}
      <button
        class:active={period === p}
        aria-pressed={period === p}
        disabled={loading}
        onclick={() => {
          period = p
          date = ''
        }}
      >
        {TEXT.period.options[p]}
      </button>
    {/each}
  </div>

  <div class="nav">
    <div class="nav-range">
      <button class="btn icon" onclick={goPrev} disabled={loading || !range} title={TEXT.period.prev}>
        <ChevronLeft size={16} aria-hidden="true" />
      </button>

      <span class="range-text" aria-live="polite">
        {#if range}
          {formatReportRange(range.from, range.to, TEXT.period.formatDate)}
        {:else}
          ...
        {/if}
      </span>

      <button class="btn icon" onclick={goNext} disabled={loading || !canNext} title={TEXT.period.next}>
        <ChevronRight size={16} aria-hidden="true" />
      </button>
    </div>

    <div class="nav-date">
      <input
        type="date"
        value={date || (range?.from ?? '')}
        max={today}
        disabled={loading}
        onchange={(e) => {
          date = clampToToday(e.currentTarget.value, today)
        }}
        class="date-input"
        title={TEXT.period.jumpToDate}
      />

      {#if date !== ''}
        <button class="btn today" onclick={goToday} disabled={loading}>{TEXT.period.today}</button>
      {/if}
    </div>
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
    max-width: 100%;
  }
  .segmented {
    display: inline-flex;
    padding: 2px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-md);
    background: var(--surface-2);
    max-width: 100%;
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
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-2);
    max-width: 100%;
  }
  .nav-range {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    min-width: 0;
  }
  .nav-date {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    min-width: 0;
  }
  .range-text {
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text);
    min-width: 130px;
    text-align: center;
  }
  .btn.icon {
    padding: 6px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .btn.today {
    font-size: var(--text-xs);
    padding: var(--space-1) var(--space-2);
    flex-shrink: 0;
  }
  .date-input {
    padding: var(--space-1) var(--space-2);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-sm);
    background: var(--surface-2);
    color: var(--text);
    font: inherit;
    font-size: var(--text-sm);
    max-width: 140px;
    box-sizing: border-box;
  }

  @media (max-width: 500px) {
    .selector {
      gap: var(--space-2);
    }
    .segmented button {
      padding: 6px 12px;
    }
    .range-text {
      font-size: var(--text-xs);
      min-width: 0;
    }
    .date-input {
      max-width: 130px;
    }
  }
</style>
