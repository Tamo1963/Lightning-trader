# Lightning Trader

Quantitative options-buying engine for Nifty 50 and Bank Nifty (DhanHQ), with Jev AI as a
single, bounded approve/reject gate. Code generates candidates, estimates edge, sizes risk and
executes. Jev can only veto. It can never override the risk engine.

Status: **foundation spec (v0.1, draft)**. Nothing here trades yet.

- `docs/foundation-spec.md`: scope, gates, risk rules, backtest protocol, acceptance criteria
- `schemas/jev_request.schema.json`, `schemas/jev_response.schema.json`: Jev contract
- `schemas/audit.sql`: decision and trade audit tables
- `config/risk.defaults.yaml`: hard-coded risk limits (placeholders to tune before freeze)
