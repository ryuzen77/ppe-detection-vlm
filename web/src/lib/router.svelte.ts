/**
 * Router berbasis hash: tiap bagian punya URL sendiri (#/monitoring, #/laporan,
 * #/pekerja, #/pengaturan) sehingga refresh, tombol Back, dan bookmark berfungsi.
 * Hash dipilih agar FastAPI tidak perlu aturan fallback untuk setiap path.
 */
export const ROUTES = ['monitoring', 'laporan', 'pekerja', 'pengaturan'] as const
export type Route = (typeof ROUTES)[number]

export const DEFAULT_ROUTE: Route = 'monitoring'

export function parseRoute(hash: string): Route {
  const name = hash.replace(/^#\/?/, '').split(/[/?]/)[0]
  return (ROUTES as readonly string[]).includes(name) ? (name as Route) : DEFAULT_ROUTE
}

export function href(route: Route): string {
  return `#/${route}`
}

class Router {
  current = $state<Route>(DEFAULT_ROUTE)

  start(): void {
    const sync = () => {
      this.current = parseRoute(location.hash)
    }
    sync()
    window.addEventListener('hashchange', sync)
  }
}

export const router = new Router()
