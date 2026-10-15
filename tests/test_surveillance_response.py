from contextlib import nullcontext
from types import SimpleNamespace

import numpy as np
import pytest

from sentinel.smolvlm import SmolVLM2Analyzer, PROMPT
from sentinel.vision import sample_frame


@pytest.mark.parametrize(('responses', 'decision', 'warning', 'count'), [
    (['ANGER : yes\nEVIDENCE: A house is engulfed in flames.'], 'yes', False, 1),
    (['DANGER : yes, DANGER : no.', 'DANGER: yes\nEVIDENCE: Flames cover the roof.'], 'yes', False, 2),
    (['DANGER : yes, DANGER : no.', 'DANGER : yes, DANGER : no.'], 'uncertain', True, 2),
    (['', ''], 'uncertain', True, 2),
    (['DANGER: uncertain\nEVIDENCE: The smoke source is obscured.'], 'uncertain', False, 1),
    (['DANGER: no\nEVIDENCE: No visible hazard.'], 'no', False, 1),
])
def test_bounded_repair_does_not_force_danger(monkeypatch, responses, decision, warning, count):
    monkeypatch.setitem(__import__('sys').modules, 'torch', SimpleNamespace(inference_mode=nullcontext))
    calls = []
    outputs = iter(responses)
    class Inputs(dict):
        def to(self, device): return self
    class Processor:
        def apply_chat_template(self, messages, **kwargs):
            calls.append(messages[0]['content'][1]['text'])
            return 'fixture'
        def __call__(self, **kwargs): return Inputs(input_ids=np.array([[1]]))
        def batch_decode(self, output, **kwargs): return [next(outputs)]
    model = SmolVLM2Analyzer()
    model._model = SimpleNamespace(device='cpu', generate=lambda **kwargs: np.array([[1, 2]]))
    model._processor = Processor()
    result = model.analyze((sample_frame(np.zeros((8, 8, 3), dtype=np.uint8), 0),))
    assert result.danger_status == decision
    assert bool(result.analysis_warning) == warning
    assert len(calls) == count
    assert all(PROMPT in prompt for prompt in calls)
    assert model._lock.acquire(blocking=False)
    model._lock.release()


def test_prompt_covers_property_hazards_and_avoids_identity_assumptions():
    assert 'even when no person is visible' in PROMPT
    for term in ('Fire', 'falling', 'drowning', 'climbing', 'forced entry'):
        assert term in PROMPT
    assert 'never label a person a thief' in PROMPT


def test_generation_constraint_allows_each_decision_but_not_malformed_header():
    from sentinel.smolvlm import decision_prefix_constraint
    class Tokenizer:
        def encode(self, text, **kwargs): return list(text.encode('ascii'))
        def __len__(self): return 128
    tokenizer = Tokenizer()
    allowed = decision_prefix_constraint(tokenizer, 2)
    for decision in ('yes', 'no', 'uncertain'):
        generated = [9, 9]
        for token in tokenizer.encode(f'DANGER: {decision}\nEVIDENCE:'):
            assert token in allowed(0, np.array(generated))
            generated.append(token)
        assert allowed(0, np.array(generated)) == list(range(128))
    assert allowed(0, np.array([9, 9])) == [ord('D')]
    with pytest.raises(ValueError):
        allowed(0, np.array([9, 9, ord('A')]))
