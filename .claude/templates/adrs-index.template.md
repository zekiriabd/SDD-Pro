# ADRs Index — {ProjectName}

> Auto-généré par l'agent `dashboard` (Haiku 4.5).
> Source de vérité : Glob `workspace/output/context/adrs/ADR-*.md`.
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

- `.claude/rules/constitution.md` — règles de création/écriture
- `.claude/rules/file-ownership.md §3` — numérotation atomique anti-race
- `workspace/output/context/constitution.md` §6 — index dans la constitution (rebuild par `arch`)
