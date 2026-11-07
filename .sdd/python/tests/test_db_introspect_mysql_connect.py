"""_connect_mysql — kwargs filtrés + TypeError classé (audit 2026-11-07).

Driver MySQL simulé via sys.modules (aucun driver réel, aucune base).
"""
from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sdd_reverse import db_introspect  # noqa: E402
from sdd_reverse.db_introspect import ReverseDbError, _connect_mysql  # noqa: E402


class _Cursor:
    def execute(self, _sql):
        return None


class _Conn:
    def cursor(self):
        return _Cursor()


def _fake_driver(connect):
    connector = types.ModuleType("mysql.connector")
    connector.connect = connect
    pkg = types.ModuleType("mysql")
    pkg.connector = connector
    return {"mysql": pkg, "mysql.connector": connector}


def test_unknown_keys_are_filtered_and_aliases_mapped(capsys):
    seen = {}

    def connect(host=None, port=None, user=None, password=None, database=None, connect_timeout=None):
        seen.update(host=host, port=port, user=user, password=password,
                    database=database, connect_timeout=connect_timeout)
        return _Conn()

    with mock.patch.dict(sys.modules, _fake_driver(connect)):
        _connect_mysql("host=h;port=3307;db=App;user=u;password=s3cret;sslmode=require;Encrypt=yes")
    assert seen == {"host": "h", "port": 3307, "user": "u", "password": "s3cret",
                    "database": "App", "connect_timeout": 10}
    err = capsys.readouterr().err
    assert "sslmode" in err and "Encrypt" in err and "s3cret" not in err


def test_driver_typeerror_is_classified_connect_failed():
    def connect(**_kw):
        raise TypeError("connect() got an unexpected keyword argument 'database'")

    with mock.patch.dict(sys.modules, _fake_driver(connect)):
        with pytest.raises(ReverseDbError) as ei:
            _connect_mysql("host=h;database=App;user=u;password=pw")
    assert ei.value.error_class == "[REVERSE_DB_CONNECT_FAILED]"
    assert "pw" not in str(ei.value).replace("password", "")


def test_network_error_still_unreachable():
    def connect(**_kw):
        raise RuntimeError("Can't connect to MySQL server on 'h'")

    with mock.patch.dict(sys.modules, _fake_driver(connect)):
        with pytest.raises(ReverseDbError) as ei:
            _connect_mysql("host=h;database=App")
    assert ei.value.error_class == "[REVERSE_DB_UNREACHABLE]"
