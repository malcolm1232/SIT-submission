# Sealing answer keys and held-out data

Date: 2026-10-02. Resolves audit P0 item 7 and M5 (`research/audit/research_audit.md`), and implements methodology R2 ("keys MUST be stored encrypted or outside the agent's sandbox"). Tier definitions are in `docs/DECISIONS.md` ADR-004.

## 1. What gets sealed

| Tier | Path today | Sealed? | What is sealed |
|---|---|---|---|
| S-dev | `eval/synthetic/*` | No. Developers use these keys for tuning and calibration | — |
| **S-heldout** | `eval/blind/item_a`, `eval/blind/item_b` (reclassified; renamed `eval/heldout/` on sealing) | **Yes** | The whole item directory: `design.md`, `README.md`, `answer_key.json`. The READMEs name the defects outright, and reading the design text is itself tuning exposure |
| **Blind** (to be commissioned) | not yet present | **Yes, from arrival** | Everything: PDFs, author keys, the third-party taxonomy mapping. Delivered already encrypted; never decrypted before `prereg.yaml` is frozen |
| OOD, sound controls | not yet present | Yes | Docs and keys |
| Supplementary pooled keys (G⁺) | created after held-out runs | Yes, same split as their parent | — |

This document's author did not open the `eval/blind/` files while writing it.

## 2. Encryption method

**Recommendation: `age` in passphrase mode** (`age -p`). Alternative: **GPG symmetric** (`gpg --symmetric --cipher-algo AES256`). Both encrypt with a passphrase only; no key server, no identity file in the repo.

| | `age -p` | `gpg --symmetric` |
|---|---|---|
| Setup on a laptop | One static binary | Often preinstalled; agent and pinentry configuration can get in the way |
| Defaults | Modern AEAD and a memory-hard passphrase KDF (scrypt) with no options to get wrong | Strong when `--cipher-algo AES256` is given; older defaults and S2K options exist |
| Failure modes | Few flags; prompts for the passphrase on the terminal and has no command-line option for it, which keeps it out of shell history and process lists | Can be scripted with `--passphrase`, which is exactly the leak we want to avoid |

Rules:
- **The passphrase is held by the user only**, in their password manager, with a second copy (if it is lost, the split is lost). It is never written to the repo, `.env`, a script argument, an environment variable, a CI secret or any LLM session, including coding-assistant sessions.
- Each split gets its own passphrase, so unsealing S-heldout cannot expose Blind.
- **Only `.age` files are committed** for sealed splits. Plaintext lives only in a temporary directory outside the repo during an authorised evaluation.
- The commissioned Blind set is encrypted by whoever authors or stores it, before the developer receives it. The passphrase is handed over at the final run.

## 3. `scripts/seal.py` and `scripts/unseal.py` (design)

Both scripts shell out to the `age` binary and let it prompt for the passphrase on the terminal; neither ever accepts a passphrase as an argument or environment variable.

**Layout after sealing**

```
eval/heldout/
  heldout.tar.age        # sealed bundle (committed)
  MANIFEST.yaml          # plaintext metadata (committed)
  ACCESS_LOG.md          # append-only access log (committed)
eval/blind/              # later: blind.tar.age, MANIFEST.yaml, ACCESS_LOG.md
```

**`scripts/seal.py <split> <source_dir>`**
1. Refuse if `<source_dir>` is inside a path the agent may read (section 5).
2. Build a deterministic tar: files sorted by path, owner and group set to 0, mtime set to 0, so the same content gives the same bundle hash.
3. Record in `MANIFEST.yaml`, per file: path, SHA-256 of the plaintext, size, canary GUID (methodology §1.1 rule 5). For the bundle: SHA-256 of the tar and of the `.age` file, `sealed_at`, `sealed_by`, split, access budget (S-heldout 3, Blind 1, OOD 1).
4. Run `age -p -o <split>.tar.age <bundle.tar>`; the user types the passphrase twice.
5. Decrypt once to memory to verify the round trip, then shred the plaintext tar and remove the plaintext source files from the working tree (the user then commits the deletion).

**`scripts/unseal.py <split> --reason "<text>" [--to <dir>]`**
1. Refuse if the access count in `ACCESS_LOG.md` already equals the budget.
2. Refuse if the git tree is dirty, or (for S-heldout and Blind) if `prereg.yaml` is missing or its hash differs from the frozen one recorded in `ACCESS_LOG.md`'s header.
3. Append an entry to `ACCESS_LOG.md` **before** decrypting: UTC time, who, reason, git commit, `prereg_sha256`, access number n of budget.
4. Decrypt with `age -d` into a fresh temporary directory **outside the repo** (default: a `mkdtemp` under the system temp directory) and verify every file's SHA-256 against `MANIFEST.yaml`.
5. Print the directory path for the eval runner, then wait; on exit (normal or Ctrl-C) delete the directory. Usable as a context manager from `eval/run_matrix.py` so the plaintext exists only while the runner needs it.
6. Never writes plaintext into the repo, never prints file contents.

**Pre-commit hook** (`scripts/hooks/pre-commit`, installed by `make hooks`):
- Rejects any staged file under `eval/heldout/` or `eval/blind/` other than `*.age`, `MANIFEST.yaml` and `ACCESS_LOG.md`.
- Rejects any staged file anywhere containing a sealed split's canary GUID (catches pasted key content).
- Rejects edits to existing `ACCESS_LOG.md` lines (append only).
- Runs `gitleaks` (secrets).

**Tests** (L0, run in the sandbox with a throwaway passphrase supplied through a pseudo-terminal): round trip; deterministic bundle hash; refusal at the access budget; refusal on a dirty tree; access log appended before decryption; plaintext directory removed on exit.

## 4. Git history

Sealing does not remove plaintext that was already committed. If the S-heldout plaintext was ever committed, then before any non-developer is given access to the repository, either rewrite history to purge those paths (for example with `git filter-repo`, then force-push and re-clone every copy), or keep history and disclose that the S-heldout items were exposed in history. ADR-004 already treats them as exposed to the developer, which is why they are S-heldout and not Blind; the purge matters for keeping them away from anyone else and from crawlers if the repository is ever made public (ADR-005).

## 5. Leakage prevention at agent runtime

The agent must not be able to read sealed material, directly or through its tools.

- **Filesystem allowlist.** The agent process reads only the input PDF, `config/`, `prompts/`, its own run directory and the cassette directory. All of `eval/` is outside the allowlist; so is any `unseal.py` temporary directory (the eval runner passes the agent only the single PDF it should review, copied into the run directory).
- **The search tool blocks the repo's domain.** `config/url_policy.yaml` has a deny list enforced by the ToolGateway for every search query result, page fetch and browser navigation: `github.com/<owner>/<repo>` and everything under it, `raw.githubusercontent.com/<owner>/<repo>`, `codeload.github.com/<owner>/<repo>`, `gist.github.com/<owner>`, plus any mirror the user creates. Results pointing at a denied URL are dropped before the model sees them and logged as `blocked_by_policy`. This holds even though a private repository is not indexed, because the policy must still be correct if ADR-005 changes or a mirror appears.
- **Canary tripwire.** The ToolGateway scans every tool result for the canary GUIDs of all sealed splits. A hit drops the result, records a leakage event in the manifest and fails the run in eval mode.
- **Query filter.** Outgoing search queries are checked against each sealed split's title and item names (held in the manifest as salted hashes of normalised n-grams, so the filter itself does not reveal them).
- **Static leakage audit** before every held-out or Blind evaluation: `scripts/leakage_grep.py` (methodology §3.2: distinctive-term grep, 13-gram overlap, canary grep) over prompts, config, code, cassettes and S-dev keys. Results go in the report's leakage table.

## 6. Interim rule (until sealing is implemented)

Effective immediately:

1. Nobody opens anything under `eval/blind/` (now S-heldout): not the developer, not a coding-assistant session, not a script. If a tool or session needs a file list of `eval/`, it lists names only.
2. No prompt, config, test fixture or research note may quote or paraphrase those items. Existing quotations in the audit stay as they are; do not add more.
3. No agent run, pilot or rehearsal uses those items. DEMO-05 rehearsals use the rehearsal pool (ADR-004).
4. Every access that has already happened is recorded in `eval/blind/ACCESS_LOG.md` when it is created: the item briefs at authoring time, and the research audit's skim on 2026-10-02 (exposure, not an evaluation; it does not count against the 3-evaluation budget but is disclosed).
5. Sealing (`seal.py`, the hook, the allowlist) is implemented **before** the first agent code that could read the filesystem is written, and the plaintext is removed from the working tree in the same change.
6. If the interim rule is broken, record it in the access log and report it as a limitation; do not quietly continue.
