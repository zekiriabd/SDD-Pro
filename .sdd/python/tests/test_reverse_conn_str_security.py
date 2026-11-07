"""Sécurité de la connexion db-reverse (audit sécurité 2026-11).

- `--conn-str` refuse toute valeur porteuse d'un mot de passe (argv = historique
  shell + liste des process + transcript) ; `-` lit stdin ; `SDD_DB_CONN` env.
- `compose_connection_string` échappe les valeurs ODBC (`{…}`) et libpq (`'…'`).
- `_harden_session` ne masque plus un refus du moteur.
- `introspect` ROLLBACK la session avant close.
"""
from __future__ import annotations

import io
from types import SimpleNamespace

import pytest

from sdd_reverse import db_introspect as dbi
from sdd_reverse.conn_string import ConnStringError
from sdd_reverse.dialects import get_dialect
from sdd_reverse_scripts.reverse_proc_introspect import CONN_ENV_VAR, resolve_conn_str


# ── --conn-str / SDD_DB_CONN ────────────────────────────────────────────────

@pytest.mark.parametrize("value", [
    "Server=h;Database=d;User ID=u;Password=Fake2002.;",
    "Server=h;Database=d;Uid=u;Pwd=x;",
    "postgresql://u:secret@h:5432/db",
    "jdbc:sqlserver://h;databaseName=d;user=u;password=x",
    "jdbc:postgresql://h/db?user=u&password=x",
    "scott/tiger@db:1521/ORCL",
    "host=h dbname=d user=u password=x",
])
def test_conn_str_with_password_refused(value):
    with pytest.raises(ConnStringError) as exc:
        resolve_conn_str(value, environ={})
    assert CONN_ENV_VAR in str(exc.value)


@pytest.mark.parametrize("value", [
    "Server=h;Database=d;Trusted_Connection=yes;",
    "postgresql://h:5432/db",
    "db:1521/ORCL",
])
def test_conn_str_without_password_accepted(value):
    assert resolve_conn_str(value, environ={}) == value


def test_conn_str_dash_reads_stdin():
    secret = "Server=h;Database=d;User ID=u;Password=Fake2002.;"
    assert resolve_conn_str("-", stdin=io.StringIO(secret + "\n"), environ={}) == secret


def test_conn_str_dash_empty_stdin_refused():
    with pytest.raises(ConnStringError):
        resolve_conn_str("-", stdin=io.StringIO(""), environ={})


def test_env_var_used_when_no_flag():
    env = {CONN_ENV_VAR: "Server=h;Database=d;Password=x;"}
    assert resolve_conn_str(None, environ=env) == env[CONN_ENV_VAR]


def test_nothing_falls_back_to_stack_md():
    assert resolve_conn_str(None, environ={}) is None


# ── escaping ────────────────────────────────────────────────────────────────

def _cfg(**kw):
    base = dict(host="dbhost", port="", name="AppDb", user="ro", password="s3cret", db_type="sqlserver")
    base.update(kw)
    return SimpleNamespace(**base)


def test_odbc_password_with_semicolon_is_braced():
    cs = dbi.compose_connection_string(_cfg(password="a;Database=master"), get_dialect("sqlserver"))
    assert "PWD={a;Database=master};" in cs
    assert cs.count("Database=master") == 1  # pas d'attribut injecté hors accolades


def test_odbc_closing_brace_doubled():
    cs = dbi.compose_connection_string(_cfg(password="x}y"), get_dialect("sqlserver"))
    assert "PWD={x}}y}" in cs


def test_odbc_plain_value_unchanged():
    cs = dbi.compose_connection_string(_cfg(), get_dialect("sqlserver"))
    assert "PWD=s3cret;" in cs


def test_libpq_value_with_space_quoted():
    cs = dbi.compose_connection_string(_cfg(password="a b'c"), get_dialect("postgresql"))
    assert "password='a b\\'c'" in cs


def test_mysql_semicolon_refused():
    with pytest.raises(dbi.ReverseDbError):
        dbi.compose_connection_string(_cfg(password="a;b"), get_dialect("mysql"))


# ── session hardening / rollback ────────────────────────────────────────────

class _BoomCursor:
    def execute(self, _sql):
        raise RuntimeError("not supported")


class _Conn:
    def __init__(self):
        self.rolled_back = False
        self.closed = False

    def cursor(self):
        return _BoomCursor()

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def test_harden_session_refusal_is_warned(capsys):
    dbi._harden_session(_Conn(), "SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED")
    assert "session pragma refused" in capsys.readouterr().err


def test_introspect_rolls_back_before_close(monkeypatch, tmp_path):
    conn = _Conn()
    monkeypatch.setattr(dbi, "connect", lambda *_a, **_k: conn)

    def _boom(*_a, **_k):
        raise RuntimeError("stop after connect")

    monkeypatch.setattr(dbi, "fetch_rows", _boom)
    with pytest.raises(RuntimeError):
        dbi.introspect(_cfg(), tmp_path, with_schema=False)
    assert conn.rolled_back and conn.closed
