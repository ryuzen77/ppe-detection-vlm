<script lang="ts">
  import Eye from '@lucide/svelte/icons/eye'
  import EyeOff from '@lucide/svelte/icons/eye-off'
  import { ADMIN_TOKEN as TEXT } from '../../lib/messages'
  import { adminToken } from '../../lib/stores/adminToken.svelte'

  let { onClose }: { onClose?: () => void } = $props()

  let value = $state('')
  let visible = $state(false)
  let status = $state(adminToken.reason === 'rejected' ? TEXT.rejected : '')

  $effect(() => {
    if (adminToken.reason === 'rejected') {
      status = TEXT.rejected
    }
  })

  function save(e: SubmitEvent) {
    e.preventDefault()
    if (!value.trim()) return
    adminToken.save(value)
    value = ''
    status = ''
    adminToken.reason = 'manual'
    onClose?.()
  }

  function clear() {
    adminToken.clear()
    value = ''
    status = TEXT.cleared
    adminToken.reason = 'manual'
  }
</script>

<div class="admin-token-card">
  <h2>{TEXT.title}</h2>
  <p class="hint">{TEXT.intro}</p>

  <form onsubmit={save}>
    <label for="admin-token-input">{TEXT.label}</label>
    <div class="field">
      <input id="admin-token-input" type={visible ? 'text' : 'password'} bind:value
             placeholder={TEXT.placeholder} autocomplete="new-password" spellcheck="false" />
      <button type="button" class="btn icon" onclick={() => (visible = !visible)}
              aria-label={visible ? TEXT.hide : TEXT.show} aria-pressed={visible}>
        {#if visible}<EyeOff size={16} />{:else}<Eye size={16} />{/if}
      </button>
    </div>
    <p class="note">{adminToken.hasToken ? TEXT.buttonSet : TEXT.buttonUnset} · {TEXT.checkedLater}</p>
    {#if status}
      <p class="status" class:warn={status === TEXT.rejected} aria-live="polite">{status}</p>
    {/if}

    <div class="actions">
      {#if adminToken.hasToken}
        <button type="button" class="btn" onclick={clear}>{TEXT.clear}</button>
      {/if}
      <span class="spacer"></span>
      {#if onClose}
        <button type="button" class="btn" onclick={onClose}>{TEXT.close}</button>
      {/if}
      <button type="submit" class="btn btn-primary" disabled={!value.trim()}>{TEXT.save}</button>
    </div>
  </form>
</div>

<style>
  .admin-token-card {
    padding: var(--space-6);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-lg);
    background: var(--surface);
    color: var(--text);
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
    background: transparent;
    border: 1px solid transparent;
    color: var(--text-muted);
    cursor: pointer;
    border-radius: var(--radius-sm);
  }
  .icon:hover {
    background: var(--surface-2);
    color: var(--text);
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
    margin: var(--space-2) 0;
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
