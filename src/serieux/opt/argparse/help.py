import inspect
import sys
from dataclasses import MISSING

from ...features.tagset import tag_field
from ...linearize import LinearField, LinearState
from .parse import CliParser, _cli_name


def _type_metavar(tp: type) -> str:
    """Short uppercase metavar for a type; empty string for bool flags."""
    if tp is bool:
        return ""
    if tp is str:
        return "TEXT"
    if tp is int:
        return "INT"
    if tp is float:
        return "FLOAT"
    return tp.__name__.upper()


def _class_doc(cls: type) -> str:
    """Class docstring, or '' for the auto-generated dataclass form."""
    doc = inspect.getdoc(cls) or ""
    # Python auto-generates "ClassName(field: type, ...)" for dataclasses.
    return "" if doc.startswith(cls.__name__ + "(") else doc


def format_help(parser: CliParser, root_type: type, color: bool = None) -> str:
    gs = parser.gs
    prog = parser.prog

    if color is None:
        color = sys.stdout.isatty()

    bold = "\033[1m" if color else ""
    dim = "\033[2m" if color else ""
    green = "\033[32m" if color else ""
    yellow = "\033[33m" if color else ""
    reset = "\033[0m" if color else ""

    c_header = lambda s: f"{bold}{s}{reset}"  # noqa: E731
    c_opt = lambda s: f"{bold}{green}{s}{reset}"  # noqa: E731
    c_meta = lambda s: f"{yellow}{s}{reset}"  # noqa: E731
    c_dim = lambda s: f"{dim}{s}{reset}"  # noqa: E731
    c_prog = lambda s: f"{bold}{s}{reset}"  # noqa: E731

    # ── Build group_field_map: gid → union LinearField ─────────────────────────
    group_field_map: dict[str, LinearField] = {}
    for fld in gs.state:
        for ul in fld.unlock:
            if ul.group.identifier not in group_field_map:
                group_field_map[ul.group.identifier] = ul.group

    # ── Collect branch fields: gid → {cid → [LinearField]} ────────────────────
    latent_by_group: dict[str, dict[int, list[LinearField]]] = {}
    for gid, subgroups in gs._option_groups.items():
        for cid, subgroup in enumerate(subgroups):
            if subgroup.fields:
                latent_by_group.setdefault(gid, {})[cid] = subgroup.fields

    # ── Collect active fields ─────────────────────────────────────────────────
    positionals: list[LinearField] = []
    # parent LinearField → {option-key → [LinearField]}; insertion order = section order
    opt_groups: dict[LinearField, dict[str, list[LinearField]]] = {}
    # gid → {cid → [trigger LinearField]} for union-discriminating option fields
    union_triggers: dict[str, dict[int, list[LinearField]]] = {}

    for fld, initial_state in gs._initial_state.items():
        if initial_state not in (LinearState.AVAILABLE, LinearState.ADVANCE):
            continue
        if fld.positional:
            positionals.append(fld)
            continue
        try:
            names = parser.option_strings(fld)
        except Exception:
            continue
        if not names:
            continue
        key = names[0]
        if fld.unlock:
            gid = fld.unlock[0].group.identifier
            cid = fld.unlock[0].choice_id
            union_triggers.setdefault(gid, {}).setdefault(cid, []).append(fld)
        else:
            parent = fld.parent
            if parent not in opt_groups:
                opt_groups[parent] = {}
            opt_groups[parent].setdefault(key, []).append(fld)

    # ── Entry builders ─────────────────────────────────────────────────────────

    def _entry(fields: list[LinearField]) -> dict:
        names = parser.option_strings(fields[0])
        short = [n for n in names if "." not in n]
        display = sorted(short if short else names, key=lambda n: (n.startswith("--"), n))
        if fields[0].field.serialized_name == tag_field:
            evs = [f.expected_value for f in fields if f.expected_value is not None]
            metavar = "{" + ",".join(evs) + "}" if evs else _type_metavar(fields[0].type)
            # Use the parent field's description (the union field), not the $class tell's doc.
            desc = (fields[0].parent.doc if fields[0].parent else None) or ""
        else:
            metavar = _type_metavar(fields[0].type)
            desc = fields[0].doc or ""
        f0 = fields[0].field
        if not f0.required:
            dflt = f0.default
            if dflt is not MISSING and dflt is not False:
                suffix = f"[default: {dflt}]"
                desc = f"{desc}  {c_dim(suffix)}".lstrip() if desc else c_dim(suffix)
        return {"names": display, "metavar": metavar, "desc": desc}

    def _render_entries(entries: list[dict], indent: str = "  ") -> list[str]:
        if not entries:
            return []
        result_lines = []
        opt_w = max(len(", ".join(e["names"])) for e in entries)
        mv_w = max(len(e["metavar"]) for e in entries)
        for e in entries:
            raw = ", ".join(e["names"])
            mv_pad = f"{e['metavar']:<{mv_w}}" if mv_w else ""
            mv_str = f"  {c_meta(mv_pad)}" if mv_w else ""
            result_lines.append(
                f"{indent}{c_opt(f'{raw:<{opt_w}}')}{mv_str}  {e['desc']}".rstrip()
            )
        return result_lines

    def _pos_display(fld: LinearField) -> str:
        if fld.field.serialized_name == tag_field and fld.parent is not None:
            evs = [
                f.expected_value
                for f in gs.state
                if f.field.serialized_name == tag_field
                and f.parent is fld.parent
                and f.expected_value is not None
            ]
            return ("{" + ",".join(evs) + "}") if evs else "TAG"
        return (fld.field.serialized_name or "ARG").upper()

    # ── Assemble output ────────────────────────────────────────────────────────
    out = []

    # Usage
    seen_pos_d: set[str] = set()
    pos_parts = []
    for fld in positionals:
        d = _pos_display(fld)
        if d not in seen_pos_d:
            seen_pos_d.add(d)
            pos_parts.append(c_meta(d))
    pos_str = (" " + " ".join(pos_parts)) if pos_parts else ""
    out.append(f"{c_header('Usage:')} {c_prog(prog)} {c_dim('[OPTIONS]')}{pos_str}")
    out.append("")

    # Description
    if root_type:
        doc = _class_doc(root_type)
        if doc:
            out.append(doc)
            out.append("")

    # Arguments
    unique_pos: list[tuple[str, LinearField]] = []
    seen_pos_d2: set[str] = set()
    for fld in positionals:
        d = _pos_display(fld)
        if d not in seen_pos_d2:
            seen_pos_d2.add(d)
            unique_pos.append((d, fld))
    if unique_pos:
        out.append(c_header("Arguments:"))
        w = max(len(d) for d, _ in unique_pos)
        for display, fld in unique_pos:
            out.append(f"  {c_meta(f'{display:<{w}}')}  {fld.doc or ''}".rstrip())
        out.append("")

    def _section_label(parent: LinearField) -> str:
        tp = parent.field.type if parent is not None else root_type
        label = parent.doc or getattr(tp, "__name__", "Options")
        return label.rstrip(".")

    def _render_opt_groups(groups):
        for parent, opts_dict in groups:
            entries = [_entry(v) for v in opts_dict.values()]
            if not entries:
                continue
            out.append(c_header(_section_label(parent) + ":"))
            out.extend(_render_entries(entries))
            out.append("")

    def _render_branches(cid_field_map, subgroups):
        multi = len(cid_field_map) > 1
        first = True
        for cid, fields in sorted(cid_field_map.items()):
            if not first:
                out.append("")
            first = False
            branch_type = fields[0].enclosing_type if fields else None
            if multi and branch_type:
                letter = chr(ord("A") + cid)
                branch_doc = _class_doc(branch_type)
                branch_name = getattr(branch_type, "__name__", str(branch_type))
                out.append(f"  [{c_dim(f'Option {letter}')}] {branch_doc or branch_name}")
                indent = "    "
            else:
                indent = "  "
            branch_entries = []
            for fld in fields:
                try:
                    names = parser.option_strings(fld)
                except Exception:
                    continue
                if names:
                    branch_entries.append(_entry([fld]))
            out.extend(_render_entries(branch_entries, indent))

    def _trigger_name(fld: LinearField) -> str:
        names = parser.option_strings(fld)
        short = [n for n in names if "." not in n]
        return (short or names)[0]

    # Separate meta (Control) groups from regular groups
    regular_groups = [
        (p, d) for p, d in opt_groups.items() if p.field.serialized_name != "__control"
    ]
    meta_groups = [(p, d) for p, d in opt_groups.items() if p.field.serialized_name == "__control"]

    # Regular options
    _render_opt_groups(regular_groups)

    # Union sections (option-triggered): summary line + expanded branches
    for gid, cid_map in union_triggers.items():
        group_fld = group_field_map.get(gid)
        label = (group_fld.doc if group_fld and group_fld.doc else None) or _cli_name(
            gid.split(".")[-1]
        )
        out.append(c_header(label.rstrip(".") + ":"))
        # Summary: "--a/--b | --c | --d"
        summary = " | ".join(
            "/".join(_trigger_name(f) for f in cid_map[cid]) for cid in sorted(cid_map)
        )
        out.append(f"  {summary}")
        out.append("")
        # Expanded branches: triggers + latent fields per choice
        subgroups = gs._option_groups.get(gid, [])
        branch_fields = {
            cid: cid_map[cid] + (subgroups[cid].fields if cid < len(subgroups) else [])
            for cid in sorted(cid_map)
        }
        _render_branches(branch_fields, subgroups)
        out.append("")

    # Latent-only sections (positional-triggered unions, old format)
    for gid, cid_map in latent_by_group.items():
        if gid in union_triggers or not cid_map:
            continue
        group_fld = group_field_map.get(gid)
        label = (group_fld.doc if group_fld and group_fld.doc else None) or _cli_name(
            gid.split(".")[-1]
        )
        out.append(c_header(label + ":"))
        _render_branches(cid_map, gs._option_groups.get(gid, []))
        out.append("")

    # Meta-options (Control)
    _render_opt_groups(meta_groups)

    return "\n".join(out).rstrip()
