<script lang="ts">
  import AdminToken from './settings/AdminToken.svelte'
  import { adminToken } from '../lib/stores/adminToken.svelte'

  let dialog: HTMLDialogElement | undefined = $state()

  $effect(() => {
    if (!dialog) return
    if (adminToken.dialogOpen && !dialog.open) {
      dialog.showModal()
    } else if (!adminToken.dialogOpen && dialog.open) {
      dialog.close()
    }
  })
</script>

<dialog bind:this={dialog} onclose={() => adminToken.close()} aria-labelledby="admin-token-title">
  <AdminToken onClose={() => adminToken.close()} />
</dialog>

<style>
  dialog {
    width: min(460px, calc(100vw - 32px));
    padding: 0;
    border: none;
    border-radius: var(--radius-lg);
    background: transparent;
  }
  dialog::backdrop {
    background: var(--backdrop);
  }
</style>
