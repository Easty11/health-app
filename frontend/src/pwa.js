import { registerSW } from 'virtual:pwa-register'

// A new deploy ships new hashed bundles and the old ones leave the server, so a
// tab left open on the old shell must not linger. The worker skips waiting and
// claims clients (vite.config.js); autoUpdate reloads the page once the new
// worker takes control. This only adds the update *checks*: an installed
// standalone window can stay open for days without a navigation, which is the
// only thing that makes the browser look for a new worker on its own.
const CHECK_EVERY_MS = 60 * 60 * 1000

export function registerPwa() {
  if (!import.meta.env.PROD) return
  registerSW({
    immediate: true,
    onRegisteredSW(_url, registration) {
      if (!registration) return
      const check = () => registration.update().catch(() => {})
      setInterval(check, CHECK_EVERY_MS)
      document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') check()
      })
    },
  })
}
