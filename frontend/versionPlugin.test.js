// The build emits `version.json` with the commit it was built from (#433, scripts/check_deploy_sha.py).
// A missing variable becomes `commit: null`, which the post-deploy check reports as a failure, never a pass.

/* global process -- build-time / Node-side file: the browser-only lint globals do not list it */
import { describe, expect, test } from 'vitest'
import emitVersion, { versionJson } from './versionPlugin.js'

const SHA = '0123456789abcdef0123456789abcdef01234567'

describe('versionJson', () => {
  test('carries the service and the commit, nothing else', () => {
    expect(JSON.parse(versionJson(SHA))).toEqual({ service: 'health-app-frontend', commit: SHA })
  })
  test('an absent or empty commit is null, not an empty string', () => {
    expect(JSON.parse(versionJson(undefined)).commit).toBeNull()
    expect(JSON.parse(versionJson('')).commit).toBeNull()
  })
})

describe('emitVersion plugin', () => {
  test('emits version.json as an asset at the build root', () => {
    const emitted = []
    const plugin = emitVersion(SHA)
    plugin.generateBundle.call({ emitFile: (f) => emitted.push(f) })
    expect(emitted).toHaveLength(1)
    expect(emitted[0].type).toBe('asset')
    expect(emitted[0].fileName).toBe('version.json')
    expect(JSON.parse(emitted[0].source).commit).toBe(SHA)
  })
  test('reads RAILWAY_GIT_COMMIT_SHA when no commit is passed', () => {
    const prev = process.env.RAILWAY_GIT_COMMIT_SHA
    process.env.RAILWAY_GIT_COMMIT_SHA = SHA
    try {
      const emitted = []
      emitVersion().generateBundle.call({ emitFile: (f) => emitted.push(f) })
      expect(JSON.parse(emitted[0].source).commit).toBe(SHA)
    } finally {
      if (prev === undefined) delete process.env.RAILWAY_GIT_COMMIT_SHA
      else process.env.RAILWAY_GIT_COMMIT_SHA = prev
    }
  })
})
