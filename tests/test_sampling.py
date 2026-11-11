"""Test sampling policy without importing ComfyUI/GPU dependencies."""
import ast
from pathlib import Path
import unittest

source = Path(__file__).resolve().parents[1] / "node.py"
function = next(n for n in ast.parse(source.read_text(encoding="utf-8")).body
                if isinstance(n, ast.FunctionDef) and n.name == "_sampling_settings")
namespace = {}
exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), "exec"), namespace)
settings = namespace["_sampling_settings"]

class SamplingTests(unittest.TestCase):
    def test_legacy_presets(self):
        self.assertEqual(settings(False)["temperature"], 0.7)
        self.assertEqual(settings(True)["temperature"], 1.0)

    def test_off_ignores_hidden_values(self):
        self.assertEqual(settings(True, {"sampling_mode": "off", "temperature": 1.8}),
                         dict(temperature=0.0, top_p=1.0, top_k=1, min_p=0.0,
                              presence_penalty=0.0, repetition_penalty=1.0))

    def test_on_uses_user_values_in_both_think_modes(self):
        custom = dict(temperature=0.4, top_p=0.9, top_k=64, min_p=0.05,
                      presence_penalty=0.2, repetition_penalty=1.05)
        for thinking in (True, False):
            self.assertEqual(settings(thinking, dict(sampling_mode="on", **custom)), custom)
