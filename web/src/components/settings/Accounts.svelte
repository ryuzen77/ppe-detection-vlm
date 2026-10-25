<script lang="ts">
  import ModalOverlay from '../ModalOverlay.svelte'
  import { onMount } from 'svelte'
  import { api } from '../../lib/api/client'
  import type { AccountInfo } from '../../lib/api/types'
  import { session } from '../../lib/stores/session.svelte'
  import { AUTH } from '../../lib/messages'
  import { MIN_PASSWORD_LENGTH } from '../../lib/settings'
  import { formatServerDate } from '../../lib/formatters'
  import { extractApiError } from '../../lib/api/error'
  import PasswordInput from '../PasswordInput.svelte'

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
      setTimeout(() => {
        resetUser = null
        resetSuccess = ''
      }, 2000)
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

<!-- T78: daftar akun selebar kartu, form berlabel; ganti sandi sendiri di kartu terpisah -->
<section class="card">
  <h3>{AUTH.listAccounts}</h3>
  {#if errorMsg}
    <div class="error-box" role="alert">{errorMsg}</div>
  {/if}
  {#if loading}
    <p>{AUTH.loadingAccounts}</p>
  {:else}
    <div class="table-wrap">
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
                  <button class="btn btn-small tone-danger" onclick={() => confirmDelete(acc.username)}
                    >{AUTH.deleteBtn}</button
                  >
                {/if}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}

  <h3 class="sub-title">{AUTH.addAccount}</h3>
  {#if addError}
    <div class="error-box" role="alert">{addError}</div>
  {/if}
  <form class="grid-form" onsubmit={handleAddAccount}>
    <div class="field">
      <label for="acc-new-user">{AUTH.username}</label>
      <input
        id="acc-new-user"
        class="input"
        type="text"
        autocomplete="off"
        bind:value={newUsername}
        disabled={adding}
        required
      />
    </div>
    <div class="field">
      <label for="acc-new-pass">{AUTH.passwordMin}</label>
      <PasswordInput
        id="acc-new-pass"
        autocomplete="new-password"
        bind:value={newPassword}
        disabled={adding}
        required
      />
    </div>
    <button type="submit" class="btn btn-primary" disabled={adding || !newUsername || !newPassword}
      >{AUTH.addBtn}</button
    >
  </form>
</section>

<section class="card">
  <h3>{AUTH.changeOwnPassword}</h3>
  {#if changePasswordError}
    <div class="error-box" role="alert">{changePasswordError}</div>
  {/if}
  {#if changePasswordSuccess}
    <div class="success-box" role="alert">{changePasswordSuccess}</div>
  {/if}
  <form class="grid-form" onsubmit={handleChangePassword}>
    <div class="field">
      <label for="acc-cur-pass">{AUTH.currentPassword}</label>
      <PasswordInput
        id="acc-cur-pass"
        autocomplete="current-password"
        bind:value={currentPassword}
        disabled={changingPassword}
        required
      />
    </div>
    <div class="field">
      <label for="acc-new-pass2">{AUTH.newPassword}</label>
      <PasswordInput
        id="acc-new-pass2"
        autocomplete="new-password"
        bind:value={changePasswordNew}
        disabled={changingPassword}
        required
      />
    </div>
    <div class="field">
      <label for="acc-rep-pass">{AUTH.repeatNewPassword}</label>
      <PasswordInput
        id="acc-rep-pass"
        autocomplete="new-password"
        bind:value={changePasswordConfirm}
        disabled={changingPassword}
        required
      />
    </div>
    <button type="submit" class="btn btn-primary" disabled={changingPassword || !currentPassword || !changePasswordNew}
      >{AUTH.saveNewPassword}</button
    >
  </form>
</section>

{#if resetUser}
  <ModalOverlay labelledby="reset-title" size="sm">
    <h3 id="reset-title">{AUTH.resetConfirmTitle} - {resetUser}</h3>
    {#if resetError}<div class="error-box">{resetError}</div>{/if}
    {#if resetSuccess}<div class="success-box">{resetSuccess}</div>{/if}
    {#if !resetSuccess}
      <form class="vertical-form" onsubmit={executeReset}>
        <PasswordInput
          placeholder={AUTH.newPassword}
          autocomplete="new-password"
          bind:value={resetPasswordNew}
          disabled={resetting}
          required
        />
        <div class="modal-actions">
          <button type="button" class="btn" onclick={() => (resetUser = null)} disabled={resetting}
            >{AUTH.cancelBtn}</button
          >
          <button type="submit" class="btn btn-primary" disabled={resetting || !resetPasswordNew}
            >{AUTH.resetPassword}</button
          >
        </div>
      </form>
    {/if}
  </ModalOverlay>
{/if}

{#if deleteUser}
  <ModalOverlay labelledby="delete-title" size="sm">
    <h3 id="delete-title">{AUTH.deleteConfirmTitle}</h3>
    <p>{AUTH.deleteConfirmPrompt.replace('{user}', deleteUser)}</p>
    {#if deleteError}<div class="error-box">{deleteError}</div>{/if}
    <form class="vertical-form" onsubmit={executeDelete}>
      <div class="modal-actions">
        <button type="button" class="btn" onclick={() => (deleteUser = null)} disabled={deleting}
          >{AUTH.cancelBtn}</button
        >
        <button
          type="submit"
          class="btn tone-danger"
          style="color: var(--surface); background: var(--danger)"
          disabled={deleting}>{AUTH.deleteBtn}</button
        >
      </div>
    </form>
  </ModalOverlay>
{/if}

<style>
  .card {
    padding: var(--space-6);
    background: var(--surface);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-lg);
    color: var(--text);
  }
  h3 {
    margin: 0 0 var(--space-3);
    font-size: var(--text-lg);
  }
  .sub-title {
    margin-top: var(--space-6);
    font-size: var(--text-md);
  }
  .table-wrap {
    overflow-x: auto;
  }
  .accounts-table {
    width: 100%;
    border-collapse: collapse;
    font-size: var(--text-sm);
  }
  .accounts-table th,
  .accounts-table td {
    padding: var(--space-2) var(--space-3);
    text-align: left;
    border-bottom: 1px solid var(--border);
    white-space: nowrap;
  }
  .accounts-table th {
    font-weight: 600;
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .grid-form {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: var(--space-3);
    align-items: end;
  }
  .grid-form .btn {
    justify-self: start;
  }
  .vertical-form {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }
  .btn-small {
    padding: 2px 8px;
    font-size: var(--text-xs);
    margin-right: 4px;
  }
  .tone-danger {
    color: var(--danger);
    border-color: var(--danger-line);
  }
  .tone-danger:hover {
    background: var(--danger-line);
  }
  .error-box {
    background: var(--danger-line);
    color: var(--danger);
    padding: var(--space-2);
    border-radius: var(--radius-sm);
    font-size: var(--text-sm);
    margin-bottom: var(--space-2);
  }
  .success-box {
    background: var(--ok-line);
    color: var(--ok);
    padding: var(--space-2);
    border-radius: var(--radius-sm);
    font-size: var(--text-sm);
    margin-bottom: var(--space-2);
  }
</style>
