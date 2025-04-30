from dataclasses import dataclass

from serieux import deserialize
from serieux.ctx import Patcher
from serieux.features.prompt import Promptable


@dataclass
class Person:
    # NAME of the person
    name: str
    # AGE of the person
    age: int
    # MADNESS of the person
    mad: bool


def _prompter(prompts):
    def resolve(ctx, prompt):
        assert prompt in prompts
        return prompts[prompt]

    return resolve


def test_resolve_prompt():
    value = deserialize(
        int,
        "${prompt:Enter your age}",
        Promptable(prompt_function=_prompter({"Enter your age": "42"})),
    )
    assert value == 42


def test_resolve_prompt_boolean():
    value = deserialize(
        bool,
        "${prompt:Are you sure?}",
        Promptable(prompt_function=_prompter({"Are you sure?": "yes"})),
    )
    assert value is True


def test_resolve_prompt_string():
    value = deserialize(
        str,
        "${prompt:What is your name?}",
        Promptable(prompt_function=_prompter({"What is your name?": "John Doe"})),
    )
    assert value == "John Doe"


TEST_YAML = """
name: "${prompt:}"
age: "${prompt:}"
mad: "${prompt:Is the person mad?}"
"""

MODIFIED_YAML = """
name: "John Doe"
age: 42
mad: true
"""


def test_prompt_with_patcher(tmp_path):
    # Create a YAML file with a prompt directive
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text(TEST_YAML)

    # Create a prompter that returns fixed values
    prompter = _prompter(
        {"NAME of the person": "John Doe", "AGE of the person": "42", "Is the person mad?": "yes"}
    )

    # Deserialize with Patcher
    ctx = Promptable(prompt_function=prompter) + Patcher()
    result = deserialize(Person, yaml_file, ctx)

    # Verify the deserialized result
    assert result == Person(name="John Doe", age=42, mad=True)

    # Apply patches
    ctx.apply_patches()

    # Verify the file was modified
    modified_content = yaml_file.read_text()
    assert modified_content == MODIFIED_YAML
