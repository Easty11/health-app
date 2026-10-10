// Age wording shared by the home load card. A number never shows without how old it is, so the
// formatter has to say something for every input, including "never" and "unknown".

export function formatAge(hours) {
  if (hours === null || hours === undefined || Number.isNaN(hours)) return 'unknown'
  if (hours < 1) return `${Math.max(Math.round(hours * 60), 0)} min ago`
  if (hours < 48) return `${Math.round(hours)} h ago`
  return `${Math.round(hours / 24)} d ago`
}

// A pipe that has never delivered is "never", not "unknown": the first is a fact, the second is a
// failure to ask.
export function formatPipeAge(pipe) {
  if (!pipe) return 'unknown'
  if (pipe.status === 'never') return 'never'
  return formatAge(pipe.age_hours)
}
