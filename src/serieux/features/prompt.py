from typing import Any, Callable, Literal

from ovld import ovld

from ..ctx import Patcher
from ..model import field_at
from .interpol import Environment, decode_string


def default_prompt(ctx, prompt):  # pragma: no cover
    return input(
        f"\033[1;36m[{'.'.join(str(x) for x in ctx.access_path)}]\033[0m \033[1;33m{prompt}\033[0m\n\033[1;32m>\033[0m "
    )


class Promptable(Environment):
    prompt_function: Callable[[str], str] = default_prompt

    @ovld
    def resolve_variable(self, t: Any, method: Literal["prompt"], expr: str, /):
        if not expr:
            objt, _, field = self.full_path[-1]
            fld = field_at(objt, [field])
            expr = (fld and fld.description) or "Enter value"
        value = decode_string(t, self.prompt_function(self, expr))
        if isinstance(self, Patcher):
            self.declare_patch(value)
        return value


__default_features__ = None
