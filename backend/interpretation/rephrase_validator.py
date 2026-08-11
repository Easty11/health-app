"""Mechanical rephrase validator — the structural gate of #202 clause 3.

Every generated rephrase passes through `validate_rephrase()` before it may render.
A rejection means the caller renders the deterministic template instead (#202 clause 4:
fail-closed). The validator is the enforcement; the prompt is not (#202 forecloses
prompt-only control — behavioural rules are model-version-variant, structural ones are not).

The contract is checkable BY CONSTRUCTION: the source is the serialiser's own fragment
text (`presentation.py`), so a fragment's allowed numerals and entities are exactly what
its source string contains. Every check below is a subset/containment test against that
source, or a lexicon scan for constructions the education register (#47) may never carry.

Checks (all must pass):
  a. numerals    — every numeral in the candidate is present in the source
  b. dates/units — ISO dates and unit tokens in the candidate ⊆ the source's
  c. entities    — known domain (marker/lever) names in the candidate ⊆ the source's
  d. status      — range/normality status terms in the candidate ⊆ the source's
                   (a dropped negation that flips "in range" to "out of range" is caught here)
  e. directive   — no imperative-mood / advice construction (#47: no personalised action)
  f. priority    — no urgency / ranking / significance-inflation term absent from the source
  g. reassurance — no reassurance construction, and no minimising adverb on a flagged marker
  h. censored    — a censored fragment (#205) may not acquire magnitude or a direction the
                   source did not carry

The validator is deliberately CONSERVATIVE: a false reject only means the safe template
renders, which #202 says is always acceptable. A false accept would leak, so every check
errs toward rejecting.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_NUMERAL = re.compile(r"-?\d+(?:\.\d+)?")
_ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
# Unit-like tokens: "nmol/L", "ng/mL", "IU/L", plus a few standalone forms.
_UNIT = re.compile(r"\b[A-Za-zµμ]+/[A-Za-zµμ]+\b|\b(?:fL|U/L|%)\b", re.IGNORECASE)
_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")
_SENTENCE_SPLIT = re.compile(r"(?<=[.;:!?])\s+")

# --- lexicons ------------------------------------------------------------- #

# Imperative verbs that, at a sentence start, make the sentence an instruction (#47).
_IMPERATIVE_VERBS = {
    "take", "start", "stop", "consult", "see", "avoid", "increase", "decrease", "reduce",
    "raise", "lower", "add", "begin", "discontinue", "adjust", "consider", "monitor",
    "check", "ask", "talk", "contact", "discuss", "speak", "try", "use", "get", "book",
    "schedule", "supplement", "eat", "drink", "exercise", "rest",
}
_DIRECTIVE_PATTERNS = [
    re.compile(r"\byou\s+(should|must|need to|ought to|had better|may want to|might want to)\b", re.I),
    re.compile(r"\b(consult|see|contact|talk to|speak to|ask|call)\s+(your\s+|a\s+)?"
               r"(doctor|physician|gp|clinician|provider|specialist|nurse)\b", re.I),
    re.compile(r"\b(we|i)\s+(recommend|advise|suggest|urge)\b", re.I),
    re.compile(r"\bit(?:'s| is)\s+(recommended|advised|advisable)\b", re.I),
]

# Urgency / ranking / significance-inflation — priority vocabulary (#202 clause 3, #47).
_PRIORITY_TERMS = {
    "urgent", "urgently", "immediately", "immediate", "critical", "critically", "dangerous",
    "danger", "severe", "severely", "emergency", "alarming", "worrying", "worrisome",
    "priority", "prioritise", "prioritize", "worst", "life-threatening", "serious",
    "seriously", "crucial", "significant", "significantly", "marked", "markedly",
    "substantial", "substantially", "dramatic", "dramatically", "notable", "notably",
    "striking", "concerning", "abnormal", "abnormally", "problematic",
}

# Range / normality status, by POLARITY. A rephrase may render a same-polarity synonym
# ("in range" -> "within the normal range") but may never FLIP polarity — a dropped
# negation that turns an in-range result out-of-range, or a minimisation that calls a
# flagged result normal, is the leak this catches. Phrase-level only (no standalone
# "normal"/"high"/"low") so "below the normal range" is not misread as positive.
_STATUS_POSITIVE = {
    "in range", "in-range", "within range", "within the range",
    "within normal", "normal limits", "in the normal range", "within the normal range",
}
_STATUS_NEGATIVE = {
    "out of range", "out-of-range", "outside range", "outside the range",
    "above range", "above the range", "below range", "below the range",
    "above the reference range", "below the reference range", "outside the reference range",
    "elevated", "abnormal",
}

# Reassurance constructions — never in the clinical base; a characterisation of the result.
_REASSURANCE_PATTERNS = [
    re.compile(r"nothing\s+to\s+(worry|be concerned)\b", re.I),
    re.compile(r"\b(no|n't)\s+(need to|cause for)\s+(worry|concern)\b", re.I),
    re.compile(r"\b(don't|do not)\s+worry\b", re.I),
    re.compile(r"\b(perfectly|completely|totally|entirely)\s+(normal|fine|healthy|safe)\b", re.I),
    re.compile(r"\b(all\s+clear|all\s+good|nothing\s+wrong|looks?\s+(great|good|fine|healthy))\b", re.I),
    re.compile(r"\breassuring\b", re.I),
]
# Minimising adverbs — rejected on a FLAGGED marker (out of range / in a safety band / news).
_MINIMISERS = {"just", "only", "merely", "simply", "barely", "slightly", "mild", "mildly", "minor"}

# Change-magnitude language — never valid on a censored comparison (#205).
_MAGNITUDE_TERMS = {
    "doubled", "halved", "tripled", "quadrupled", "percent",
}
_MAGNITUDE_PATTERNS = [
    re.compile(r"\b(increased|decreased|rose|fell|dropped|climbed|jumped|grew|shrank|gained|lost)\s+by\b", re.I),
    re.compile(r"\b(up|down|higher|lower)\s+by\b", re.I),
    re.compile(r"%", re.I),
]
# Direction verbs — on a censored fragment, allowed only if the source carried them.
_DIRECTION_TERMS = {
    "up", "down", "rose", "fell", "increased", "decreased", "higher", "lower",
    "climbed", "dropped", "risen", "fallen", "grew", "declined",
}


@dataclass
class Result:
    ok: bool
    rejections: list[str] = field(default_factory=list)


def _words(text: str) -> list[str]:
    return _WORD.findall(text)


def _numerals(text: str) -> set[float]:
    out = set()
    for tok in _NUMERAL.findall(text):
        try:
            out.add(float(tok))
        except ValueError:
            pass
    return out


def _lexicon_hits(text: str, terms: set[str]) -> set[str]:
    low = text.lower()
    hits = set()
    for t in terms:
        # word-boundary match for single words; substring for multi-word phrases
        if " " in t or "-" in t:
            if t in low:
                hits.add(t)
        elif re.search(rf"\b{re.escape(t)}\b", low):
            hits.add(t)
    return hits


def validate_rephrase(source: str, candidate: str, *, censored: bool = False,
                      flagged: bool = False, known_entities: set[str] | None = None) -> Result:
    """Gate one rephrase against its source fragment. ok=True only if every check passes.

    `known_entities` is the domain vocabulary — the distinctive marker/lever name words
    the producer knows about (e.g. {"testosterone", "cortisol", "ferritin"}). Any such
    entity appearing in the candidate but not the source is an entity substitution and is
    rejected. Passing it is how the entity check stays PRECISE (a swapped marker name is
    caught; a common English word is not), rather than guessing from capitalisation.
    """
    rej: list[str] = []
    src_low = source.lower()
    cand_low = candidate.lower()

    # a. numerals ⊆ source
    src_nums = _numerals(source)
    extra_nums = sorted(n for n in _numerals(candidate) if n not in src_nums)
    if extra_nums:
        rej.append(f"numeral(s) absent from source: {extra_nums}")

    # b. dates + units ⊆ source
    src_dates = set(_ISO_DATE.findall(source))
    extra_dates = sorted(set(_ISO_DATE.findall(candidate)) - src_dates)
    if extra_dates:
        rej.append(f"date(s) absent from source: {extra_dates}")
    src_units = {u.lower() for u in _UNIT.findall(source)}
    # _UNIT groups can return tuples via alternation; normalise via finditer
    src_units = {m.group(0).lower() for m in _UNIT.finditer(source)}
    cand_units = {m.group(0).lower() for m in _UNIT.finditer(candidate)}
    extra_units = sorted(cand_units - src_units)
    if extra_units:
        rej.append(f"unit(s) absent from source: {extra_units}")

    # c. known domain entities ⊆ source (precise — a swapped marker name is caught,
    #    a common word is not). No vocabulary passed -> the check is skipped, so the
    #    caller (endpoint) must supply it in production.
    if known_entities:
        for ent in known_entities:
            el = ent.lower()
            if re.search(rf"\b{re.escape(el)}\b", cand_low) and not re.search(rf"\b{re.escape(el)}\b", src_low):
                rej.append(f"entity absent from source: {ent!r}")

    # d. status polarity may not flip
    src_pos = _lexicon_hits(source, _STATUS_POSITIVE)
    src_neg = _lexicon_hits(source, _STATUS_NEGATIVE)
    cand_pos = _lexicon_hits(candidate, _STATUS_POSITIVE)
    cand_neg = _lexicon_hits(candidate, _STATUS_NEGATIVE)
    if src_pos and not src_neg and cand_neg:
        rej.append(f"status flipped in-range -> out-of-range: {sorted(cand_neg)}")
    if src_neg and not src_pos and cand_pos:
        rej.append(f"status flipped out-of-range -> in-range: {sorted(cand_pos)}")

    # e. directive mood
    for sentence in _SENTENCE_SPLIT.split(candidate.strip()):
        first = (_words(sentence)[:1] or [""])[0].lower()
        if first in _IMPERATIVE_VERBS:
            rej.append(f"imperative-mood sentence: {sentence.strip()!r}")
            break
    for pat in _DIRECTIVE_PATTERNS:
        if pat.search(candidate):
            rej.append(f"directive construction: {pat.pattern!r}")
            break

    # f. priority / significance-inflation not in source
    extra_priority = sorted(_lexicon_hits(candidate, _PRIORITY_TERMS) - _lexicon_hits(source, _PRIORITY_TERMS))
    if extra_priority:
        rej.append(f"priority vocabulary absent from source: {extra_priority}")

    # g. reassurance construction / minimiser on a flagged marker
    for pat in _REASSURANCE_PATTERNS:
        if pat.search(candidate):
            rej.append(f"reassurance construction: {pat.pattern!r}")
            break
    if flagged:
        extra_min = sorted(_lexicon_hits(candidate, _MINIMISERS) - _lexicon_hits(source, _MINIMISERS))
        if extra_min:
            rej.append(f"minimising adverb on a flagged marker: {extra_min}")

    # h. censored preservation (#205)
    if censored:
        mag = _lexicon_hits(candidate, _MAGNITUDE_TERMS)
        for pat in _MAGNITUDE_PATTERNS:
            if pat.search(candidate):
                mag.add(pat.pattern)
        if mag:
            rej.append(f"magnitude language on a censored comparison: {sorted(mag)}")
        extra_dir = sorted(_lexicon_hits(candidate, _DIRECTION_TERMS) - _lexicon_hits(source, _DIRECTION_TERMS))
        if extra_dir:
            rej.append(f"direction absent from a censored source: {extra_dir}")

    return Result(ok=not rej, rejections=rej)
