from dataclasses import dataclass

from ...linearize import LinearField, LinearState
from .parse import CliParser


@dataclass
class ArgparseFormatter:
    parser: CliParser

    def format_trigger(self, fld: LinearField) -> str:
        """Format a single trigger field as a human-readable prerequisite."""
        if fld.positional:
            if fld.expected_value is not None:
                return repr(fld.expected_value)
            return fld.field.serialized_name.upper() if fld.field.serialized_name else "ARG"
        primary, _ = self.parser.option_strings(fld)
        opt = primary[0] if primary else fld.identifier
        if fld.expected_value is not None:
            return f"{opt}={fld.expected_value!r}"
        return opt

    def explain_unknown_named(self, opt: str) -> str | None:
        """If *opt* matches a LATENT or UNAVAILABLE field, return an explanation string."""
        gs = self.parser.gs
        latent_hints = []
        unavailable_hints = []

        for fld in gs.state:
            fs = gs.state[fld]
            if fld.positional:
                continue
            try:
                primary, aliases = self.parser.option_strings(fld)
            except Exception:
                continue
            if opt not in primary + aliases:
                continue

            if fs.state == LinearState.LATENT:
                triggers = gs.latent_triggers(fld)
                if triggers:
                    prereqs = " or ".join(self.format_trigger(t) for t in triggers)
                    latent_hints.append(f"{opt} requires {prereqs}")
                else:
                    latent_hints.append(f"{opt} is not yet available")
            elif fs.state == LinearState.UNAVAILABLE:
                disabler = gs.disabled_by(fld)
                if disabler is not None:
                    latent_hints.append(f"{opt} was disabled by {self.format_trigger(disabler)}")
                else:
                    unavailable_hints.append(f"{opt} is not available")

        hints = latent_hints + unavailable_hints
        return hints[0] if hints else f"Unknown option: {opt}"
