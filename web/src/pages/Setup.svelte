<script lang="ts">
  import { session } from '../lib/stores/session.svelte'
  import { AUTH } from '../lib/messages'
  import { MIN_PASSWORD_LENGTH } from '../lib/settings'
  import { getSetupUrl } from '../lib/url'
  import { extractApiError } from '../lib/api/error'
  import { ApiError } from '../lib/api/client'
  import PasswordInput from '../components/PasswordInput.svelte'

  let username = $state('')
  let password = $state('')
  let confirmPassword = $state('')
  let loading = $state(false)
  let errorMsg = $state('')

  function focus(node: HTMLElement) {
    node.focus()
  }

  async function handleSetup(e: Event) {
    e.preventDefault()
    errorMsg = ''
    
    if (password.length < MIN_PASSWORD_LENGTH) {
      errorMsg = AUTH.errorPasswordLength
      return
    }
    if (password !== confirmPassword) {
      errorMsg = AUTH.errorPasswordMismatch
      return
    }

    loading = true
    try {
      await session.setup({ username, password })
    } catch (e) {
      if (e instanceof ApiError && e.body && typeof e.body === 'object' && 'detail' in e.body) {
        errorMsg = extractApiError(e)
      } else {
        errorMsg = e instanceof Error ? e.message : String(e)
      }
    } finally {
      loading = false
    }
  }
</script>

<div class="login-container">
  <div class="login-card">
    <h2>{AUTH.setupTitle}</h2>
    
    {#if !session.setupAllowed}
      <div class="info-box" role="alert">
        {AUTH.setupUrlInfo.replace('{url}', getSetupUrl(window.location.port))}
      </div>
    {:else}
      {#if errorMsg}
        <div class="error-box" role="alert">
          {errorMsg}
        </div>
      {/if}
      
      <form onsubmit={handleSetup} class="form-content">
        <div class="input-group">
          <label for="username">{AUTH.username}</label>
          <input type="text" id="username" bind:value={username} disabled={loading} use:focus />
        </div>

        <div class="input-group">
          <label for="password">{AUTH.passwordMin}</label>
          <PasswordInput id="password" bind:value={password} autocomplete="new-password" disabled={loading} />
        </div>

        <div class="input-group">
          <label for="confirm">{AUTH.repeatPassword}</label>
          <PasswordInput id="confirm" bind:value={confirmPassword} autocomplete="new-password" disabled={loading} />
        </div>
        
        <button type="submit" class="btn btn-primary" disabled={!username || !password || !confirmPassword || loading}>
          {AUTH.setupBtn}
        </button>
      </form>
    {/if}
  </div>
</div>

<style>
  .login-container {
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: calc(100vh - var(--topbar-h));
    padding: var(--space-4);
  }
  .login-card {
    background: var(--surface);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-lg);
    padding: var(--space-8);
    width: 100%;
    max-width: 400px;
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
  }
  .form-content {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
  }
  h2 {
    margin: 0;
    text-align: center;
    font-size: var(--text-xl);
  }
  .error-box {
    background: var(--danger-line);
    color: var(--danger);
    padding: var(--space-3);
    border-radius: var(--radius-sm);
    font-size: var(--text-sm);
    text-align: center;
  }
  .info-box {
    background: var(--surface-2);
    color: var(--text);
    padding: var(--space-4);
    border-radius: var(--radius-sm);
    font-size: var(--text-sm);
    text-align: center;
    border: 1px solid var(--border);
  }
  .input-group {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  input {
    padding: var(--space-2) var(--space-3);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-sm);
    background: var(--surface-2);
    color: var(--text);
  }
  button {
    margin-top: var(--space-2);
    width: 100%;
    padding: var(--space-3);
  }
</style>
