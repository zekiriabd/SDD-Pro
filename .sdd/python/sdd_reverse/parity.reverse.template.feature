# parity.reverse.template.feature — Template ISOLÉ pour les specs de parité
# comportementale Gherkin (Phase 3.8, agent reverse-parity-inspector).
#
# Convention (validée par validate_parity_features.py) :
#   - Mots-clés Gherkin ANGLAIS (Feature/Scenario/Scenario Outline/Given/When/
#     Then/And/But/Examples) ; texte métier en FRANÇAIS.
#   - Chaque Scenario porte >= 1 tag @AC-N pointant un AC existant de la FEAT
#     reverse source (+ @US-{n}-{m} optionnel).
#   - Evidence + confidence hérités de l'item FEAT en commentaires, JAMAIS
#     inventés ni upgradés (min-monotone Q3).
#   - Aucun détail d'implémentation (classe, route HTTP, SQL, techno cible) —
#     les step definitions sont écrites en aval par la stack qa/* choisie.
#
# Placeholders : {n}, {m}, {Name}, {FeatTitle}, {ScenarioTitle}, {AC}, {US},
# {Evidence}, {Confidence}, {Given}, {When}, {Then}.

# parity-source: FEAT {n} — workspace/input/feats/{n}-{Name}.md
# generated-by: sdd-reverse-parity
Feature: {FeatTitle}
  Parité comportementale legacy <-> application régénérée.
  Dérivée des Acceptance Criteria de la FEAT reverse {n}-{Name}.

  @AC-{AC} @US-{US}
  Scenario: {ScenarioTitle}
    # evidence: {Evidence}
    # confidence: {Confidence}
    Given {Given}
    When {When}
    Then {Then}
