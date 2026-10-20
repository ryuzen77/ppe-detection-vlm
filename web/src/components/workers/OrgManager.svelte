<script lang="ts">
  // Kelola daftar divisi & perusahaan (T79). Hapus ditolak server bila masih dipakai pekerja
  // (409 in_use) atau perusahaan bawaan (409 builtin); pesannya ditampilkan apa adanya.
  import { api } from '../../lib/api/client'
  import type { OrgEntry, OrgKind } from '../../lib/api/types'
  import { extractApiError } from '../../lib/api/error'
  import { ORG_MANAGER as TEXT } from '../../lib/messages'

  interface Props {
    open: boolean
    lists: Record<OrgKind, OrgEntry[]>
    onChanged: () => void
    onClose: () => void
  }

  let { open, lists, onChanged, onClose }: Props = $props()

  const KINDS: OrgKind[] = ['departments', 'companies']
  let drafts = $state<Record<OrgKind, string>>({ departments: '', companies: '' })
  let editing = $state<{ kind: OrgKind; id: number; name: string } | null>(null)
  let error = $state('')
  let busy = $state(false)

  async function run(action: () => Promise<unknown>, fallback: string) {
    busy = true
    error = ''
    try {
      await action()
      onChanged()
      return true
    } catch (e) {
      error = extractApiError(e, fallback)
      return false
    } finally {
      busy = false
    }
  }

  async function add(kind: OrgKind, e: Event) {
    e.preventDefault()
    const name = drafts[kind].trim()
    if (name && (await run(() => api.createOrg(kind, name), TEXT.errSave))) drafts[kind] = ''
  }

  async function saveRename(e: Event) {
    e.preventDefault()
    const target = editing
    if (!target || !target.name.trim()) return
    if (await run(() => api.renameOrg(target.kind, target.id, target.name.trim()), TEXT.errSave)) editing = null
  }

  function onKeydown(e: KeyboardEvent) {
    if (open && e.key === 'Escape' && !busy) onClose()
  }
</script>

<svelte:window onkeydown={onKeydown} />

{#if open}
  <div class="overlay" role="dialog" aria-modal="true" aria-labelledby="org-title">
    <div class="card">
      <h2 id="org-title">{TEXT.title}</h2>
      <p class="sub">{TEXT.subtitle}</p>
      {#if error}<p class="error" role="alert">{error}</p>{/if}

      <div class="cols">
        {#each KINDS as kind (kind)}
          <section>
            <h3>{TEXT[kind]}</h3>
            {#if lists[kind].length === 0}<p class="sub">{TEXT.empty}</p>{/if}
            <ul>
              {#each lists[kind] as entry (entry.id)}
                <li>
                  {#if editing?.kind === kind && editing.id === entry.id}
                    <form class="row" onsubmit={saveRename}>
                      <input class="input" bind:value={editing.name} disabled={busy} aria-label={TEXT.renameBtn} />
                      <button class="btn btn-primary" disabled={busy || !editing.name.trim()}>{TEXT.saveBtn}</button>
                    </form>
                  {:else}
                    <span class="name">{entry.name}{#if entry.builtin}<span class="meta"> · {TEXT.builtin}</span>{/if}</span>
                    <span class="meta">{TEXT.workers(entry.workers)}</span>
                    <button type="button" class="btn" disabled={busy} onclick={() => (editing = { kind, id: entry.id, name: entry.name })}>{TEXT.renameBtn}</button>
                    {#if !entry.builtin}
                      <button type="button" class="btn" disabled={busy} onclick={() => run(() => api.deleteOrg(kind, entry.id), TEXT.errDelete)}>{TEXT.deleteBtn}</button>
                    {/if}
                  {/if}
                </li>
              {/each}
            </ul>
            <form class="row" onsubmit={(e) => add(kind, e)}>
              <input class="input" placeholder={TEXT.addPlaceholder[kind]} bind:value={drafts[kind]} disabled={busy} aria-label={TEXT.addPlaceholder[kind]} />
              <button class="btn" disabled={busy || !drafts[kind].trim()}>{TEXT.addBtn}</button>
            </form>
          </section>
        {/each}
      </div>

      <div class="actions"><button type="button" class="btn" onclick={onClose} disabled={busy}>{TEXT.close}</button></div>
    </div>
  </div>
{/if}

<style>
  .overlay {
    position: fixed;
    inset: 0;
    z-index: 50;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: var(--space-4);
    background: var(--backdrop);
  }
  .card {
    width: 100%;
    max-width: 760px;
    max-height: calc(100dvh - 2 * var(--space-4));
    overflow-y: auto;
    padding: var(--space-6);
    background: var(--surface);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-lg);
  }
  h2 {
    margin: 0;
    font-size: var(--text-lg);
  }
  h3 {
    margin: 0 0 var(--space-2);
    font-size: var(--text-md);
  }
  .sub,
  .meta {
    color: var(--text-muted);
    font-size: var(--text-sm);
  }
  .sub {
    margin: var(--space-1) 0 var(--space-4);
  }
  .error {
    color: var(--danger);
    font-size: var(--text-sm);
  }
  .cols {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: var(--space-6);
  }
  ul {
    list-style: none;
    margin: 0 0 var(--space-3);
    padding: 0;
  }
  li {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-2) 0;
    border-bottom: 1px solid var(--border);
    font-size: var(--text-sm);
  }
  .name {
    flex: 1;
    min-width: 0;
  }
  .row {
    display: flex;
    gap: var(--space-2);
    flex: 1;
  }
  .actions {
    display: flex;
    justify-content: flex-end;
    margin-top: var(--space-5);
  }
</style>
