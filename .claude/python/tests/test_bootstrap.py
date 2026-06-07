"""Tests for bootstrap.py — SDD_Pro project scaffold.

Strategy : import bootstrap.py as a module and test the pure functions
(combo definitions, validation, template rendering) without going through
interactive prompts. The CLI flow is covered by a single subprocess test
using stdin to simulate user input on a tmp repo.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))


def _load_bootstrap():
    """Import bootstrap.py from the repo root (not on sys.path by default)."""
    bootstrap_path = _REPO / "bootstrap.py"
    spec = importlib.util.spec_from_file_location("bootstrap", bootstrap_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bootstrap = _load_bootstrap()


# ============================================================================
# Combo catalog
# ============================================================================

class TestCombos(unittest.TestCase):

    def test_two_validated_combos_present(self):
        self.assertIn("c1", bootstrap.COMBOS)
        self.assertIn("c2", bootstrap.COMBOS)

    def test_c1_is_dotnet_react(self):
        c1 = bootstrap.COMBOS["c1"]
        self.assertEqual(c1["backend"], "dotnet-minimalapi")
        self.assertEqual(c1["frontend"], "react")
        self.assertEqual(c1["ui"], "shadcn")
        self.assertIn("dotnet-xunit", c1["qa"])

    def test_c2_is_kotlin_react(self):
        c2 = bootstrap.COMBOS["c2"]
        self.assertEqual(c2["backend"], "kotlin-spring-boot")
        self.assertEqual(c2["frontend"], "react")
        self.assertIn("kotlin-junit", c2["qa"])

    def test_all_combos_have_required_fields(self):
        required = {"label", "backend", "frontend", "ui", "qa", "auth",
                    "archi", "lib_strategy", "backend_port", "frontend_port"}
        for name, combo in bootstrap.COMBOS.items():
            self.assertTrue(required.issubset(combo.keys()),
                            f"combo {name} missing fields: {required - combo.keys()}")

    def test_combo_stacks_exist_on_disk(self):
        """Each declared stack must have a corresponding .md in .claude/stacks/."""
        for name, combo in bootstrap.COMBOS.items():
            backend_md = _REPO / ".claude" / "stacks" / "backend" / f"{combo['backend']}.md"
            frontend_md = _REPO / ".claude" / "stacks" / "frontend" / f"{combo['frontend']}.md"
            ui_md = _REPO / ".claude" / "stacks" / "ui" / f"{combo['ui']}.md"
            archi_md = _REPO / ".claude" / "stacks" / "archi" / f"{combo['archi']}.md"
            for path in (backend_md, frontend_md, ui_md, archi_md):
                self.assertTrue(path.is_file(),
                                f"combo {name} references missing stack {path}")
            for qa in combo["qa"]:
                qa_md = _REPO / ".claude" / "stacks" / "qa" / f"{qa}.md"
                self.assertTrue(qa_md.is_file(),
                                f"combo {name} references missing QA stack {qa_md}")


# ============================================================================
# Validation helpers
# ============================================================================

class TestValidateAppName(unittest.TestCase):

    def test_pascalcase_ok(self):
        for name in ("MyApp", "EcommerceApi", "Auth", "X1"):
            self.assertIsNone(bootstrap._validate_app_name(name),
                              f"{name!r} should be valid")

    def test_lowercase_rejected(self):
        self.assertIn("PascalCase", bootstrap._validate_app_name("myapp"))

    def test_space_rejected(self):
        self.assertIn("PascalCase", bootstrap._validate_app_name("My App"))

    def test_too_long_rejected(self):
        long_name = "A" + "b" * 40
        err = bootstrap._validate_app_name(long_name)
        self.assertIn("too long", err)

    def test_special_chars_rejected(self):
        self.assertIn("PascalCase", bootstrap._validate_app_name("My-App"))
        self.assertIn("PascalCase", bootstrap._validate_app_name("My_App"))


# ============================================================================
# Template rendering
# ============================================================================

class TestRenderStackMd(unittest.TestCase):
    """The render must produce a stack.md ready to be consumed by SDD agents."""

    def _render(self, **overrides):
        info = {
            "app_name": "TestApp",
            "backend_name": "TestBack",
            "db_type": "PostgreSql",
            "auth": "azure-ad",
            "archi": "mvc",
            "backend": "dotnet-minimalapi",
            "frontend": "react",
            "ui": "shadcn",
            "qa": ["dotnet-xunit", "node-vitest"],
            "lib_strategy": "openapi-codegen",
            "backend_port": "5097",
            "frontend_port": "5173",
            "label": "C1",
        }
        info.update(overrides)
        return bootstrap.render_stack_md(info)

    def test_substitutes_app_name(self):
        out = self._render(app_name="MyApp")
        self.assertIn("AppName: MyApp", out)
        self.assertIn("FrontendName: MyApp", out)
        self.assertNotIn("{{AppName}}", out)

    def test_substitutes_backend_name(self):
        out = self._render(backend_name="MyBack")
        self.assertIn("BackendName: MyBack", out)

    def test_substitutes_ports(self):
        out = self._render(frontend_port="3000", backend_port="9000")
        self.assertIn("FrontendLocalPort: 3000", out)
        self.assertIn("BackendLocalPort: 9000", out)

    def test_substitutes_archi(self):
        out = self._render(archi="ddd")
        self.assertIn(".claude/stacks/archi/ddd.md", out)
        self.assertNotIn("{{ArchiPattern}}", out)

    def test_substitutes_active_tech_specs(self):
        out = self._render(backend="kotlin-spring-boot", frontend="vue")
        self.assertIn(".claude/stacks/backend/kotlin-spring-boot.md", out)
        self.assertIn(".claude/stacks/frontend/vue.md", out)

    def test_substitutes_qa_list(self):
        out = self._render(qa=["dotnet-xunit", "node-vitest"])
        self.assertIn(".claude/stacks/qa/dotnet-xunit.md", out)
        self.assertIn(".claude/stacks/qa/node-vitest.md", out)

    def test_azure_ad_block_commented_keys(self):
        # Audit 2026-06-06 — Azure AD keys are commented (Tech Lead must
        # paste real values from Azure portal). No fake `<your-tenant-id>`
        # placeholder that could ship to prod unchanged.
        out = self._render(auth="azure-ad")
        self.assertIn(".claude/stacks/auth/azure-ad.md", out)
        self.assertIn("# - AZ_TENANTID:", out)
        self.assertIn("# - AZ_CLIENTID:", out)
        self.assertIn("paste-tenant-id-from-azure-portal", out)

    def test_auth_local_block_generates_real_jwt_secret(self):
        # Audit 2026-06-06 — JWT secret is a real random nonce (Pattern B),
        # not a placeholder. stack.md is gitignored so this is safe.
        out = self._render(auth="auth-local", app_name="MyApp")
        self.assertIn("AUTH_JWT_SECRET:", out)
        self.assertIn("AUTH_JWT_ISSUER:MyAppBack", out)
        self.assertIn(".claude/stacks/auth/auth-local.md", out)
        # The generated secret must NOT be a placeholder string.
        self.assertNotIn("<replace-with-long-random-secret>", out)
        self.assertNotIn("<replace-with-secret>", out)

    def test_auth_none_does_not_activate_any_profile(self):
        out = self._render(auth="none")
        self.assertNotIn(".claude/stacks/auth/azure-ad.md\n", out)
        self.assertNotIn(".claude/stacks/auth/auth-local.md\n", out)

    def test_database_postgres_includes_port(self):
        out = self._render(db_type="PostgreSql")
        self.assertIn(" - DB_PORT:5432", out)
        self.assertIn("DatabaseType: PostgreSql", out)

    def test_database_sqlserver_uses_1433(self):
        out = self._render(db_type="SqlServer")
        self.assertIn(" - DB_PORT:1433", out)

    def test_database_none_skips_env_lines(self):
        out = self._render(db_type="none")
        self.assertIn("DatabaseType: none", out)
        self.assertNotIn("DB_HOST:127.0.0.1", out)

    def test_no_placeholder_leaks(self):
        """A rendered stack.md must not contain any remaining {{...}} token."""
        for combo_name, combo in bootstrap.COMBOS.items():
            out = self._render(**combo,
                               app_name="TestApp",
                               backend_name="TestBack",
                               db_type="PostgreSql")
            remaining = [tok for tok in out.split() if "{{" in tok and "}}" in tok]
            self.assertEqual(remaining, [],
                             f"combo {combo_name} leaks placeholders: {remaining}")


# ============================================================================
# Detection helpers
# ============================================================================

class TestDetection(unittest.TestCase):
    """detect_existing_project + detect_stack_md must respect the workspace state."""

    def test_constants_point_under_repo_root(self):
        for path in (bootstrap.STACK_TEMPLATE, bootstrap.STACK_TARGET,
                     bootstrap.FEATS_DIR, bootstrap.UI_DIR,
                     bootstrap.PYTHON_DIR, bootstrap.CONSOLE_DIR):
            self.assertTrue(
                str(path).startswith(str(bootstrap.REPO_ROOT)),
                f"{path} should be under REPO_ROOT={bootstrap.REPO_ROOT}",
            )


# ============================================================================
# CLI : dry-run on real repo
# ============================================================================

class TestNonValidatedDetection(unittest.TestCase):
    """Audit CTO 2026-06-07 — bootstrap.py previously hardcoded
    `_EXPERIMENTAL_*` sets that drifted from `combos.json/componentLevels`
    SSoT. Pin the SSoT-derived behavior so the bug doesn't regress."""

    def test_shadcn_is_validated_not_experimental(self):
        """shadcn is 🟢 reference in combos.json — must NOT warn."""
        self.assertFalse(bootstrap._is_non_validated("ui", "shadcn"))

    def test_radzen_blazor_is_validated_not_experimental(self):
        """radzen-blazor is 🟢 reference in combos.json — must NOT warn."""
        self.assertFalse(bootstrap._is_non_validated("ui", "radzen-blazor"))

    def test_node_express_is_validated_not_experimental(self):
        """node-express is `validated` in combos.json — must NOT warn."""
        self.assertFalse(bootstrap._is_non_validated("backend", "node-express"))

    def test_python_fastapi_is_validated_not_experimental(self):
        """python-fastapi is `validated` in combos.json — must NOT warn."""
        self.assertFalse(bootstrap._is_non_validated("backend", "python-fastapi"))

    def test_vue_is_validated_not_experimental(self):
        """vue is `validated` in combos.json — must NOT warn."""
        self.assertFalse(bootstrap._is_non_validated("frontend", "vue"))

    def test_angular_is_validated_not_experimental(self):
        """angular is `validated` in combos.json — must NOT warn."""
        self.assertFalse(bootstrap._is_non_validated("frontend", "angular"))

    def test_vuetify_is_bench_validated_not_experimental(self):
        """vuetify is 🟢 bench-validated in combos.json (Sprint 2 CRIT-11
        closure — bench 2026-06-05 PASS sur C5/C7/C10/C12). Pas de warn."""
        self.assertFalse(bootstrap._is_non_validated("ui", "vuetify"))

    def test_ddd_is_bench_validated_not_experimental(self):
        """ddd is 🟢 bench-validated in combos.json (Sprint 2 CRIT-11
        closure — utilisé dans combo C2 validated). Pas de warn."""
        self.assertFalse(bootstrap._is_non_validated("archi", "ddd"))

    def test_microservice_remains_untested(self):
        """microservice is `untested` in combos.json — must warn."""
        self.assertTrue(bootstrap._is_non_validated("archi", "microservice"))

    def test_mvc_is_validated(self):
        """mvc is `validated` in combos.json — must NOT warn."""
        self.assertFalse(bootstrap._is_non_validated("archi", "mvc"))


class TestCliDryRun(unittest.TestCase):
    """End-to-end check that --dry-run doesn't write anything."""

    def test_dry_run_combo_c1_does_not_modify_stack_md(self):
        """Dry-run must NOT touch the existing stack.md."""
        stack_md = _REPO / "workspace" / "input" / "stack" / "stack.md"
        before = stack_md.read_bytes() if stack_md.is_file() else None

        # Provide all answers via stdin : decline re-init prompt
        # Question 1 : "Continue (will OVERWRITE existing stack.md)? [y/N] : "
        # → 'n' to decline (safe — dry-run still works)
        result = subprocess.run(
            [sys.executable, str(_REPO / "bootstrap.py"),
             "--combo", "c1", "--dry-run", "--skip-install"],
            cwd=_REPO,
            input="n\n",  # decline re-init
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=10,
        )
        # Either exit 1 (user declined) or exit 0 (no existing project)
        self.assertIn(result.returncode, (0, 1), f"unexpected exit {result.returncode}\n{result.stderr}")

        after = stack_md.read_bytes() if stack_md.is_file() else None
        self.assertEqual(before, after,
                         "Dry-run must not modify existing stack.md")


if __name__ == "__main__":
    unittest.main()
