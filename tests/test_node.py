"""Exercise node execution without requiring a GPU or importing ComfyUI."""
from __future__ import annotations

import importlib.util
import asyncio
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "image_prompt_test_package"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT)]
sys.modules[PACKAGE] = package


class Field:
    def __init__(self, name=None, **kwargs):
        self.name = name
        self.__dict__.update(kwargs)


class NodeOutput:
    def __init__(self, *values):
        self.result = values


io = types.SimpleNamespace(ComfyNode=object, Schema=Field, NodeOutput=NodeOutput,
                           **{name: types.SimpleNamespace(Input=Field, Output=Field)
                              for name in ("Image", "String", "Combo", "Boolean", "Int")})
management = types.ModuleType("comfy.model_management")
management.soft_empty_cache = Mock()
management.unload_all_models = Mock()
comfy = types.ModuleType("comfy")
comfy.model_management = management
api = types.ModuleType("comfy_api.latest")
api.io = io
api.ComfyExtension = object
folder_paths = types.ModuleType("folder_paths")
folder_paths.models_dir = "unused"
media = types.ModuleType(PACKAGE + ".media")
media.image_content = lambda image: {"type": "image_url", "image_url": {"url": image.label}}
media.text_content = lambda text: {"type": "text", "text": text}
with patch.dict(sys.modules, {"comfy": comfy, "comfy.model_management": management,
                            "comfy_api": types.ModuleType("comfy_api"), "comfy_api.latest": api,
                            "folder_paths": folder_paths, PACKAGE + ".media": media}):
    spec = importlib.util.spec_from_file_location(PACKAGE + ".node", ROOT / "node.py")
    node = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = node
    spec.loader.exec_module(node)


def image(label="image", batch=1):
    return types.SimpleNamespace(shape=(batch, 16, 16, 3), label=label)


def response(mode="T2I", skill=""):
    value = {"rewritten_prompt": "A precise image prompt.", "wh_ratio": "1:1"}
    if skill == node.BBOX_SKILL_ID:
        row = {"id": "person_1", "desc": "A person."}
        row.update({"from": "ref_image_0", "src_bbox": [0, 0, 1000, 1000],
                    "tgt_bbox": [0, 0, 1000, 1000]} if mode == "I2I"
                   else {"bbox": [0, 0, 1000, 1000]})
        value["rewritten_prompt"] += " " + json.dumps([row])
    if mode == "I2I":
        value["ratio_follow"] = ""
    return json.dumps(value), {"total_tokens": 42}


class NodeTests(unittest.TestCase):
    def test_package_entrypoint_loads_new_node(self):
        spec = importlib.util.spec_from_file_location(PACKAGE, ROOT / "__init__.py",
                                                     submodule_search_locations=[str(ROOT)])
        entrypoint = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {PACKAGE: entrypoint, PACKAGE + ".node": node}):
            spec.loader.exec_module(entrypoint)
        extension = asyncio.run(entrypoint.comfy_entrypoint())
        self.assertEqual(asyncio.run(extension.get_node_list()), [node.ImagePromptLlamaCpp])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in (*node.DEFAULT_MODELS.values(), node.DEFAULT_MMPROJ):
            (self.root / name).touch()
        self.server = Mock()
        self.server.chat.return_value = response()
        self.manager = Mock()
        self.manager.acquire.return_value = self.server, True
        for target, value in (("MODEL_DIR", self.root), ("SERVER_MANAGER", self.manager)):
            patcher = patch.object(node, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_schema_has_ten_fixed_optional_images_and_expected_outputs(self):
        schema = node.ImagePromptLlamaCpp.define_schema()
        images = [field for field in schema.inputs if (field.name or "").startswith("reference_image_")]
        self.assertEqual(len(images), 10)
        self.assertTrue(all(field.optional for field in images))
        self.assertEqual([o.name for o in schema.outputs], ["enhanced_prompt", "selected_skill", "detected_mode", "system_prompt"])
        for removed in ("model_mode", "t2i_model", "i2i_model", "prompt_profile"):
            self.assertNotIn(removed, [f.name for f in schema.inputs])
        self.assertEqual(next(f for f in schema.inputs if f.name == "mode").options, ["T2I", "I2I"])
        self.assertEqual(schema.node_id, "ComfyUI_Image_Prompt_llama-cpp")
        self.assertEqual(schema.display_name, "ComfyUI_Image_Prompt_llama-cpp")
        model_field = next(f for f in schema.inputs if f.name == "model")
        self.assertEqual(set(model_field.options), set(node.DEFAULT_MODELS.values()))
        self.assertIn(model_field.default, model_field.options)
        self.assertEqual(next(f for f in schema.inputs if f.name == "skill").options,
                         list(node.SKILL_NAMES))
        self.assertEqual(next(f for f in schema.inputs if f.name == "mmproj").default, "")

    def test_t2i_without_images_loads_only_t2i_without_projector(self):
        (self.root / node.DEFAULT_MMPROJ).unlink()
        (self.root / node.DEFAULT_MODELS["I2I"]).unlink()
        result = node.ImagePromptLlamaCpp.execute("A bicycle", reference_image_3=None)
        self.assertEqual(result.result, ("A precise image prompt.", "qwen-image-prompt", "T2I",
                                         self.server.chat.call_args.args[0][0]["content"].replace("{", "{{").replace("}", "}}")))
        self.assertIsNone(self.manager.acquire.call_args.args[1])
        self.manager.release.assert_called_once()

    def test_sparse_images_are_forwarded_in_socket_order(self):
        self.server.chat.return_value = response("I2I")
        result = node.ImagePromptLlamaCpp.execute("Combine these", mode="I2I", model=node.DEFAULT_MODELS["I2I"], mmproj=node.DEFAULT_MMPROJ, reference_image_2=image("second"),
                                             reference_image_10=image("tenth"), force_unload_model=False)
        self.assertEqual(result.result[2], "I2I")
        content = self.server.chat.call_args.args[0][1]["content"]
        self.assertEqual([item["image_url"]["url"] for item in content if item["type"] == "image_url"],
                         ["second", "tenth"])
        self.assertEqual([item["text"] for item in content if item["type"] == "text"],
                         ["<image1>", "<image2>", "Combine these"])
        self.assertEqual(self.manager.acquire.call_args.args[1], self.root / node.DEFAULT_MMPROJ)
        self.manager.release.assert_not_called()

    def test_krea_instructions_reach_server_without_qwen_prompt(self):
        result = node.ImagePromptLlamaCpp.execute("A bicycle", skill="krea-2-text-expansion")
        system = self.server.chat.call_args.args[0][0]["content"]
        expansion = (ROOT / "custom_skills/krea-2-text-expansion/prompts/expansion.txt").read_text(encoding="utf-8")
        self.assertIn(expansion, system)
        self.assertNotIn((ROOT / "custom_skills/qwen-image-prompt/prompts/T2I.txt").read_text(encoding="utf-8"), system)
        self.assertEqual(result.result[1], "krea-2-text-expansion")

    def test_additional_instructions_reach_model_and_system_prompt_output(self):
        for skill in node.SKILL_NAMES:
            with self.subTest(skill=skill):
                self.server.chat.return_value = response(skill=skill)
                extra = "Use warm lighting and a muted palette."
                result = node.ImagePromptLlamaCpp.execute(
                    "A bicycle", skill=skill, additional_system_instructions=extra)
                system = self.server.chat.call_args.args[0][0]["content"]
                self.assertIn(extra, system)
                self.assertIn(node.system_prompt(skill, "T2I").split("# ComfyUI transport contract")[0].strip(), system)
                self.assertEqual(result.result[3].format(), system)

    def test_system_output_survives_krea_template_formatting(self):
        for skill in node.SKILL_NAMES:
            for mode in ("T2I", "I2I"):
                with self.subTest(skill=skill, mode=mode):
                    self.server.chat.return_value = response(mode, skill)
                    extra = 'Keep {subject}, {}, {0}, {{literal}}, and JSON {"color": "red"}.'
                    kwargs = (dict(reference_image_1=image(), mmproj=node.DEFAULT_MMPROJ)
                              if mode == "I2I" else {})
                    result = node.ImagePromptLlamaCpp.execute(
                        "A bicycle", skill=skill, mode=mode,
                        additional_system_instructions=extra, **kwargs)
                    original = self.server.chat.call_args.args[0][0]["content"]
                    template = ("<|im_start|>system\n" + result.result[3] + "<|im_end|>\n"
                                "<|im_start|>user\n{}<|im_end|>\n<|im_start|>assistant\n")
                    user_text = 'A bicycle with {red} wheels'
                    rendered = template.format(user_text)
                    self.assertEqual(rendered, "<|im_start|>system\n" + original + "<|im_end|>\n"
                                     + "<|im_start|>user\n" + user_text
                                     + "<|im_end|>\n<|im_start|>assistant\n")
                    self.assertIn(extra, original)

    def test_krea_i2i_forwards_references_and_parses_output(self):
        self.server.chat.return_value = (json.dumps({"rewritten_prompt": "Edit the person from <image1> using the pose from <image2>.",
                                                    "wh_ratio": "", "ratio_follow": "<image1>"}), {})
        result = node.ImagePromptLlamaCpp.execute(
            "Use the second pose", skill="krea-2-text-expansion", mode="I2I",
            model=node.DEFAULT_MODELS["I2I"], mmproj=node.DEFAULT_MMPROJ,
            reference_image_2=image("identity"), reference_image_7=image("pose"))
        messages = self.server.chat.call_args.args[0]
        prompt = (ROOT / "custom_skills/krea-2-text-expansion/prompts/expansion-i2i.txt").read_text(encoding="utf-8")
        self.assertIn(prompt, messages[0]["content"])
        content = messages[1]["content"]
        self.assertEqual([p["text"] for p in content if p["type"] == "text"],
                         ["<image1>", "<image2>", "Use the second pose"])
        self.assertEqual([p["image_url"]["url"] for p in content if p["type"] == "image_url"],
                         ["identity", "pose"])
        self.assertEqual(result.result, ("Edit the person from <image1> using the pose from <image2>.",
                                         "krea-2-text-expansion", "I2I", messages[0]["content"].replace("{", "{{").replace("}", "}}")))

    def test_all_ten_images_forwarded(self):
        self.server.chat.return_value = response("I2I")
        node.ImagePromptLlamaCpp.execute("Combine", mode="I2I", model=node.DEFAULT_MODELS["I2I"], mmproj=node.DEFAULT_MMPROJ, **{f"reference_image_{i}": image(str(i)) for i in range(1, 11)})
        content = self.server.chat.call_args.args[0][1]["content"]
        self.assertEqual(sum(part["type"] == "image_url" for part in content), 10)

    def test_t2i_ignores_stale_projector_selection(self):
        node.ImagePromptLlamaCpp.execute("A bicycle", mmproj="missing.gguf")
        self.assertIsNone(self.manager.acquire.call_args.args[1])

    def test_explicit_i2i_projector(self):
        projector = self.root / "I2I" / node.DEFAULT_MMPROJ
        projector.parent.mkdir()
        projector.touch()
        self.server.chat.return_value = response("I2I")
        node.ImagePromptLlamaCpp.execute("Edit", mode="I2I", model=node.DEFAULT_MODELS["I2I"], reference_image_1=image(),
                                     mmproj="I2I/" + node.DEFAULT_MMPROJ)
        self.assertEqual(self.manager.acquire.call_args.args[1], projector)

    def test_t2i_never_sends_connected_images_or_projector(self):
        result = node.ImagePromptLlamaCpp.execute("A bicycle", reference_image_1=image(),
                                             mmproj=node.DEFAULT_MMPROJ)
        self.assertEqual(result.result[2], "T2I")
        self.assertIsNone(self.manager.acquire.call_args.args[1])
        content = self.server.chat.call_args.args[0][1]["content"]
        self.assertTrue(all(item["type"] == "text" for item in content))

    def test_i2i_requires_images_and_projector(self):
        with self.assertRaisesRegex(ValueError, "at least one"):
            node.ImagePromptLlamaCpp.execute("Edit", mode="I2I", model=node.DEFAULT_MODELS["I2I"])
        with self.assertRaisesRegex(ValueError, "Select the I2I mmproj"):
            node.ImagePromptLlamaCpp.execute("Edit", mode="I2I", model=node.DEFAULT_MODELS["I2I"], reference_image_1=image())
        with self.assertRaisesRegex(ValueError, "not a model file"):
            node.ImagePromptLlamaCpp.execute("Edit", mode="I2I", model=node.DEFAULT_MODELS["I2I"],
                                         reference_image_1=image(), mmproj=node.DEFAULT_MODELS["I2I"])
        self.manager.acquire.assert_not_called()

    def test_other_model_loads_with_and_without_reference_images(self):
        model = self.root / "Other" / "model-Q5_K_M.gguf"
        model.parent.mkdir()
        model.touch()
        projector = model.parent / "mmproj-other-f16.gguf"
        projector.touch()
        schema = node.ImagePromptLlamaCpp.define_schema()
        self.assertIn("Other/model-Q5_K_M.gguf", next(f for f in schema.inputs if f.name == "model").options)
        self.assertIn("Other/mmproj-other-f16.gguf", next(f for f in schema.inputs if f.name == "mmproj").options)
        result = node.ImagePromptLlamaCpp.execute("Describe", model="Other/model-Q5_K_M.gguf")
        self.assertEqual(result.result[2], "T2I")
        self.manager.acquire.assert_called_with(model, None)
        with self.assertRaisesRegex(ValueError, "Select the I2I mmproj"):
            node.ImagePromptLlamaCpp.execute("Edit", mode="I2I", model="Other/model-Q5_K_M.gguf", reference_image_1=image())
        self.server.chat.return_value = response("I2I")
        result = node.ImagePromptLlamaCpp.execute("Edit", mode="I2I", model="Other/model-Q5_K_M.gguf",
                                             mmproj="Other/mmproj-other-f16.gguf", reference_image_1=image("reference"))
        self.assertEqual(result.result[2], "I2I")
        self.manager.acquire.assert_called_with(model, projector)
        content = self.server.chat.call_args.args[0][1]["content"]
        self.assertTrue(any(part.get("image_url", {}).get("url") == "reference" for part in content))

    def test_auto_and_unknown_selections_rejected(self):
        for selection in ("auto", "unknown"):
            with self.assertRaisesRegex(ValueError, "Unknown model mode"):
                node.ImagePromptLlamaCpp.execute("A bicycle", mode=selection)
            with self.assertRaisesRegex(ValueError, "Unknown skill"):
                node.ImagePromptLlamaCpp.execute("A bicycle", skill=selection)
        self.manager.acquire.assert_not_called()

    def test_selected_skill_is_used_without_router(self):
        with patch.object(node, "SKILL_NAMES", ("custom-style",)), patch.object(node, "system_prompt", return_value="Custom instructions") as build:
            result = node.ImagePromptLlamaCpp.execute("A bicycle", skill="custom-style")
        self.assertEqual(result.result[1], "custom-style")
        self.assertEqual(build.call_args.args[0], "custom-style")
        self.server.chat.assert_called_once()

    def test_mode_overrides_model_filename_and_connected_images(self):
        result = node.ImagePromptLlamaCpp.execute("A bicycle", mode="T2I", model=node.DEFAULT_MODELS["I2I"], reference_image_1=image())
        self.assertEqual(result.result[2], "T2I")
        self.manager.acquire.assert_called_with(self.root / node.DEFAULT_MODELS["I2I"], None)

    def test_more_than_ten_images_rejected(self):
        with self.assertRaisesRegex(ValueError, "At most 10"):
            node._validate_reference_images([image() for _ in range(11)])

    def test_batch_rejected_before_acquiring_server(self):
        with self.assertRaisesRegex(ValueError, "exactly one image"):
            node.ImagePromptLlamaCpp.execute("Edit", mode="I2I", model=node.DEFAULT_MODELS["I2I"], reference_image_1=image(batch=2))
        self.manager.acquire.assert_not_called()
        self.manager.release.assert_called_once()

    def test_repairs_invalid_json_once(self):
        self.server.chat.side_effect = [("invalid", {}), response()]
        self.assertEqual(node.ImagePromptLlamaCpp.execute("A bicycle").result[0], "A precise image prompt.")
        self.assertEqual(self.server.chat.call_count, 2)

    def test_bbox_missing_table_is_repaired_and_references_are_zero_based(self):
        repaired = response("I2I", node.BBOX_SKILL_ID)
        self.server.chat.side_effect = [response("I2I"), repaired]
        result = node.ImagePromptLlamaCpp.execute(
            'Change <obj_1> to a dark skinned boy. '
            '[{"id":"obj_1","from":"ref_image_0","src_bbox":[118,221,1000,543],'
            '"tgt_bbox":null,"desc":""}]',
            skill=node.BBOX_SKILL_ID, mode="I2I", mmproj=node.DEFAULT_MMPROJ,
            reference_image_2=image("first"), reference_image_10=image("second"))
        self.assertEqual(result.result[0], json.loads(repaired[0])["rewritten_prompt"])
        messages = self.server.chat.call_args.args[0]
        self.assertEqual([p["text"] for p in messages[1]["content"][:-1]
                          if p["type"] == "text"], ["<ref_image_0>", "<ref_image_1>"])
        self.assertIn("do not omit the table", messages[-1]["content"])
        self.assertEqual(self.server.chat.call_count, 2)

    def test_failure_always_unloads_even_when_reuse_enabled(self):
        self.server.chat.return_value = ("invalid", {})
        with self.assertRaises(ValueError):
            node.ImagePromptLlamaCpp.execute("A bicycle", force_unload_model=False)
        self.manager.release.assert_called_once()

    def test_missing_projector_fails_before_server(self):
        (self.root / node.DEFAULT_MMPROJ).unlink()
        with self.assertRaises(FileNotFoundError):
            node.ImagePromptLlamaCpp.execute("Edit", mode="I2I", model=node.DEFAULT_MODELS["I2I"], mmproj=node.DEFAULT_MMPROJ, reference_image_1=image())
        self.manager.acquire.assert_not_called()


if __name__ == "__main__":
    unittest.main()
