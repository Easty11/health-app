"""Education-thread generator (increment 3 steps 2-3, #47) — faked at the transport layer.

Per the #166 companion rule, code interpreting a third party's response is tested against a
FAKED transport, never the live model. The fake `client` mimics the one attribute the
generator touches: `client.messages.create(...).content[0].text`.
"""
from interpretation.education_thread import answer_education

_SEED = {
    "lever_key": "testosterone_substrate_load",
    "marker": {"marker_canonical": "oestradiol", "display_name": "Oestradiol"},
    "mechanism": {
        "label": "Testosterone substrate load",
        "mechanism_summary": "Exogenous testosterone sets the substrate pool the axis aromatises to oestradiol.",
        "grade": "high", "grade_rationale": "Direct interventional evidence.",
        "citations": ["10.1000/x"],
    },
    "why_surfaced": {"delta": None, "news_gate": None, "range_gate": None, "safety_gate": None,
                     "lever_effect": {"lever_key": "testosterone_substrate_load",
                                      "direction": "raises", "grade": "high"}},
    "protocol_context": {"as_of": "2026-05-30", "factors": []},
}
_MSGS = [{"role": "user", "content": "How does this lever work?"}]


class _Resp:
    def __init__(self, text):
        self.content = [type("Block", (), {"text": text})()]


class _FakeClient:
    """`fn(system, messages) -> candidate`, or raises to simulate a transport error."""
    def __init__(self, fn):
        self.messages = self
        self._fn = fn

    def create(self, *, model, max_tokens, system, messages):
        return _Resp(self._fn(system, messages))


def test_no_client_serves_the_deterministic_mechanism():
    out = answer_education(_SEED, _MSGS, client=None)
    assert out["source"] == "template"
    assert out["deflected"] is False
    assert out["text"] == _SEED["mechanism"]["mechanism_summary"]


def test_transport_error_fails_closed_to_the_mechanism():
    def boom(system, messages):
        raise RuntimeError("network")
    out = answer_education(_SEED, _MSGS, client=_FakeClient(boom))
    assert out["source"] == "template"
    assert out["text"] == _SEED["mechanism"]["mechanism_summary"]


def test_faithful_mechanism_answer_passes_through():
    client = _FakeClient(lambda s, m: "Aromatase converts a fraction of the testosterone pool "
                                      "into oestradiol, so a larger pool raises oestradiol.")
    out = answer_education(_SEED, _MSGS, client=client)
    assert out["source"] == "model"
    assert out["deflected"] is False
    assert "aromatase" in out["text"].lower()


def test_directive_output_is_replaced_by_the_deflection():
    client = _FakeClient(lambda s, m: "You should lower your testosterone dose to bring oestradiol down.")
    out = answer_education(_SEED, _MSGS, client=client)
    assert out["source"] == "deflection"
    assert out["deflected"] is True
    assert "prescriber" in out["text"]
    assert "lower your testosterone dose" not in out["text"]  # the model's directive never served


def test_system_prompt_carries_only_the_seed():
    """The system prompt the client sees is the education frame + the seed — no other context."""
    captured = {}

    def fn(system, messages):
        captured["system"] = system
        return "Aromatase converts testosterone to oestradiol."
    answer_education(_SEED, _MSGS, client=_FakeClient(fn))
    assert "oestradiol" in captured["system"]
    assert "education" in captured["system"].lower()
    # the seed is the only injected context — no general personal sweep
    assert "SCOPED SEED" in captured["system"]
