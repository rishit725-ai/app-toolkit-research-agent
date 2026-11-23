# Headline
Most of these 100 apps can become agent toolkits today: 77% give developers self-serve credentials, 62 are buildable now, and OAuth2 is the dominant auth (66 apps). The real friction is access gating, not missing APIs, and gating is also where the agent was least accurate.

## Patterns
- **Auth:** OAuth2 dominates (66 apps), and half the apps (50) also offer an API key (84 accept an API key or bearer token) for single-user use, so toolkits should support both.
- **Self-serve vs gated:** Communications, Developer/Infra and Productivity are fully self-serve (10 of 10 each). Marketing/Ads, Ecommerce and Finance are the most gated (4 of 10 each).
- **Most common blocker:** credential gates such as paid plans or trials (19 apps), then admin or partner approval (9).
- **MCP is going mainstream:** the agent found an official MCP server for 53 vendors, and the hand check showed it still under-counts recent launches.
- **Composio already covers 75 of 100.** The 7 easy wins are ready-now apps not yet on Composio: Vonage, systeme.io, WooCommerce, Magento (Adobe Commerce), MongoDB Atlas, Binance, Reducto.
- **Needs outreach (11):** DealCloud, Gladly, LinkedIn Ads, Salesforce Commerce Cloud, fanbasis, Sherlock, Waterfall.io, Paygent Connect, PitchBook, Otter AI, Consensus. These go through partnerships, not engineering.

## What the agent got wrong (from the 20-app hand check)
- Gating and auth lists were the weakest fields (most misses were in auth_methods and credential_access): trials vs paid plans vs app review are buried in pricing pages.
- It labelled documented REST APIs as SDK/CLI-only (Twilio and Snowflake in pass 1; Close, Vercel, Asana and Snowflake from the auditor).
- It missed recently launched official MCP servers (Twilio, Airtable, Snowflake, systeme.io, iPayX).
- The independent auditor prompt scored 69% vs 62% for the first pass. The automatic fact-check did not move accuracy, because its flags (auth word not on the page) did not target the real errors. Next step: gating-specific checks and source-quote verification.
