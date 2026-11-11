# Chantier 95 — Masked Mandates : reconstruction et campagne du 11/11/2026

L'archive du 09/11 (`masked-mandates-chantier95-2026-11-09.zip`) est introuvable : ni sur le Mac, ni dans les conversations
claude.ai, ni dans les sessions Code. Le prototype a donc été **reconstruit d'après la section V du manuscrit**, avec les
versions de bibliothèques citées (proof_system 0.34.0, bbs_plus 0.25.0, vb_accumulator 0.29.0, bulletproofs_plus_plus 0.9.0,
BLS12-381), puis toutes les expériences ont été rejouées. Aucun chiffre n'est saisi à la main : `gen_tex.py` lit `results/*.json`.

Machine : VM cloud, Intel Xeon 2,30 GHz, 2 vCPU, Rust 1.97.0, release, un fil (RAYON_NUM_THREADS=1). Graine 20261109.
MesoNET (Zen, Juliet) n'était pas joignable depuis la session (pas de SSH ni de DNS vers les clusters).

## Reproduire
    cd code && cargo build --release
    ./target/release/attacks                      # results/attacks.json
    RAYON_NUM_THREADS=1 ./target/release/bench costs   # puis depth, msgs, rev
    (cd mmpy && maturin build --release && pip install target/wheels/*.whl)
    pip install "mcp<2" pyjwt cryptography biscuit-python pymacaroons
    python e2/e2.py client results/e2.json        # E2 (MCP)
    python sim/e3.py                               # E3 / E3b
    python gen_tex.py ../manuscrit                 # numbers.tex, tab_*.tex, fig_*.pdf

## Fichiers à déposer sur Overleaf (95-MASKED-MANDATES/manuscrit/)
numbers.tex, tab_attacks.tex, tab_costs.tex, tab_rev.tex, tab_e2e.tex, tab_link.tex, tab_timing.tex, fig_costs.pdf, fig_timing.pdf.
Le PDF joint a été compilé avec `\bibliographystyle{IEEEtran}` (IEEEtranUrldate.bst introuvable) ; main.tex est sinon inchangé.

## Écarts avec le README du chantier (chiffres de l'archive perdue)
| | README (09/11) | Campagne du 11/11 |
|---|---|---|
| Attaques | 40/40 rejetées, 14 contrôles | 44/44 rejetées, 11 contrôles |
| Présentation / vérification | 277 / 65 ms | 293 / 66 ms |
| Taille d'une présentation | ≈ 6,8 ko | 11,8 ko (12,1 ko avec séquestre) |
| Délégation, parent | 1,84 s | 1,62 s (émetteur 315 ms) |
| Appel MCP de bout en bout | 353 ms | 363 ms (références : 2,3 à 2,9 ms) |
L'écart de taille vient sans doute d'un autre encodage ou d'une agrégation des preuves d'intervalle dans le code perdu ; non vérifiable.

## Non fait
E4 (LLM dans la boucle) : pas de clé API disponible ici ; MesoNET injoignable.
