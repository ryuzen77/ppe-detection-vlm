<script lang="ts">
  // Tab Laporan: statistik kepatuhan, riwayat pemeriksaan (saring & halaman),
  // foto bukti, ekspor CSV. Statistik dari backend berlaku untuk seluruh
  // riwayat, bukan hanya hasil saringan.
  import Download from '@lucide/svelte/icons/download'
  import RefreshCw from '@lucide/svelte/icons/refresh-cw'
  import { onDestroy, onMount } from 'svelte'
  import ReportTable from '../components/reports/ReportTable.svelte'
  import SnapshotDialog from '../components/reports/SnapshotDialog.svelte'
  import StatTile from '../components/reports/StatTile.svelte'
  import PeriodSelector from '../components/reports/PeriodSelector.svelte'
  import ReportChart from '../components/reports/ReportChart.svelte'
  import MissingItemsChart from '../components/reports/MissingItemsChart.svelte'
  import { api } from '../lib/api/client'
  import type { OrgEntry, ReportRecord, ReportsPage, ReportStatusFilter, ReportPeriod, ReportSummary, ReportWhoFilter, Worker } from '../lib/api/types'
  import { REPORTS as TEXT, count, percent, withError } from '../lib/messages'
  import { complianceTone, historyHead, pageInfo } from '../lib/reports'
  import { REPORTS } from '../lib/settings'
  import { catalog } from '../lib/stores/catalog.svelte'
  import { telemetry } from '../lib/stores/telemetry.svelte'

  const STATUSES: ReportStatusFilter[] = ['all', 'complete', 'incomplete']


  let status = $state<ReportStatusFilter>('all')
  let period = $state<ReportPeriod>('day')
  let date = $state('')
  let offset = $state(0)
  
  let summary = $state<ReportSummary | null>(null)
  let page = $state<ReportsPage | null>(null)
  
  let loading = $state(false)
  let error = $state('')
  let photo = $state<ReportRecord | null>(null)

  // Saringan identitas (T79). Daftar diambil sekali; server tanpa T79a = daftar kosong, saringan disembunyikan
  let workerId = $state<number | null>(null)
  let department = $state('')
  let company = $state('')
  let workerOptions = $state<Worker[]>([])
  let departments = $state<OrgEntry[]>([])
  let companies = $state<OrgEntry[]>([])
  const who = $derived<ReportWhoFilter>({
    worker_id: workerId ?? undefined,
    department: department || undefined,
    company: company || undefined,
  })

  onMount(() => {
    api.workers().then((r) => (workerOptions = r.workers), () => {})
    api.orgList('departments').then((d) => (departments = d), () => {})
    api.orgList('companies').then((c) => (companies = c), () => {})
  })

  // Hanya balasan permintaan terakhir yang dipakai (saringan bisa berganti cepat)
  let requestSeq = 0


  async function load() {
    const seq = ++requestSeq
    loading = true
    try {
      const sumData = await api.reportsSummary({ period, date: date || undefined, ...who })
      if (seq !== requestSeq) return
      summary = sumData

      // Use summary's range to fetch the table data so they match exactly
      const pageData = await api.reports({ 
        limit: REPORTS.pageSize, 
        offset, 
        status, 
        from: summary.range.from,
        to: summary.range.to,
        ...who,
      })
      if (seq !== requestSeq) return
      page = pageData
      
      error = ''
    } catch (e) {
      if (seq !== requestSeq) return
      error = withError(TEXT.loadFailed, e)
    } finally {
      if (seq === requestSeq) loading = false
    }
  }

  // Muat ulang setiap saringan atau halaman berubah
  $effect(() => {
    void [period, date, status, offset, who]
    load()
  })


  function setFilter(apply: () => void) {
    apply()
    offset = 0
  }

  // Pemeriksaan baru terlihat dari riwayat telemetri → muat ulang (ditunda sebentar)
  let lastHead: string | null = null
  let debounce: ReturnType<typeof setTimeout> | null = null
  $effect(() => {
    const head = historyHead(telemetry.data?.history)
    if (lastHead === null || head === lastHead) {
      lastHead = head
      return
    }
    lastHead = head
    if (debounce) clearTimeout(debounce)
    debounce = setTimeout(load, REPORTS.refreshDebounceMs)
  })
  onDestroy(() => {
    if (debounce) clearTimeout(debounce)
  })

  const records = $derived(page?.page_records ?? [])
  const info = $derived(pageInfo(offset, records.length, page?.filtered_total ?? 0))
  const filtered = $derived(status !== 'all' || date !== '' || workerId !== null || department !== '' || company !== '')
</script>

<div class="laporan">
  <header class="head">
    <div>
      <h1>{TEXT.title}</h1>
      <p class="subtitle">{TEXT.subtitle}</p>
    </div>
    <div class="actions">
      <button class="btn" onclick={load} disabled={loading}>
        <RefreshCw size={16} aria-hidden="true" />{TEXT.refresh}
      </button>
      <a class="btn" href={api.exportCsvUrl({ from: summary?.range.from, to: summary?.range.to, ...who })} download title={TEXT.exportHint}>
        <Download size={16} aria-hidden="true" />{TEXT.exportCsv}
      </a>
    </div>
  </header>

  <PeriodSelector bind:period bind:date range={summary?.range ?? null} {loading} />

  <section aria-label={TEXT.stats.ariaLabel}>
    <p class="scope">
      {#if summary}
        {#if summary.range.from === summary.range.to}
          {TEXT.period.formatDate(summary.range.from)}
        {:else}
          {TEXT.period.formatDate(summary.range.from)} – {TEXT.period.formatDate(summary.range.to)}
        {/if}
      {:else}
        {TEXT.stats.scopeAll}
      {/if}
    </p>
    <div class="tiles">
      <StatTile label={TEXT.stats.total} value={count(summary?.totals.total)} />
      <StatTile label={TEXT.stats.passed} value={count(summary?.totals.passed)} />
      <StatTile label={TEXT.stats.denied} value={count(summary?.totals.rejected)} />
      <StatTile label={TEXT.stats.compliance} value={summary?.totals.compliance_rate === null ? '–' : percent(summary?.totals.compliance_rate)}
                meter={summary?.totals.compliance_rate ?? null} tone={complianceTone(summary?.totals.compliance_rate ?? null)} />
      <StatTile label={TEXT.stats.backup} value={count(page?.backup_count)} />
      <StatTile label={TEXT.stats.outages} value={count(page?.system_outages)} 
                note={TEXT.stats.scopeSinceStart} hint={TEXT.stats.outagesHint} />
    </div>
  </section>

  <div class="chart-row">
    <ReportChart buckets={summary?.buckets ?? []} totals={{ total: summary?.totals.total ?? 0 }} />
    <MissingItemsChart items={summary?.missing_items ?? []} />
  </div>

  <section class="card">
    <div class="filters" role="group" aria-label={TEXT.filters.ariaLabel}>
      <div class="segmented">
        {#each STATUSES as s (s)}
          <button class:active={status === s} aria-pressed={status === s}
                  onclick={() => setFilter(() => (status = s))}>{TEXT.filters.status[s]}</button>
        {/each}
      </div>
      {#if workerOptions.length}
        <select class="input who" aria-label={TEXT.filters.worker} value={workerId ?? ""}
                onchange={(e) => setFilter(() => (workerId = e.currentTarget.value ? Number(e.currentTarget.value) : null))}>
          <option value="">{TEXT.filters.allWorkers}</option>
          {#each workerOptions as w (w.id)}<option value={w.id}>{w.name} · {w.employee_no}</option>{/each}
        </select>
      {/if}
      {#if departments.length}
        <select class="input who" aria-label={TEXT.filters.department} value={department}
                onchange={(e) => setFilter(() => (department = e.currentTarget.value))}>
          <option value="">{TEXT.filters.allDepartments}</option>
          {#each departments as d (d.id)}<option value={d.name}>{d.name}</option>{/each}
        </select>
      {/if}
      {#if companies.length}
        <select class="input who" aria-label={TEXT.filters.company} value={company}
                onchange={(e) => setFilter(() => (company = e.currentTarget.value))}>
          <option value="">{TEXT.filters.allCompanies}</option>
          {#each companies as c (c.id)}<option value={c.name}>{c.name}</option>{/each}
        </select>
      {/if}
    </div>

    {#if error}
      <p class="state error" role="alert">{error}</p>
    {/if}

    {#if records.length}
      <ReportTable {records} items={catalog.items} onOpen={(r) => (photo = r)} />
    {:else if !error}
      <p class="state">{loading ? TEXT.loading : (summary?.totals.total === 0 ? TEXT.emptyPeriod : (filtered ? TEXT.emptyFiltered : TEXT.empty))}</p>
    {/if}

    {#if info.total > 0 || info.hasPrev}
      <nav class="pager" aria-label={TEXT.page.ariaLabel}>
        <span class="mono range">{TEXT.page.range(info.from, info.to, info.total)}</span>
        <button class="btn" disabled={!info.hasPrev || loading}
                onclick={() => (offset = Math.max(0, offset - REPORTS.pageSize))}>{TEXT.page.prev}</button>
        <button class="btn" disabled={!info.hasNext || loading}
                onclick={() => (offset += REPORTS.pageSize)}>{TEXT.page.next}</button>
      </nav>
    {/if}
  </section>
</div>

<SnapshotDialog bind:record={photo} />

<style>
  .who {
    width: auto;
    max-width: 240px;
  }

  .chart-row {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-4);
    align-items: stretch;
  }
  @media (max-width: 768px) {
    .chart-row {
      flex-direction: column;
    }
  }

  .laporan {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    padding: var(--space-4);
    max-width: 1400px;
    margin: 0 auto;
  }
  .head {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-end;
    justify-content: space-between;
    gap: var(--space-4);
  }
  h1 {
    margin: 0;
    font-size: var(--text-xl);
  }
  .subtitle {
    margin: var(--space-1) 0 0;
    color: var(--text-muted);
    font-size: var(--text-sm);
  }
  .actions {
    display: flex;
    gap: var(--space-2);
  }
  a.btn {
    text-decoration: none;
    color: var(--text);
  }
  .scope {
    margin: 0 0 var(--space-2);
    font-size: var(--text-xs);
    color: var(--text-faint);
  }
  .tiles {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: var(--space-3);
  }
  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: var(--space-4);
  }
  .filters {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-3);
    margin-bottom: var(--space-3);
  }
  .segmented {
    display: inline-flex;
    padding: 2px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-sm);
    background: var(--surface-2);
  }
  .segmented button {
    padding: 4px 12px;
    border: 0;
    border-radius: 4px;
    background: transparent;
    font-size: var(--text-sm);
    color: var(--text-muted);
    cursor: pointer;
  }
  .segmented button.active {
    background: var(--accent-soft);
    color: var(--text);
  }
  .state {
    margin: var(--space-6) 0;
    text-align: center;
    color: var(--text-faint);
    font-size: var(--text-sm);
  }
  .error {
    color: var(--danger);
  }
  .pager {
    display: flex;
    justify-content: flex-end;
    align-items: center;
    gap: var(--space-2);
    margin-top: var(--space-3);
  }
  .range {
    margin-right: var(--space-2);
    font-size: var(--text-sm);
    color: var(--text-muted);
  }
</style>
