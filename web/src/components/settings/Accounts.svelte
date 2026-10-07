<script lang="ts">
  import { onMount } from 'svelte'
  import { api, ApiError } from '../../lib/api/client'
  import type { AccountInfo } from '../../lib/api/types'
  import { session } from '../../lib/stores/session.svelte'
  import { AUTH } from '../../lib/messages'
  import { MIN_PASSWORD_LENGTH } from '../../lib/settings'
  import { formatServerDate } from '../../lib/formatters'
  import { extractApiError } from '../../lib/api/error'
  
  let accounts = $state<AccountInfo[]>([])
  let loading = $state(false)
  let errorMsg = $state('')

  // Add account
  let newUsername = $state('')
  let newPassword = $state('')
  let adding = $state(false)
  let addError = $state('')

  // Change password
  let currentPassword = $state('')
  let changePasswordNew = $state('')
  let changePasswordConfirm = $state('')
  let changingPassword = $state(false)
  let changePasswordError = $state('')
  let changePasswordSuccess = $state('')

  // Dialog Reset Password
  let resetUser = $state<string | null>(null)
  let resetPasswordNew = $state('')
  let resetting = $state(false)
  let resetError = $state('')
  let resetSuccess = $state('')

  // Dialog Delete Account
  let deleteUser = $state<string | null>(null)
  let deleting = $state(false)
  let deleteError = $state('')

  onMount(() => {
    loadAccounts()
  })

  async function loadAccounts() {
    loading = true
    errorMsg = ''
    try {
      accounts = await api.accounts()
    } catch (e) {
      errorMsg = extractApiError(e)
    } finally {
      loading = false
    }
  }

  async function handleAddAccount(e: Event) {
    e.preventDefault()
    addError = ''
    if (newPassword.length < MIN_PASSWORD_LENGTH) {
      addError = AUTH.errorPasswordLength
      return
    }
    adding = true
    try {
      await api.createAccount({ username: newUsername, password: newPassword })
      newUsername = ''
      newPassword = ''
      await loadAccounts()
    } catch (e) {
      addError = extractApiError(e)
    } finally {
      adding = false
    }
  }

  function confirmDelete(username: string) {
    deleteUser = username
    deleteError = ''
  }

  async function executeDelete(e: Event) {
    e.preventDefault()
    if (!deleteUser) return
    deleting = true
    deleteError = ''
    try {
      await api.deleteAccount(deleteUser)
      deleteUser = null
      await loadAccounts()
    } catch (e) {
      deleteError = extractApiError(e)
    } finally {
      deleting = false
    }
  }

  function startReset(username: string) {
    resetUser = username
    resetPasswordNew = ''
    resetError = ''
    resetSuccess = ''
  }

  async function executeReset(e: Event) {
    e.preventDefault()
    if (!resetUser) return
    resetError = ''
    resetSuccess = ''
    if (resetPasswordNew.length < MIN_PASSWORD_LENGTH) {
      resetError = AUTH.errorPasswordLength
      return
    }
    resetting = true
    try {
      await api.resetAccountPassword(resetUser, { new_password: resetPasswordNew })
      resetSuccess = AUTH.resetSuccess.replace('{user}', resetUser)
      setTimeout(() => { resetUser = null; resetSuccess = '' }, 2000)
    } catch (e) {
      resetError = AUTH.resetFailed.replace('{err}', extractApiError(e))
    } finally {
      resetting = false
    }
  }

  async function handleChangePassword(e: Event) {
    e.preventDefault()
    changePasswordError = ''
    changePasswordSuccess = ''
    if (changePasswordNew.length < MIN_PASSWORD_LENGTH) {
      changePasswordError = AUTH.errorPasswordLength
      return
    }
    if (changePasswordNew !== changePasswordConfirm) {
      changePasswordError = AUTH.errorPasswordMismatch
      return
    }
    changingPassword = true
    try {
      await api.changePassword({ current_password: currentPassword, new_password: changePasswordNew })
      currentPassword = ''
      changePasswordNew = ''
      changePasswordConfirm = ''
      changePasswordSuccess = AUTH.successPasswordChange
    } catch (e) {
      changePasswordError = extractApiError(e)
    } finally {
      changingPassword = false
    }
  }

</script>

<section class="card">
  <h2>{AUTH.accounts}</h2>

  <div class="split-layout">
    <div class="accounts-list-container">
      <h3>{AUTH.listAccounts}</h3>
      {#if errorMsg}
        <div class="error-box" role="alert">{errorMsg}</div>
      {/if}
      {#if loading}
        <p>{AUTH.loadingAccounts}</p>
      {:else}
        <table class="accounts-table">
          <thead>
            <tr>
              <th>{AUTH.username}</th>
              <th>{AUTH.role}</th>
              <th>{AUTH.createdAt}</th>
              <th>{AUTH.lastLogin}</th>
              <th>{AUTH.actions}</th>
            </tr>
          </thead>
          <tbody>
            {#each accounts as acc (acc.username)}
              <tr>
                <td>{acc.username} {acc.username === session.user?.username ? AUTH.you : ''}</td>
                <td>{acc.role}</td>
                <td>{formatServerDate(acc.created_at)}</td>
                <td>{formatServerDate(acc.last_login_at)}</td>
                <td>
                  {#if acc.username !== session.user?.username}
                    <button class="btn btn-small" onclick={() => startReset(acc.username)}>{AUTH.resetPassword}</button>
                    <button class="btn btn-small tone-danger" onclick={() => confirmDelete(acc.username)}>{AUTH.deleteBtn}</button>
                  {/if}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      {/if}

      <div class="add-account-box">
        <h3>{AUTH.addAccount}</h3>
        {#if addError}
          <div class="error-box" role="alert">{addError}</div>
        {/if}
        <form class="inline-form" onsubmit={handleAddAccount}>
          <input type="text" placeholder={AUTH.username} bind:value={newUsername} disabled={adding} required />
          <input type="password" placeholder={AUTH.passwordMin} bind:value={newPassword} disabled={adding} required />
          <button type="submit" class="btn btn-primary" disabled={adding || !newUsername || !newPassword}>{AUTH.addBtn}</button>
        </form>
      </div>
    </div>

    <div class="change-password-box">
      <h3>{AUTH.changeOwnPassword}</h3>
      {#if changePasswordError}
        <div class="error-box" role="alert">{changePasswordError}</div>
      {/if}
      {#if changePasswordSuccess}
        <div class="success-box" role="alert">{changePasswordSuccess}</div>
      {/if}
      <form class="vertical-form" onsubmit={handleChangePassword}>
        <input type="password" placeholder={AUTH.currentPassword} bind:value={currentPassword} disabled={changingPassword} required />
        <input type="password" placeholder={AUTH.newPassword} bind:value={changePasswordNew} disabled={changingPassword} required />
        <input type="password" placeholder={AUTH.repeatNewPassword} bind:value={changePasswordConfirm} disabled={changingPassword} required />
        <button type="submit" class="btn btn-primary" disabled={changingPassword || !currentPassword || !changePasswordNew}>{AUTH.saveNewPassword}</button>
      </form>
    </div>
  </div>
</section>

{#if resetUser}
<div class="modal-overlay">
  <div class="modal-card">
    <h3>{AUTH.resetConfirmTitle} - {resetUser}</h3>
    {#if resetError}<div class="error-box">{resetError}</div>{/if}
    {#if resetSuccess}<div class="success-box">{resetSuccess}</div>{/if}
    {#if !resetSuccess}
    <form class="vertical-form" onsubmit={executeReset}>
      <input type="password" placeholder={AUTH.newPassword} bind:value={resetPasswordNew} disabled={resetting} required />
      <div class="modal-actions">
        <button type="button" class="btn" onclick={() => resetUser = null} disabled={resetting}>{AUTH.cancelBtn}</button>
        <button type="submit" class="btn btn-primary" disabled={resetting || !resetPasswordNew}>{AUTH.resetPassword}</button>
      </div>
    </form>
    {/if}
  </div>
</div>
{/if}

{#if deleteUser}
<div class="modal-overlay">
  <div class="modal-card">
    <h3>{AUTH.deleteConfirmTitle}</h3>
    <p>{AUTH.deleteConfirmPrompt.replace('{user}', deleteUser)}</p>
    {#if deleteError}<div class="error-box">{deleteError}</div>{/if}
    <form class="vertical-form" onsubmit={executeDelete}>
      <div class="modal-actions">
        <button type="button" class="btn" onclick={() => deleteUser = null} disabled={deleting}>{AUTH.cancelBtn}</button>
        <button type="submit" class="btn tone-danger" style="color: var(--surface); background: var(--danger)" disabled={deleting}>{AUTH.deleteBtn}</button>
      </div>
    </form>
  </div>
</div>
{/if}

<style>
  .card {
    padding: var(--space-6);
    background: var(--surface);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-lg);
    color: var(--text);
  }
  h2 { margin: 0 0 var(--space-4); font-size: var(--text-lg); }
  h3 { margin: 0 0 var(--space-3); font-size: var(--text-md); }
  .split-layout { display: flex; gap: var(--space-6); flex-wrap: wrap; }
  .accounts-list-container { flex: 2; min-width: 300px; display: flex; flex-direction: column; gap: var(--space-4); }
  .change-password-box { flex: 1; min-width: 250px; background: var(--surface-2); padding: var(--space-4); border-radius: var(--radius-md); }
  .accounts-table { width: 100%; border-collapse: collapse; font-size: var(--text-sm); }
  .accounts-table th, .accounts-table td { padding: var(--space-2); text-align: left; border-bottom: 1px solid var(--border); }
  .accounts-table th { font-weight: 600; color: var(--text-muted); }
  .add-account-box { background: var(--surface-2); padding: var(--space-4); border-radius: var(--radius-md); }
  .inline-form { display: flex; gap: var(--space-2); flex-wrap: wrap; }
  .vertical-form { display: flex; flex-direction: column; gap: var(--space-3); }
  input { padding: var(--space-2) var(--space-3); border: 1px solid var(--border-strong); border-radius: var(--radius-sm); background: var(--surface); color: var(--text); }
  .btn-small { padding: 2px 8px; font-size: var(--text-xs); margin-right: 4px; }
  .tone-danger { color: var(--danger); border-color: var(--danger-line); }
  .tone-danger:hover { background: var(--danger-line); }
  .error-box { background: var(--danger-line); color: var(--danger); padding: var(--space-2); border-radius: var(--radius-sm); font-size: var(--text-sm); margin-bottom: var(--space-2); }
  .success-box { background: var(--ok-line); color: var(--ok); padding: var(--space-2); border-radius: var(--radius-sm); font-size: var(--text-sm); margin-bottom: var(--space-2); }
  .modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 1000; }
  .modal-card { background: var(--surface); padding: var(--space-6); border-radius: var(--radius-lg); width: min(400px, 90%); }
  .modal-actions { display: flex; justify-content: flex-end; gap: var(--space-2); margin-top: var(--space-4); }
</style>
