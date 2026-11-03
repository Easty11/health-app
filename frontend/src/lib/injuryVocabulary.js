// The injury row's closed shape, MIRRORED from the backend (DECISIONS_LOG "The injury row has a
// closed shape"). The backend is the one definition: `engine/engine_defaults.py` (`INJURY_BODY_PARTS`)
// and `routers/knowledge.py` (`INJURY_SIDES`, `INJURY_SIGNAL_TYPES`, `INJURY_COURSES`,
// `INJURY_DIAGNOSIS_STATUSES`). A backend test (`tests/test_injury_shape.py`) parses THIS file and
// fails when a list here drifts from the validator's tuple, so edit the Python first and copy.
// No route serves the vocabulary (the brief adds none); the card's selects read these.

export const INJURY_BODY_PARTS = [
  'hamstring', 'shoulder', 'calf', 'ankle', 'knee',
  'finger', 'thumb', 'neck', 'lumbar', 'pelvis', 'hip', 'foot',
  'hand', 'wrist', 'elbow', 'groin', 'achilles', 'toe', 'rib',
]

export const INJURY_SIDES = ['left', 'right', 'bilateral']

export const INJURY_SIGNAL_TYPES = ['mechanical', 'neural', 'radicular']

export const INJURY_COURSES = ['acute', 'gradual', 'chronic', 'niggle']

export const INJURY_DIAGNOSIS_STATUSES = ['suspected', 'imaged', 'clinician_confirmed']
