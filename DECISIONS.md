# DECISIONS

**1. PostgreSQL for the database**
Alternative: SQLite.
PostgreSQL is the production-appropriate choice for a multi-tenant app with real concurrent writers and indexed queries. SQLite has no row-level locking and would be the wrong choice once more than one process touches the data. The test suite uses SQLite in-memory (`test_settings.py`) so tests run fast with zero external dependencies — the reconciliation logic is pure-function tested anyway, so the DB engine matters less there.

**2. Materialise disagreements into a DB table rather than computing on request**
Alternative: run the comparison query on every API call.
With 120 rows either approach is instant, but materialising separates the import/reconcile step from the serve step, makes the API trivially fast, and lets us store a `created_at` timestamp showing when the reconciliation last ran.

**3. Keep reconciliation logic in a pure function (`find_disagreements`) with no ORM dependency**
Alternative: put the logic directly inside a management command or view.
A pure function that takes dicts and returns dicts can be tested without a database, without migrations, and without Django's test runner overhead. The ORM bridge (`reconcile_from_db`) is a thin wrapper around it.

**4. Store `record_ref_raw` alongside the resolved FK in `SystemBEntry`**
Alternative: normalise the ref on import and discard the original.
The raw string is evidence. If normalisation is wrong, the original is there to debug from. It is also what gets shown in the UI's "ref" column so users can see the dirty value that caused the problem.

**5. Log dirty-ref normalisations as INFO-level ImportIssues**
Alternative: only log failures (unresolvable refs).
A successful normalisation (`rec1034` → `REC-1034`) is not an error, but it is worth knowing about — it means the upstream system is inconsistent. INFO-level keeps it visible without inflating the error count.

**6. Compare System B `value` against System A `total_value` (not `base_value`)**
Alternative: compare against `base_value`.
Looking at the data: `ENT/2026/4001` has value `88969.92` which matches `REC-1001`'s `total_value` exactly. The `base_value` is `69507.75`. System B records the final amount, not the pre-adjustment amount. This is confirmed by the majority of matching rows.

**7. Tenant isolation enforced at the query layer, not the data layer**
Alternative: physically separate tables or schemas per org.
A single schema with `org_id` on `Location` and consistent filtering in every query is simpler to operate, simpler to migrate, and adequate for this scale. Separate schemas would be worth revisiting for strict regulatory isolation requirements.

**8. Reconciliation runs globally; tenant filtering happens at the API layer**
Alternative: reconcile per-org in isolation.
Reconciling per-org misses a genuine class of disagreement: a System A record in `ORG-A` matched by `record_id` to a System B entry filed under `ORG-B` (e.g. `REC-1077`/`ENT-4077` in the real dataset). The per-org approach incorrectly flags `REC-1077` as `MISSING_IN_B` and silently drops the matching B entry — the exact scenario the brief's "few dozen rows anyone cares about" is testing. The fix is to compare records globally so the match is found by `record_id`, then store the disagreement anchored to the System A location. The API layer applies `location__org_id` filtering at query time so tenants only see their own data; no data ever crosses the boundary at the HTTP layer.
