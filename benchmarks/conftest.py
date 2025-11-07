from collections import defaultdict

import pytest


@pytest.hookimpl(hookwrapper=True)
def pytest_benchmark_group_stats(config, benchmarks, group_by):
    outcome = yield
    results = defaultdict(list)
    for bench in benchmarks:
        case = bench["params"]["case"]
        an = case.adapter_name
        group = bench["name"].replace(an, "").replace(",]", "]").replace("[]", "")
        results[group].append(bench)
    outcome.force_result(results.items())
