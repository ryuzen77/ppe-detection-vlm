<script lang="ts">
  import type { ReportBucket } from '../../lib/api/types'
  import { REPORTS as TEXT } from '../../lib/messages'
  import { CHART } from '../../lib/settings'

  let { buckets }: { buckets: ReportBucket[] } = $props()

  // Find max total to scale the chart
  const maxTotal = $derived(Math.max(1, ...buckets.map(b => b.passed + b.rejected)))
  
  // Chart dimensions
  const height = CHART.height
  const barWidth = CHART.barWidth
  const gap = 16
  const paddingY = 24
  const usableHeight = height - paddingY * 2
  
  // Calculate total width based on number of buckets
  const width = $derived(Math.max(600, buckets.length * (barWidth + gap) + 40))
  
  function getBarHeight(val: number) {
    return (val / maxTotal) * usableHeight
  }
</script>

<div class="chart-container" role="figure" aria-label={TEXT.charts.complianceTitle}>
  <div class="header">
    <h3>{TEXT.charts.complianceTitle}</h3>
    <div class="legend">
      <span class="legend-item passed">
        <span class="dot"></span> {TEXT.charts.passed}
      </span>
      <span class="legend-item rejected">
        <span class="dot"></span> {TEXT.charts.rejected}
      </span>
    </div>
  </div>
  
  {#if buckets.length === 0}
    <div class="empty">{TEXT.charts.noData}</div>
  {:else}
    <div class="svg-scroll">
      <svg {width} {height} viewBox="0 0 {width} {height}">
        <!-- Y Axis Guidelines -->
        {#each [0, 0.25, 0.5, 0.75, 1] as tick}
          <line x1="40" y1={paddingY + usableHeight * (1 - tick)} 
                x2={width} y2={paddingY + usableHeight * (1 - tick)} 
                stroke="var(--border-strong)" stroke-dasharray="4 4" />
          <text x="32" y={paddingY + usableHeight * (1 - tick) + 4} 
                class="axis-label" text-anchor="end">
            {Math.round(maxTotal * tick)}
          </text>
        {/each}
        
        <!-- Bars -->
        {#each buckets as b, i}
          {@const x = 40 + gap + i * (barWidth + gap)}
          {@const passedH = getBarHeight(b.passed)}
          {@const rejectedH = getBarHeight(b.rejected)}
          {@const totalH = passedH + rejectedH}
          {@const y = paddingY + usableHeight - totalH}
          
          <g class="bar-group">
            <title>{b.label}: {b.passed} {TEXT.charts.passed}, {b.rejected} {TEXT.charts.rejected}</title>
            
            <!-- Rejected (Top part) -->
            {#if b.rejected > 0}
              <rect {x} {y} width={barWidth} height={rejectedH} 
                    fill="var(--danger)" class="bar" />
            {/if}
            
            <!-- Passed (Bottom part) -->
            {#if b.passed > 0}
              <rect {x} y={y + rejectedH} width={barWidth} height={passedH} 
                    fill="var(--ok)" class="bar" />
            {/if}
            
            <!-- X Axis Label -->
            <text x={x + barWidth / 2} y={height - 6} 
                  class="axis-label" text-anchor="middle">
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
  .passed .dot { background: var(--ok); }
  .rejected .dot { background: var(--danger); }
  
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
