# Implementation Readiness Report — FEAT {n}-{Name}

- **Date** : {YYYY-MM-DD HH:mm}
- **Validateur** : `/feat-validate`
- **Décision** : {🟢 GO | 🟡 WARN | 🔴 NO-GO}
- **Bypass disponible** : `--force` (ignore NO-GO)

---

## Résumé

- Validations déterministes : {N_pass} / {N_total} ✅
- Erreurs bloquantes (rouge) : {N_fail}
- Warnings (jaune)           : {N_warn}

> **v6.0** : section §2 « Validations sémantiques » retirée (agent
> `validator` supprimé pour économie tokens). Review sémantique
> à la charge du PO humain lors de la relecture de la FEAT.

---

## 1. Validations déterministes (PowerShell, 0 token)

### 1.1 Cohérence numérotation IDs FEAT
- [ ] SFD-N : continuité, pas de doublons → {pass | fail: liste}
- [ ] BR-N  : continuité, pas de doublons → {pass | fail | n/a (section vide)}
- [ ] AC-N  : continuité, pas de doublons → {pass | fail | n/a}
- [ ] FD-N  : continuité, pas de doublons → {pass | fail | n/a}

### 1.2 Traçabilité 100% FEAT → US
- [ ] Tous les SFD-N couverts par au moins 1 US (`Covers`) → {pass | fail: liste IDs orphelins}
- [ ] Tous les FD-N couverts → {pass | fail | n/a}
- [ ] Tous les BR-N couverts → {pass | fail | n/a}
- [ ] Tous les AC-N couverts → {pass | fail | n/a}

### 1.3 Cohérence stack
- [ ] `workspace/input/stack/stack.md` existe → {pass | fail}
- [ ] Au moins 1 backend OU 1 frontend actif → {pass | fail}
- [ ] `## Project Config` rempli (`AppName`, `BackendName` si backend actif) → {pass | fail}
- [ ] `DatabaseType` cohérent (none ou type valide) → {pass | fail}

### 1.4 Cohérence US ↔ HTML mockups (v4)
- [ ] Chaque mockup `workspace/input/ui/{n}-{m}-*.html` a une US `workspace/output/us/{n}-{m}-*.md` correspondante → {pass | fail: liste HTML orphelins}
- [ ] Aucune US ne pointe vers un mockup HTML inexistant → {pass | fail | n/a}

### 1.5 Constitution (si SDD_Pro v3)
- [ ] `workspace/output/.sys/.context/constitution.md` existe → {pass | fail | n/a (projet pre-v3)}
- [ ] Acteurs de la FEAT tous présents en §3 → {pass | warn}

---

## 2. Validations sémantiques — RETIRÉ EN v6.0

> Section retirée. Le PO humain est responsable de la review sémantique
> de la FEAT (mesurabilité ACs, ambiguïtés cross-artefact, hypothèses
> implicites) avant de lancer `/dev-run`.

---

## 3. Erreurs bloquantes (rouge)

> Listées seulement si décision = NO-GO.

```
ERROR-1: <message bref>
CAUSE: <précision>
FIX: <action concrète>

ERROR-2: ...
```

---

## 4. Warnings (jaune, non bloquants)

> Listées seulement si présentes.

- WARN-1: <message>
- WARN-2: ...

---

## 5. Décision finale

### {🟢 GO}
La FEAT est prête pour `/dev-run {n}`. Toutes les validations
déterministes passent. Aucune ambiguïté sémantique critique détectée.

### {🟡 WARN}
La FEAT peut passer en `/dev-run {n}` mais une review humaine est
recommandée avant. Les warnings ci-dessus n'invalident pas le code
généré mais peuvent dégrader sa qualité.

### {🔴 NO-GO}
`/dev-run {n}` est **bloqué**. Corriger les erreurs ci-dessus avant
de relancer. Pour bypass exceptionnel : `/dev-run {n} --force` (à
utiliser uniquement en connaissance de cause).

---

## 6. Prochaines actions

- 🟢 GO : lancer `/dev-run {n}`
- 🟡 WARN : review puis `/dev-run {n}`
- 🔴 NO-GO :
  1. Corriger les erreurs listées en §3
  2. Relancer `/feat-validate {n}`
  3. Une fois GO ou WARN, lancer `/dev-run {n}`
