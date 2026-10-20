from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

PROMPT_PROFILE_STANDARD = "standard"
PROMPT_PROFILE_UNCENSORED_QWEN = "uncensored fidelity QWEN"
PROMPT_PROFILES = (PROMPT_PROFILE_STANDARD, PROMPT_PROFILE_UNCENSORED_QWEN)
MODE_OPTIONS = ("T2I", "I2I")
BBOX_SKILL_ID = "flux-3-image-klein-pup-bbox"
CUSTOM_SKILL_ROOT = Path(__file__).with_name("custom_skills")
LOGGER = logging.getLogger("ComfyUI.QwenImagePrompt.skills")
SKILL_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


@dataclass(frozen=True)
class SkillSpec:
    """A discovered prompt-only Skill available to the local node."""

    id: str
    path: Path
    description: str
    source: str
    display_name: str | None = None
    version: str | None = None
    tags: tuple[str, ...] = ()


def _scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _list_values(value: str | tuple[str, ...] | None) -> tuple[str, ...]:
    if isinstance(value, tuple):
        return tuple(item for item in value if item.strip())
    if not isinstance(value, str) or not value.strip():
        return ()
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
        return tuple(
            item
            for item in (_scalar(part) for part in value.split(","))
            if item.strip()
        )
    return (value,)


def _front_matter(path: Path) -> dict[str, str]:
    """Read the small subset of YAML front matter needed for Skill discovery."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    if not lines or lines[0].strip() != "---":
        return {}

    end = next(
        (
            index
            for index in range(1, len(lines))
            if lines[index].strip() == "---"
            and not lines[index].startswith((" ", "\t"))
        ),
        None,
    )
    if end is None:
        return {}

    values: dict[str, str] = {}
    index = 1
    while index < end:
        line = lines[index]
        match = re.match(
            r"^(?P<indent>\s*)(?P<key>[A-Za-z0-9_-]+):\s*(?P<value>.*)$",
            line,
        )
        if not match or match.group("indent"):
            index += 1
            continue

        key = match.group("key").replace("-", "_").casefold()
        value = match.group("value").strip()
        if value.startswith(("|", ">")):
            block: list[str] = []
            cursor = index + 1
            while cursor < end:
                candidate = lines[cursor]
                if candidate.strip() and not candidate.startswith((" ", "\t")):
                    break
                block.append(candidate)
                cursor += 1
            non_empty = [line for line in block if line.strip()]
            indent = min((len(line) - len(line.lstrip()) for line in non_empty), default=0)
            block = [line[indent:] if line.strip() else "" for line in block]
            values[key] = ("\n" if value.startswith("|") else " ").join(block).strip()
            index = cursor
            continue
        if value:
            values[key] = _scalar(value)
        index += 1
    return values


def _meta_yaml(path: Path) -> dict[str, str | tuple[str, ...]]:
    """Read simple scalar and list metadata from the bundled meta.yaml convention."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}

    values: dict[str, str | tuple[str, ...]] = {}
    index = 0
    while index < len(lines):
        match = re.match(r"^(?P<key>[A-Za-z0-9_-]+):\s*(?P<value>.*)$", lines[index])
        if not match:
            index += 1
            continue
        key = match.group("key").replace("-", "_").casefold()
        value = match.group("value").strip()
        if value:
            values[key] = _scalar(value)
            index += 1
            continue

        items: list[str] = []
        cursor = index + 1
        while cursor < len(lines):
            item = re.match(r"^\s*-\s*(.+?)\s*$", lines[cursor])
            if not item:
                break
            items.append(_scalar(item.group(1)))
            cursor += 1
        if items:
            values[key] = tuple(items)
        index = cursor
    return values


def _metadata(skill_root: Path) -> tuple[str, str, str | None, str | None, tuple[str, ...]]:
    front = _front_matter(skill_root / "SKILL.md")
    meta = _meta_yaml(skill_root / "meta.yaml")
    skill_id = front.get("name", "").strip() or skill_root.name
    description = (
        front.get("description", "").strip()
        or str(meta.get("summary_en", "")).strip()
        or str(meta.get("desc_en", "")).strip()
        or skill_id
    )
    description = " ".join(description.split())
    display_name = (
        front.get("display_name", "").strip()
        or front.get("display_name_en", "").strip()
        or front.get("display_name_zh", "").strip()
        or str(meta.get("display_name_en", "")).strip()
        or str(meta.get("display_name_zh", "")).strip()
        or None
    )
    version = (
        front.get("version", "").strip()
        or str(meta.get("version", "")).strip()
        or None
    )
    raw_tags: list[str] = []
    for values in (
        _list_values(front.get("tags")),
        _list_values(front.get("tag_en")),
        _list_values(front.get("tag_cn")),
        _list_values(meta.get("tags")),
        _list_values(meta.get("tag_en")),
        _list_values(meta.get("tag_cn")),
        _list_values(meta.get("complete_tags_en")),
        _list_values(meta.get("complete_tags_cn")),
    ):
        raw_tags.extend(values)
    return skill_id, description, display_name, version, tuple(dict.fromkeys(raw_tags))


def _discover_skills(root: Path, source: str) -> list[SkillSpec]:
    if not root.is_dir():
        return []
    resolved_root = root.resolve()
    discovered: list[SkillSpec] = []
    for candidate in sorted(root.iterdir(), key=lambda item: item.name.casefold()):
        if not candidate.is_dir():
            continue
        skill_path = candidate.resolve()
        if skill_path.parent != resolved_root:
            LOGGER.warning("Ignoring Skill outside %s: %s", resolved_root, candidate)
            continue
        skill_file = skill_path / "SKILL.md"
        if not skill_file.is_file() or skill_file.resolve().parent != skill_path:
            LOGGER.warning("Ignoring Skill without SKILL.md: %s", skill_path)
            continue
        skill_id, description, display_name, version, tags = _metadata(skill_path)
        if not SKILL_ID_RE.fullmatch(skill_id) or skill_id == "auto":
            LOGGER.warning("Ignoring Skill with invalid id %r: %s", skill_id, skill_path)
            continue
        discovered.append(
            SkillSpec(
                id=skill_id,
                path=skill_path,
                description=description,
                source=source,
                display_name=display_name,
                version=version,
                tags=tags,
            )
        )
    return discovered


def discover_skill_registry(
    custom_root: Path | None = None,
) -> tuple[SkillSpec, ...]:
    """Discover all skills from the single custom_skills directory."""
    custom_root = CUSTOM_SKILL_ROOT if custom_root is None else custom_root
    registry: list[SkillSpec] = []
    seen: set[str] = set()
    candidates = [
        *_discover_skills(custom_root, "custom"),
    ]
    for spec in candidates:
        key = spec.id.casefold()
        if key in seen:
            LOGGER.warning("Ignoring duplicate Skill id %r from %s", spec.id, spec.path)
            continue
        seen.add(key)
        registry.append(spec)
    return tuple(registry)


SKILL_REGISTRY = discover_skill_registry()
SKILL_NAMES = tuple(spec.id for spec in SKILL_REGISTRY)
SKILL_DESCRIPTIONS = {spec.id: spec.description for spec in SKILL_REGISTRY}
SKILL_BY_ID = {spec.id.casefold(): spec for spec in SKILL_REGISTRY}
DEFAULT_SKILL_ID = (
    "qwen-image-prompt"
    if "qwen-image-prompt" in SKILL_NAMES
    else (SKILL_NAMES[0] if SKILL_NAMES else "")
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _skill_spec(skill: str) -> SkillSpec:
    spec = SKILL_BY_ID.get(skill.casefold())
    if spec is None:
        raise ValueError(f"Unknown skill: {skill}")
    return spec


def _skill_path(skill: str) -> Path:
    spec = _skill_spec(skill)
    root = spec.path.resolve()
    if root.parent != CUSTOM_SKILL_ROOT.resolve():
        raise FileNotFoundError(f"Skill path is outside the configured Skill roots: {skill}")
    skill_file = root / "SKILL.md"
    if (
        not root.is_dir()
        or not skill_file.is_file()
        or skill_file.resolve().parent != root
    ):
        raise FileNotFoundError(f"Skill is missing SKILL.md: {skill}")
    return root


def normalize_model_output(text: str) -> str:
    """Remove harmless transport formatting without rewriting model content."""
    stripped = text.lstrip("\ufeff").strip()
    fenced = re.fullmatch(
        r"```[^\r\n]*\r?\n(?P<body>.*?)\r?\n```",
        stripped,
        flags=re.DOTALL,
    )
    if fenced:
        return fenced.group("body").strip()
    return stripped


def is_custom_skill(skill: str) -> bool:
    return _skill_spec(skill).source == "custom"


def resolve_mode(selection: str, image_count: int) -> str:
    if not 0 <= image_count <= 10:
        raise ValueError("At most 10 reference images are supported")
    if selection not in MODE_OPTIONS:
        raise ValueError(f"Unknown model mode: {selection}")
    return selection



def skill_instructions(skill: str, max_chars: int = 72000) -> str:
    root = _skill_path(skill)
    # Discovery metadata describes the skill to the loader, not to the model.
    body = _read(root / "SKILL.md")
    body = re.sub(r"\A\ufeff?---[^\S\r\n]*\r?\n.*?\r?\n---[^\S\r\n]*(?:\r?\n|$)",
                  "", body, count=1, flags=re.DOTALL).strip()
    parts = [body]
    for path in sorted((root / "references").glob("**/*")):
        resolved = path.resolve()
        if (path.is_file() and path.suffix.lower() in {".md", ".txt"}
                and resolved.is_relative_to(root)):
            addition = _read(resolved)
            if sum(map(len, parts)) + len(addition) > max_chars:
                break
            parts.append(addition)
    return "\n\n".join(parts)


def _read_skill_file(root: Path, relative: str) -> str:
    path = (root / relative).resolve()
    if Path(relative).is_absolute() or not path.is_relative_to(root):
        raise ValueError(f"Skill file must stay inside its skill directory: {relative}")
    return _read(path)


def system_prompt(skill: str, mode: str, prompt_profile: str = PROMPT_PROFILE_STANDARD,
                  additional_system_instructions: str = "") -> str:
    if mode not in {"T2I", "I2I"}:
        raise ValueError(f"Unknown model mode: {mode}")
    if prompt_profile not in PROMPT_PROFILES:
        raise ValueError(f"Unknown prompt profile: {prompt_profile}")
    root = _skill_path(skill)
    config_path = root / "skill.json"
    config = {"modes": {"T2I": None}, "profiles": {"standard": None}}
    if config_path.exists():
        config = json.loads(_read_skill_file(root, "skill.json"))
    if not isinstance(config, dict):
        raise ValueError(f"Invalid skill.json for {skill}: expected an object")
    for key, allowed in (("modes", MODE_OPTIONS), ("profiles", PROMPT_PROFILES)):
        mapping = config.get(key)
        if (not isinstance(mapping, dict) or not mapping
                or any(name not in allowed for name in mapping)
                or any(value is not None and not isinstance(value, str) for value in mapping.values())):
            raise ValueError(f"Invalid {key} in skill.json for {skill}")
    if mode not in config["modes"]:
        raise ValueError(f"{skill} supports {', '.join(config['modes'])} only")
    if prompt_profile not in config["profiles"]:
        raise ValueError(f"{skill} supports {', '.join(config['profiles'])} prompt profile only")
    parts = []
    mode_file = config["modes"][mode]
    if mode_file is not None:
        parts.append(_read_skill_file(root, mode_file))
    parts.append(skill_instructions(skill))
    profile_file = config["profiles"][prompt_profile]
    if profile_file is not None:
        parts.append(_read_skill_file(root, profile_file))
    fields = '"rewritten_prompt" and "wh_ratio"'
    if mode == "I2I":
        fields += ' and "ratio_follow"'
    if skill == BBOX_SKILL_ID:
        parts.append(
            "# Required bounding-box payload\n"
            "Return BOTH the expanded instruction/caption AND "
            "the complete JSON element array directly, without an outer JSON object. "
            "Never return only the instruction or discard the input element table. "
            "Use supplied object IDs and source boxes to identify the requested edit; "
            "fill empty descriptions from the reference images. For an appearance "
            "change, the object remains present: provide its target box, not null. "
            "A null target box means removal only. Reference images are numbered "
            "from ref_image_0 in attachment order."
        )
    if additional_system_instructions.strip():
        parts.append("# Additional system instructions\n" + additional_system_instructions.strip())
    if skill == BBOX_SKILL_ID:
        parts.append(
            "# ComfyUI transport contract\n"
            "Return the native annotation format: one instruction/caption paragraph, "
            "one space, then one JSON element array. Do not wrap it in rewritten_prompt "
            "or add wh_ratio or ratio_follow fields. This overrides any instruction "
            "to escape the annotation inside a JSON string. No reasoning or markdown fences."
        )
        return "\n\n".join(parts)
    parts.append(
        "# ComfyUI transport contract\n"
        f"Return exactly one JSON object with exactly these string fields: {fields}. "
        "Put the complete skill output in rewritten_prompt, including any required "
        "element array, and escape quotes for JSON. "
        "This contract replaces any plain-text/no-JSON output instruction in the skill. "
        "Do not output reasoning, markdown fences, or follow-up questions. "
        "Preserve reference-image facts. Follow the skill's aspect-ratio rules; "
        "if it supplies none, use the user's requested ratio or an empty wh_ratio. "
        + ("For I2I, ratio_follow is the reference image tag whose ratio should be used, "
           "or an empty string. wh_ratio and ratio_follow must not both be nonempty."
           if mode == "I2I" else "")
    )
    return "\n\n".join(parts)


def extract_prompt(text: str, mode: str, skill: str = "") -> str:
    text = re.sub(r"^\s*<think>.*?</think>\s*", "", text, flags=re.DOTALL)
    text = normalize_model_output(text)
    if skill == BBOX_SKILL_ID:
        # Prefer the model's native annotation format; retain compatibility with
        # responses following the older JSON transport instructions.
        try:
            wrapped = json.loads(text)
        except ValueError:
            wrapped = None
        if isinstance(wrapped, dict) and isinstance(wrapped.get("rewritten_prompt"), str):
            text = wrapped["rewritten_prompt"].strip()
        _validate_bbox_payload(text, mode)
        return text
    data = json.loads(text)
    expected = {"rewritten_prompt", "wh_ratio"}
    if mode == "I2I":
        expected.add("ratio_follow")
    if not isinstance(data, dict) or set(data) != expected:
        raise ValueError(f"Expected JSON fields: {', '.join(sorted(expected))}")
    if any(not isinstance(data[key], str) for key in expected):
        raise ValueError("All output fields must be strings")
    result = data["rewritten_prompt"].strip()
    if not result:
        raise ValueError("rewritten_prompt must not be empty")
    if mode == "I2I" and data["wh_ratio"] and data["ratio_follow"]:
        raise ValueError("wh_ratio and ratio_follow must be mutually exclusive")
    return result


def _validate_bbox_payload(result: str, mode: str) -> None:
    """Reject missing/incomplete tables so the node can request a repaired answer."""
    for match in re.finditer(r"\[", result):
        try:
            rows, end = json.JSONDecoder().raw_decode(result[match.start():])
        except ValueError:
            continue
        if result[match.start() + end:].strip() or not result[:match.start()].strip():
            continue
        if not isinstance(rows, list):
            continue
        required = ({"id", "from", "src_bbox", "tgt_bbox", "desc"} if mode == "I2I"
                    else {"id", "bbox", "desc"})
        if all(isinstance(row, dict) and required <= row.keys() for row in rows):
            return
    raise ValueError(
        "The output must contain the complete instruction/caption followed by "
        "a JSON element array with all required bbox row fields; do not omit the table"
    )
