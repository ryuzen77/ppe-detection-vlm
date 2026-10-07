<script lang="ts">
  import { onMount } from 'svelte'
  import { api, ApiError } from '../../lib/api/client'
  import type { AccountInfo } from '../../lib/api/types'
  import { session } from '../../lib/stores/session.svelte'
  
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

  onMount(() => {
    loadAccounts()
  })

  async function loadAccounts() {
    loading = true
    errorMsg = ''
    try {
      accounts = await api.accounts()
    } catch (e) {
      errorMsg = e instanceof Error ? e.message : String(e)
    } finally {
      loading = false
    }
  }

  async function handleAddAccount(e: Event) {
    e.preventDefault()
    addError = ''
    if (newPassword.length < 12) {
      addError = 'Kata sandi minimal 12 karakter'
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

  async function handleDeleteAccount(username: string) {
    if (!confirm(`Hapus akun ${username}?`)) return
    try {
      await api.deleteAccount(username)
      await loadAccounts()
    } catch (e) {
      errorMsg = extractApiError(e)
    }
  }

  async function handleResetPassword(username: string) {
    const newPass = prompt(`Masukkan kata sandi baru untuk ${username} (min 12 karakter):`)
    if (!newPass) return
    if (newPass.length < 12) {
      alert('Kata sandi minimal 12 karakter')
      return
    }
    try {
      await api.resetAccountPassword(username, { new_password: newPass })
      alert(`Sandi untuk ${username} berhasil direset.`)
    } catch (e) {
      alert(`Gagal mereset sandi: ${extractApiError(e)}`)
    }
  }

  async function handleChangePassword(e: Event) {
    e.preventDefault()
    changePasswordError = ''
    changePasswordSuccess = ''
    if (changePasswordNew.length < 12) {
      changePasswordError = 'Kata sandi baru minimal 12 karakter'
      return
    }
    if (changePasswordNew !== changePasswordConfirm) {
      changePasswordError = 'Konfirmasi kata sandi tidak cocok'
      return
    }
    changingPassword = true
    try {
      await api.changePassword({ current_password: currentPassword, new_password: changePasswordNew })
      currentPassword = ''
      changePasswordNew = ''
      changePasswordConfirm = ''
      changePasswordSuccess = 'Kata sandi berhasil diubah.'
    } catch (e) {
      changePasswordError = extractApiError(e)
    } finally {
      changingPassword = false
    }
  }

  function extractApiError(e: unknown): string {
    if (e instanceof ApiError && e.body && typeof e.body === 'object' && 'detail' in e.body) {
      return (e.body as any).detail.message || String((e.body as any).detail)
    }
    return e instanceof Error ? e.message : String(e)
  }
</script>

<section class="card">
  <h2>Akun Pengguna</h2>

  <div class="split-layout">
    <div class="accounts-list-container">
      <h3>Daftar Akun</h3>
      {#if errorMsg}
        <div class="error-box" role="alert">{errorMsg}</div>
      {/if}
      {#if loading}
        <p>Memuat akun...</p>
      {:else}
        <table class="accounts-table">
          <thead>
            <tr>
              <th>Nama Pengguna</th>
              <th>Peran</th>
              <th>Login Terakhir</th>
              <th>Aksi</th>
            </tr>
          </thead>
          <tbody>
            {#each accounts as acc (acc.username)}
              <tr>
                <td>{acc.username} {acc.username === session.user?.username ? '(Anda)' : ''}</td>
                <td>{acc.role}</td>
                <td>{acc.last_login_at ? new Date(acc.last_login_at + 'Z').toLocaleString('id-ID') : '-'}</td>
                <td>
                  {#if acc.username !== session.user?.username}
                    <button class="btn btn-small" onclick={() => handleResetPassword(acc.username)}>Reset Sandi</button>
                    <button class="btn btn-small tone-danger" onclick={() => handleDeleteAccount(acc.username)}>Hapus</button>
                  {/if}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      {/if}

      <div class="add-account-box">
        <h3>Tambah Akun</h3>
        {#if addError}
          <div class="error-box" role="alert">{addError}</div>
        {/if}
        <form class="inline-form" onsubmit={handleAddAccount}>
          <input type="text" placeholder="Nama pengguna" bind:value={newUsername} disabled={adding} required />
          <input type="password" placeholder="Sandi (min. 12)" bind:value={newPassword} disabled={adding} required />
          <button type="submit" class="btn btn-primary" disabled={adding || !newUsername || !newPassword}>Tambah</button>
        </form>
      </div>
    </div>

    <div class="change-password-box">
      <h3>Ganti Sandi Sendiri</h3>
      {#if changePasswordError}
        <div class="error-box" role="alert">{changePasswordError}</div>
      {/if}
      {#if changePasswordSuccess}
        <div class="success-box" role="alert">{changePasswordSuccess}</div>
      {/if}
      <form class="vertical-form" onsubmit={handleChangePassword}>
        <input type="password" placeholder="Sandi saat ini" bind:value={currentPassword} disabled={changingPassword} required />
        <input type="password" placeholder="Sandi baru (min. 12)" bind:value={changePasswordNew} disabled={changingPassword} required />
        <input type="password" placeholder="Ulangi sandi baru" bind:value={changePasswordConfirm} disabled={changingPassword} required />
        <button type="submit" class="btn btn-primary" disabled={changingPassword || !currentPassword || !changePasswordNew}>Simpan Sandi Baru</button>
      </form>
    </div>
  </div>
</section>

<style>
  .card {
    padding: var(--space-6);
    background: var(--surface);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-lg);
    color: var(--text);
  }
  h2 {
    margin: 0 0 var(--space-4);
    font-size: var(--text-lg);
  }
  h3 {
    margin: 0 0 var(--space-3);
    font-size: var(--text-md);
  }
  .split-layout {
    display: flex;
    gap: var(--space-6);
    flex-wrap: wrap;
  }
  .accounts-list-container {
    flex: 2;
    min-width: 300px;
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }
  .change-password-box {
    flex: 1;
    min-width: 250px;
    background: var(--surface-2);
    padding: var(--space-4);
    border-radius: var(--radius-md);
  }
  .accounts-table {
    width: 100%;
    border-collapse: collapse;
    font-size: var(--text-sm);
  }
  .accounts-table th, .accounts-table td {
    padding: var(--space-2);
    text-align: left;
    border-bottom: 1px solid var(--border);
  }
  .accounts-table th {
    font-weight: 600;
    color: var(--text-muted);
  }
  .add-account-box {
    background: var(--surface-2);
    padding: var(--space-4);
    border-radius: var(--radius-md);
  }
  .inline-form {
    display: flex;
    gap: var(--space-2);
    flex-wrap: wrap;
  }
  .vertical-form {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }
  input {
    padding: var(--space-2) var(--space-3);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-sm);
    background: var(--surface);
    color: var(--text);
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
