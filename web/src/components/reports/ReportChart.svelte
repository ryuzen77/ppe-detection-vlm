<script lang="ts">
  import type { ReportBucket } from '../../lib/api/types'
  import { REPORTS as TEXT } from '../../lib/messages'
  import { CHART } from '../../lib/settings'

  let { buckets, totals }: { buckets: ReportBucket[]; totals: { total: number } } = $props()

  // Find max total to scale the chart
  const maxTotal = $derived(Math.max(1, ...buckets.map((b) => b.passed + b.rejected)))

  import { calculateYAxis } from '../../lib/reports'

  let scrollWidth = $state(0)

  // Chart dimensions
  const height = CHART.height
  const barWidth = CHART.barWidth
  const gap = CHART.gap
  const paddingY = CHART.paddingY
  const axisXStart = CHART.axisXStart
  const usableHeight = height - paddingY * 2

  // Calculate width: at least minRequiredWidth to avoid crowded bars, or fills available container width
  const minRequiredWidth = $derived(axisXStart + buckets.length * (barWidth + gap) + gap)
  const width = $derived(Math.max(scrollWidth || 0, minRequiredWidth))

  const yTicks = $derived(calculateYAxis(maxTotal, paddingY, usableHeight))
  const yMax = $derived(yTicks[yTicks.length - 1]?.value || maxTotal || 1)

  function getBarHeight(val: number) {
    return (val / yMax) * usableHeight
  }

  const availablePlotWidth = $derived(Math.max(0, width - axisXStart - gap))
  const slotWidth = $derived(buckets.length > 0 ? availablePlotWidth / buckets.length : barWidth + gap)
</script>

<div class="chart-container" role="figure" aria-label={TEXT.charts.complianceTitle}>
  <div class="header">
    <h3>{TEXT.charts.complianceTitle}</h3>
    <div class="legend">
      <span class="legend-item passed">
        <span class="dot"></span>
        {TEXT.charts.passed}
      </span>
      <span class="legend-item rejected">
        <span class="dot"></span>
        {TEXT.charts.rejected}
      </span>
    </div>
  </div>

  {#if totals.total === 0}
    <div class="empty">{TEXT.charts.noData}</div>
  {:else}
    <div class="svg-scroll" bind:clientWidth={scrollWidth}>
      <svg {width} {height} viewBox="0 0 {width} {height}">
        <!-- Y Axis Guidelines -->
        {#each yTicks as t (t.value)}
          <line x1={axisXStart} y1={t.y} x2={width} y2={t.y} stroke="var(--border-strong)" stroke-dasharray="4 4" />
          <text x={axisXStart - 8} y={t.y + 4} class="axis-label" text-anchor="end">
            {t.value}
          </text>
        {/each}

        <!-- Bars -->
        {#each buckets as b, i (b.start)}
          {@const slotCenter = axisXStart + gap / 2 + i * slotWidth + slotWidth / 2}
          {@const x = slotCenter - barWidth / 2}
          {@const passedH = getBarHeight(b.passed)}
          {@const rejectedH = getBarHeight(b.rejected)}
          {@const totalH = passedH + rejectedH}
          {@const y = paddingY + usableHeight - totalH}

          <g class="bar-group">
            <title>{b.label}: {b.passed} {TEXT.charts.passed}, {b.rejected} {TEXT.charts.rejected}</title>

            <!-- Rejected (Top part) -->
            {#if b.rejected > 0}
              <rect {x} {y} width={barWidth} height={rejectedH} fill="var(--danger)" class="bar" />
            {/if}

            <!-- Passed (Bottom part) -->
            {#if b.passed > 0}
              <rect {x} y={y + rejectedH} width={barWidth} height={passedH} fill="var(--ok)" class="bar" />
            {/if}

            <!-- X Axis Label -->
            <text x={slotCenter} y={height - 6} class="axis-label" text-anchor="middle">
              {b.label}
            </text>
          </g>
        {/each}
      </svg>
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
    flex: 2;
    min-width: 0;
    max-width: 100%;
  }
  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: var(--space-4);
  }
  h3 {
    margin: 0;
    font-size: var(--text-md);
    color: var(--text);
  }
  .legend {
    display: flex;
    gap: var(--space-3);
  }
  .legend-item {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: var(--text-xs);
    color: var(--text-muted);
  }
  .dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
  }
  .passed .dot {
    background: var(--ok);
  }
  .rejected .dot {
    background: var(--danger);
  }

  .empty {
    height: 240px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-faint);
    font-size: var(--text-sm);
  }

  .svg-scroll {
    overflow-x: auto;
    overflow-y: hidden;
    width: 100%;
    max-width: 100%;
  }
  svg {
    display: block;
    min-width: 100%;
  }
  .axis-label {
    font-size: 10px;
    fill: var(--text-muted);
    font-family: inherit;
  }
  .bar {
    transition: opacity 0.2s;
  }
  .bar-group:hover .bar {
    opacity: 0.8;
  }
</style>
