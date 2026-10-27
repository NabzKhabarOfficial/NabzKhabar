# Claude Code / ECC Instructions

Before acting, read `AGENTS.md` and follow its rules. Use installed Everything Claude Code (ECC) skills, hooks, commands, and specialized subagents when they are available in this workspace; do not assume ECC components are installed merely because this file exists.

For non-trivial tasks, delegate independent audit, implementation, and test/review work to available subagents. Keep one lead responsible for the plan, integration, tests, and final report. If the current runtime exposes no subagent/team capability, work sequentially and say so accurately.

Do not treat FCC fallback routing as a simultaneous multi-model team: a fallback chain generally retries another provider/model after a failure or routing decision; it does not make every model review the same task. Use explicit subagent calls for collaboration where supported. Do not change FCC configuration or consume paid APIs without explicit approval.

Always inspect recent GitHub Actions failures and relevant source before editing. Keep changes scoped, run tests, and report evidence.