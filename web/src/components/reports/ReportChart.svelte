<script lang="ts">
  import type { ReportBucket } from '../../lib/api/types'
  import { REPORTS as TEXT } from '../../lib/messages'
  import { CHART } from '../../lib/settings'

  let { buckets, totals }: { buckets: ReportBucket[]; totals: { total: number } } = $props()

  import { BUCKET_SERIES, bucketSegments, bucketTitle, bucketTotal, calculateYAxis } from '../../lib/reports'

  // Skala grafik dari batang tertinggi (lolos + ditahan + ditolak, T101)
  const maxTotal = $derived(Math.max(1, ...buckets.map(bucketTotal)))
  const SERIES_LABEL = { passed: TEXT.charts.passed, held: TEXT.charts.held, rejected: TEXT.charts.rejected }

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
      {#each [...BUCKET_SERIES].reverse() as s (s.key)}
        <span class="legend-item">
          <span class="dot" style:background="var(--{s.tone})"></span>
          {SERIES_LABEL[s.key]}
        </span>
      {/each}
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
          {@const y = paddingY + usableHeight - getBarHeight(bucketTotal(b))}

          <g class="bar-group">
            <title>{bucketTitle(b, SERIES_LABEL)}</title>

            <!-- Ditolak (atas) → Ditahan → Lolos (bawah) -->
            {#each bucketSegments(b, getBarHeight) as seg (seg.key)}
              <rect {x} y={y + seg.offset} width={barWidth} height={seg.height} fill="var(--{seg.tone})" class="bar" />
            {/each}

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
