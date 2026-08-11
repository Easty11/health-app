"""Rephrase generator (increment 2 step 2, #202) — faked at the transport layer.

Per the #166 companion rule, code interpreting a third party's response is tested against a
FAKED transport, never the live model. The fake `client` mimics the one attribute the
generator touches: `client.messages.create(...).content[0].text`.
"""
from interpretation.presentation import FRAGMENT, Fragment, render_base_text
from interpretation.rephrase import generate_plain, rephrase_fragment

KNOWN = {"testosterone", "cortisol", "ferritin"}

_FRAGS = [
    Fragment("m.movement", "Testosterone (total): 23.9 nmol/L; in range.", FRAGMENT,
             censored=False, flagged=False, kind="movement"),
]


class _Resp:
    def __init__(self, text):
        self.content = [type("Block", (), {"text": text})()]


class _FakeClient:
    """A fake Anthropic client. `fn(user_text) -> candidate`, or raises to simulate an error."""
    def __init__(self, fn):
        self.messages = self
        self._fn = fn

    def create(self, *, model, max_tokens, system, messages):
        return _Resp(self._fn(messages[0]["content"]))


def test_validated_rephrase_is_used():
    client = _FakeClient(lambda src: "Your total testosterone is 23.9 nmol/L, "
                                     "which is within the normal range.")
    text, was = rephrase_fragment(_FRAGS[0], client=client, known_entities=KNOWN)
    assert was is True
    assert "23.9 nmol/L" in text and "normal range" in text


def test_claim_changing_candidate_falls_back_to_template():
    # Adds a numeral AND flips status -> validator rejects -> template text.
    client = _FakeClient(lambda src: "Your testosterone jumped 38% and is now out of range.")
    text, was = rephrase_fragment(_FRAGS[0], client=client, known_entities=KNOWN)
    assert was is False
    assert text == _FRAGS[0].text


def test_transport_error_falls_back_to_template():
    def boom(src):
        raise RuntimeError("network")
    text, was = rephrase_fragment(_FRAGS[0], client=_FakeClient(boom), known_entities=KNOWN)
    assert was is False
    assert text == _FRAGS[0].text


def test_missing_client_returns_the_base_text():
    """The missing-key fail-closed path (#202 clause 4): with client=None every unit falls
    back, so the assembled plain text is byte-identical to the template render."""
    gen = generate_plain(_FRAGS, client=None, known_entities=KNOWN)
    assert gen["any_rephrased"] is False
    assert gen["text"] == render_base_text(_FRAGS)


def test_generate_plain_assembles_validated_and_fallback_units():
    frags = [
        Fragment("a.movement", "Testosterone (total): 23.9 nmol/L; in range.", FRAGMENT,
                 kind="movement"),
        Fragment("b.movement", "Cortisol: 300 nmol/L; in range.", FRAGMENT, kind="movement"),
    ]

    def fn(src):
        if "Testosterone" in src:
            return "Your total testosterone is 23.9 nmol/L and within the normal range."
        return "Cortisol shot up 999% — see your doctor immediately."  # rejected

    gen = generate_plain(frags, client=_FakeClient(fn), known_entities=KNOWN)
    assert gen["any_rephrased"] is True
    assert "within the normal range" in gen["text"]      # unit a: validated rephrase
    assert "Cortisol: 300 nmol/L; in range." in gen["text"]  # unit b: fell back to template
    assert gen["per_fragment"] == [
        {"addr": "a.movement", "rephrased": True},
        {"addr": "b.movement", "rephrased": False},
    ]
