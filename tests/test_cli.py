"""Integration tests use the real entry point and never mutate fixture inputs."""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def cli(*args: object, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, PYTHONPATH=str(ROOT / 'src'))
    return subprocess.run([sys.executable, '-m', 'joinwitness', *map(str, args)],
                          cwd=cwd or ROOT, env=env, capture_output=True, text=True)


def inputs(tmp_path: Path) -> tuple[Path, Path]:
    left = tmp_path / 'secret-left.csv'
    right = tmp_path / 'secret-right.csv'
    left.write_text('secret_id,private_amount\n001,10.25\n002,-10.25\n', encoding='utf-8')
    right.write_text('secret_id\n001\n001\n002\n002\n', encoding='utf-8')
    return left, right


def test_help_and_version():
    result = cli('--help')
    assert result.returncode == 0, result.stderr
    assert 'audit' in result.stdout and 'demo' in result.stdout
    assert cli('--version').stdout.strip() == 'JoinWitness 0.1.0'


def test_cli_quality_exit_privacy_and_exact_money(tmp_path):
    left, right = inputs(tmp_path)
    original = (left.read_bytes(), right.read_bytes())
    result = cli('audit', left, right, '--left-key', 'secret_id', '--right-key', 'secret_id',
                 '--amount', 'private_amount', cwd=tmp_path)
    assert result.returncode == 1, result.stderr
    data = json.loads((tmp_path / 'report.json').read_text(encoding='utf-8'))
    assert data['predicted_rows'] == 4
    assert data['money']['duplicated_signed_amount'] == '0'
    assert data['money']['duplicated_absolute_amount'] == '20.5'
    public = (tmp_path / 'report.html').read_text(encoding='utf-8') + (tmp_path / 'report.json').read_text(encoding='utf-8')
    for secret in ('secret_id', 'private_amount', 'secret-left', str(tmp_path), '001', '002'):
        assert secret not in public
    assert (left.read_bytes(), right.read_bytes()) == original


def test_save_and_rerun_config_is_portable_and_deterministic(tmp_path):
    left, right = inputs(tmp_path)
    config_path = tmp_path / 'audit.json'
    command = ['audit', left, right, '--left-key', 'secret_id', '--right-key', 'secret_id',
               '--expect', 'many-to-many', '--save-config', config_path]
    assert cli(*command, cwd=tmp_path).returncode == 0
    first = (tmp_path / 'report.json').read_bytes()
    config = json.loads(config_path.read_text(encoding='utf-8'))
    assert config['left'] == 'secret-left.csv'
    rerun = tmp_path / 'rerun'
    rerun.mkdir()
    assert cli('run', config_path, cwd=rerun).returncode == 0
    assert (rerun / 'report.json').read_bytes() == first


def test_refuses_overwrite_and_input_alias_even_with_force(tmp_path):
    left, right = inputs(tmp_path)
    result = cli('audit', left, right, '--left-key', 'secret_id', '--right-key', 'secret_id',
                 '--html', left, '--force', cwd=tmp_path)
    assert result.returncode == 2
    assert left.read_text(encoding='utf-8').startswith('secret_id,private_amount')
    assert not (tmp_path / 'report.json').exists()
    (tmp_path / 'report.html').write_text('keep me')
    result = cli('audit', left, right, '--left-key', 'secret_id', '--right-key', 'secret_id', cwd=tmp_path)
    assert result.returncode == 2
    assert (tmp_path / 'report.html').read_text(encoding='utf-8') == 'keep me'


def test_json_stdout_is_machine_readable(tmp_path):
    left, right = inputs(tmp_path)
    result = cli('audit', left, right, '--left-key', 'secret_id', '--right-key', 'secret_id',
                 '--expect', 'many-to-many', '--json', '-', cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['predicted_rows'] == 4
    assert 'Predicted' in result.stderr


def test_demo_real_computation_and_rerun(tmp_path):
    result = cli('demo', '--output', tmp_path / 'demo')
    assert result.returncode == 0, result.stderr
    data = json.loads((tmp_path / 'demo/report.json').read_text(encoding='utf-8'))
    assert data['left']['rows'] == 4 and data['predicted_rows'] == 8
    assert data['money']['input_total'] == '250'
    assert data['money']['output_total'] == '510'
    assert data['money']['duplicated_absolute_amount'] == '320'
    assert cli('run', tmp_path / 'demo/audit.json', '--html', tmp_path / 'again.html',
               '--json', tmp_path / 'again.json').returncode == 1


def test_bad_config_and_missing_input_return_two_without_traceback(tmp_path):
    config = tmp_path / 'bad.json'
    config.write_text('{"schema_version":1,"left":"x","right":"y","left_keys":["id"],"right_keys":["id"],"samples":1}')
    result = cli('run', config, cwd=tmp_path)
    assert result.returncode == 2 and 'Traceback' not in result.stderr
    assert 'unknown' in result.stderr.lower()
    result = cli('audit', 'missing.csv', 'also-missing.csv', '--left-key', 'id', '--right-key', 'id', cwd=tmp_path)
    assert result.returncode == 2 and 'Traceback' not in result.stderr


def test_output_collision_rejected(tmp_path):
    left, right = inputs(tmp_path)
    result = cli('audit', left, right, '--left-key', 'secret_id', '--right-key', 'secret_id',
                 '--html', tmp_path / 'same', '--json', tmp_path / 'same', cwd=tmp_path)
    assert result.returncode == 2
    assert not (tmp_path / 'same').exists()


def test_symlink_cycle_returns_input_error_without_traceback(tmp_path):
    left, right = inputs(tmp_path)
    a, b = tmp_path / 'cycle-a', tmp_path / 'cycle-b'
    try:
        a.symlink_to(b)
        b.symlink_to(a)
    except OSError:
        import pytest
        pytest.skip('symlinks require extra permission on this platform')
    result = cli('audit', a, right, '--left-key', 'secret_id', '--right-key', 'secret_id', cwd=tmp_path)
    assert result.returncode == 2 and 'Traceback' not in result.stderr
