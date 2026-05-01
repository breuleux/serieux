import inspect
import sys

from serieux.linearize import LinearField, LinearState

from .parse import GroupState, _cli_name, _option_strings


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


def format_help(gs: GroupState, prog: str, root_type: type, color: bool = None) -> str:
    from dataclasses import MISSING

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

    def _is_control(fld: LinearField) -> bool:
        return any(isinstance(s, str) and s.startswith("__control") for s in fld.signature)

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
            branch_fields = [f for f in subgroup.fields if not _is_control(f)]
            if branch_fields:
                latent_by_group.setdefault(gid, {})[cid] = branch_fields

    # ── Collect active fields ──────────────────────────────────────────────────
    positionals: list[LinearField] = []
    active_opts: dict[str, list[LinearField]] = {}
    ctrl_opts: dict[str, list[LinearField]] = {}

    for fld, fs in gs.state.items():
        if fs.state not in (LinearState.AVAILABLE, LinearState.ADVANCE):
            continue
        if fld.positional:
            positionals.append(fld)
            continue
        try:
            primary, aliases = _option_strings(fld)
        except Exception:
            continue
        if not primary:
            continue
        key = primary[0]
        if _is_control(fld):
            ctrl_opts.setdefault(key, []).append(fld)
        else:
            active_opts.setdefault(key, []).append(fld)

    # ── Entry builders ─────────────────────────────────────────────────────────

    def _opt_s(name: str) -> str:
        return f"-{name}" if len(name) == 1 else f"--{name}"

    def _entry(fields: list[LinearField]) -> dict:
        primary, aliases = _option_strings(fields[0])
        names = primary + aliases
        short = [n for n in names if "." not in n]
        display = sorted(short if short else names, key=lambda n: (len(n) > 1, n))
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
        opt_w = max(len(", ".join(_opt_s(n) for n in e["names"])) for e in entries)
        mv_w = max(len(e["metavar"]) for e in entries)
        for e in entries:
            raw = ", ".join(_opt_s(n) for n in e["names"])
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

    # Options
    opt_entries = [_entry(v) for v in active_opts.values()]
    if opt_entries:
        out.append(c_header("Options:"))
        out.extend(_render_entries(opt_entries))
        out.append("")

    # Union branches
    for gid, cid_map in latent_by_group.items():
        if not cid_map:
            continue
        group_fld = group_field_map.get(gid)
        label = (group_fld.doc if group_fld and group_fld.doc else None) or _cli_name(
            gid.split(".")[-1]
        )
        out.append(c_header(label + ":"))
        subgroups = gs._option_groups.get(gid, [])
        multi = len(cid_map) > 1
        first = True
        for cid, fields in sorted(cid_map.items()):
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
                    primary, _ = _option_strings(fld)
                except Exception:
                    continue
                if primary:
                    branch_entries.append(_entry([fld]))
            out.extend(_render_entries(branch_entries, indent))
        out.append("")

    # Global options
    ctrl_entries = [_entry(v) for v in ctrl_opts.values()]
    if ctrl_entries:
        out.append(c_header("Global options:"))
        out.extend(_render_entries(ctrl_entries))

    return "\n".join(out).rstrip()
