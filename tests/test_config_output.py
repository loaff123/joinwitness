import json

import pytest

from joinwitness.config import dump_config, load_config
from joinwitness.models import AuditConfig, InputError
from joinwitness.output import write_outputs


def raw_config():
    return {'schema_version': 1, 'left': 'a.csv', 'right': 'b.csv',
            'left_keys': ['id'], 'right_keys': ['id']}


@pytest.mark.parametrize('key,value', [
    ('schema_version', True), ('left_keys', 'id'), ('right_keys', []),
    ('null_values', [None]), ('sample_limit', True), ('max_output_rows', True),
    ('fail_on_expansion', 1), ('fail_on_unmatched', 'false'), ('delimiter', 1),
    ('amount_column', ['amount']), ('left', ''), ('right', 1),
])
def test_config_rejects_wrong_types(tmp_path, key, value):
    data = raw_config()
    data[key] = value
    path = tmp_path / 'config.json'
    path.write_text(json.dumps(data))
    with pytest.raises(InputError):
        load_config(path)


def test_config_rejects_duplicate_json_fields(tmp_path):
    path = tmp_path / 'config.json'
    path.write_text('{"schema_version":1,"schema_version":1}')
    with pytest.raises(InputError, match='Duplicate'):
        load_config(path)


def test_config_roundtrip_all_options(tmp_path):
    expected = AuditConfig(tmp_path / 'a.csv', tmp_path / 'b.csv', ('a', 'b'), ('x', 'y'),
        relationship='one-to-many', join_type='inner', amount_column='fee', delimiter=';',
        null_values=('NULL',), sample_limit=7, max_output_rows=100,
        fail_on_unmatched=True, fail_on_expansion=True)
    path = tmp_path / 'config.json'
    path.write_text(dump_config(expected, path))
    assert load_config(path) == expected


def test_existing_files_unchanged_when_another_output_conflicts(tmp_path):
    first, second = tmp_path / 'first', tmp_path / 'second'
    second.write_text('original')
    with pytest.raises(InputError):
        write_outputs([(first, 'new'), (second, 'replacement')], [], False)
    assert not first.exists()
    assert second.read_text(encoding='utf-8') == 'original'
    assert not list(tmp_path.glob('.joinwitness-*'))


def test_hardlink_input_alias_never_overwritten(tmp_path):
    source = tmp_path / 'source.csv'
    alias = tmp_path / 'alias.html'
    source.write_text('private')
    alias.hardlink_to(source)
    with pytest.raises(InputError, match='aliases'):
        write_outputs([(alias, 'replacement')], [source], True)
    assert source.read_text(encoding='utf-8') == 'private'


def test_symlink_input_alias_never_overwritten(tmp_path):
    source = tmp_path / 'source.csv'
    alias = tmp_path / 'alias.html'
    source.write_text('private')
    try:
        alias.symlink_to(source)
    except OSError:
        pytest.skip('symlinks require extra permission on this platform')
    with pytest.raises(InputError, match='aliases'):
        write_outputs([(alias, 'replacement')], [source], True)
    assert source.read_text(encoding='utf-8') == 'private'


def test_written_file_is_complete_and_no_temporary_files_remain(tmp_path):
    output = tmp_path / 'report.html'
    write_outputs([(output, '完整\nreport')], [], False)
    assert output.read_text(encoding='utf-8') == '完整\nreport'
    write_outputs([(output, 'updated')], [], True)
    assert output.read_text(encoding='utf-8') == 'updated'
    assert not list(tmp_path.glob('.joinwitness-*'))


def test_saved_config_over_symlink_uses_final_config_directory(tmp_path):
    directory = tmp_path / 'a'
    directory.mkdir()
    old_directory = tmp_path / 'b' / 'nested'
    old_directory.mkdir(parents=True)
    previous = old_directory / 'previous.json'
    previous.write_text('{}')
    config_path = directory / 'audit.json'
    try:
        config_path.symlink_to(previous)
    except OSError:
        pytest.skip('symlinks require extra permission on this platform')
    left, right = directory / 'left.csv', directory / 'right.csv'
    left.write_text('id\nx\n')
    right.write_text('id\nx\n')
    config = AuditConfig(left, right, ('id',), ('id',))
    write_outputs([(config_path, dump_config(config, config_path))], [left, right], True)
    assert not config_path.is_symlink()
    loaded = load_config(config_path)
    assert loaded.left.resolve() == left.resolve()
    assert loaded.right.resolve() == right.resolve()
    assert previous.read_text(encoding='utf-8') == '{}'
