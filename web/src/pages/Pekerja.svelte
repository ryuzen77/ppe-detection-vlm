<script lang="ts">
  // Halaman Pekerja (T79): daftar selebar layar + detail per orang. Dipindah dari Pengaturan
  // karena dipakai rutin (pekerja baru/keluar/foto ulang), bukan setelan teknis sekali pasang.
  import { onMount } from 'svelte'
  import { api, ApiError } from '../lib/api/client'
  import type { OrgEntry, OrgKind, Worker } from '../lib/api/types'
  import { extractApiError } from '../lib/api/error'
  import { WORKERS, WORKERS_PAGE as TEXT } from '../lib/messages'
  import { filterWorkers, type WorkerStatusFilter } from '../lib/workers'
  import WorkerTable from '../components/workers/WorkerTable.svelte'
  import WorkerDetail from '../components/workers/WorkerDetail.svelte'
  import WorkerAddModal from '../components/workers/WorkerAddModal.svelte'
  import WorkerEditModal from '../components/workers/WorkerEditModal.svelte'
  import WorkerDeleteDialog from '../components/workers/WorkerDeleteDialog.svelte'
  import WorkerPhotoModal from '../components/workers/WorkerPhotoModal.svelte'
  import OrgManager from '../components/workers/OrgManager.svelte'
  import AlertTriangle from '@lucide/svelte/icons/alert-triangle'
  import Building2 from '@lucide/svelte/icons/building-2'
  import Search from '@lucide/svelte/icons/search'
  import ShieldAlert from '@lucide/svelte/icons/shield-alert'
  import UserPlus from '@lucide/svelte/icons/user-plus'

  let workers = $state<Worker[]>([])
  let faceReady = $state(true)
  let galleryLimit = $state<{ tested: number; count: number; over: boolean } | null>(null)
  let orgs = $state<Record<OrgKind, OrgEntry[]>>({ departments: [], companies: [] })
  let loading = $state(false)
  let errorMsg = $state('')

  let q = $state('')
  let status = $state<WorkerStatusFilter>('active')
  let departmentId = $state<number | null>(null)
  let companyId = $state<number | null>(null)
  let selectedId = $state<number | null>(null)

  let showAdd = $state(false)
  let showOrg = $state(false)
  let editing = $state<Worker | null>(null)
  let photoWorker = $state<Worker | null>(null)
  let deleteFaceWorker = $state<Worker | null>(null)
  let deleteTemplateTarget = $state<{ workerId: number; templateId: number } | null>(null)

  const shown = $derived(filterWorkers(workers, { q, status, departmentId, companyId }))
  const selected = $derived(workers.find((w) => w.id === selectedId) ?? null)
  const STATUSES: WorkerStatusFilter[] = ['active', 'inactive', 'all']

  onMount(() => {
    loadWorkers()
    loadOrgs()
  })

  async function loadWorkers() {
    loading = true
    errorMsg = ''
    try {
      const res = await api.workers()
      workers = res.workers
      faceReady = res.face_ready
      galleryLimit = res.limit
    } catch (e) {
      errorMsg = extractApiError(e, WORKERS.errLoad)
    } finally {
      loading = false
    }
  }

  /** Server tanpa T79a (404) = tanpa divisi/perusahaan; kolom & saringannya tidak ditampilkan. */
  async function loadOrgs() {
    try {
      const [departments, companies] = await Promise.all([api.orgList('departments'), api.orgList('companies')])
      orgs = { departments, companies }
    } catch (e) {
      if (!(e instanceof ApiError && e.status === 404)) errorMsg = extractApiError(e, TEXT.errOrgLoad)
    }
  }

  async function toggleActive(worker: Worker) {
    try {
      await (worker.active ? api.deactivateWorker(worker.id) : api.activateWorker(worker.id))
      await loadWorkers()
    } catch (e) {
      errorMsg = extractApiError(e, WORKERS.errStatus)
    }
  }

  async function afterSave(close: () => void) {
    close()
    await Promise.all([loadWorkers(), loadOrgs()])
  }
</script>

<div class="page">
  <div class="head">
    <div>
      <h1>{TEXT.title}</h1>
      <p class="sub">{TEXT.subtitle}</p>
    </div>
    <div class="head-actions">
      {#if orgs.companies.length}
        <button type="button" class="btn" onclick={() => (showOrg = true)}><Building2 size={16} /> {TEXT.manageOrg}</button>
      {/if}
      <button type="button" class="btn btn-primary" onclick={() => (showAdd = true)}><UserPlus size={16} /> {WORKERS.addWorkerBtn}</button>
    </div>
  </div>

  {#if !faceReady}
    <div class="banner warn" role="alert">
      <ShieldAlert size={20} />
      <div><p>{WORKERS.faceDisabledBanner}</p><code>{WORKERS.generateKeyHint}</code></div>
    </div>
  {/if}
  {#if galleryLimit?.over}
    <div class="banner danger" role="alert"><AlertTriangle size={20} /><p>{WORKERS.limitOverWarning(galleryLimit.count, galleryLimit.tested)}</p></div>
  {/if}
  {#if errorMsg}<p class="error" role="alert">{errorMsg}</p>{/if}

  <div class="toolbar">
    <label class="search">
      <Search size={16} aria-hidden="true" />
      <input class="input" type="search" placeholder={TEXT.searchPlaceholder} aria-label={TEXT.searchLabel} bind:value={q} />
    </label>
    <select class="input narrow" aria-label={TEXT.statusLabel} bind:value={status}>
      {#each STATUSES as s (s)}<option value={s}>{TEXT.statusOptions[s]}</option>{/each}
    </select>
    {#if orgs.departments.length}
      <select class="input narrow" aria-label={TEXT.departmentLabel} bind:value={departmentId}>
        <option value={null}>{TEXT.allDepartments}</option>
        {#each orgs.departments as d (d.id)}<option value={d.id}>{d.name}</option>{/each}
      </select>
    {/if}
    {#if orgs.companies.length}
      <select class="input narrow" aria-label={TEXT.companyLabel} bind:value={companyId}>
        <option value={null}>{TEXT.allCompanies}</option>
        {#each orgs.companies as c (c.id)}<option value={c.id}>{c.name}</option>{/each}
      </select>
    {/if}
    <span class="count">{TEXT.shown(shown.length, workers.length)}</span>
  </div>

  <div class="body">
    <div class="list">
      <WorkerTable workers={shown} {loading} {selectedId} onSelect={(w) => (selectedId = w.id)} />
    </div>
    {#if selected}
      <WorkerDetail
        worker={selected}
        onClose={() => (selectedId = null)}
        onEdit={(w) => (editing = w)}
        onEnroll={(w) => (photoWorker = w)}
        onToggleActive={toggleActive}
        onDeleteFace={(w) => (deleteFaceWorker = w)}
        onDeleteTemplate={(workerId, templateId) => (deleteTemplateTarget = { workerId, templateId })}
      />
    {:else if workers.length}
      <p class="pick">{TEXT.pickHint}</p>
    {/if}
  </div>
</div>

<WorkerAddModal show={showAdd} departments={orgs.departments} companies={orgs.companies}
  onClose={() => (showAdd = false)} onSaved={() => afterSave(() => (showAdd = false))} />
<WorkerEditModal worker={editing} departments={orgs.departments} companies={orgs.companies}
  onClose={() => (editing = null)} onSaved={() => afterSave(() => (editing = null))} />
<WorkerPhotoModal worker={photoWorker} onClose={() => (photoWorker = null)} onSaved={() => afterSave(() => (photoWorker = null))} />
<WorkerDeleteDialog {deleteFaceWorker} {deleteTemplateTarget}
  onClose={() => { deleteFaceWorker = null; deleteTemplateTarget = null }}
  onDeleted={() => afterSave(() => { deleteFaceWorker = null; deleteTemplateTarget = null })} />
<OrgManager open={showOrg} lists={orgs} onChanged={loadOrgs} onClose={() => (showOrg = false)} />

<style>
  .page {
    max-width: 1440px;
    margin: 0 auto;
    padding: var(--space-6) var(--space-5) var(--space-8);
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }
  .head {
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    gap: var(--space-4);
    flex-wrap: wrap;
  }
  h1 {
    margin: 0;
    font-size: var(--text-xl);
  }
  .sub {
    margin: var(--space-1) 0 0;
    color: var(--text-muted);
    font-size: var(--text-sm);
  }
  .head-actions {
    display: flex;
    gap: var(--space-2);
    flex-wrap: wrap;
  }
  .banner {
    display: flex;
    align-items: flex-start;
    gap: var(--space-3);
    padding: var(--space-3) var(--space-4);
    border-radius: var(--radius);
    font-size: var(--text-sm);
  }
  .banner p {
    margin: 0 0 var(--space-1);
  }
  .banner.warn {
    color: var(--warn);
    background: var(--warn-soft);
    border: 1px solid var(--warn-line);
  }
  .banner.danger {
    color: var(--danger);
    background: var(--danger-soft);
    border: 1px solid var(--danger-line);
  }
  .error {
    margin: 0;
    color: var(--danger);
    font-size: var(--text-sm);
  }
  .toolbar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-2);
  }
  .search {
    position: relative;
    flex: 1 1 260px;
    max-width: 380px;
    color: var(--text-muted);
  }
  .search :global(svg) {
    position: absolute;
    left: 10px;
    top: 50%;
    transform: translateY(-50%);
  }
  .search .input {
    padding-left: 34px;
  }
  .narrow {
    width: auto;
    min-width: 150px;
  }
  .count {
    margin-left: auto;
    color: var(--text-muted);
    font-size: var(--text-sm);
  }
  .body {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: var(--space-4);
    align-items: start;
  }
  .list {
    min-width: 0;
    background: var(--surface);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-lg);
    overflow: hidden;
  }
  .pick {
    display: none;
  }
  @media (min-width: 1180px) {
    .body {
      grid-template-columns: minmax(0, 1fr) 400px;
    }
    .pick {
      display: block;
      margin: 0;
      padding: var(--space-6);
      color: var(--text-muted);
      font-size: var(--text-sm);
      border: 1px dashed var(--border-strong);
      border-radius: var(--radius-lg);
    }
  }
</style>
