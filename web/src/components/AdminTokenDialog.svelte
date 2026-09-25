<script lang="ts">
  // Isian token admin. Terbuka dari tombol kunci di bilah atas, atau otomatis
  // saat server menolak perintah (401). Token tidak pernah ditampilkan ulang:
  // isian selalu kosong saat dibuka, cukup "tersimpan / belum".
  import Eye from '@lucide/svelte/icons/eye'
  import EyeOff from '@lucide/svelte/icons/eye-off'
  import { ADMIN_TOKEN as TEXT } from '../lib/messages'
  import { adminToken } from '../lib/stores/adminToken.svelte'

  let dialog: HTMLDialogElement | undefined = $state()
  let value = $state('')
  let visible = $state(false)
  let status = $state('')

  $effect(() => {
    if (!dialog) return
    if (adminToken.dialogOpen && !dialog.open) {
      value = ''
      visible = false
      status = adminToken.reason === 'rejected' ? TEXT.rejected : ''
      dialog.showModal()
    } else if (!adminToken.dialogOpen && dialog.open) {
      dialog.close()
    }
  })

  function save(e: SubmitEvent) {
    e.preventDefault()
    if (!value.trim()) return
    adminToken.save(value)
    value = ''
    status = TEXT.saved
  }

  function clear() {
    adminToken.clear()
    value = ''
    status = TEXT.cleared
  }
</script>

<dialog bind:this={dialog} onclose={() => adminToken.close()} aria-labelledby="admin-token-title">
  <h2 id="admin-token-title">{TEXT.title}</h2>
  <p class="hint">{TEXT.intro}</p>

  <form onsubmit={save}>
    <label for="admin-token-input">{TEXT.label}</label>
    <div class="field">
      <input id="admin-token-input" type={visible ? 'text' : 'password'} bind:value
             placeholder={TEXT.placeholder} autocomplete="off" spellcheck="false" />
      <button type="button" class="btn icon" onclick={() => (visible = !visible)}
              aria-label={visible ? TEXT.hide : TEXT.show} aria-pressed={visible}>
        {#if visible}<EyeOff size={16} />{:else}<Eye size={16} />{/if}
      </button>
    </div>
    <p class="note">{adminToken.hasToken ? TEXT.buttonSet : TEXT.buttonUnset} · {TEXT.checkedLater}</p>
    <p class="status" class:warn={adminToken.reason === 'rejected' && status === TEXT.rejected} aria-live="polite">{status}</p>

    <div class="actions">
      {#if adminToken.hasToken}
        <button type="button" class="btn" onclick={clear}>{TEXT.clear}</button>
      {/if}
      <span class="spacer"></span>
      <button type="button" class="btn" onclick={() => adminToken.close()}>{TEXT.close}</button>
      <button type="submit" class="btn btn-primary" disabled={!value.trim()}>{TEXT.save}</button>
    </div>
  </form>
</dialog>

<style>
  dialog {
    width: min(460px, calc(100vw - 32px));
    padding: var(--space-6);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-lg);
    background: var(--surface);
    color: var(--text);
  }
  dialog::backdrop {
    background: var(--backdrop);
  }
  h2 {
    margin: 0 0 var(--space-2);
    font-size: var(--text-lg);
  }
  .hint {
    margin: 0 0 var(--space-4);
    color: var(--text-muted);
    font-size: var(--text-sm);
  }
  label {
    display: block;
    margin-bottom: var(--space-1);
    font-size: var(--text-sm);
    color: var(--text-muted);
  }
  .field {
    display: flex;
    gap: var(--space-2);
  }
  input {
    flex: 1;
    min-width: 0;
    padding: 6px 10px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-sm);
    background: var(--surface-2);
    color: var(--text);
    font: inherit;
    font-family: var(--font-mono);
  }
  .icon {
    padding: 6px;
  }
  .note {
    margin: var(--space-2) 0 0;
    font-size: var(--text-xs);
    color: var(--text-faint);
  }
  .status {
    min-height: 1.4em;
    font-size: var(--text-sm);
    color: var(--text-muted);
  }
  .warn {
    color: var(--warn);
  }
  .actions {
    display: flex;
    gap: var(--space-2);
    align-items: center;
  }
  .spacer {
    flex: 1;
  }
</style>
