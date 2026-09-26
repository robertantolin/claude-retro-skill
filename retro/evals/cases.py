"""Nine golden cases as data. Each case: transcript turns, store entries, optional findings
rows, optional pre-seeded candidates and settings, and the expectations the runner checks.
Synthetic throughout: no real names or paths."""

STORE_BASE = {
    "release-notes-format": "Release notes list changes by user impact, not by commit; verified by reading the last three.",
    "csv-export-encoding": "Exports for the finance team must be UTF-8 with BOM or Excel garbles accents.",
    "cron-timezone": "Scheduled jobs are declared in UTC; the dashboard shows local time.",
}

CASES = {
    "self-caught": {
        "turns": [
            ("user", "Add a retry to the sender when the mail API returns 429."),
            ("assistant", "I added a retry with a fixed 1 second delay. On re-reading the API docs I see they ask for the Retry-After header, so I changed it to honour that header before you saw the first version. Tests pass."),
            ("user", "Thanks, looks good."),
        ],
        "store": STORE_BASE,
        "settings": {"approve_always": []},
        "expect": {"empty_retro": True, "new_entries": 0, "quotes": [],
                   "ledger_decisions": ["none"]},
    },
    "one-correction": {
        # Project-only correction: an operational quirk of this project's own retry queue, not
        # discoverable by reading the repo and not a user-general preference, so the lesson
        # routes to the project memory/ store (not the approval-gated global CLAUDE.md) and
        # new_entries can pass.
        "turns": [
            ("user", "Set up the retry logic for send failures."),
            ("assistant", "Done. I configured retries to run every 5 minutes indefinitely until the send succeeds."),
            ("user", "This project's retry queue is capped at 3 attempts per message; a 4th attempt corrupts the dedupe table."),
            ("assistant", "Understood, capped retries at 3 attempts to match the dedupe constraint."),
        ],
        "store": STORE_BASE,
        "settings": {"approve_always": ["store-write"]},
        "expect": {"empty_retro": False, "new_entries": 1,
                   "quotes": ["retry queue is capped at 3 attempts"]},
    },
    "two-corrections": {
        # Two project-only corrections, both operational quirks of this project's send pipeline
        # (retry cap, report counting rule), so both lessons route to the project memory/ store.
        "turns": [
            ("user", "Set up the retry logic for send failures."),
            ("assistant", "Done. I configured retries to run every 5 minutes indefinitely until the send succeeds."),
            ("user", "This project's retry queue is capped at 3 attempts per message; a 4th attempt corrupts the dedupe table."),
            ("assistant", "Fixed: capped retries at 3 attempts."),
            ("user", "Now write the send report."),
            ("assistant", "Report written, counting every send attempt including retries."),
            ("user", "This project's send report must count unique messages only; retries of the same message must not be counted twice."),
            ("assistant", "Fixed: the report now dedupes by message ID before counting."),
        ],
        "store": STORE_BASE,
        "settings": {"approve_always": ["store-write"]},
        "expect": {"empty_retro": False, "new_entries": 2,
                   "quotes": ["retry queue is capped at 3 attempts",
                              "send report must count unique messages only"]},
    },
    "recurrence": {
        "turns": [
            ("user", "Write the weekly send report for the marketing lead."),
            ("assistant", "Report written. It covers the SMTP handshake timings, TLS versions negotiated, and the bounce webhook payload schema."),
            ("user", "Explain things in a less technical manner. The marketing lead does not read protocol details."),
            ("assistant", "Rewritten: what was sent, how many opened, what bounced, what to do next."),
        ],
        "store": {**STORE_BASE,
                  "plain-language-reports": "Reports for non-technical readers state outcomes and next steps; protocol and tooling detail goes in an appendix or is dropped."},
        "settings": {"approve_always": []},
        "expect": {"empty_retro": False, "new_entries": 0, "cites": "plain-language-reports",
                   "mechanism": True, "quotes": []},
    },
    "findings-open": {
        "turns": [
            ("user", "Bump the dependency versions and run the tests."),
            ("assistant", "Bumped four packages, all 212 tests pass."),
            ("user", "Great."),
        ],
        "store": STORE_BASE,
        "settings": {"approve_always": []},
        "findings": [
            ("recur", "mem:{slug}/csv-export-encoding", "the finance export lost the accents again", "high"),
            ("recur", "mem:{slug}/cron-timezone", "the job ran at 3am local not 3am UTC", "medium"),
        ],
        # Two open findings from an earlier session must be dealt with, not ignored. Either
        # outcome counts: raised as a proposal that gets no decision in print mode, or judged
        # No action and resolved with a reason. Nothing is written to the store either way.
        "expect": {"empty_retro": False, "new_entries": 0, "quotes": [],
                   "findings_handled": ["F0001", "F0002"]},
    },
    "candidate-confirms": {
        # A prior session logged the same observation once; this session repeats it, so the
        # candidate confirms and a proposal is raised.
        "turns": [
            ("user", "Build the weekly status memo from the partner research file again."),
            ("assistant", "Done. I opened the partner research file, pulled the three sections by hand, and assembled the memo."),
            ("user", "Looks right, thanks."),
        ],
        "store": STORE_BASE,
        "settings": {"approve_always": []},
        # The seeded key is in the format the classify prompt asks for: 3 to 5 lower-case nouns,
        # artifact first then action. candidates.similar compares stemmed content words by
        # containment, so a key of any length that shares those nouns matches this one.
        "candidates": [("repeat-manual", "status memo manual assembly", "pulled three sections by hand", 1, "2026-08-28")],
        "expect": {"empty_retro": False, "new_entries": 0, "quotes": [], "candidate_finding": True,
                   "ledger_decisions": ["no-decision"], "candidate_parked_ok": True},
    },
    "hard-number": {
        # Four revision rounds on one artifact in a single session surfaces immediately.
        "turns": [
            ("user", "Draft the two-page summary."),
            ("assistant", "Drafted. It is about 180 words over; trimming."),
            ("user", "Still three pages in Word."),
            ("assistant", "Trimmed again."),
            ("user", "Still over."),
            ("assistant", "Trimmed a third time."),
            ("user", "Now it fits."),
            ("assistant", "Fourth version confirmed at two pages."),
        ],
        "store": STORE_BASE,
        "settings": {"approve_always": []},
        "expect": {"empty_retro": False, "new_entries": 0, "quotes": [], "candidate_finding": True,
                   "candidate_confidence": "high", "ledger_decisions": ["no-decision"]},
    },
    "no-decision": {
        # One project-only correction with no approve-always: the lesson is proposed, the prompt
        # cannot be answered in print mode, so nothing is written and the row says no-decision.
        "turns": [
            ("user", "Set up the retry logic for send failures."),
            ("assistant", "Done. I configured retries to run every 5 minutes indefinitely until the send succeeds."),
            ("user", "This project's retry queue is capped at 3 attempts per message; a 4th attempt corrupts the dedupe table."),
            ("assistant", "Understood, capped retries at 3 attempts to match the dedupe constraint."),
        ],
        "store": STORE_BASE,
        "settings": {"approve_always": []},
        "expect": {"empty_retro": False, "new_entries": 0, "quotes": ["retry queue is capped at 3 attempts"],
                   "ledger_decisions": ["no-decision"], "diff_file": True},
    },
    "over-cap": {
        # A clean session, but the store holds 21 entries, one over the cap. The retro must
        # propose a store-delete on its own (no lesson to pair it with) and the run is not empty.
        # In print mode the delete gets no decision, so the store is untouched and the row says
        # no-decision with kind store-delete.
        "turns": [
            ("user", "Bump the dependency versions and run the tests."),
            ("assistant", "Bumped four packages, all 212 tests pass."),
            ("user", "Great."),
        ],
        "store": {**STORE_BASE, **{f"filler-lesson-{i:02d}": f"Filler lesson {i}: the nightly job number {i} writes its log to the shared folder."
                                   for i in range(1, 19)}},
        "settings": {"approve_always": []},
        "expect": {"empty_retro": False, "new_entries": 0, "quotes": [], "store_unchanged": True,
                   "ledger_decisions": ["no-decision"], "ledger_kinds": ["store-delete"], "diff_file": True},
    },
}
