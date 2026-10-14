<script lang="ts">
  import type { MissingItemStat } from '../../lib/api/types'
  import { REPORTS as TEXT } from '../../lib/messages'
  import { CHART } from '../../lib/settings'

  let { items }: { items: MissingItemStat[] } = $props()
  
  // Show top missing items
  const displayItems = $derived(items.slice(0, CHART.maxMissingItems))
  const maxCount = $derived(Math.max(1, ...displayItems.map(i => i.count)))
  
  const itemHeight = CHART.missingItemHeight
  const paddingY = 16
  const labelWidth = CHART.missingLabelWidth
  const height = $derived(displayItems.length * itemHeight + paddingY * 2)
  const width = '100%'
  
  function getBarWidth(count: number) {
    return `${(count / maxCount) * 100}%`
  }
</script>

<div class="chart-container" role="figure" aria-label={TEXT.charts.missingItemsTitle}>
  <div class="header">
    <h3>{TEXT.charts.missingItemsTitle}</h3>
  </div>
  
  {#if displayItems.length === 0}
    <div class="empty">{TEXT.charts.noData}</div>
  {:else}
    <div class="chart-content">
      {#each displayItems as item}
        <div class="row">
          <div class="label" style="width: {labelWidth}px;" title={item.label}>{item.label}</div>
          <div class="bar-area">
            <div class="bar" style="width: {getBarWidth(item.count)}">
              <span class="count" class:inside={item.count / maxCount > 0.1}>
                {item.count}
              </span>
            </div>
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .chart-container {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: var(--space-4);
    margin-bottom: var(--space-4);
    flex: 1;
    min-width: 0;
    max-width: 100%;
  }
  .header {
    margin-bottom: var(--space-4);
  }
  h3 {
    margin: 0;
    font-size: var(--text-md);
    color: var(--text);
  }
  .empty {
    padding: var(--space-6) 0;
    text-align: center;
    color: var(--text-faint);
    font-size: var(--text-sm);
  }
  .chart-content {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }
  .row {
    display: flex;
    align-items: center;
    gap: var(--space-3);
  }
  .label {
    flex-shrink: 0;
    font-size: var(--text-sm);
    color: var(--text-muted);
    text-align: right;
    line-height: 1.25;
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    overflow: hidden;
    overflow-wrap: break-word;
    word-break: break-word;
  }
  .bar-area {
    flex: 1;
    height: 24px;
    background: var(--surface-2);
    border-radius: var(--radius-sm);
    position: relative;
  }
  .bar {
    height: 100%;
    background: var(--danger-soft);
    border-radius: var(--radius-sm);
    display: flex;
    align-items: center;
    transition: width 0.3s ease;
  }
  .count {
    font-size: var(--text-xs);
    font-weight: 600;
    color: var(--text);
    position: absolute;
    left: calc(100% + 8px);
  }
  /* If bar is wide enough, put text inside */
  .bar:has(.count.inside) {
    justify-content: flex-end;
  }
  .count.inside {
    position: static;
    padding-right: 8px;
    color: var(--danger-fg);
  }
</style>
