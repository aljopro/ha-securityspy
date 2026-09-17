# Sprint Change Proposal — Story 1.21 unmet sub-ACs (follow-up)

**Date:** 2026-09-16
**Trigger:** Re-review of Ben Software forum thread [4922](https://bensoftware.com/forum/discussion/4922/suggestion-an-integration-tokens-screen-for-third-party-clients) (already tracked in memory `ben-software-token-request.md`), specifically the Sept 16 follow-up's concern #3: whether the observed `API_[A-Za-z0-9]{32}` key shape is reliable enough for redaction/type-identification, given only 5 samples and no vendor confirmation.

## 1. Issue Summary

Story 1.21 (spike, done — see `spec-1-21-spike-do-securityspy-api-keys-replace-credentials.md`) shipped without exercising one of its own acceptance criteria: epics.md originally required (lines 846-849) that "the write-up states what happens when an ordinary account password itself begins with `API_`, so detection by prefix never locks out such a user." The delivered research doc (`research/securityspy-api-keys-6.22.md`) records the observed key shape and the password-*equals*-key lock-out, but never tests a password that merely *begins with* `API_` without matching the full shape. Two other sub-ACs from the same story were explicitly left open by design: key regenerate/delete behavior, and behavior on a camera the account cannot see.

Two of the three deferred items from Story 1.21's review pass (raw `auth=` query-string rejection, password-equals-key lock-out) were already closed by follow-up commits `1d5ebd90` and `974a3098`. This proposal addresses the remaining, distinct gap: the unmet AC and the two still-open sub-ACs.

## 2. Impact Analysis

- **Epic Impact:** Epic 1 only. Epic 1 is not blocked and its retrospective already ran; this is a small follow-up story appended after it, not a reopening of epic scope.
- **Story Impact:** No existing story's AC changes. One new story added: **1.22**.
- **Artifact Conflicts:** None. PRD Open Question 11 correctly remains "reopened" — nothing here justifies adopting AD-13 Option 2 (relay authenticates upstream with a key) yet; that remains a future decision gated on its own correct-course, per Story 1.21's and 1.22's own ACs.
- **Technical Impact:** None to production code. Same boundary as 1.21: recommendation only, no implementation of shape-based detection inside this story.

## 3. Recommended Approach

**Direct Adjustment (Option 1 of 3 evaluated):** add Story 1.22 to Epic 1, testing the three remaining gaps live where feasible, and making one explicit recommendation (adopt shape-based key detection now, or keep deferring). Rollback was not viable (nothing to revert) and MVP review was not viable (no MVP impact).

- Effort: Low
- Risk: Low
- Timeline impact: negligible — one small spike-style story

## 4. Detailed Change Proposal

**Artifact: `_bmad-output/planning-artifacts/epics.md`**

Added Story 1.22 under Epic 1, after Story 1.21, before the Epic 2 heading. Full text:

> ### Story 1.22: Close Story 1.21's unmet sub-ACs and decide on shape-based key detection
>
> As a builder, I want Story 1.21's outstanding acceptance criteria exercised live and a final call made on shape-based API key detection, so that PRD Open Question 11's evidence base is complete before any future story adopts a key-authentication path. *(PRD Open Question 11; follows Story 1.21)*
>
> **Acceptance Criteria:**
> 1. A password beginning with `API_` but not matching the full 32-char base62 shape is tested; result compared against the existing password-equals-key finding.
> 2. Key regenerate/delete is tested if it can be done without disrupting other test accounts; if not safely testable, the write-up says why and leaves the sub-AC open.
> 3. A lower-permission account's key is tested against a camera it cannot see; same open-if-untestable rule.
> 4. The write-up makes one recommendation (adopt shape-based detection now / keep deferring) with rationale, implementing neither; PRD Q11 status is updated only if the recommendation is to close it.

Rationale: closes a real gap between what Story 1.21 promised and what it delivered, without expanding scope beyond what the original story already committed to.

**Artifact: `_bmad-output/implementation-artifacts/sprint-status.yaml`**

Added under `development_status`, Epic 1, immediately after 1.21:
```
1-22-close-story-1-21s-unmet-sub-acs-and-decide-on-shape-based-key-detection: backlog
```

## 5. Implementation Handoff

**Change scope: Minor.**

- **Route to:** Developer agent (bmad-dev-auto or bmad-quick-dev) for direct implementation once Story 1.22 is picked up.
- **Deliverables:** Updated `research/securityspy-api-keys-6.22.md` covering the three remaining sub-ACs, live test additions where testable (mirroring Story 1.21's pattern), and one explicit adopt/defer recommendation.
- **Success criteria:** All three sub-ACs are either exercised live or explicitly documented as untestable with reason; no production code changes beyond what Story 1.21 already boundaries permit; PRD Q11 status updated only if the recommendation says to close it.

## Approval

Approved by Jensen (2026-09-16), batch mode, no revisions requested.
