# Sprint Change Proposal — Reopen PRD Open Question 11 (SecuritySpy API keys)

- **Date:** 2026-09-16
- **Author:** Jensen (via bmad-correct-course)
- **Mode:** Batch
- **Scope classification:** Minor (planning-artifact edits plus one spike story; no change to delivered code)

## 1. Issue Summary

**Trigger:** a vendor change, not a story defect. On 2026-09-13 we asked Ben Software for an "Integration tokens" screen ([forum thread 4922](https://bensoftware.com/forum/discussion/4922/suggestion-an-integration-tokens-screen-for-third-party-clients/p1)). On 2026-09-15 Ben replied that **SecuritySpy 6.22b9 (beta) ships API keys**:

- Created in Settings → Web account management → "API Key".
- Used in URLs as `&auth=API_<random>`.
- A key cannot open the web interface, manage accounts, or control the Mac.
- It is a random string, not derived from the username and password.
- **Not included:** per-camera or per-resource limits (the key carries its account's permissions). Created/last-used dates are a possible later addition.

**Category:** strategic change in the platform. PRD Open Q11 was closed on 2026-09-13 with the note "Revisit only if SecuritySpy ships an HTTP token-issuing endpoint." What shipped is a GUI-issued, per-account key rather than an HTTP endpoint, but it removes the reason Q11 was closed: tokens no longer need a manual paste per camera.

**Evidence status:** vendor statement only. Nothing is verified against a live 6.22b9 server. Open unknowns: whether the key works over RTSP as well as HTTP, on `++image`, on `++eventStream`, and how it interacts with a restricted account's permissions.

## 2. Impact Analysis

### Checklist results

| Item | Status | Finding |
|---|---|---|
| 1.1 Triggering story | [x] | None. The trigger is external; related delivered stories are 1.19, 1.20, 2.6. |
| 1.2 Problem statement | [x] | Q11's closing condition has effectively been met; the relay design's justification needs re-examination. |
| 1.3 Evidence | [!] | Vendor reply only. Verification is the spike below. |
| 2.1 Current epic viable | [x] | Epics 1 and 2 remain complete as built. The relay works and satisfies FR-22 today. |
| 2.2 Epic changes | [x] | Add one spike story to Epic 1 (library owns wire format and auth, AD-13). |
| 2.3–2.5 Future epics | [x] | No effect on Epics 3–7. Epic 7's release could later carry a 6.22 minimum-version note if keys are adopted (ties to Open Q8). |
| 3.1 PRD conflicts | [!] | Open Q11 text says "Resolved"; must say reopened. FR-22 is unchanged until the spike reports. |
| 3.2 Architecture conflicts | [!] | AD-13 item 3 and the deferred-decisions entry describe tokens as superseded; mark under review. AD-13 must also classify the API key as a secret (it is one). |
| 3.3 UX | [N/A] | No custom UI. A future config-flow field would be a later story. |
| 3.4 Other artifacts | [x] | Research note for spike results; memlogs record the reopening. |
| 4.1 Direct adjustment | [x] | Viable: reopen + spike. |
| 4.2 Rollback | [N/A] | Nothing to roll back. The relay stays and is still the only path for SecuritySpy < 6.22. |
| 4.3 MVP review | [N/A] | MVP unaffected. |

### Epic impact
- **Epic 1:** gains Story 1.21 (spike). Epic status stays `in-progress`; its retrospective is already done, so the spike's outcome is recorded in its own write-up rather than a re-run retro.
- **Epic 2:** no change now. Story 2.6 may be revised after the spike.

### Artifact conflicts
- PRD §13 Open Q11, architecture AD-13 item 3 and the deferred-decisions list.

### Technical impact
- None until the spike reports. **Security note, independent of the outcome:** an API key is a secret. Even though it is safer than `username:password`, a key in an RTSP URL handed to Home Assistant/go2rtc would reach stream sources, logs and diagnostics. So "use keys" does not automatically mean "drop the relay"; the spike must answer that trade-off explicitly.

## 3. Recommended Approach

**Direct adjustment: reopen Q11 and gate any design change on a spike.**

- **Rationale:** the relay is built, tested and meets FR-22. Changing design on an unverified beta would risk rework. **The relay stays regardless of the outcome** (Jensen, 2026-09-16): servers older than 6.22 have no API keys, so username/password through the relay remains a supported path for the foreseeable future. A short spike against 6.22b9 turns the vendor statement into facts; a follow-up correct-course then decides only whether keys become an *additional* option: the relay authenticates upstream with a key when one is configured (smaller blast radius, same public surface), with or without also offering key-bearing URLs directly to consumers. Retiring the credential path is out of scope until a minimum-version decision (Open Q8) makes 6.22 the floor.
- **Effort:** spike ≈ half a day against a test server. Artifact edits are small.
- **Risk:** low. The main risk is designing around a beta feature that changes before release; the spike records the exact build tested.
- **Timeline:** no effect on Epic 3–7 sequencing. The spike can run any time; it does not block anything in flight.

## 4. Detailed Change Proposals

### 4.1 PRD — §13 Open Question 11

File: `prds/prd-ha-securityspy-2026-08-09/prd.md`

**OLD:**
> 11. **Resource-scoped auth tokens.** *Resolved 2026-09-13 — superseded by the local relay.* Tokens are verified real and scoped to one endpoint on one camera (research 6.21 §5.16.1), but no HTTP endpoint issues them, so they would cost a manual paste per camera. FR-22 instead routes live video through a relay inside the API Library that attaches credentials only on the upstream connection. Revisit only if SecuritySpy ships an HTTP token-issuing endpoint — requested from the vendor as an "Integration tokens" screen: [forum thread 4922](…).

**NEW:**
> 11. **Resource-scoped auth tokens → per-account API keys.** *Reopened 2026-09-16.* Originally resolved 2026-09-13 in favour of the local relay: the only tokens then were scoped to one endpoint on one camera (research 6.21 §5.16.1) and nothing issued them over HTTP, so they would cost a manual paste per camera. In reply to our request ([forum thread 4922](…)), SecuritySpy 6.22b9 (beta) added **API keys**: created per account under Settings → Web account management, passed as `auth=API_…`, unable to reach the web interface, manage accounts or control the Mac, and carrying the account's own permissions (no per-camera or per-resource limit). Unverified. Story 1.21 tests them against a live server; its findings decide whether keys are added as an option alongside username and password. The relay and the credential path remain supported regardless, because servers older than 6.22 have no keys. Until then FR-22 stands unchanged.

**Rationale:** records the trigger and keeps FR-22 authoritative until evidence exists.

### 4.2 Architecture — AD-13 item 3 (append)

File: `architecture/architecture-ha-securityspy-2026-08-09/ARCHITECTURE-SPINE.md`

**ADD** after the sentence ending "…is redacted like any other.":
> **Under review (Jensen, 2026-09-16):** SecuritySpy 6.22b9 adds per-account API keys (`auth=API_…`, PRD Open Q11 reopened). An API key is a secret under this rule and is redacted like a password. Whether keys change the relay's upstream authentication or the consumer-facing surface is decided only after Story 1.21 verifies them; until then this amendment stands. The relay's credential-based upstream path is retained in any outcome, for servers without API keys.

**Rationale:** the anonymizer must treat the new credential type as a secret whatever the design outcome.

### 4.3 Architecture — deferred decisions entry

**OLD:**
> - **Resource-scoped auth tokens** — superseded 2026-09-13 by the library RTSP relay (AD-13 item 3, FR-22); tokens need a manual paste per camera because nothing issues them over HTTP. Revisit only if SecuritySpy ships a token-issuing endpoint (PRD Open Q11).

**NEW:**
> - **Resource-scoped auth tokens / API keys** — superseded 2026-09-13 by the library RTSP relay (AD-13 item 3, FR-22) because tokens needed a manual paste per camera. **Reopened 2026-09-16:** SecuritySpy 6.22b9 adds per-account API keys (PRD Open Q11); spike-gated on Story 1.21. Any adoption is additive; the relay and credential path stay for servers older than 6.22.

### 4.4 Epics — new Story 1.21 (after Story 1.20)

File: `epics.md`

> ### Story 1.21: Spike — do SecuritySpy API keys replace credentials on every path the library uses?
>
> As a builder,
> I want to know exactly what a SecuritySpy 6.22 API key can and cannot authenticate,
> So that PRD Open Question 11 is decided on evidence rather than a forum reply. *(PRD Open Question 11; informs FR-22, FR-42)*
>
> **Acceptance Criteria:**
>
> **Given** a test server running SecuritySpy 6.22b9 or later and an API key created for a least-privileged account
> **When** the key is sent as `auth=API_…` to `++systemInfo`, `++image`, `++eventStream`, capture media, and the RTSP `stream` URL
> **Then** each path's result (accepted, refused, status code) is recorded, including whether a header form works in place of the query parameter
> **And** the same paths are tried with the key supplied as the password (HTTP `Authorization: Basic`, and RTSP authentication), with both the account's username and an empty or arbitrary username, since the settings screen says the key can be entered wherever software asks for a password
>
> **Given** the same key
> **When** it is used on a camera the account may not view and on an endpoint the account lacks permission for
> **Then** the result confirms whether the key carries exactly the account's permissions and the library's `401`-means-permission rule still holds
>
> **Given** keys are displayed with an `API_` prefix
> **When** several keys are generated and inspected
> **Then** the prefix, length and character set are recorded, so the library can tell a key from a password by shape (for choosing how to authenticate and for redacting keys in logs and diagnostics)
> **And** the write-up states what happens when an ordinary account password itself begins with `API_`, so detection by prefix never locks out such a user
> 
> **Given** the settings screen shows one key per account, displayed only at creation, with regenerate and delete controls
> **When** the key is regenerated or deleted and the old key is used again
> **Then** the observed response is recorded, so the library can map it to its existing exception types
>
> **Given** the findings
> **When** they are written up in `research/` and the architecture memlog
> **Then** they state the SecuritySpy build tested and compare, against AD-13's egress threat model, the options for adding keys alongside the existing credential path — no change; relay authenticates upstream with a key when one is configured; that plus key-bearing URLs offered directly to consumers
> **And** every option keeps the relay and username/password authentication working for servers without API keys
> **And** they recommend one option, which is adopted only through a follow-up correct-course, not inside this story
>
> **Given** no 6.22 server can be obtained
> **When** the spike cannot run
> **Then** Open Question 11 stays open and the relay remains the design, with no further decision needed

### 4.5 Sprint status

File: `implementation-artifacts/sprint-status.yaml` — add under Epic 1:

```yaml
  1-21-spike-do-securityspy-api-keys-replace-credentials: backlog
```

### 4.6 Memlogs

Append one `(change)` line to the PRD and architecture `.memlog.md` files recording the reopening and pointing to this proposal.

## 5. Implementation Handoff

- **Scope:** Minor.
- **Artifact edits (4.1–4.6):** applied directly on approval.
- **Story 1.21:** Developer agent via `bmad-create-story` then `bmad-dev-story` (or bmad-loop), but it needs a human to install 6.22b9 and create an API key first. Keys must not be committed or pasted into logs.
- **After the spike:** run `bmad-correct-course` again with its findings if it recommends changing FR-22, Stories 1.19/2.6, or the config flow.

**Success criteria:** Q11 reads as open with Ben's reply recorded; AD-13 classifies API keys as secrets; Story 1.21 is in `epics.md` and `sprint-status.yaml` as backlog; no delivered code or FR-22 behaviour changed; every artifact states the relay and credential path stay supported for servers older than 6.22.
