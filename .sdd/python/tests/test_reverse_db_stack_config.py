"""Reading the DB configuration from `stack.md` + environment variables.

That is the CANONICAL path of the DB-reverse: `## Active Database` holds the
parameters, with `${VAR}` placeholders resolved from a `.env` file and from the
real environment (which always wins). Confirmed with the Tech Lead 2026-08-25.

Audit 2026-08-25 found a real defect on that path: the `.env` search was
relative to `Path.cwd()` ONLY, so running from a subdirectory, from a hook, from
a CI step with its own working directory, or with an absolute `--stack` path made
the loader miss the file and fail with "references unset environment variable(s)"
— actively misleading, since the variables were set in a file it never opened.
The search is now anchored on stack.md's own location.

The connection-string parser is a strictly OPTIONAL fallback: it only fires when
a `DB_CONNECTION_STRING`-style key is present, and the decomposed keys always
win, so the canonical path is never altered.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_reverse.stack_db_config import StackConfigError, read_db_config  # noqa: E402

_STACK = """\
# stack

## Active Database

- DatabaseType: SqlServer
- DB_HOST: ${SQL_HOST}
- DB_PORT: ${SQL_PORT}
- DB_NAME: ${SQL_DB}
- DB_USER: ${SQL_USER}
- DB_PASSWORD: ${SQL_PWD}

## Active Tech Specs
"""

_DOTENV = """\
# provisioned by the DBA, gitignored
SQL_HOST=sqlprd01.corp.local
SQL_PORT=1433
SQL_DB=Facturation
SQL_USER=svc_reverse
SQL_PWD=Sup3rS3cret!
"""


@pytest.fixture()
def project(tmp_path, monkeypatch):
    """A repo laid out like a real one: stack.md under workspace/stack/, .env at root."""
    (tmp_path / "workspace" / "stack").mkdir(parents=True)
    (tmp_path / "workspace" / "stack" / "stack.md").write_text(_STACK, encoding="utf-8")
    (tmp_path / ".env").write_text(_DOTENV, encoding="utf-8")
    (tmp_path / "deep" / "nested").mkdir(parents=True)
    for var in ("SQL_HOST", "SQL_PORT", "SQL_DB", "SQL_USER", "SQL_PWD"):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


def _assert_resolved(cfg):
    assert cfg.db_type == "SqlServer"
    assert cfg.host == "sqlprd01.corp.local"
    assert cfg.port == "1433"
    assert cfg.name == "Facturation"
    assert cfg.user == "svc_reverse"
    assert cfg.password == "Sup3rS3cret!"


class TestDotenvAnchoring:
    """The .env must be found regardless of the working directory."""

    def test_from_repo_root(self, project, monkeypatch):
        monkeypatch.chdir(project)
        _assert_resolved(read_db_config("workspace/stack/stack.md"))

    def test_from_a_subdirectory_with_a_relative_path(self, project, monkeypatch):
        """This used to fail with a misleading 'unset environment variable(s)'."""
        monkeypatch.chdir(project / "deep" / "nested")
        _assert_resolved(read_db_config("../../workspace/stack/stack.md"))

    def test_with_an_absolute_path_from_an_unrelated_cwd(self, project, monkeypatch, tmp_path):
        elsewhere = tmp_path.parent
        monkeypatch.chdir(elsewhere)
        _assert_resolved(read_db_config(project / "workspace" / "stack" / "stack.md"))

    def test_dotenv_next_to_stack_md_is_also_found(self, project, monkeypatch):
        (project / ".env").unlink()
        (project / "workspace" / "stack" / ".env").write_text(_DOTENV, encoding="utf-8")
        monkeypatch.chdir(project / "deep")
        _assert_resolved(read_db_config(project / "workspace" / "stack" / "stack.md"))

    def test_most_specific_dotenv_wins(self, project, monkeypatch):
        (project / "workspace" / ".env").write_text(
            "SQL_HOST=closer.corp.local\n", encoding="utf-8")
        monkeypatch.chdir(project)
        cfg = read_db_config(project / "workspace" / "stack" / "stack.md")
        assert cfg.host == "closer.corp.local"
        assert cfg.name == "Facturation"        # the rest still comes from root


class TestEnvironmentPrecedence:
    def test_real_environment_overrides_dotenv(self, project, monkeypatch):
        monkeypatch.chdir(project)
        monkeypatch.setenv("SQL_HOST", "sqlqua01.corp.local")
        cfg = read_db_config("workspace/stack/stack.md")
        assert cfg.host == "sqlqua01.corp.local"   # shell wins
        assert cfg.name == "Facturation"           # .env fills the rest

    def test_env_only_no_dotenv_at_all(self, project, monkeypatch):
        (project / ".env").unlink()
        monkeypatch.chdir(project)
        for var, value in (("SQL_HOST", "h"), ("SQL_PORT", "1"), ("SQL_DB", "d"),
                           ("SQL_USER", "u"), ("SQL_PWD", "p")):
            monkeypatch.setenv(var, value)
        cfg = read_db_config("workspace/stack/stack.md")
        assert (cfg.host, cfg.name, cfg.password) == ("h", "d", "p")

    def test_unset_variable_names_where_it_looked(self, project, monkeypatch):
        """A clear error beats a wrong one: list the paths actually searched."""
        (project / ".env").unlink()
        monkeypatch.chdir(project)
        with pytest.raises(StackConfigError) as exc:
            read_db_config("workspace/stack/stack.md")
        msg = str(exc.value)
        assert "SQL_HOST" in msg
        assert "Searched for .env in" in msg

    def test_password_is_never_revealed_by_masked(self, project, monkeypatch):
        monkeypatch.chdir(project)
        masked = read_db_config("workspace/stack/stack.md").masked()
        assert "Sup3rS3cret" not in masked
        assert "password=***" in masked


class TestLiteralValues:
    def test_plain_values_need_no_env_at_all(self, tmp_path, monkeypatch):
        (tmp_path / "workspace" / "stack").mkdir(parents=True)
        (tmp_path / "workspace" / "stack" / "stack.md").write_text(
            "## Active Database\n\n"
            "- DatabaseType: PostgreSQL\n- DB_HOST: db.local\n"
            "- DB_NAME: erp\n- DB_USER: ro\n- DB_PASSWORD: x\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        cfg = read_db_config("workspace/stack/stack.md")
        assert (cfg.db_type, cfg.host, cfg.name) == ("PostgreSQL", "db.local", "erp")


class TestConnectionStringFallback:
    """Optional convenience — must never disturb the canonical path."""

    def _write(self, tmp_path, body):
        (tmp_path / "workspace" / "stack").mkdir(parents=True, exist_ok=True)
        p = tmp_path / "workspace" / "stack" / "stack.md"
        p.write_text("## Active Database\n\n" + body, encoding="utf-8")
        return p

    def test_decomposed_keys_win_over_a_connection_string(self, tmp_path, monkeypatch):
        """stack.md remains the SSoT: an explicit key is a deliberate override."""
        monkeypatch.chdir(tmp_path)
        p = self._write(tmp_path,
            "- DatabaseType: SqlServer\n"
            "- DB_HOST: explicit.corp.local\n"
            "- DB_NAME: Explicit\n"
            "- DB_CONNECTION_STRING: Server=ignored.local;Database=Ignored;User Id=u;Password=p\n")
        cfg = read_db_config(p)
        assert cfg.host == "explicit.corp.local"
        assert cfg.name == "Explicit"

    def test_connection_string_fills_only_the_gaps(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        p = self._write(tmp_path,
            "- DB_CONNECTION_STRING: Server=sqlprd01,1433;Database=Facturation;"
            "User Id=svc;Password=secret\n")
        cfg = read_db_config(p)
        assert (cfg.db_type, cfg.host, cfg.port) == ("sqlserver", "sqlprd01", "1433")
        assert (cfg.name, cfg.user) == ("Facturation", "svc")

    def test_connection_string_supports_env_placeholders_too(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("PG_DSN", "postgresql://ro:pw@pg.local:5432/erp")
        p = self._write(tmp_path, "- DB_CONNECTION_STRING: ${PG_DSN}\n")
        cfg = read_db_config(p)
        assert (cfg.db_type, cfg.host, cfg.name) == ("postgresql", "pg.local", "erp")

    def test_malformed_connection_string_fails_loudly(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        p = self._write(tmp_path, "- DB_CONNECTION_STRING: total-nonsense\n")
        with pytest.raises(StackConfigError):
            read_db_config(p)


class TestConnStringParser:
    """Formats a Tech Lead may paste from a real config file."""

    @pytest.mark.parametrize("raw, engine, host, name", [
        ("Server=sqlprd01,1433;Database=Facturation;User Id=sa;Password=x;",
         "sqlserver", "sqlprd01", "Facturation"),
        ("Data Source=tcp:sqlprd01,1433;Initial Catalog=Facturation;"
         "Integrated Security=True", "sqlserver", "sqlprd01", "Facturation"),
        ("jdbc:sqlserver://sqlprd01:1433;databaseName=Facturation;user=sa",
         "sqlserver", "sqlprd01", "Facturation"),
        ("jdbc:postgresql://pg.local:5432/erp?user=ro&password=pw",
         "postgresql", "pg.local", "erp"),
        ("postgresql://ro:pw@pg.local:5432/erp", "postgresql", "pg.local", "erp"),
        ("host=pg.local port=5432 dbname=erp user=ro password=pw",
         "postgresql", "pg.local", "erp"),
        ("jdbc:oracle:thin:@ora.local:1521/ORCLPDB", "oracle", "ora.local", "ORCLPDB"),
        ("scott/tiger@ora.local:1521/ORCLPDB", "oracle", "ora.local", "ORCLPDB"),
        ("jdbc:mysql://my.local:3306/shop?user=ro", "mysql", "my.local", "shop"),
        ("mysql://ro:pw@my.local:3306/shop", "mysql", "my.local", "shop"),
    ])
    def test_recognised_formats(self, raw, engine, host, name):
        from sdd_reverse.conn_string import parse_connection_string
        p = parse_connection_string(raw, db_type_hint="postgresql")
        assert p.db_type == engine
        assert p.host == host
        assert p.name == name

    def test_password_is_masked_in_diagnostics(self):
        from sdd_reverse.conn_string import parse_connection_string
        p = parse_connection_string(
            "Server=h;Database=d;User Id=u;Password=Sup3rS3cret!")
        assert "Sup3rS3cret" not in p.masked()

    def test_integrated_security_is_understood(self):
        from sdd_reverse.conn_string import parse_connection_string
        p = parse_connection_string(
            "Server=h;Database=d;Trusted_Connection=yes", db_type_hint="sqlserver")
        assert p.trusted is True
        assert not p.password

    def test_engine_may_come_from_the_odbc_driver_token(self):
        from sdd_reverse.conn_string import parse_connection_string
        p = parse_connection_string(
            "DRIVER={ODBC Driver 18 for SQL Server};SERVER=h;DATABASE=d;UID=u;PWD=p")
        assert p.db_type == "sqlserver"

    def test_missing_database_is_refused_not_half_filled(self):
        from sdd_reverse.conn_string import ConnStringError, parse_connection_string
        with pytest.raises(ConnStringError):
            parse_connection_string("Server=h;User Id=u;Password=p",
                                    db_type_hint="sqlserver")

    def test_unknown_engine_without_hint_is_refused(self):
        from sdd_reverse.conn_string import ConnStringError, parse_connection_string
        with pytest.raises(ConnStringError):
            parse_connection_string("Server=h;Database=d")
