"""test_validators_parity.py — Parité comportementale des 2 validateurs FEAT.

Audit M5 (2026-06-11). Le framework a DEUX validateurs de FEAT qui ne
partagent aucun code (interdiction D4 d'importer sdd_lib/sdd_scripts depuis
sdd_reverse — l'unification par import est donc impossible BY DESIGN) :

  - forward : `sdd_scripts/validate_readiness.py` (/feat-validate)
  - reverse : `sdd_reverse_scripts/validate_reverse_feat.py` (+ le contrat
    `sdd_reverse/feat_structure_spec.py`)

Ce fichier était PROMIS par le docstring de feat_structure_spec.py mais
n'existait pas. Il pinne :

  §1 CONTRAT PARTAGÉ — les deux validateurs doivent voir la même chose sur
     la forme canonique `- SFD-1: ...` : mêmes IDs extraits, doublons
     rejetés des deux côtés, section manquante détectée des deux côtés.
     (Bug historique corrigé ici : le reverse matchait `^**SFD-1**` sans
     tiret → /feat-validate voyait les FEATs reverse comme « vides » et
     sautait silencieusement toute la traçabilité.)

  §2 ASYMÉTRIES ASSUMÉES — pinnées explicitement pour que toute
     convergence/divergence future soit un choix conscient (le test casse) :
     GWT + evidence/confidence par item = reverse-only ; couverture US,
     stack, mockups = forward-only ; gaps d'IDs = WARN forward / tolérés
     reverse (items rejetés pour evidence cassée laissent des trous).
"""
from __future__ import annotations

import pytest

from sdd_reverse.feat_structure_spec import (
    ID_PATTERNS,
    REQUIRED_SECTIONS,
    ids_are_stable,
    section_order_violations,
)
# alias : sans lui pytest collecterait `test_id_sequence` comme un test
from sdd_scripts.validate_readiness import get_all_ids
from sdd_scripts.validate_readiness import test_id_sequence as _fwd_id_sequence

pytestmark = pytest.mark.smoke

# Forme CANONIQUE framework-wide (templates/feat.template.md, prescrite au
# composer reverse 3c depuis l'audit M5).
_CANONICAL_BODY = """## Actors

- Utilisateur

## Functional Needs

- SFD-1: Permettre la connexion <!-- evidence: Login.aspx.cs:34-45 --> <!-- confidence: high -->
- SFD-2: Permettre la déconnexion <!-- evidence: Logout.aspx.cs:10-12 --> <!-- confidence: high -->

## Functional Deliverables

- FD-1: Écran de connexion <!-- evidence: Login.aspx:1-40 --> <!-- confidence: high -->

## Business Rules

- BR-1: Le mot de passe est comparé en hash <!-- evidence: DataAccess.cs:32 --> <!-- confidence: high -->

## Acceptance Criteria

- AC-1: Given credentials valides, when soumission, then session créée. <!-- evidence: Login.aspx.cs:40-45 --> <!-- confidence: high -->
- AC-2: Given credentials invalides, when soumission, then erreur affichée. <!-- evidence: Login.aspx.cs:47-50 --> <!-- confidence: high -->

## Project Config

(Tech Lead Phase 5)
"""

_SECTIONS = [
    ("SFD", "Functional Needs", "## Functional Needs"),
    ("FD", "Functional Deliverables", "## Functional Deliverables"),
    ("BR", "Business Rules", "## Business Rules"),
    ("AC", "Acceptance Criteria", "## Acceptance Criteria"),
]


# ---------------------------------------------------------------------------
# §1 — Contrat partagé
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("prefix,fwd_heading,rev_section", _SECTIONS)
def test_canonical_form_seen_identically(prefix, fwd_heading, rev_section):
    """Forme canonique `- ID: ...` : mêmes IDs extraits des deux côtés."""
    fwd_ids = get_all_ids(_CANONICAL_BODY, prefix, fwd_heading)
    rev_nums = [
        int(m.group(1))
        for m in ID_PATTERNS[rev_section].finditer(_CANONICAL_BODY)
    ]
    assert fwd_ids, (
        f"forward aveugle sur la forme canonique pour {prefix} — "
        f"régression validate_readiness"
    )
    assert [f"{prefix}-{n}" for n in rev_nums] == fwd_ids, (
        f"DRIFT M5 : reverse extrait {rev_nums}, forward extrait {fwd_ids} "
        f"pour {rev_section} — les deux validateurs ne voient plus la même FEAT"
    )


def test_duplicate_ids_rejected_both_sides():
    body = _CANONICAL_BODY.replace(
        "- SFD-2: Permettre la déconnexion",
        "- SFD-1: Permettre la déconnexion",
    )
    fwd = _fwd_id_sequence(body, "SFD", "Functional Needs")
    assert fwd["duplicates"] == [1], "forward doit rejeter les doublons"
    ok, msg = ids_are_stable(body, "## Functional Needs")
    assert not ok and "Duplicate" in msg, (
        "reverse doit rejeter les doublons (parité M5 — historiquement toléré)"
    )


def test_missing_section_detected_both_sides():
    body = _CANONICAL_BODY.replace(
        "## Business Rules\n\n- BR-1: Le mot de passe est comparé en hash "
        "<!-- evidence: DataAccess.cs:32 --> <!-- confidence: high -->\n\n",
        "",
    )
    fwd = _fwd_id_sequence(body, "BR", "Business Rules")
    assert fwd.get("skipped"), "forward doit voir la section absente"
    rev_errors = section_order_violations(body)
    assert any("## Business Rules" in e for e in rev_errors), (
        "reverse doit voir la section absente"
    )


def test_bold_form_still_accepted_by_reverse():
    """Compat : les FEATs reverse historiques (forme `**SFD-1**`) restent lisibles."""
    body = _CANONICAL_BODY.replace("- SFD-1:", "**SFD-1**:").replace("- SFD-2:", "**SFD-2**:")
    rev_nums = [int(m.group(1)) for m in ID_PATTERNS["## Functional Needs"].finditer(body)]
    assert rev_nums == [1, 2]


# ---------------------------------------------------------------------------
# §2 — Asymétries assumées (toute évolution = casser ce test = choix conscient)
# ---------------------------------------------------------------------------

def test_asymmetry_gaps_tolerated_reverse_warned_forward():
    """Trous d'IDs : WARN forward (numérotation discontinue), tolérés reverse
    (un item rejeté pour evidence cassée laisse un trou légitime)."""
    body = _CANONICAL_BODY.replace(
        "- SFD-2: Permettre la déconnexion",
        "- SFD-3: Permettre la déconnexion",
    )
    fwd = _fwd_id_sequence(body, "SFD", "Functional Needs")
    assert fwd["missing"] == [2], "forward signale le trou (WARN)"
    ok, _ = ids_are_stable(body, "## Functional Needs")
    assert ok, "reverse tolère le trou (item rejeté = trou légitime)"


def test_asymmetry_reverse_only_sections():
    """`## Actors` + `## Project Config` requis reverse-only ; le forward ne
    les valide pas structurellement (il valide stack.md / US à la place)."""
    assert "## Actors" in REQUIRED_SECTIONS
    assert "## Project Config" in REQUIRED_SECTIONS
    # Forward : l'asymétrie est désormais lue dans la table déclarative
    # `validate_readiness.FEAT_ID_SECTIONS` plutôt que dans le texte source
    # de main() — le pin survit à un refactor sans perdre son rôle.
    #
    # Audit 2026-09-01 : `## Acceptance Criteria` est devenue une section
    # OBLIGATOIRE. Elle etait optionnelle des deux cotes, si bien qu'une FEAT
    # sans un seul AC sortait en GO et que la gate spec-compliance post-dev
    # verifiait ensuite l'ensemble vide et rendait GREEN. Sa COUVERTURE par
    # les US reste non bloquante : un AC non cite est un defaut de
    # tracabilite, pas une FEAT invalide — d'ou deux drapeaux distincts.
    from sdd_scripts import validate_readiness as vr
    sections_requises = {
        section for _p, section, obligatoire, _cov in vr.FEAT_ID_SECTIONS if obligatoire
    }
    couverture_bloquante = {
        section for _p, section, _obl, bloquante in vr.FEAT_ID_SECTIONS if bloquante
    }
    assert sections_requises == {
        "Functional Needs", "Functional Deliverables", "Acceptance Criteria",
    }, "si le forward rend BR requise, mettre à jour cette asymétrie pinnée"
    assert couverture_bloquante == {"Functional Needs", "Functional Deliverables"}, (
        "si la couverture BR/AC devient bloquante, mettre à jour cette asymétrie pinnée"
    )


def test_asymmetry_gwt_and_evidence_are_reverse_only():
    """GWT structurel + evidence par item : enforced uniquement côté reverse
    (le forward délègue le GWT à l'agent po / revue humaine). Pinné pour que
    l'ajout d'un check GWT forward déclenche une mise à jour consciente ici."""
    import inspect
    from sdd_scripts import validate_readiness as vr
    src = inspect.getsource(vr)
    assert "Given" not in src, (
        "validate_readiness valide désormais le GWT — asymétrie M5 résolue ? "
        "Mettre à jour test_validators_parity §2 et feat_structure_spec docstring."
    )
    assert "evidence:" not in src, (
        "validate_readiness lit désormais les commentaires evidence — "
        "mettre à jour l'asymétrie pinnée."
    )
