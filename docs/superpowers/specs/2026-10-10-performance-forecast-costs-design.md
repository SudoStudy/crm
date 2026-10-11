# Approved Performance forecast and Twilio costs

Scope approved by Arslan: editable expected monthly revenue, probability (including explicit zero), and expected closing month using the existing expected_closure_date field. Actual attainment remains based on actual MRR and latest Won history; open weighted pipeline is expected MRR times probability, restricted to the selected month/quarter. Undated deals remain visible as needing timing, but contribute zero until scheduled. Reps edit only their own writable deals; managers may edit writable team deals. No target values are changed.

Show platform-originated Twilio voice charges in Performance and beside call recordings. Shared aggregate costs are visible to CRM users without exposing other reps' deal or activity details. Call details retain existing read permissions. Reconcile stored Twilio parent and child legs, deduplicated by SID; null/unavailable prices are pending, never treated as confirmed free. Exclude Bland calls, number rental, recording/storage and unrelated account calls. Keep currency explicit and do not convert non-USD charges implicitly. Provider access stays server-side using existing CRM Twilio Settings, never browser secrets.

No live test calls. No automatic redial. No production writes, merges or deployment as part of building this branch. A new PR requires explicit merge approval.
