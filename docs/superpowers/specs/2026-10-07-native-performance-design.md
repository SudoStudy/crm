# Native CRM Performance

Approved by the user on 2026-10-07: implement the HTML preview at
`/Users/arslan/.gstack/projects/SudoStudy-crm/designs/performance-20261007/finalized.html`
inside CRM and roll out this page first. Calling ideas are out of scope.

## Page and calculations

- `/crm/performance`, accessible via CRM sidebar on desktop and mobile.
- Rep selector (manager only; reps default to self), month/quarter and period navigation.
- USD monthly new-MRR target, Won MRR, attainment, remaining; progress bar.
- Quarterly targets sum the three monthly targets. Missing targets are visible, not implicit zero.
- Won MRR uses actual `deal_value` of currently Won deals and latest Won transition's `from_date`.
  Never fall back to `closed_date` or count expected MRR as actual revenue. Use current deal owner.
- Weighted pipeline includes all current open deals, expected MRR × probability / 100;
  coverage divides by remaining target, explicitly not a dated monthly forecast.
- Currency mismatches, missing Won history and zero/missing targets have explicit warnings.
- Contributing deal table links to real CRM records. Paginate rather than silently truncating.
- Daily activity over last seven calendar days in site timezone, independently of target period.
  Day-grouped compact expandable rows, distinct icons, source/actor/time/details/record link.
  Sources: lead/deal/task Versions, comments, notes, call logs, tasks, communications;
  use actual caller/receiver identity for calls, not webhook creator. Distinguish performed-by
  from owned-record scope. Respect record read permissions. Hide routine derived-field noise.
  Enable future task version tracking without inventing missing historical actions.
- Existing `CRM Sales Target` rows and schema survive. Managers can edit one monthly target
  and optionally repeat it for future months with a defined effective month. Never overwrite
  historical rows. Quarterly editing updates one explicitly selected month's target, not all months.
  Rep-only target access also applies to native list/document APIs, not only the Performance page.
- No new calling behavior, no changes to Twilio configuration, no paid/live call tests.

## Rollout

Branch from the deployed keypad baseline, not newer upstream. Test/review, create PR but do not
merge without specific PR authorization. Deploy branch directly, with backup and CRM-only source
change on bench-47516 / crm-tdu-mvn.z.frappe.cloud (sales.sudostudy.com). Preserve other apps and
commits. Verify API metrics against an independent CRM read and page rendering after site migration.
The unused standalone sales app source can remain on the bench until the native page is verified;
no app uninstall or data deletion is part of this initial page rollout.
