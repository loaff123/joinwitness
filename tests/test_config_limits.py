import json

import pytest

from joinwitness.config import load_config
from joinwitness.models import InputError


def test_config_path_nul_rejected_as_input_error(tmp_path):
    path = tmp_path / 'config.json'
    path.write_text(json.dumps({'schema_version': 1, 'left': 'evil\u0000.csv', 'right': 'r.csv',
                                'left_keys': ['id'], 'right_keys': ['id']}))
    with pytest.raises(InputError, match='path'):
        load_config(path)


def test_config_size_limit(tmp_path):
    path = tmp_path / 'config.json'
    path.write_bytes(b' ' * (1_048_576 + 1))
    with pytest.raises(InputError, match='1 MiB'):
        load_config(path)


def test_deeply_nested_json_is_controlled_input_error(tmp_path):
    path = tmp_path / 'config.json'
    path.write_text('[' * 10_000 + '0' + ']' * 10_000)
    with pytest.raises(InputError, match='JSON'):
        load_config(path)


def test_json_integer_beyond_parser_limit_is_controlled_input_error(tmp_path):
    path = tmp_path / 'config.json'
    path.write_text('{"schema_version":' + '9' * 10_000 + '}')
    with pytest.raises(InputError):
        load_config(path)
