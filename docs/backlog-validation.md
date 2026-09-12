# Backlog validation

Run from `omni-backend`:

```powershell
& ..\.agent\validate-backlog.ps1 -AllowCompleted
```

Validation checks task IDs, spec/index alignment, dependency existence/order/cycles,
metadata references, timing bounds, and external-wait declarations.

Known external gates remain separate from code validation:

- Real Meta payload capture and deployed-provider fixtures.
- Sustained load run plus drain and measured latency.
- Encrypted backup provider configuration and isolated restore drill.

Backend acceptance tests remain executable locally with:

```powershell
$env:PYTHONPATH='.'
.\.venv\Scripts\python.exe -m pytest -q
```
