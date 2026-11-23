# Allowed values for review/human_audit.csv

Lists (auth_methods, api_styles) are separated with `;` e.g. `oauth2;api_key`.

| Field | Allowed values |
|---|---|
| auth_methods | oauth2, api_key, bearer_token, basic, jwt, hmac_signature, other, none |
| credential_access | self_serve_free, self_serve_trial, paid_plan, admin_approval, partner_or_sales_gated, open_source_local, unclear |
| api_styles | rest, graphql, soap, websocket, sdk_or_cli_only, none |
| official_mcp | yes, no, unclear |
| buildability | ready_now, ready_with_constraints, outreach_required, not_buildable_now |
| primary_blocker | none, credential_gate, admin_or_partner_approval, no_public_api, narrow_or_read_only_api, unstable_or_undocumented, local_only, compliance_or_scope, unclear |

**Meaning of the tricky ones**
- self_serve_free: any developer can sign up and get working credentials for free (free plan, dev account or sandbox).
- self_serve_trial: only works during a time-limited trial.
- paid_plan: API access needs a paid plan or tier.
- admin_approval: needs app review / marketplace approval / workspace admin before real use.
- partner_or_sales_gated: needs a partnership, contact-sales or enterprise contract.
- ready_now: public documented API AND self-serve credentials. primary_blocker must then be `none`.
- ready_with_constraints: buildable, but with a limit (paid tier, app review, narrow API).
- outreach_required: we must talk to the vendor first.
- official_mcp = yes only when the vendor itself publishes the MCP server.

**status column**: `confirmed` (agent was right on every field), `corrected` (you changed at least one value), `unresolved` (docs don't settle it; this row is left out of scoring).
