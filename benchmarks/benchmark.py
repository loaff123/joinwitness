"""Reproducible synthetic cardinality benchmarks; no materialized comparison at scale.

Run from the project root: python benchmarks/benchmark.py --rows 100000 --keys 100
Peak RSS is the entire worker-process high-water mark, not allocation delta.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def worker(rows: int, keys: int, money: bool) -> dict[str, object]:
    from joinwitness.engine import audit
    from joinwitness.models import AuditConfig

    with tempfile.TemporaryDirectory(prefix='joinwitness-bench-') as folder:
        root = Path(folder)
        left, right = root / 'left.csv', root / 'right.csv'
        for path in (left, right):
            with path.open('w', encoding='utf-8', newline='') as out:
                out.write('id,amount\n')
                for index in range(rows):
                    out.write(f'K{index % keys:09d},1.25\n')
        byte_count = left.stat().st_size + right.stat().st_size
        config = AuditConfig(left, right, ('id',), ('id',), relationship='many-to-many',
                             amount_column='amount' if money else None)
        start = time.perf_counter()
        result = audit(config)
        seconds = time.perf_counter() - start
        quotient, remainder = divmod(rows, keys)
        expected = remainder * (quotient + 1) ** 2 + (keys - remainder) * quotient ** 2
        if result.predicted_rows != expected:
            raise AssertionError(f'{result.predicted_rows} != {expected}')
        peak_mib = None
        try:
            import resource
            raw_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            peak_mib = raw_rss / (1024 * 1024 if sys.platform == 'darwin' else 1024)
        except ImportError:
            pass
        return {
            'rows_per_input': rows, 'distinct_keys_per_input': min(rows, keys),
            'amount_enabled': money, 'total_input_bytes': byte_count,
            'predicted_rows': result.predicted_rows, 'verified_expected_rows': expected,
            'elapsed_seconds': round(seconds, 6),
            'peak_process_rss_mib': None if peak_mib is None else round(peak_mib, 3),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rows', type=int, default=100_000)
    parser.add_argument('--keys', type=int, default=100)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--money', action='store_true')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if min(args.rows, args.keys, args.repeats) <= 0:
        parser.error('rows, keys and repeats must be positive')
    if args.worker:
        print(json.dumps(worker(args.rows, args.keys, args.money)))
        return
    records = []
    for _ in range(args.repeats):
        command = [sys.executable, str(Path(__file__).resolve()), '--worker',
                   '--rows', str(args.rows), '--keys', str(args.keys)]
        if args.money:
            command.append('--money')
        records.append(json.loads(subprocess.check_output(command, text=True)))
    print(json.dumps({
        'python': platform.python_version(), 'os': platform.platform(),
        'machine': platform.machine(), 'logical_cpus_visible': os.cpu_count(),
        'method': 'Fresh process per repeat; generate files before timer; time audit only; warm OS cache possible; RSS includes interpreter/imports; no cross-product materialized.',
        'runs': records,
    }, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
