// Rendering an API error's `detail` for a user-facing banner.
//
// WHY THIS EXISTS. Both lab-ingest catch blocks used to read
// `typeof detail === 'string' ? detail : detail?.error` and fall back to a constant
// string. FastAPI's request-validation rejection is neither of those shapes: a 422
// raised by Pydantic BEFORE the handler runs carries `detail` as an ARRAY of
// `{loc, msg, type}`. `typeof [] === 'object'`, and an array has no `.error`, so the
// whole structured rejection collapsed to "Failed to save report" — the one string
// that names nothing. A genuine document could not be saved and the banner could not
// say why, so every extraction failure of every shape presented identically and the
// user could not self-serve.
//
// The three detail shapes are NOT interchangeable and the array one is the only one
// the caller cannot otherwise obtain: a handler-raised string detail is already
// readable, but a validation rejection never reaches the handler at all, so the
// response body is the sole account of which field was refused.

// FastAPI prefixes `loc` with the request part — "body", "query", "path". "body" is
// noise on an endpoint that takes one; the others are load-bearing and stay.
function formatLoc(loc) {
  if (!Array.isArray(loc)) return ''
  const parts = loc[0] === 'body' ? loc.slice(1) : loc
  return parts.join('.')
}

function formatValidationEntry(entry) {
  if (!entry || typeof entry !== 'object') return null
  const path = formatLoc(entry.loc)
  const msg = typeof entry.msg === 'string' ? entry.msg : entry.type
  if (!path && !msg) return null
  if (!path) return msg
  if (!msg) return path
  return `${path}: ${msg}`
}

// A rejection over many rows can carry dozens of entries; a banner listing all of them
// is unreadable. The first few name the shape of the fault and the count carries the
// rest — truncating the LIST while stating the TOTAL, never truncating silently.
const MAX_ENTRIES = 5

/**
 * Turn an axios error into a banner string.
 *
 * Handles, in order: an array `detail` (FastAPI request validation), a string `detail`
 * (a handler's own `HTTPException`), an object `detail` with `.error`, and finally the
 * caller's fallback when `detail` is genuinely absent — which is the transport case
 * (network failure, 502, no response body) and the only one the fallback should ever
 * describe.
 */
export function formatApiError(err, fallback) {
  const detail = err?.response?.data?.detail

  if (Array.isArray(detail)) {
    const lines = detail.map(formatValidationEntry).filter(Boolean)
    if (lines.length === 0) return fallback
    const shown = lines.slice(0, MAX_ENTRIES).join('; ')
    return lines.length > MAX_ENTRIES
      ? `${shown} (+${lines.length - MAX_ENTRIES} more)`
      : shown
  }

  if (typeof detail === 'string') return detail || fallback
  if (detail && typeof detail === 'object' && typeof detail.error === 'string') {
    return detail.error || fallback
  }

  return fallback
}
