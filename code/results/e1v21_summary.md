# E1 v2.1 et suite d'attaques — résumé (généré depuis paper-v2/numbers.tex et code/results/)

Toutes les valeurs ci-dessous sont les macros générées par `code/gen_tex_v21.py` à partir des fichiers de résultats (aucune saisie à la main).

| Macro | Valeur |
|---|---|
| `AblBbsPres` | 4 |
| `AblDyAdd` | 165 |
| `AblHideCost` | 0.5 |
| `AblNmAdd` | 58 |
| `AblRangeAdd` | 163 |
| `AblRevAdd` | 164 |
| `BenchN` | 100 |
| `CampSpread` | 0.7\,\% |
| `CpuMac` | Apple M5 Pro |
| `CpuZen` | AMD EPYC 9534 |
| `DelIssuerMs` | 423 |
| `DelMsgHiS` | 5.23 |
| `DelMsgLoMs` | 1{,}292 |
| `DelParentS` | 2.27 |
| `DepthPresMax` | 390 |
| `DepthPresMin` | 389 |
| `EscExtraB` | 500 |
| `GitCommit` | 21a8dace1f54 |
| `MsgBMax` | 14{,}688 |
| `MsgBMin` | 13{,}152 |
| `MsgHi` | 64 |
| `MsgLo` | 16 |
| `MsgPresMax` | 391 |
| `MsgPresMin` | 390 |
| `NAttMP` | 6 |
| `NAttProver` | 12 |
| `NAttacks` | 70 |
| `NBitFlips` | 2{,}000 |
| `NChecks` | 21 |
| `NMsgs` | 28 |
| `OmegaKB` | 4.8 |
| `PresB` | 13{,}536 |
| `PresKB` | 13.5 |
| `PresMacMs` | 291 |
| `PresMs` | 390 |
| `PubParamsKB` | 0.5 |
| `RevMax` | $10^{6}$ |
| `RevPresMax` | 390 |
| `RevPresMin` | 390 |
| `RevRefreshMs` | 5.2 |
| `RevWitMs` | 35 |
| `ThrBadMean` | 19 |
| `ThrBadMs` | 13 |
| `ThrBadPninety` | 58 |
| `ThrGarbageUs` | 1 |
| `ThrMpCores` | 64 |
| `ThrMpEff` | 91\,\% |
| `ThrMpRate` | 555 |
| `ThrPerCore` | 10 |
| `ThrVerMs` | 105 |
| `VerBytesMs` | 105 |
| `VerMacMs` | 63 |
| `VerMs` | 86 |
| `Warmup` | 5 |

Tables générées : `tab_costs.tex`, `tab_ablation.tex`, `tab_rev.tex`, `tab_attacks.tex` (voir `manuscrit/`).
Sources : `code/results/v21/zen/c{1,2,3}/` (3 campagnes, nœuds exclusifs, 1 cœur épinglé), `code/results/v21/zen/mp/`, `code/results/v21/mac/`, `code/results/attacks.json`.
