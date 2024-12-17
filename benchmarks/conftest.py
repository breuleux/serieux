from collections import defaultdict

import pytest


@pytest.mark.hookwrapper
def pytest_benchmark_group_stats(config, benchmarks, group_by):
    outcome = yield
    results = defaultdict(list)
    for bench in benchmarks:
        iface = bench["params"]["interface"].__name__
        group = bench["name"].replace(iface, "").replace(",]", "]").replace("[]", "")
        results[group].append(bench)
    outcome.force_result(results.items())
