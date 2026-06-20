# ADRs Index — {ProjectName}

> Auto-généré par `python -m sdd_scripts.index_adrs` (déterministe v7.0.0,
> remplace l'agent `dashboard` Haiku 4.5 retiré).
> Source de vérité : Glob `workspace/output/.sys/.context/adrs/ADR-*.md`.
> Tri chronologique par timestamp ISO du filename.
> Idempotent — re-générer via `/doc-refresh` ou en fin d'`arch`.

Généré le **{GeneratedAt}** · **{ADRCount}** ADR(s).

---

| ADR | Titre | Statut | Phase | Date |
|-----|-------|--------|-------|------|
{ADRRows}

---

## Légende

- **Statut** : `Accepted` (par défaut SDD_Pro) · `Superseded by ADR-X` · `Deprecated`
- **Phase** : `4-ARCH` (créés par agent `arch` lors du bootstrap) · `5-CODE` (créés par `dev-backend` ou `dev-frontend` pendant l'implémentation)
- **Date** : extraite du timestamp ISO du filename (`ADR-{YYYYMMDDTHHmmss}-{slug}.md`)

## Voir aussi

- `.claude/rules/ownership.md` Partie B — règles de création/écriture (ex-constitution.md)
- `.claude/rules/ownership.md §3` (Partie B) — numérotation atomique anti-race (ex-file-ownership.md §3)
- `workspace/output/.sys/.context/constitution.md` §6 — index dans la constitution (rebuild par `arch`)
