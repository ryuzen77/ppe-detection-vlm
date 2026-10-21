<script lang="ts">
  // Laporan → tab Kehadiran (T80): siapa saja yang lewat gerbang pada satu hari. Informasi dari
  // pengenalan wajah, BUKAN absensi resmi — label & keterangan wajib (keputusan pengguna 21-10).
  import Download from '@lucide/svelte/icons/download'
  import Info from '@lucide/svelte/icons/info'
  import RefreshCw from '@lucide/svelte/icons/refresh-cw'
  import StatTile from './StatTile.svelte'
  import { api } from '../../lib/api/client'
  import type { AttendanceReport, OrgEntry } from '../../lib/api/types'
  import { attendanceError, attendanceTiles, localDateIso, orgText } from '../../lib/attendance'
  import { ATTENDANCE as TEXT, REPORTS } from '../../lib/messages'

  let { departments, companies }: { departments: OrgEntry[]; companies: OrgEntry[] } = $props()

  const today = localDateIso()
  let date = $state(today)
  let department = $state('')
  let company = $state('')
  let report = $state<AttendanceReport | null>(null)
  let loading = $state(false)
  let error = $state('')

  const filter = $derived({ date, department: department || undefined, company: company || undefined })
  const tiles = $derived(report ? attendanceTiles(report) : [])

  // Hanya balasan permintaan terakhir yang dipakai (tanggal/saringan bisa berganti cepat)
  let seq = 0
  async function load() {
    const mine = ++seq
    loading = true
    try {
      const data = await api.attendance(filter)
      if (mine !== seq) return
      report = data
      error = ''
    } catch (e) {
      if (mine !== seq) return
      report = null
      error = attendanceError(e)
    } finally {
      if (mine === seq) loading = false
    }
  }

  $effect(() => {
    void filter
    load()
  })
</script>

<div class="attendance">
  <p class="notice" role="note"><Info size={16} aria-hidden="true" /> {TEXT.notice}</p>

  <div class="toolbar">
    <label class="date">
      <span>{TEXT.date}</span>
      <input class="input" type="date" max={today} bind:value={date} />
    </label>
    {#if departments.length}
      <select class="input" aria-label={REPORTS.filters.department} bind:value={department}>
        <option value="">{REPORTS.filters.allDepartments}</option>
        {#each departments as d (d.id)}<option value={d.name}>{d.name}</option>{/each}
      </select>
    {/if}
    {#if companies.length}
      <select class="input" aria-label={REPORTS.filters.company} bind:value={company}>
        <option value="">{REPORTS.filters.allCompanies}</option>
        {#each companies as c (c.id)}<option value={c.name}>{c.name}</option>{/each}
      </select>
    {/if}
    <div class="actions">
      <button class="btn" onclick={load} disabled={loading}><RefreshCw size={16} aria-hidden="true" />{REPORTS.refresh}</button>
      <a class="btn" href={api.attendanceCsvUrl(filter)} download><Download size={16} aria-hidden="true" />{TEXT.exportCsv}</a>
    </div>
  </div>

  {#if error}
    <p class="error" role="alert">{error}</p>
  {:else if !report}
    <p class="muted">{TEXT.loading}</p>
  {:else}
    <div class="tiles">
      {#each tiles as tile (tile.label)}
        <StatTile label={tile.label} value={tile.value} note={tile.hint} tone={tile.tone}
                  meter={tile.label === TEXT.tiles.rate && report.totals.recognition_rate !== null ? report.totals.recognition_rate * 100 : null} />
      {/each}
    </div>

    <section class="card" aria-labelledby="att-seen">
      <h2 id="att-seen">{TEXT.sections.seen} <span class="count">{report.seen.length}</span></h2>
      {#if report.seen.length}
        <div class="table-wrap">
          <table>
            <thead><tr>
              <th>{TEXT.cols.no}</th><th>{TEXT.cols.name}</th><th>{TEXT.cols.org}</th>
              <th>{TEXT.cols.first}</th><th>{TEXT.cols.last}</th><th>{TEXT.cols.passes}</th><th>{TEXT.cols.result}</th>
            </tr></thead>
            <tbody>
              {#each report.seen as w (w.worker_id)}
                <tr>
                  <td class="mono">{w.employee_no}</td>
                  <td class="name">{w.name}</td>
                  <td class="muted">{orgText(w.department, w.company)}</td>
                  <td class="mono">{w.first_seen}</td>
                  <td class="mono">{w.last_seen}</td>
                  <td>{w.passes} <span class="muted">({TEXT.passResult(w.passed, w.rejected)})</span></td>
                  <td><span class="tag {w.last_complete ? 'tag-ok' : 'tag-danger'}">{w.last_complete ? TEXT.lastPassed : TEXT.lastRejected}</span></td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      {:else}
        <p class="muted">{TEXT.emptySeen}</p>
      {/if}
    </section>

    <section class="card" aria-labelledby="att-not-seen">
      <h2 id="att-not-seen">{TEXT.sections.notSeen} <span class="count">{report.not_seen.length}</span></h2>
      <p class="hint">{TEXT.notSeenNotice}</p>
      {#if report.not_seen.length}
        <div class="table-wrap">
          <table>
            <thead><tr><th>{TEXT.cols.no}</th><th>{TEXT.cols.name}</th><th>{TEXT.cols.org}</th></tr></thead>
            <tbody>
              {#each report.not_seen as w (w.worker_id)}
                <tr><td class="mono">{w.employee_no}</td><td class="name">{w.name}</td><td class="muted">{orgText(w.department, w.company)}</td></tr>
              {/each}
            </tbody>
          </table>
        </div>
      {:else}
        <p class="muted">{TEXT.emptyNotSeen}</p>
      {/if}
    </section>
  {/if}
</div>

<style>
  .attendance {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }
  .notice {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    margin: 0;
    padding: var(--space-3) var(--space-4);
    border: 1px solid var(--warn-line);
    border-radius: var(--radius);
    background: var(--warn-soft);
    color: var(--warn);
    font-size: var(--text-sm);
    font-weight: 600;
  }
  .toolbar {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-end;
    gap: var(--space-2);
  }
  .date {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    font-size: var(--text-xs);
    color: var(--text-muted);
  }
  .toolbar select {
    width: auto;
    min-width: 160px;
  }
  .actions {
    display: flex;
    gap: var(--space-2);
    margin-left: auto;
  }
  .tiles {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: var(--space-3);
  }
  .card {
    padding: var(--space-4) var(--space-5);
    background: var(--surface);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-lg);
  }
  h2 {
    margin: 0 0 var(--space-3);
    font-size: var(--text-md);
  }
  .count {
    margin-left: var(--space-1);
    color: var(--text-muted);
    font-weight: 500;
  }
  .table-wrap {
    overflow-x: auto;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: var(--text-sm);
  }
  th,
  td {
    padding: var(--space-2) var(--space-3);
    text-align: left;
    border-bottom: 1px solid var(--border);
    white-space: nowrap;
  }
  th {
    font-size: var(--text-xs);
    font-weight: 600;
    color: var(--text-muted);
  }
  .name {
    font-weight: 600;
  }
  .muted,
  .hint {
    color: var(--text-muted);
  }
  .hint {
    margin: 0 0 var(--space-3);
    font-size: var(--text-sm);
  }
  .error {
    margin: 0;
    color: var(--danger);
    font-size: var(--text-sm);
  }
</style>
