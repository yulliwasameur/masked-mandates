# Related-work verification and Table 1 audit (Masked Mandates)

Date: 2026-11-13. BibTeX: `refs-additions.bib` (same folder).

How the metadata was checked:
- **Springer, ACM and NDSS papers:** title, authors, pages and DOI come from the Crossref API (`api.crossref.org/works/<doi>`). For LNCS papers, the volume number comes from the publisher's Crossref deposit XML.
- **RFCs:** `rfc-editor.org/rfc/<n>.json`.
- **Internet-Drafts:** datatracker API plus the draft text at `ietf.org/archive/id/`.
- **arXiv papers:** `export.arxiv.org/api`.
- **DBLP and Springer HTML** were not used. Both returned bot-protection pages, and I did not try to bypass them.

Legend for Table 1: ✓ provided, ◐ partial, ✗ stated as not provided, – not addressed.

---

## Part A — references

| # | Key | Verification source | Relevant property (1–2 sentences) |
|---|---|---|---|
| 1 | `blomer2019uacs` | Crossref 10.1145/3319535.3354223; ePrint 2019/169 | **Updatable anonymous credentials.** The user runs an update function with the issuer, and the issuer "does not learn the user's previous attributes" (abstract). Updates need the issuer **online**. Double-spending in the incentive system identifies the cheater. Closest prior work to our "re-issuance through an online issuer", but it has no delegation. |
| 2 | `hartung2017bbaplus` | Crossref 10.1145/3133956.3134071; PDF at acmccs.github.io/papers/p1925-hartungA.pdf | Unlinkable point collection ("piggy bank") with double-spending detection: "double-spending reveals the user identity" (§4). A TTP trapdoor that removes unlinkability is "only needed for definitional purposes" (§3.1), so it is **not** an operational escrow. |
| 3 | `teranishi2004ktaa` | Crossref 10.1007/978-3-540-30539-2_22 (LNCS 3329); journal version IEICE E92-A(1):147–165, 2009, doi 10.1587/transfun.E92.A.147 | **k-TAA.** Each application provider fixes a bound k. Users authenticate anonymously and unlinkably up to k times. Anyone can identify a user who exceeds k, with no authority involved. This is the classic **per-verifier anonymous rate limit**. |
| 4 | `au2006bbsplus` (existing) | Crossref 10.1007/11832072_8 (SCN 2006, LNCS 4116, pp. 111–125); extended version ePrint 2008/136 | **Confirmed: it is a dynamic k-TAA.** Application providers "independently grant or revoke" users from their own access group (ePrint abstract). The scheme's signature component is what is now called BBS+. Add the DOI to refs.bib. |
| 5 | `bobolz2021ihabc` | Crossref 10.1007/978-3-030-92548-2_9 (LNCS 13099); ePrint 2022/213 | **Issuer hiding.** The verifier publishes a policy, and the user "can prove that her credential was issued by one of the accepted issuers" without revealing which one. |
| 6 | `connolly2022spseq` | Crossref 10.1007/978-3-030-97121-2_15 (LNCS 13177); ePrint 2021/1680 | SPS-EQ-based credentials. **Yes, it offers issuer hiding, under the name "signer-hiding"**: "the issuing organization is not revealed" when showing (abstract). Caveat: the ePrint page notes an "Erratum … regarding the signer-hiding property of the signature construction". Cite the ePrint (2022-06-06 revision) alongside the PKC paper. |
| 7 | `sonnino2019coconut` | Crossref 10.14722/ndss.2019.23272; arXiv 1802.07344 | Threshold issuance by t-of-n authorities, with "multiple unlinkable selective attribute revelations" (abstract). It has no delegation and no revocation. The petition application uses a per-scope value ζ to stop double signing, which is an application-level rate limit of one per scope. |
| 8 | `chase2020signal` | Crossref 10.1145/3372297.3417887 | Signal private groups: users authenticate to the server and only reveal "that they correspond to some encrypted entry" (abstract). It introduces keyed-verification credentials with efficient verifiable encryption of attributes. This is a precedent for proving that a ciphertext encrypts a credential attribute, which our escrow does. |
| 9 | `kreuter2020pmb` | Crossref 10.1007/978-3-030-56784-2_11 (**LNCS 12170**); ePrint 2020/072 | Privately verifiable anonymous tokens with "unforgeability, unlinkability, and privacy for the metadata bit" (ePrint abstract). One hidden bit is readable only by the key holder. Related to Privacy Pass and Trust Tokens. |
| 10 | `bellare2005dynamic` | Crossref 10.1007/978-3-540-30574-3_11 (LNCS 3376) | **BSZ model** for dynamic group signatures: separate issuer and opener, with anonymity, traceability and non-frameability. It is the standard model for an opening (escrow) authority, and its "Judge" verifies openings, matching our Judge. Description from standard knowledge; metadata verified. |
| 11 | `camenisch2003verenc` | Crossref 10.1007/978-3-540-45146-4_8 (LNCS 2729) | Verifiable encryption of discrete logarithms, with CCA security and labels. It is the standard reference for proving that a ciphertext contains a committed value, as our ElGamal escrow does. Description from standard knowledge; metadata verified. |
| 12 | `dodis2005vrf` | Crossref 10.1007/978-3-540-30580-4_28 (LNCS 3386) | The Dodis–Yampolskiy VRF/PRF g^{1/(sk+x)}. It underlies pseudonyms and serial numbers of the form PRF_k(scope ‖ counter) in rate-limited credentials. Description from standard knowledge; metadata verified. |
| 13 | `attema2022fsmulti`, `attema2023fsmultijoc` | Crossref 10.1007/978-3-031-22318-1_5 (TCC 2022, LNCS 13747, pp. 113–142); 10.1007/s00145-023-09478-y (JoC 36(4), article 36, 2023) | Knowledge soundness of Fiat–Shamir for multi-round (k-special-sound) protocols, with tight bounds. This is needed for the soundness of the non-interactive proofs, e.g. Bulletproofs. Description from standard knowledge. |
| 14 | `fischlin2005online` | Crossref 10.1007/11535218_10 (LNCS 3621) | NIZK proofs of knowledge with straight-line (online) extraction in the ROM. This is relevant if the security proof needs extraction without rewinding, as in UC or with concurrent presentations. Description from standard knowledge. |
| 15 | `camenisch2017cdd` | Crossref 10.1145/3133956.3134025 | Practical UC-secure delegatable anonymous credentials with attributes. The delegation chain is hidden "during both delegation and presentation" (abstract). Delegation is done **by the holder, without the root issuer**. It has no revocation, rate limiting or escrow. |
| 16 | `rfc9576`, `rfc9577`, `rfc9578`, `rfc9474` | rfc-editor.org JSON; DOIs 10.17487/RFC95xx | Architecture, HTTP auth scheme, issuance (VOPRF and blind RSA), and RSA blind signatures. RFC 9577 §2.1: `redemption_context` "can be a unique per-request nonce", and `origin_info` scopes tokens to origins. Section 2.2 binds `challenge_digest = SHA-256(TokenChallenge)` into the token. |
| 17 | `yun2026arccrypto`, `yun2026arcprotocol` | datatracker API + draft text | Both drafts are **-01, dated 2 March 2026**, and **expired on 3 Sep 2026**. Their IETF stream state is **"Dead WG Document"**. ARC is a keyed-verification anonymous credential in which each presentation is bound to a `presentation_context` (issuer_name ‖ origin_info ‖ redemption_context ‖ key id) and limited to a per-origin `presentation_limit`. Cite the drafts as "expired/dead WG document". |
| 18 | `rfc9901`, `openid4vci`, `eudiarf2025privacy` | RFC 9901 JSON (Nov 2025, Proposed Standard; it supersedes draft-ietf-oauth-selective-disclosure-jwt-22); openid.net (OpenID4VCI 1.0 Final, Sep 2025); eudi.dev, redirected from the official eu-digital-identity-wallet GitHub Pages | RFC 9901 §10.1: unlinkability between verifiers and between presentations "can be achieved using batch issuance". It also says SD-JWT "does not meet the security properties for anonymous credentials". OpenID4VCI §3.3.2: credentials in a batch "SHOULD contain different Cryptographic Data". The ARF Discussion Topic A (v1.0, 14 Jan 2025) analyses once-only, rotating-batch and per-RP attestations, and ZKPs against relying-party linkability. The ARF main document page (dated 2026-07-21) shows no version number. |
| 19 | `rfc8693`, `rfc9396`, `rfc9728`, `tulshibagwale2026txntokens`, `mcpauth` | rfc-editor.org JSON; datatracker; modelcontextprotocol.io | RFC 8693: token exchange, where the `act` claim records the acting party (delegation chain). RFC 9396: `authorization_details` (fine-grained, per-transaction). RFC 9728: protected-resource metadata, which MCP servers MUST implement. Transaction Tokens: **-11, 30 Jul 2026**, state "WG Consensus: Waiting for Write-Up"; it propagates identity and context along a call chain inside one trust domain. MCP authorization: **revision 2026-07-28**, OAuth 2.1 based, with RFC 8707 audience binding and Bearer tokens on every request. The existing `mcpspec` should state that revision. |
| 20 | `rfc8785`, `rfc9380`, `rfc9458` | rfc-editor.org JSON | JCS (Jun 2020, Informational); hash-to-curve (Aug 2023, Informational); Oblivious HTTP (Jan 2024, Proposed Standard), relevant for hiding the client's network identifier from tools. |
| 21 | `south2025authdeleg` / `south2025icml` | arxiv.org/abs/2501.09674; proceedings.mlr.press/v267/south25a.html | arXiv v1 (16 Jan 2025): "Authenticated Delegation and Authorized AI Agents", 8 authors: South, Marro, Hardjono, Mahari, Whitney, Greenwood, Chan, Pentland. The ICML 2025 version (PMLR 267:82211–82231) is titled **"Position: AI Agents Need Authenticated Delegation"** and has 7 authors (no Greenwood). It extends OAuth/OpenID with agent-specific credentials, for accountable (not unlinkable) delegation. |
| 22 | `danezis2003sda`, `serjantov2002metric`, `diaz2002measuring` | Crossref | Danezis 2003 is in *Security and Privacy in the Age of Uncertainty*, pp. 421–426, doi 10.1007/978-0-387-35691-4_40. The "IFIP SEC 2003" label and the IFIP series volume number were **not** found in Crossref; drop them if unsure. Serjantov–Danezis and Díaz et al. are both in PET 2002, LNCS 2482 (published 2003), pp. 41–53 and 54–68. Both define entropy-based anonymity metrics. |

### A23 — 2025–2026 agent-specific work (verified on arXiv / datatracker abstract pages)

I found **no** 2025–2026 paper or draft that gives unlinkable credentials, anonymous rate limits or anonymous delegation for LLM/MCP/A2A agents, beyond the works already cited. The following are verified and useful to show the gap:

- **`huang2025zerotrustagents`** — arXiv 2505.19301. DIDs/VCs plus ZKP-based attribute disclosure for agents. It does not claim unlinkability or delegation.
- **`south2025idmgmt`** — arXiv 2510.25819, OpenID Foundation whitepaper, 21 authors. A position paper on delegated authority and MCP. Whether the full text names anonymous credentials as a remedy for tracking is **unverified** (search snippet only).
- **`zhou2026capbinding`** — arXiv 2603.14332. BBS+ capability certificates with selective disclosure for agent tool use. It aims at accountability and does not claim unlinkability. This is the closest in primitives: cite it and contrast.
- **`kasselman2026aims`** — draft-ietf-wimse-aims-01, Nov 2026; it replaces draft-klrc-aiagent-auth. It maps WIMSE and OAuth token exchange onto agents. On privacy it offers only claim minimisation and down-scoping.
- **Not added to the .bib; verified by the sub-search but secondary:**
  - Jing & Qi, arXiv 2512.14737 (ZK audit inside MCP)
  - Gopalakrishna, arXiv 2608.30083 (ZK predicate proofs over MCP/A2A)
  - Acharya, arXiv 2511.15712
  - Saavedra, arXiv 2601.14982 (delegation grants)
  - draft-mishra-oauth-agent-grants-02
  - Rometsch et al., ePrint 2026/1855 (DAC from JWTs via recursive SNARKs)
  - Mirzamohammadi et al., ePrint 2026/2860 (delegatable keyed-verification ACs)
  - Schlesinger & Katz, draft-schlesinger-cfrg-act-01 (Anonymous Credit Tokens)

  The last three are recent non-agent DAC/rate-limit work worth considering.

---

## Part B — Table 1 audit

The agent-system papers (rows 1–7) were read in full on arXiv or Frontiers, except B-CM. The crypto rows were read on ePrint, arXiv and RFC text, except TDAC. Quotes are verbatim; each is under 15 words.

### Existing rows

**Agentic JWT** — arXiv 2509.13597 (Goswami, single author, no venue)
- **Unlinkable ✗.** "We need to have separate identities for each agent" (§III-C).
- **Deleg ◐.** "a chained delegation assertion to prove which downstream agent may execute" (abstract). No narrowing of scope is specified.
- **Bound ◐.** The token is "scoped to a single agent + intent + workflow step" (§III-C2). A proof-of-possession key "is used to sign the HTTP request" (§III-C4). There is no nonce or request hash.
- **RL / Subtree –.**
- **Offline delegation ✗.** The shim "will initiate token minting request with the IDP" (§III-D2).
- **No change.**

**AIP** — arXiv 2603.24775
- **Unlinkable ✗.** "the identifier is the public key itself" (§3.1).
- **Deleg ✓.** "Scope attenuation is cryptographically enforced" (§3.2).
- **Bound ✗.** "real-time replay within the token's TTL window is not prevented" (§6).
- **RL –.** Only a spend budget, "the runtime's responsibility" (§3.4).
- **Subtree ✗ (keep).** §7 lists "No revocation infrastructure." as a limitation. That is *stated*, so ✗ fits the legend. A sub-agent proposed –, which I reject.
- **Offline delegation ✓.** "Each intermediary agent appends a delegation block, signed with its own key" (§3.2). Verification "is purely local" (§5.4).

**InterSAGE** — arXiv 2608.13030, self-described "Positioning paper"
- **Unlinkable ✗.** "exposes the requester's full AIC attributes to the responder" (§10.2).
- **Deleg ✓.** "Authority can only be attenuated, never amplified" (§3.1).
- **Bound – (keep).** "Session tokens are bound to specific agent instances" (§6.1). Per-call trace signatures (§7.3) are an after-the-fact audit log, not authorisation.
- **Subtree ✓.** "revoking an AIC atomically invalidates it and all its delegated descendants" (§4.3). This is a design only: no construction, proofs or benchmarks.
- **Offline delegation ✗.** "GAR issues child AIC signed by the parent's key" (§6.2).
- **Suggestion:** add a footnote that it is a positioning paper.

**DID/VC agents** — ICAART 2026, doi 10.5220/0014234400004052; arXiv 2511.02841
- **Unlinkable ✗.** Persistent ledger-anchored DIDs (§4).
- **Deleg –.** VCs are only described as "suitable for carrying human-to-agent and agent-to-agent delegations" (§2); nothing is built.
- **Bound –.** The holder proof is over the VP at session level (§5).
- **RL / Subtree / Escrow –.** "Revocation" never appears.
- **Offline delegation –.**
- **No change.**

**KITA** — arXiv **2609.05901** (Zheng & Zhang, v2 23 Oct 2026)
- **Bound ✓.** Signers release "an action-bound signature share" (§1), over a canonical action with a nonce. "Execution atomically consumes that ID and the nonce" (§2).
- **Deleg –.** It is threshold custody of a delegated key, not agent-to-agent attenuation.
- **RL –.** Rate limits are only called "relevant" (App. B.5).
- **Venue unverifiable.** neurips.cc lists the title but the page returned HTTP 500, and the PDF does not name the venue. **Cite the arXiv version** unless the workshop is confirmed by hand.

**Verifiable authorisation (CVA)** — Frontiers Comput. Sci. 8:1966725, doi 10.3389/fcomp.2026.1966725
- **Unlinkable ✗.** The public statement includes the agent's public identifier (§1, §3.2).
- **Deleg ✗.** Multi-hop delegation is left to future work.
- **Bound ✓.** The public statement contains a request commitment, a nonce and a timestamp (abstract, §4). Caveat: its own Table 2 rates its binding "partial relative to full CVA request binding". It is plan-level, which still counts as ✓ for "tied to one call".
- **Bibliography fix:** the printed title is in sentence case: "Cryptographically verifiable authorization for autonomous AI agents: a falsifiable hypothesis and proof of concept".

**B-CM** — IEEE TNSE 13:9379–9393, doi 10.1109/TNSE.2026.3695095
- **Full text not accessible:** closed access, IEEE Xplore blocks automated fetches, and no preprint exists.
- **Unlinkable ✓.** Abstract: "to enable unlinkable and auditable agent authentication in a decentralized manner".
- **Escrow: cannot be determined.** The abstract says "auditable" and mentions distributed key generation, but does not say whether a tracing or opening authority exists.
- **Deleg / Bound / RL / Subtree:** absent from the abstract and keywords.
- **Recommendation:** change Escrow from "–" to "?", with the footnote: *"described as 'auditable' (abstract); we could not determine whether an opening authority exists."* Better: obtain the PDF and settle it. The reviewer's point is legitimate.

**DAC (mercurial), Griffy et al.** — ASIACRYPT 2024, LNCS **15485**, pp. 296–325; ePrint 2024/1216
- **Unlinkable ✓, with a trust assumption.** The anonymity adversary controls the root but "does not control the TRA" (§4.2).
- **Deleg ◐.** Delegation is level-based only; attribute support is left "to future work" (§5).
- **Bound –.**
- **RL –.**
- **Subtree ✓.** "a revocation authority maintains a public deny list" (§1.2). On revocation the TRA must "look through all the secret ephemeral keys they generated to recognize the credential chain" (§1.3). So revocation goes through a trusted TRA, not an accumulator.
- **Escrow ◐ (keep).** "the TRA generates an opener secret key and public key" (§4.1). But registration "is anonymous and neither a verification of the user's identity is needed" (§1.2). The TRA can link and revoke a chain, but it cannot reveal a real-world identity.
- **Offline delegation ✓.** A user delegates by interacting with "the root (or an issuer that the root has delegated to)" (§4.1). One registration with the TRA per key is required.

**TDAC (Mir, Slamanig, Mayrhofer)** — TDSC 21(4):2312–2326
- **No open version found:** closed access, no ePrint or arXiv copy.
- **Supported by the title and abstract (via OpenAlex):** Unlinkable ✓; "Controlled and Fine-Grained Delegation" → Deleg ✓; "the first decentralized and delegatable AC system", built from threshold delegatable subset predicate encryption.
- **Unverified:** RL, Subtree and Escrow (left as –) and offline delegation.
- A later paper, ePrint 2025/2134 §1, says TDAC "does not enforce non-transferability" and "requires an extra round during showing". That is a secondary source.

**FDAAC-CR** — TIFS 20:7572–7587, doi 10.1109/TIFS.2025.3587182
- **ePrint 2024/610 is the earlier version:** "Practical Delegatable Attribute-Based Anonymous Credentials with Chainable Revocation" (DAAC-CR). Same authors except Man Ho Au, who was added in TIFS. The audit below used the ePrint version.
- **Unlinkable ✓.** "users cannot be traced when showing, delegating, or receiving credentials" (§3.2).
- **Deleg ✓.** It can restrict "the set of delegable attributes and the depth of delegation" (§1.1).
- **Subtree ✓.** "all subsequent credentials derived from it are also invalid" (abstract). Revocation goes through a revocation authority, which is involved in non-membership witness generation (§3.1).
- **Escrow –.** No tracing, opening or audit found.
- **RL –.**
- **Offline delegation ✓.** Delegation "involves an issuer R and a receiver U" (§3.1), where R is the delegator.

**ACT** — ASIACRYPT 2023, LNCS 14439; ePrint 2023/320
- **Unlinkable ✓.**
- **Bound ◐.** "At redemption, the message is revealed" (§1). It binds a client-chosen message, not a verifier challenge.
- **RL ✓.** "each client will be able to obtain only one token per message" (abstract). Users must register a public key with the issuer.
- **No change.**

**Privacy Pass** — Hanff et al., CCS 2025; RFC 9576/9577/9578
- **Bound: change – → ◐ (the reviewer is right).**
  - RFC 9577 §2.1.1: `redemption_context` "can be a unique per-request nonce".
  - §2.2: the token carries `challenge_digest = SHA-256(TokenChallenge)`.
  - Hanff et al. §1: "a token bound to this redemption context".
  - It is partial because it binds the origin's challenge, not the request or call content.
- **RL ◐ (keep).** RFC 9576 §3.2: "help rate-limit malicious or otherwise abusive traffic". Per-origin rate-limited issuance (draft-ietf-privacypass-rate-limit-tokens-06) **expired in Oct 2024**. Base tokens are one-time-use.
- **Citation:** cite the RFCs in this row, not only Hanff et al.

### Candidate new rows

**UACS** (Blömer et al., CCS'19)
- Unlinkable ✓. The issuer "does not learn the user's previous attributes".
- Deleg –, Bound –, RL –, Subtree –.
- **Escrow ◐.** Double-spenders "can be identified" (§1); this is accountability, not escrow.
- Agents –. Offline delegation: n/a.
- **Remark:** an issuer-online update is the closest analogue to our re-issuance.

**BBA+** (CCS'17)
- Unlinkable ✓. Deleg –, Bound –, RL –, Subtree –.
- **Escrow ◐.** "double-spending reveals the user identity" (§4). The TTP trapdoor is "only needed for definitional purposes" (§3.1) and is **not** an escrow.
- Agents –. Offline delegation: n/a.

**ARC** (draft-ietf-privacypass-arc-*-01)
- Unlinkable ✓. Credentials allow "unlinkable presentations" (crypto §4).
- **Bound ◐.** "The presentation is cryptographically bound to the state's presentation context" (crypto §4.3). That context covers origin and redemption_context.
- **RL ✓.** Per-origin `presentation_limit`.
- Deleg –, Subtree –, Escrow –, Agents –. Offline delegation: n/a.
- **Status:** dead WG document.

**SD-JWT + batch issuance** (RFC 9901, OpenID4VCI 1.0)
- **Unlinkable ◐.** Only with one-time batch credentials (RFC 9901 §10.1). It "does not meet the security properties for anonymous credentials".
- **Bound ✓.** The KB-JWT nonce ensures "binding to the given transaction" (§4.3), and `aud` is required.
- Deleg –, RL –, Subtree –. Escrow: n/a (identified). Agents –.

**Coconut** (NDSS'19)
- Unlinkable ✓.
- Deleg –. Bound –: Fiat–Shamir proofs, but no message binding is specified.
- **RL ◐.** Per-petition ζ "prevents a citizen from signing the same petition multiple times" (§V-B).
- Subtree –, Escrow –, Agents –.

**Optional extra rows:** CDD17 (unlinkable ✓, delegation with attributes ✓, offline delegation ✓, everything else –) and k-TAA / dynamic k-TAA (unlinkable ✓, RL ✓, Escrow ◐ through public tracing of over-use). These are strong RL precedents that reviewers may expect.

### Proposed corrected Table 1

The new last column, **Offl.**, is "delegation without online issuer". "n/a" means the scheme has no delegation. Changes from the current table are **bold**.

| System | Unl. | Deleg+att | Bound | RL | Subtree | Escrow | Agents | Offl. |
|---|---|---|---|---|---|---|---|---|
| Agentic JWT | ✗ | ◐ | ◐ | – | – | n/a | ✓ | **✗** |
| AIP | ✗ | ✓ | ✗ | – | ✗ | n/a | ✓ | **✓** |
| InterSAGE¹ | ✗ | ✓ | – | – | ✓ | n/a | ✓ | **✗** |
| DID/VC agents | ✗ | – | – | – | – | n/a | ✓ | **–** |
| KITA² | – | – | ✓ | – | – | n/a | ✓ | **–** |
| Verifiable authorisation | ✗ | ✗ | ✓ | – | – | n/a | ✓ | **–** |
| B-CM | ✓ | – | – | – | – | **?³** | ✓ | **–** |
| DAC (mercurial) | ✓⁴ | ◐ | – | – | ✓⁴ | ◐ | – | **✓** |
| TDAC⁵ | ✓ | ✓ | – | – | – | – | – | **?** |
| FDAAC-CR | ✓ | ✓ | – | – | ✓ | – | – | **✓** |
| CDD17 (new, optional) | **✓** | **✓** | **–** | **–** | **–** | **–** | **–** | **✓** |
| Dynamic k-TAA (new, optional) | **✓** | **–** | **–** | **✓** | **–** | **◐** | **–** | **n/a** |
| UACS (new) | **✓** | **–** | **–** | **–** | **–** | **◐** | **–** | **n/a** |
| BBA+ (new) | **✓** | **–** | **–** | **–** | **–** | **◐** | **–** | **n/a** |
| ACT | ✓ | – | ◐ | ✓ | – | – | – | **n/a** |
| Privacy Pass | ✓ | – | **◐** | ◐ | – | – | – | **n/a** |
| ARC (new) | **✓** | **–** | **◐** | **✓** | **–** | **–** | **–** | **n/a** |
| SD-JWT batch (new) | **◐** | **–** | **✓** | **–** | **–** | **n/a** | **–** | **n/a** |
| Coconut (new) | **✓** | **–** | **–** | **◐** | **–** | **–** | **–** | **n/a** |
| **This work** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | **✗** |

Footnotes:
1. Positioning paper; no construction or evaluation.
2. arXiv 2609.05901.
3. Described as "auditable"; whether it has an opening authority could not be verified (closed access).
4. Assumes an honest trusted revocation authority (TRA) that can link chains.
5. Closed access; only the title and abstract were verified.

**Implication for the text:** the honest new column puts this work at ✗ for "delegation without online issuer". AIP, Griffy et al., FDAAC-CR and CDD17 are ✓. The paper should state this trade-off explicitly: the online issuer enables the delegation rate limit and the seen-set, at the cost of availability and issuer-side metadata.

Wording fixes for §2:
- The claim that Privacy Pass carries "no delegation" is fine, but Bound is now ◐.
- "two of them let one revoke a delegator together with the credentials derived from it [griffy, xie]" is confirmed. Griffy's revocation needs a trusted TRA. FDAAC-CR's needs a revocation authority with an accumulator.

---

## Unverifiable or uncertain items
1. **B-CM full text:** whether it has an opening or escrow authority, delegation or revocation. Closed access, IEEE blocked fetches, no preprint.
2. **TDAC full text:** revocation, tracing, RL and offline delegation. Closed access.
3. **KITA's NeurIPS 2026 workshop venue:** the neurips.cc page returned HTTP 500 and there is no OpenReview entry.
4. **Danezis 2003:** the IFIP series volume number and the "SEC 2003" label are not in Crossref. The book title, pages and DOI are verified.
5. **ARF main document version number:** not shown on eudi.dev, only the date 2026-07-21. I cited Discussion Topic A v1.0 instead.
6. **Descriptions of items 10–14** (BSZ, Camenisch–Shoup, Dodis–Yampolskiy, Attema–Fehr–Klooß, Fischlin) come from standard knowledge. Their metadata is Crossref-verified, but I did not re-read the papers.
7. **arXiv 2510.25819** (South et al. whitepaper): whether it advocates anonymous credentials is known only from a search snippet.
8. **DBLP** was not consulted (bot wall). Crossref was used as the primary metadata source instead.

## Round A changes (2026-11-14)
- The "Agents" column was removed (application domain, not a property; reviewer R3-B5b).
- **Clone Wars** [camenisch2006clonewars] row added: unlinkable periodic n-times anonymous authentication (✓), no delegation (–), not bound to a call (–), per-verifier rate limit per period (✓), no subtree revocation (–), identity revealed on over-use (◐ for trace), n/a for offline delegation.
- **UACS, Deleg.+att. ◐** is now marked as our inference (*): UACS lets the issuer update hidden attributes under a proven relation, which can express attenuation; UACS does not claim delegation.
- **AIP, Bound ✗** now has footnote 4: AIP calls its tokens "invocation-bound capability tokens", but states that replay within the token lifetime is not prevented.

- **SD-JWT batch, Bnd.** changed from ✓ to ◐ in round B: its key-binding JWT binds a nonce, the audience and sd_hash (a verifier challenge), not the call content — the same rule as Privacy Pass, ARC and ACT.

## Round E changes (external referee, 2026-11-14)
- Rows added: AP2 v0.1.0 (Unl ✗, Del ◐*, Bnd ✓ via cart mandate, Tr ✓ trivially, Off –), DAC from JWTs [Rometsch et al., ePrint 2026/1855] (Unl ✓, Del ◐*, Off ✓*), Delegatable KVAC [Mirzamohammadi et al., ePrint 2026/2860] (Unl ✓, Del ✓, Off ?), BBS per-verifier pseudonyms [IRTF CFRG draft] (Unl ◐ across verifiers only, Bnd ◐* via presentation header).
- Tr. column: identity-bearing schemes now ✓⁵ (trivially traceable) instead of n/a.
- ACT row relabelled "ACT (counting tokens)" to avoid confusion with anonymous credit tokens.
- The supplement now lists the evidence for every partial and inferred cell (Sec. "Evidence for Table 1").
