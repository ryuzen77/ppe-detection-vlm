<script lang="ts">
  import { LOGIN } from '../lib/messages'
  import { session } from '../lib/stores/session.svelte'
  import { ApiError } from '../lib/api/client'
  import { tickCountdown } from '../lib/sessionLogic'
  
  let username = $state('')
  let password = $state('')
  let loading = $state(false)
  let errorMsg = $state('')
  let waitSecs = $state<number | null>(null)

  let timer: ReturnType<typeof setInterval> | null = null
  $effect(() => {
    if (waitSecs !== null && waitSecs > 0) {
      if (!timer) {
        timer = setInterval(() => {
          waitSecs = tickCountdown(waitSecs, 1)
          if (waitSecs === null) {
            clearInterval(timer!)
            timer = null
          }
        }, 1000)
      }
    } else {
      if (timer) {
        clearInterval(timer)
        timer = null
      }
    }
  })

  function focus(node: HTMLElement) {
    node.focus()
  }

  async function handleLogin(e: Event) {
    e.preventDefault()
    if (!username || !password || waitSecs !== null) return
    loading = true
    errorMsg = ''
    try {
      await session.login({ username, password })
    } catch (e) {
      if (e instanceof ApiError) {
        if (e.status === 429 && typeof e.body === 'object' && e.body !== null && 'retry_after_s' in e.body) {
          waitSecs = Number((e.body as any).retry_after_s)
          errorMsg = LOGIN.waitInfo.replace('{s}', String(waitSecs))
        } else if (e.body && typeof e.body === 'object' && 'detail' in e.body) {
          errorMsg = (e.body as any).detail.message || String((e.body as any).detail)
        } else {
          errorMsg = e.message
        }
      } else {
        errorMsg = String(e)
      }
    } finally {
      loading = false
    }
  }
</script>

<div class="login-container">
  <form class="login-card" onsubmit={handleLogin}>
    <h2>{LOGIN.title}</h2>
    
    {#if errorMsg}
      <div class="error-box" role="alert">
        {#if waitSecs !== null}
          {LOGIN.waitInfo.replace('{s}', String(waitSecs))}
        {:else}
          {errorMsg}
        {/if}
      </div>
    {/if}
    
    <div class="input-group">
      <label for="username">Nama Pengguna</label>
      <input type="text" id="username" bind:value={username} disabled={loading || waitSecs !== null} use:focus />
    </div>

    <div class="input-group">
      <label for="password">{LOGIN.password}</label>
      <input type="password" id="password" bind:value={password} disabled={loading || waitSecs !== null} />
    </div>
    
    <button type="submit" class="btn btn-primary" disabled={!username || !password || loading || waitSecs !== null}>
      {LOGIN.loginBtn}
    </button>
  </form>
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
