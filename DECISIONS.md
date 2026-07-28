# DECISIONS

**1. SQLite for the database**
Alternative: PostgreSQL.
SQLite is zero-config and the brief is explicit that performance is not being tested (120 rows). PostgreSQL would be the right call for anything production-shaped.

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
