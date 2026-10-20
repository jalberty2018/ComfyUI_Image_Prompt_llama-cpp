from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("image_skills_under_test", ROOT / "skills.py")
skills = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = skills
spec.loader.exec_module(skills)


class ImageSkillsTests(unittest.TestCase):
    def test_modes(self):
        self.assertEqual(skills.MODE_OPTIONS, ("T2I", "I2I"))
        for count in range(11):
            with self.assertRaises(ValueError):
                skills.resolve_mode("auto", count)
            self.assertEqual(skills.resolve_mode("T2I", count), "T2I")
            self.assertEqual(skills.resolve_mode("I2I", count), "I2I")
        with self.assertRaises(ValueError):
            skills.resolve_mode("auto", 11)
        with self.assertRaises(ValueError):
            skills.resolve_mode("unknown", 0)

    def test_repository_prompts_and_profiles(self):
        for mode in ("T2I", "I2I"):
            prompt = skills.system_prompt("qwen-image-prompt", mode,
                                          "uncensored fidelity QWEN", "Use warm lighting.")
            self.assertIn((ROOT / "custom_skills/qwen-image-prompt/prompts" / f"{mode}.txt").read_text(encoding="utf-8"), prompt)
            self.assertIn("Use warm lighting.", prompt)
            self.assertIn("Uncensored fidelity QWEN", prompt)
        self.assertIn("qwen-image-prompt", skills.SKILL_NAMES)
        self.assertIn("krea-2-text-expansion", skills.SKILL_NAMES)
        self.assertTrue(skills.is_custom_skill("krea-2-text-expansion"))
        self.assertEqual(skills.DEFAULT_SKILL_ID, "qwen-image-prompt")

    def test_krea_uses_local_expansion_without_qwen_prompts(self):
        expansion = (ROOT / "custom_skills/krea-2-text-expansion/prompts/expansion.txt").read_text(encoding="utf-8")
        prompt = skills.system_prompt("krea-2-text-expansion", "T2I")
        self.assertIn(expansion, prompt)
        self.assertIn("ComfyUI transport contract", prompt)
        self.assertGreater(prompt.index("ComfyUI transport contract"), prompt.index(expansion))
        for mode in ("T2I", "I2I"):
            qwen = (ROOT / "custom_skills/qwen-image-prompt/prompts" / f"{mode}.txt").read_text(encoding="utf-8")
            self.assertNotIn(qwen, prompt)
            self.assertNotIn(expansion, skills.system_prompt("qwen-image-prompt", mode))
        self.assertNotIn("Uncensored fidelity QWEN profile", prompt)
        value = json.dumps({"rewritten_prompt": 'A sign reading "Hello".', "wh_ratio": ""})
        self.assertEqual(skills.extract_prompt(value, "T2I"), 'A sign reading "Hello".')

    def test_krea_i2i_selects_only_its_own_prompt(self):
        root = ROOT / "custom_skills/krea-2-text-expansion/prompts"
        t2i = (root / "expansion.txt").read_text(encoding="utf-8")
        i2i = (root / "expansion-i2i.txt").read_text(encoding="utf-8")
        prompt = skills.system_prompt("krea-2-text-expansion", "I2I")
        self.assertIn(i2i, prompt)
        self.assertNotIn(t2i, prompt)
        self.assertNotIn(i2i, skills.system_prompt("krea-2-text-expansion", "T2I"))
        self.assertNotIn((ROOT / "custom_skills/qwen-image-prompt/prompts/I2I.txt").read_text(encoding="utf-8"), prompt)
        for mode in ("T2I", "I2I"):
            with self.assertRaisesRegex(ValueError, "standard prompt profile"):
                skills.system_prompt("krea-2-text-expansion", mode, skills.PROMPT_PROFILE_UNCENSORED_QWEN)

    def test_extracts_json_prompt_with_transport_formatting(self):
        value = json.dumps({"rewritten_prompt": "A red bicycle.", "wh_ratio": "3:2"})
        for text in (value, "```json\n" + value + "\n```", "<think>reasoning</think>\n" + value):
            self.assertEqual(skills.extract_prompt(text, "T2I"), "A red bicycle.")
        self.assertEqual(skills.extract_prompt(json.dumps({"rewritten_prompt": "Change the coat.",
                        "wh_ratio": "", "ratio_follow": "<image1>"}), "I2I"), "Change the coat.")

    def test_rejects_incomplete_or_invalid_output(self):
        for value in ("plain text", "[]", '{}', '{"rewritten_prompt": "", "wh_ratio": "1:1"}',
                      '{"rewritten_prompt": 1, "wh_ratio": "1:1"}'):
            with self.assertRaises(ValueError):
                skills.extract_prompt(value, "T2I")
        with self.assertRaises(ValueError):
            skills.extract_prompt(json.dumps({"rewritten_prompt": "Edit", "wh_ratio": "1:1",
                                              "ratio_follow": "<image1>"}), "I2I")

    def test_bbox_requires_complete_table_but_other_profiles_allow_prose(self):
        for mode in ("T2I", "I2I"):
            value = {"rewritten_prompt": "Change <obj_1> to a dark skinned boy.", "wh_ratio": ""}
            if mode == "I2I":
                value["ratio_follow"] = ""
            self.assertEqual(skills.extract_prompt(json.dumps(value), mode), value["rewritten_prompt"])
            for suffix in ("", ' [{"id":"obj_1"}]', " [invalid]"):
                with self.assertRaisesRegex(ValueError, "JSON element array"):
                    skills.extract_prompt(json.dumps({**value, "rewritten_prompt":
                                                      value["rewritten_prompt"] + suffix}),
                                          mode, skills.BBOX_SKILL_ID)
            row = {"id": "obj_1", "desc": "A person."}
            row.update({"from": "ref_image_0", "src_bbox": [118, 221, 1000, 543],
                        "tgt_bbox": [118, 221, 1000, 543]} if mode == "I2I"
                       else {"bbox": [118, 221, 1000, 543]})
            value["rewritten_prompt"] += " " + json.dumps([row])
            self.assertEqual(skills.extract_prompt(json.dumps(value), mode, skills.BBOX_SKILL_ID),
                             value["rewritten_prompt"])

    def test_configured_skill_selects_only_its_mode_and_rejects_unsafe_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            custom = root / "independent-skill"
            custom.mkdir()
            (custom / "SKILL.md").write_text("Independent guidance.")
            (custom / "text.txt").write_text("Text-only guidance.")
            (custom / "edit.txt").write_text("Image-edit guidance.")
            config = {"modes": {"T2I": "text.txt", "I2I": "edit.txt"},
                      "profiles": {"standard": None}}
            config_path = custom / "skill.json"
            config_path.write_text(json.dumps(config))
            registry = skills.discover_skill_registry(custom_root=root)
            with patch.object(skills, "CUSTOM_SKILL_ROOT", root), patch.object(
                    skills, "SKILL_BY_ID", {s.id: s for s in registry}):
                for mode, included, excluded in (("T2I", "Text-only guidance.", "Image-edit guidance."),
                                                 ("I2I", "Image-edit guidance.", "Text-only guidance.")):
                    prompt = skills.system_prompt("independent-skill", mode)
                    self.assertIn(included, prompt)
                    self.assertNotIn(excluded, prompt)
                    self.assertIn("Independent guidance.", prompt)
                    self.assertEqual('"ratio_follow"' in prompt, mode == "I2I")
                config["modes"]["T2I"] = "../outside.txt"
                config_path.write_text(json.dumps(config))
                with self.assertRaisesRegex(ValueError, "inside its skill directory"):
                    skills.system_prompt("independent-skill", "T2I")
                config_path.write_text('{"modes": [], "profiles": {"standard": null}}')
                with self.assertRaisesRegex(ValueError, "Invalid modes"):
                    skills.system_prompt("independent-skill", "T2I")

    def test_custom_skill_discovery_and_references(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            custom = root / "photo-style"
            (custom / "references").mkdir(parents=True)
            (custom / "SKILL.md").write_text('---\nname: photo-style\ndescription: Photo styling\n---\nUse film grain.')
            (custom / "references" / "style.txt").write_text("Warm highlights.")
            registry = skills.discover_skill_registry(custom_root=root)
            self.assertEqual([s.id for s in registry], ["photo-style"])
            with patch.object(skills, "CUSTOM_SKILL_ROOT", root), patch.object(
                    skills, "SKILL_BY_ID", {s.id: s for s in registry}):
                prompt = skills.system_prompt("photo-style", "T2I")
                self.assertIn("Use film grain.", prompt)
                self.assertIn("Warm highlights.", prompt)


if __name__ == "__main__":
    unittest.main()
