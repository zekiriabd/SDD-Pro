# /sdd-profile — Gestion des profiles team config (v6.7.2)

> ⚠️ **Commande interne v7.0.0** — invocation manuelle (gouvernance team config, wrapper `manage_profile.py`).
> Pas d'usage pipeline ; outil ops dédié.

Wrapper autour de `python .claude/python/sdd_scripts/manage_profile.py`.
Permet d'exporter/importer/lister les profiles `~/.sdd/profiles/{name}.yml`,
qui sont des snapshots de `~/.sdd/config.team.yml` (le niveau team du
layered config v6.7.1).

**Usage :**
- `/sdd-profile export <name>` — sauve la team config actuelle comme profile
- `/sdd-profile export <name> --force` — overwrite un profile existant
- `/sdd-profile import <name>` — charge un profile (backup auto de l'actuel en `.bak`)
- `/sdd-profile list` — liste tous les profiles + active team config
- `/sdd-profile show <name>` — affiche le contenu d'un profile
- `/sdd-profile delete <name>` — supprime un profile

**Garanties** :
- Aucune modification de `workspace/input/stack/stack.md` (per-project)
- Aucune modification du moteur SDD_Pro
- N'a un effet que sur **futures exécutions** (la config layered est lue à chaque commande)
- Backup automatique avant overwrite (`.bak`)

---

## STEP 1 — Dispatch

Invoquer directement le script Python :

```bash
python .claude/python/sdd_scripts/manage_profile.py {subcommand} {args}
```

Tous les arguments sont passés tels quels. Le script retourne :
- exit 0 : succès, output sur stdout
- exit 1 : I/O error (profile not found, team config absent)
- exit 2 : misuse (invalid name, profile exists sans --force)

---

## STEP 2 — Exemple workflow

**Définir une policy stricte pour une équipe sécurité** :
```powershell
# 1. Configurer ~/.sdd/config.team.yml manuellement
# Ex. CoverageMin: 90, SecurityFailOn: critical, SpecComplianceMode: full

# 2. Sauver comme profile
/sdd-profile export strict-prod

# 3. Lister
/sdd-profile list
# Output:
#   - strict-prod
#   - dev-only
#   Active team config: ~/.sdd/config.team.yml

# 4. Sur un autre projet, basculer en mode dev
/sdd-profile import dev-only
# ✓ profile 'dev-only' loaded → ~/.sdd/config.team.yml
# ↻ existing team config backed up → ~/.sdd/config.team.yml.bak
```

---

## STEP 3 — Anti-derive

- Cette commande **ne modifie jamais** :
  - `workspace/input/stack/stack.md` (ni les autres workspace/)
  - `.claude/config.base.yml`
  - Le code de prod, FEATs, US, rapports
- Outputs uniquement :
  - `~/.sdd/profiles/{name}.yml` (create/overwrite/delete)
  - `~/.sdd/config.team.yml` (overwrite à l'import, avec backup `.bak`)
- Idempotente : re-exporter avec `--force` overwrite proprement
- Hors network, hors LLM (Python pur)

---

## STEP 4 — Variables d'environnement (test/CI)

| Var | Sens | Défaut |
|---|---|---|
| `$SDD_PROFILES_DIR` | Override du dossier des profiles | `~/.sdd/profiles/` |
| `$SDD_TEAM_CONFIG` | Override du path team.yml | `~/.sdd/config.team.yml` |

Utile pour CI/CD ou environnements multi-utilisateurs.

---

## STEP 5 — Format des profiles

Les profiles sont des fichiers YAML plats (subset minimal — pas
d'imbrication). Exemple :

```yaml
# strict-prod profile
CoverageMin: 90
SecurityFailOn: critical
SpecComplianceMode: full
SpecComplianceFailOn: serious
CodeReviewMode: full
CodeReviewFailOn: serious
ArchReviewMode: full
ArchReviewFailOn: serious
AcceptanceGate: strict
```
> ⚠️ `A11yFailOn`/`PerfMode`/`PerfFailOn` retirés v7.0.0 (agents
> `accessibility-auditor`/`performance-auditor` supprimés). Remplacement :
> ingest CI déterministe v7.2.0 (`ingest_axe.py`, `ingest_lighthouse.py`).

Validation :
- Le profile doit être valide selon le schéma layered config (parseur
  `sdd_lib/layered_config._parse_yaml_minimal`)
- Le contenu est **non-validé** au moment de l'export/import (validation
  au prochain `read_layered_config()` d'une command SDD)
- Si un profile est invalide, la `read_layered_config()` produira un
  ERROR `[CONFIG_*]` clair → le Tech Lead édite le profile manuellement

---

## STEP 6 — Limitations connues v6.7.2

- Pas de mécanisme de versionning des profiles (git de `~/.sdd/` recommandé)
- Pas de partage cloud (profiles locaux uniquement, sync manuel par le Tech Lead)
- Pas de validation au moment de l'import (validation lazy au prochain read)
- Profile name limité à `[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}` (regex)
