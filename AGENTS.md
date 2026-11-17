# ExecPlans

When writing complex features or significant refactors, use an ExecPlan (as described in .agent/PLANS.md) from design to implementation.

Always get the user's approval of the ExecPlan before starting implementation.

## Language

All non-code artifacts must be written in Russian unless the user explicitly asks otherwise.

This includes:
- ExecPlans
- progress updates
- decision logs
- retrospectives
- final summaries
- PR descriptions
- review notes
- task documentation

Keep code identifiers, public API names, filenames, commands, logs, and error messages in their original language.
For Python code, keep comments and docstrings in English.


## ExecPlan usage

Use an ExecPlan only for complex or risky tasks.

Use an ExecPlan when the task includes at least one of:
- significant feature work
- significant refactoring
- database migrations
- changes across multiple layers
- API contract changes
- background jobs or async flows
- security/auth/payment-related logic
- performance-sensitive changes
- unclear requirements that require research

Do not use an ExecPlan for:
- small bug fixes
- simple validation changes
- copy/text changes
- renaming
- formatting
- adding one small test
- changing one isolated function
- mechanical cleanup

If the user says "без ExecPlan", "no ExecPlan", "quick fix", or "just implement", do not create or update an ExecPlan.
Proceed directly with the smallest safe change.

After execplan implementation or atomic updates remind me to commit: from you - text for commit, from me - make commit. Commits in english, one short string

## Tests

Write tests only for meaningful user-facing and business behavior, as well as regressions that could compromise it.

Do not add tests solely for implementation details—such as whether or at what level something is logged, internal method calls, renaming, or mechanical component wiring—unless they are part of an explicit contract or pose a significant risk.
