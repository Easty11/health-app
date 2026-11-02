// Emits `version.json` into the build: the commit this bundle was built from (Railway's
// RAILWAY_GIT_COMMIT_SHA), for the post-deploy check (#433, scripts/check_deploy_sha.py).
//
// `commit` is null when the variable is absent at build time, which the check reports as a failure
// instead of a pass. Only the SHA is emitted. Not precached by the service worker (its globPatterns
// do not match .json), so a stale shell never answers for a fresh deploy.

/* global process -- build-time / Node-side file: the browser-only lint globals do not list it */

export function versionJson(commit) {
  return JSON.stringify({ service: 'health-app-frontend', commit: commit || null }) + '\n'
}

export default function emitVersion(commit = process.env.RAILWAY_GIT_COMMIT_SHA) {
  return {
    name: 'emit-version-json',
    generateBundle() {
      this.emitFile({ type: 'asset', fileName: 'version.json', source: versionJson(commit) })
    },
  }
}
