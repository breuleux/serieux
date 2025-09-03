# Serieux documentation

[Repository](https://github.com/breuleux/serieux)

## Install

Install Serieux with `pip install` or `uv add`:

```bash
pip install serieux
```

### File format support

Serieux natively supports loading and dumping data from/to JSON files and loading from TOML files. For YAML support, install `pyyaml`:

```bash
pip install pyyaml
```

Note that for the time being, YAML is the only filetype for which Serieux implements location tracking and patching. Loading data as YAML will therefore enable better errors (note that JSON is valid YAML).

For faster JSON processing, I recommend installing `msgspec`. Here's a list of all packages recognized by Serieux:

* **JSON**: `msgspec`, `orjson`, `ujson` (built-in `json` module as a last resort)
* **YAML**: `pyyaml`
* **TOML**: `toml`, `tomli`, `tomli-w` (for writing) (built-in `tomllib` as a last resort)
