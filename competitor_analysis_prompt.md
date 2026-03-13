# Prompt: Babylon TBV Competitor Analysis — UV + Streamlit Dashboard

## Context

I'm a DeFi Product Lead at Babylon Labs. We're building Trustless Bitcoin Vaults (TBV) — a system that lets BTC holders use their bitcoin as collateral in DeFi without wrapping it or giving up custody. I need a competitor analysis dashboard that lives on the web as a team tool.

**Key constraint: ZERO manual work to get started.** Qualitative data is pre-baked from research. Quantitative data fetched from APIs and refreshable.

## Task

Build a `uv` Python project with a Streamlit multipage dashboard. 5 pages, each with a clear purpose:

1. **Overview** — "here's the landscape" (for anyone opening the dashboard)
2. **On-Chain Deep Dive** — "here's what's actually happening on-chain" (Aave/Uniswap/Dune data)
3. **Trust & Composability** — "here's the strategic map" (the positioning chart)
4. **Babylon vs Competition** — "here's why we win" (S/W + differentiation + rate comparison)
5. **Market Dynamics** — "here's where things are heading" (trends, flows, adoption)

**Target audience:** Internal product/eng team at Babylon Labs. Detailed metrics, technical depth, actionable insights.
**Timeline context:** TBV launch planned Q2 2026 — dashboard serves as pre-launch competitive monitoring tool.
**Deployment:** Streamlit Cloud — use `st.secrets` for API keys (not .env in production).
**Language:** All UI text in English.

## Project Structure

```
babylon-competitor-analysis/
├── pyproject.toml                  # uv project: streamlit, requests, pandas, plotly
├── README.md
├── .streamlit/
│   └── config.toml                 # dark theme + Bitcoin orange
├── src/
│   ├── config.py                   # Competitor registry
│   ├── fetch_defillama.py          # TVL from DeFi Llama
│   ├── fetch_thegraph.py           # Aave + Uniswap via The Graph
│   ├── fetch_defi_yields.py        # DeFi integrations via DeFi Llama yields
│   ├── fetch_dune.py               # Dune Analytics: holders, active addresses, bridge flows
│   ├── static_metadata.py          # Pre-baked qualitative data
│   └── aggregate.py                # Merge everything
├── data/
│   └── .gitkeep
├── Home.py                         # Page 1: Overview
└── pages/
    ├── 1_On_Chain_Deep_Dive.py     # Page 2: Aave/Uniswap/Dune
    ├── 2_Trust_and_Composability.py # Page 3: Strategic map
    ├── 3_Babylon_vs_Competition.py  # Page 4: S/W + radar + rate comparison
    └── 4_Market_Dynamics.py         # Page 5: Trends, flows, adoption
```

### `.streamlit/config.toml`
```toml
[theme]
base = "dark"
primaryColor = "#F7931A"
```

---

## Competitor Registry (config.py)

Each entry:
```python
{
    "name": str,
    "cluster": int,             # 1-4
    "cluster_name": str,        # human label
    "defillama_slug": str|None,
    "aave_symbol": str|None,    # for The Graph
    "website": str,
    "token_contract": str|None, # Ethereum mainnet
    "dune_token_address": str|None,  # for Dune SQL queries (ERC-20 address)
}
```

### Cluster 1 — CeFi Bitcoin Lending
| Name | Website | Notes |
|------|---------|-------|
| Nexo | nexo.com/borrow/bitcoin | Custodial, KYC |
| Ledn | ledn.io | Largest retail BTC lender, $2.8B originated, $100M+ ARR, Tether investor, PoR |
| Xapo Bank | xapobank.com | Banking license |
| Lygos Finance | lygos.finance | Institutional |
| Two Prime | twoprime.com | Institutional fund |
| Bitcoin Suisse | bitcoinsuisse.com | Swiss regulated |
| SatsTerminal | borrow.satsterminal.com | Non-custodial, $1.7M seed (Coinbase Ventures, Draper), Gate Ventures Mar 2026 |

### Cluster 2 — Centralized Wrapped BTC
| Name | DeFi Llama slug | Aave symbol | Token (ETH) |
|------|----------------|-------------|-------------|
| wBTC | wbtc | WBTC | 0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599 |
| cbBTC | coinbase-wrapped-btc | cbBTC | 0xcbB7C0000aB88B473b1f5aFd9ef808440eed33Bf |

### Cluster 3 — Trust-Minimized BTC & LSTs (PRIMARY FOCUS)
| Name | DeFi Llama slug | Aave symbol | Notes |
|------|----------------|-------------|-------|
| tBTC | threshold-btc | tBTC | Threshold, federated multisig |
| LBTC | lombard | LBTC | Lombard, ~$1.4B TVL, 260K users, 55+ integrations, 32% in Aave |
| SolvBTC | solv-protocol | — | $2.5B+ staked, 30K users, Chainlink CCT, multichain |
| FBTC | fbtc | — | Ignition/Mantle |
| uniBTC | bedrock | — | Bedrock, $140M TVL |
| eBTC | ebtc | — | BadgerDAO CDP |
| pumpBTC | pumpbtc | — | Babylon LST, $180M+ |
| sBTC | stacks | — | Stacks L2, ~$545M TVL, 14 signers, Fireblocks |
| Lorenzo stBTC | lorenzo-protocol | — | Babylon LST, BANK on Binance |
| coreBTC | core-dao | — | Core Chain, overcollateralized lockers |

### Cluster 4 — Bitcoin L2 & Infrastructure
| Name | DeFi Llama slug |
|------|----------------|
| BOB | bob-fusion |
| BitLayer | bitlayer |
| Citrea | citrea |
| Stacks | stacks |
| Core Chain | core |
| Mezo | mezo |

---

## Data Modules

### Module 1 — DeFi Llama TVL (`fetch_defillama.py`)

Free, no key.

- `GET https://api.llama.fi/v2/protocols` → find by slug
- `GET https://api.llama.fi/protocol/{slug}` → TVL history, chains, mcap

For each competitor with slug:
- Current TVL, TVL 7d ago, TVL 30d ago → `tvl_change_7d_pct`, `tvl_change_30d_pct`
- Chains list + count, mcap, TVL history array (for sparklines)

Output: `name, tvl_usd, tvl_change_7d_pct, tvl_change_30d_pct, chains_count, mcap, tvl_history`

### Module 2 — The Graph (`fetch_thegraph.py`)

Requires `THEGRAPH_API_KEY` env var. Skip gracefully if missing.

**Aave V3:**
Subgraph: `https://gateway.thegraph.com/api/[api-key]/subgraphs/id/Cd2gEDVeqnjBn1hSeqFMitw8Q1iiyV9FYUZkLNRcL87g`

```graphql
{
  reserves(where: { symbol_in: ["WBTC", "cbBTC", "tBTC", "LBTC"] }) {
    symbol, name, totalATokenSupply, totalCurrentVariableDebt,
    availableLiquidity, baseLTVasCollateral, liquidationThreshold,
    utilizationRate, price { priceInUsd }
  }
}
```

**Uniswap V3:** Search The Graph Explorer for "uniswap-v3-ethereum".
Query pools with `token0_` and `token1_` filters for BTC assets. Get `totalValueLockedUSD`, `volumeUSD`, `feeTier`.

Output: `name, aave_supply_usd, aave_borrow_usd, aave_utilization, aave_ltv_onchain, aave_liq_threshold, uniswap_tvl_usd, uniswap_volume_7d`

### Module 3 — DeFi Integrations (`fetch_defi_yields.py`)

Free, no key. `GET https://yields.llama.fi/pools`

For each token symbol (tBTC, LBTC, SolvBTC, wBTC, cbBTC, sBTC, pumpBTC, uniBTC...):
- Filter pools by symbol match
- Count unique projects → `defi_integrations_count`
- Sum pool TVL → `total_pool_tvl`
- Top 5 projects by TVL → `top_integrations`

Output: `name, defi_integrations_count, total_pool_tvl, top_integrations`

### Module 4 — Dune Analytics (`fetch_dune.py`)

Requires `DUNE_API_KEY` env var (on Streamlit Cloud: `st.secrets["DUNE_API_KEY"]`). Skip gracefully if missing.

**API Pattern (v2):**
- Preferred: `GET https://api.dune.com/api/v1/query/{query_id}/results` — latest cached results (cheap, fast)
- Fallback: `POST https://api.dune.com/api/v1/query/{query_id}/execute` → poll `GET /execution/{id}/status` every 2s (max 60s) → `GET /execution/{id}/results`
- Header: `X-Dune-API-Key: {key}`
- Rate limit: Community tier = 10 requests/min — implement exponential backoff

**Queries to create on Dune and reference by query_id:**

**Query 1 — ERC-20 Holder Counts:**
```sql
SELECT
    t.contract_address,
    COUNT(DISTINCT t.to) as holder_count
FROM erc20_ethereum.evt_Transfer t
WHERE t.contract_address IN (
    0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599,  -- wBTC
    0xcbB7C0000aB88B473b1f5aFd9ef808440eed33Bf,  -- cbBTC
    0x18084fbA666a33d37592fA2633fD49a74DD93a88,  -- tBTC
    0x8236a87084f8B84306f72007F36F2618A5634494,  -- LBTC
    0x7A56E1C57C7475CCf65CfbCd7E7c62F694d313A4   -- SolvBTC
)
GROUP BY t.contract_address
```

**Query 2 — Daily Active Addresses (30d avg):**
```sql
SELECT
    contract_address,
    COUNT(DISTINCT "from") + COUNT(DISTINCT "to") as daily_active,
    DATE_TRUNC('day', evt_block_time) as day
FROM erc20_ethereum.evt_Transfer
WHERE contract_address IN ({{token_addresses}})
  AND evt_block_time >= NOW() - INTERVAL '30' DAY
GROUP BY contract_address, DATE_TRUNC('day', evt_block_time)
```

**Query 3 — Bridge/Mint Volume (30d):**
```sql
SELECT
    contract_address,
    SUM(value / 1e8) as total_minted_btc,
    SUM(value / 1e8 * p.price) as total_minted_usd
FROM erc20_ethereum.evt_Transfer t
LEFT JOIN prices.usd p ON p.symbol = 'BTC' AND p.minute = DATE_TRUNC('minute', t.evt_block_time)
WHERE t."from" = 0x0000000000000000000000000000000000000000
  AND t.contract_address IN ({{token_addresses}})
  AND t.evt_block_time >= NOW() - INTERVAL '30' DAY
GROUP BY t.contract_address
```

**Implementation notes:**
- Create these queries on dune.com under your account, save them, get query_ids
- Store query_ids in `config.py` as `DUNE_QUERIES = {"holders": 12345, "active_addresses": 12346, "bridge_volume": 12347}`
- Use parameterized queries where possible (`{{token_addresses}}`)
- Cache results aggressively — `st.cache_data(ttl=7200)` for Dune (slower to refresh)
- If query is still executing or fails, return partial data + `st.warning`

**Output per asset:**
`name, holders_count, daily_active_addresses_avg, bridge_volume_30d_usd, bridge_volume_30d_btc`

---

### Static Metadata (`static_metadata.py`)

All qualitative data pre-baked. Zero manual work.

**New fields per competitor (added to original schema):**
| Field | Type | Description |
|-------|------|-------------|
| `threat_level` | `"high"` / `"medium"` / `"low"` | Strategic priority for Babylon TBV |
| `momentum` | `"growing"` / `"stable"` / `"declining"` | Current adoption/TVL trend |
| `key_risk_to_babylon` | `str` | Specific competitive threat to TBV |
| `manual_aum` | `float\|None` | For CeFi (Cluster 1) without DeFi Llama — estimated AUM in USD |
| `funding` | `str\|None` | Latest known funding round |
| `audit_status` | `"audited"` / `"partial"` / `"unaudited"` | Security audit status |

```python
COMPETITOR_METADATA = {
    # ===== Cluster 1: CeFi =====
    "Nexo": {
        "custody_type": "custodial", "kyc": True, "self_custodial": False,
        "ltv_max": 0.50, "apr_range": "2.9%–13.9%",
        "description": "Large CeFi lender, multi-jurisdiction regulated",
        "threat_level": "low", "momentum": "stable",
        "key_risk_to_babylon": "CeFi incumbents retain conservative BTC holders who won't try DeFi",
        "manual_aum": 4_000_000_000, "funding": "Series A (undisclosed)", "audit_status": "audited",
        "strengths": {"btc_holder": "Easy UX, instant loans, regulated", "custodian": "Established compliance", "defi_protocol": "N/A — centralized"},
        "weaknesses": {"btc_holder": "Custodial risk, KYC, counterparty exposure", "custodian": "Competes with own custody", "defi_protocol": "No composability"},
    },
    "Ledn": {
        "custody_type": "custodial", "kyc": True, "self_custodial": False,
        "ltv_max": 0.50, "apr_range": "~12%",
        "description": "Largest retail BTC lender. $2.8B originated, $100M+ ARR, Tether investor, PoR",
        "threat_level": "medium", "momentum": "growing",
        "key_risk_to_babylon": "Largest retail lender; BTC holders may choose simplicity over self-custody",
        "manual_aum": 2_800_000_000, "funding": "$70M Series B", "audit_status": "audited",
        "strengths": {"btc_holder": "No credit check, fast funding, transparent PoR, BTC-only", "custodian": "Survived 2022 crisis, strong risk mgmt", "defi_protocol": "N/A — centralized"},
        "weaknesses": {"btc_holder": "Custodial, KYC, jurisdiction limits", "custodian": "Centralized model limits scale", "defi_protocol": "No composability"},
    },
    "Xapo Bank": {
        "custody_type": "custodial", "kyc": True, "self_custodial": False,
        "ltv_max": 0.40, "apr_range": "Unknown",
        "description": "Licensed bank, BTC-backed credit lines",
        "threat_level": "low", "momentum": "stable",
        "key_risk_to_babylon": "Banking license offers regulatory comfort TBV lacks",
        "manual_aum": None, "funding": "Acquired by Coinbase alumni", "audit_status": "audited",
        "strengths": {"btc_holder": "Banking license, deposit protection", "custodian": "Regulated bank", "defi_protocol": "N/A"},
        "weaknesses": {"btc_holder": "Low LTV, limited access", "custodian": "N/A", "defi_protocol": "N/A"},
    },
    "Lygos Finance": {
        "custody_type": "custodial", "kyc": True, "self_custodial": False,
        "ltv_max": None, "apr_range": "Unknown",
        "description": "Institutional BTC lending",
        "threat_level": "low", "momentum": "stable",
        "key_risk_to_babylon": "Institutional niche overlap",
        "manual_aum": None, "funding": "Undisclosed", "audit_status": "unaudited",
        "strengths": {"btc_holder": "Institutional grade", "custodian": "Enterprise-focused", "defi_protocol": "N/A"},
        "weaknesses": {"btc_holder": "Not retail, custodial", "custodian": "Niche", "defi_protocol": "N/A"},
    },
    "Two Prime": {
        "custody_type": "custodial", "kyc": True, "self_custodial": False,
        "ltv_max": None, "apr_range": "Unknown",
        "description": "Institutional digital asset fund",
        "threat_level": "low", "momentum": "stable",
        "key_risk_to_babylon": "Minimal overlap — institutional fund, not infra",
        "manual_aum": None, "funding": "Undisclosed", "audit_status": "unaudited",
        "strengths": {"btc_holder": "Institutional infra", "custodian": "Fund-level risk mgmt", "defi_protocol": "N/A"},
        "weaknesses": {"btc_holder": "Not retail, custodial", "custodian": "N/A", "defi_protocol": "N/A"},
    },
    "Bitcoin Suisse": {
        "custody_type": "custodial", "kyc": True, "self_custodial": False,
        "ltv_max": None, "apr_range": "Unknown",
        "description": "Swiss-regulated crypto financial services",
        "threat_level": "low", "momentum": "stable",
        "key_risk_to_babylon": "Swiss regulation as competitive moat for EU market",
        "manual_aum": None, "funding": "Undisclosed", "audit_status": "audited",
        "strengths": {"btc_holder": "Swiss regulation, brand", "custodian": "Strong compliance", "defi_protocol": "N/A"},
        "weaknesses": {"btc_holder": "High barriers, custodial", "custodian": "Jurisdiction-limited", "defi_protocol": "N/A"},
    },
    "SatsTerminal": {
        "custody_type": "non-custodial", "kyc": False, "self_custodial": True,
        "ltv_max": None, "apr_range": "Unknown",
        "description": "BTC-native non-custodial. Cross-chain stablecoins. $1.7M seed. Gate Ventures Mar 2026",
        "threat_level": "medium", "momentum": "growing",
        "key_risk_to_babylon": "Non-custodial BTC lending is closest CeFi analog to TBV value prop",
        "manual_aum": None, "funding": "$1.7M seed (Coinbase Ventures, Draper)", "audit_status": "unaudited",
        "strengths": {"btc_holder": "Non-custodial, no KYC, native BTC, cross-chain", "custodian": "No custody needed", "defi_protocol": "Cross-chain composability"},
        "weaknesses": {"btc_holder": "Early stage, unproven", "custodian": "New integration model", "defi_protocol": "Small TVL"},
    },

    # ===== Cluster 2: Centralized Wrapped BTC =====
    "wBTC": {
        "custody_type": "custodial", "kyc": False, "self_custodial": False,
        "ltv_max": 0.73, "apr_range": "Variable (Aave ~2-5%)",
        "description": "Largest wrapped BTC. BitGo custody. $8.2B mcap",
        "threat_level": "high", "momentum": "stable",
        "key_risk_to_babylon": "Deep liquidity moat; DeFi protocols default to wBTC collateral",
        "funding": "N/A (BitGo)", "audit_status": "audited",
        "strengths": {"btc_holder": "Deepest liquidity, accepted everywhere, 1:1 redeemable", "custodian": "Standardized ERC-20", "defi_protocol": "Most liquid BTC collateral, proven"},
        "weaknesses": {"btc_holder": "Centralized custody (BitGo), peg risk", "custodian": "BitGo dependency", "defi_protocol": "Single point of failure"},
    },
    "cbBTC": {
        "custody_type": "custodial", "kyc": False, "self_custodial": False,
        "ltv_max": 0.73, "apr_range": "Variable (Aave)",
        "description": "Coinbase wrapped BTC. $5B bridged to Monad via CCIP (Mar 2026)",
        "threat_level": "high", "momentum": "growing",
        "key_risk_to_babylon": "Coinbase distribution + institutional trust; Monad bridge shows aggressive expansion",
        "funding": "N/A (Coinbase)", "audit_status": "audited",
        "strengths": {"btc_holder": "Regulated custodian, institutional trust, PoR", "custodian": "Coinbase compliance", "defi_protocol": "Growing integrations"},
        "weaknesses": {"btc_holder": "Coinbase SPOF, US regulatory risk", "custodian": "Concentrated", "defi_protocol": "Less liquid than wBTC"},
    },

    # ===== Cluster 3: Trust-Minimized =====
    "tBTC": {
        "custody_type": "federated-multisig", "kyc": False, "self_custodial": False,
        "ltv_max": None, "apr_range": "Variable",
        "description": "Threshold Network. Oldest trust-minimized BTC bridge",
        "threat_level": "medium", "momentum": "stable",
        "key_risk_to_babylon": "Oldest trust-minimized bridge; growing Aave integration",
        "funding": "Threshold DAO treasury", "audit_status": "audited",
        "strengths": {"btc_holder": "No KYC, decentralized custody, battle-tested", "custodian": "No single custodian", "defi_protocol": "Trust-minimized, Aave/Curve growing"},
        "weaknesses": {"btc_holder": "Lower liquidity, federation trust", "custodian": "Threshold trust", "defi_protocol": "Smaller pools"},
    },
    "LBTC": {
        "custody_type": "trust-minimized", "kyc": False, "self_custodial": False,
        "ltv_max": 0.84, "apr_range": "Staking yield + DeFi",
        "description": "Lombard. ~$1.4B TVL, 260K users, 55+ integrations. 32% in Aave, 12% in Spark",
        "threat_level": "high", "momentum": "growing",
        "key_risk_to_babylon": "Strongest direct competitor: 260K users, 55+ integrations, 84% LTV. Babylon dependency means they co-opt TBV narrative",
        "funding": "$16M seed", "audit_status": "audited",
        "strengths": {"btc_holder": "Staking yield + DeFi, 84% LTV, 55+ integrations", "custodian": "CubeSigner non-custodial keys", "defi_protocol": "High composability, blue-chip protocols"},
        "weaknesses": {"btc_holder": "Not truly self-custodial (security consortium)", "custodian": "Babylon dependency", "defi_protocol": "Concentrated in Aave (~32%)"},
    },
    "SolvBTC": {
        "custody_type": "trust-minimized", "kyc": False, "self_custodial": False,
        "ltv_max": None, "apr_range": "Variable yield",
        "description": "$2.5B+ staked, 30K users, Chainlink CCT, multichain, BTC+ Vault",
        "threat_level": "high", "momentum": "growing",
        "key_risk_to_babylon": "Multichain presence + $2.5B staked could fragment BTC DeFi before TBV launches",
        "funding": "$11M total", "audit_status": "partial",
        "strengths": {"btc_holder": "Multichain, yield strategies, institutional vault", "custodian": "Chainlink PoR + CCT", "defi_protocol": "Wide multichain, Chainlink stack"},
        "weaknesses": {"btc_holder": "Basket structure, not single-BTC", "custodian": "Multiple bridge surfaces", "defi_protocol": "Fragmented liquidity"},
    },
    "FBTC": {
        "custody_type": "custodial", "kyc": False, "self_custodial": False,
        "ltv_max": None, "apr_range": "Variable",
        "description": "Ignition/Mantle ecosystem wrapped BTC",
        "threat_level": "low", "momentum": "stable",
        "key_risk_to_babylon": "Ecosystem-locked to Mantle — minimal overlap",
        "funding": "Ignition/Mantle backed", "audit_status": "partial",
        "strengths": {"btc_holder": "Mantle access", "custodian": "Ecosystem-native", "defi_protocol": "Mantle DeFi"},
        "weaknesses": {"btc_holder": "Ecosystem-locked", "custodian": "Niche", "defi_protocol": "Limited cross-chain"},
    },
    "uniBTC": {
        "custody_type": "trust-minimized", "kyc": False, "self_custodial": False,
        "ltv_max": None, "apr_range": "Variable",
        "description": "Bedrock. $140M TVL. Proxy/conversion staking to Babylon",
        "threat_level": "medium", "momentum": "stable",
        "key_risk_to_babylon": "Proxy Babylon staking dilutes TBV differentiation",
        "funding": "OKX Ventures", "audit_status": "partial",
        "strengths": {"btc_holder": "Babylon exposure, flexible staking", "custodian": "OKX Ventures backed", "defi_protocol": "Multi-asset staking"},
        "weaknesses": {"btc_holder": "Proxy staking intermediary risk", "custodian": "Third-party staking", "defi_protocol": "Smaller scale"},
    },
    "eBTC": {
        "custody_type": "trustless", "kyc": False, "self_custodial": True,
        "ltv_max": None, "apr_range": "CDP model",
        "description": "BadgerDAO CDP. Synthetic BTC against stETH",
        "threat_level": "low", "momentum": "declining",
        "key_risk_to_babylon": "Synthetic model, different market segment",
        "funding": "BadgerDAO treasury", "audit_status": "audited",
        "strengths": {"btc_holder": "Trustless CDP, no intermediary", "custodian": "No custodian", "defi_protocol": "Immutable contracts"},
        "weaknesses": {"btc_holder": "Synthetic — not real BTC", "custodian": "N/A", "defi_protocol": "Small TVL, niche"},
    },
    "pumpBTC": {
        "custody_type": "semi-custodial", "kyc": False, "self_custodial": False,
        "ltv_max": None, "apr_range": "Staking yield",
        "description": "Babylon LST. $180M+. Custodians: Cobo, Coincover",
        "threat_level": "medium", "momentum": "growing",
        "key_risk_to_babylon": "Direct Babylon LST competitor; custodial but simpler UX",
        "funding": "Undisclosed", "audit_status": "partial",
        "strengths": {"btc_holder": "Simple Babylon staking, points", "custodian": "Professional custodians", "defi_protocol": "Babylon ecosystem"},
        "weaknesses": {"btc_holder": "Third-party custody", "custodian": "Custodian concentration", "defi_protocol": "Smaller scale"},
    },
    "sBTC": {
        "custody_type": "federated-multisig", "kyc": False, "self_custodial": False,
        "ltv_max": None, "apr_range": "STRK staking rewards",
        "description": "Stacks L2. ~$545M TVL, 7,400+ holders. 14 signers → permissionless. Fireblocks",
        "threat_level": "high", "momentum": "growing",
        "key_risk_to_babylon": "Bitcoin finality + $545M TVL + Fireblocks institutional backing is strong narrative",
        "funding": "$165M+ via Stacks ecosystem", "audit_status": "audited",
        "strengths": {"btc_holder": "100% Bitcoin finality, BitGo + Fireblocks, no KYC", "custodian": "Institutional via Fireblocks", "defi_protocol": "Rich Stacks DeFi, Wormhole multichain"},
        "weaknesses": {"btc_holder": "14 signers (not fully decentralized)", "custodian": "Signer rotation complexity", "defi_protocol": "Clarity limits dev ecosystem"},
    },
    "Lorenzo stBTC": {
        "custody_type": "trust-minimized", "kyc": False, "self_custodial": False,
        "ltv_max": None, "apr_range": "Staking yield",
        "description": "Babylon LST. BANK on Binance (Nov 2025)",
        "threat_level": "medium", "momentum": "growing",
        "key_risk_to_babylon": "Babylon LST with Binance listing — distribution advantage",
        "funding": "Binance Labs", "audit_status": "partial",
        "strengths": {"btc_holder": "Babylon yield, governance", "custodian": "Binance listing", "defi_protocol": "USD1 stablecoin"},
        "weaknesses": {"btc_holder": "Small TVL, BANK volatile (-67% 90d)", "custodian": "Unproven", "defi_protocol": "Limited integrations"},
    },
    "coreBTC": {
        "custody_type": "trustless", "kyc": False, "self_custodial": False,
        "ltv_max": None, "apr_range": "Variable",
        "description": "Core Chain. Overcollateralized lockers + guardians. $354M chain TVL",
        "threat_level": "medium", "momentum": "stable",
        "key_risk_to_babylon": "Trustless lockers model is conceptually similar to TBV vaults",
        "funding": "Core Foundation", "audit_status": "partial",
        "strengths": {"btc_holder": "Trustless via overcollateralization", "custodian": "Distributed lockers", "defi_protocol": "EVM compatible"},
        "weaknesses": {"btc_holder": "Smaller ecosystem, complexity", "custodian": "Collateral management", "defi_protocol": "Core-specific"},
    },

    # ===== Cluster 4: Infrastructure =====
    "BOB": {
        "custody_type": "trust-minimized", "kyc": False, "self_custodial": True,
        "description": "BitVM-based bridge. SolvBTC integrated",
        "threat_level": "medium", "momentum": "growing",
        "key_risk_to_babylon": "BitVM bridge could become preferred infra if TBV doesn't ship first",
        "funding": "$10M seed", "audit_status": "partial",
        "strengths": {"btc_holder": "BitVM verification", "custodian": "Bridge security", "defi_protocol": "EVM+Bitcoin"},
        "weaknesses": {"btc_holder": "BitVM maturing", "custodian": "Integration overhead", "defi_protocol": "Small ecosystem"},
    },
    "BitLayer": {
        "custody_type": "trust-minimized", "kyc": False, "self_custodial": True,
        "description": "Optimistic verification. BitVM bridge with Cardano",
        "threat_level": "low", "momentum": "stable",
        "key_risk_to_babylon": "Early stage, different approach — low overlap",
        "funding": "Undisclosed", "audit_status": "unaudited",
        "strengths": {"btc_holder": "Scalable optimistic", "custodian": "Bridge innovation", "defi_protocol": "Growing L2"},
        "weaknesses": {"btc_holder": "Challenge delays", "custodian": "Unproven", "defi_protocol": "Fragmented"},
    },
    "Citrea": {
        "custody_type": "trustless", "kyc": False, "self_custodial": True,
        "description": "ZK rollup on Bitcoin. Chainway",
        "threat_level": "medium", "momentum": "growing",
        "key_risk_to_babylon": "ZK rollup on Bitcoin is strongest verification narrative, competes with BitVM3",
        "funding": "$2.7M pre-seed", "audit_status": "unaudited",
        "strengths": {"btc_holder": "ZK = strongest verification", "custodian": "No custody", "defi_protocol": "Bitcoin-native"},
        "weaknesses": {"btc_holder": "Pre-production", "custodian": "Not live", "defi_protocol": "No ecosystem"},
    },
    "Mezo": {
        "custody_type": "semi-custodial", "kyc": False, "self_custodial": False,
        "description": "Thesis venture. Bitcoin L2. stBTC via Acre. 12K users, 2,300+ BTC",
        "threat_level": "medium", "momentum": "stable",
        "key_risk_to_babylon": "Thesis-backed, stBTC integration, yield stacking competes with TBV yield",
        "funding": "$21M Series A", "audit_status": "partial",
        "strengths": {"btc_holder": "Yield stacking", "custodian": "Thesis backing", "defi_protocol": "Curve integration"},
        "weaknesses": {"btc_holder": "Semi-custodial, 2-3% fees", "custodian": "Venture-dependent", "defi_protocol": "Niche L2"},
    },

    # ===== Babylon TBV (comparison overlay) =====
    "Babylon TBV": {
        "custody_type": "trustless", "kyc": False, "self_custodial": True,
        "ltv_max": None, "apr_range": "TBD — projected competitive with Aave BTC rates",
        "description": "Trustless Bitcoin Vaults. Native BTC via BitVM3/ZK. No wrapping. $5B+ staked. Aave V4 spoke. $15M a16z (Jan 2026)",
        "threat_level": "n/a", "momentum": "growing",
        "key_risk_to_babylon": "N/A — this is us",
        "funding": "$15M a16z (Jan 2026)", "audit_status": "partial",
        "strengths": {"btc_holder": "TRUE self-custody, no wrapping, no KYC, native BTC", "custodian": "Standardized vault integration", "defi_protocol": "Native BTC collateral, Aave V4 spoke"},
        "weaknesses": {"btc_holder": "Pre-launch, BitVM3 complexity", "custodian": "New standard, not battle-tested", "defi_protocol": "No live liquidity yet"},
    },
}
```

---

## Aggregation (`aggregate.py`)

1. config.py registry → base DataFrame
2. Left-join DeFi Llama TVL
3. Left-join The Graph on-chain
4. Left-join DeFi yields
5. Left-join Dune Analytics (holders, active addresses, bridge volume)
6. Left-join static_metadata (including `manual_aum`, `threat_level`, `momentum`, etc.)
7. Compute derived columns:
   - `effective_tvl`: `coalesce(tvl_usd, manual_aum)` — ensures CeFi players appear in TVL charts
   - `tvl_source`: `"defillama"` if tvl_usd exists, else `"manual"` — for footnotes/asterisks
   - `composite_adoption_score`: `normalize(holders_count) * 0.5 + normalize(effective_tvl) * 0.3 + normalize(daily_active_addresses) * 0.2`
8. Save `data/competitors.csv`

Each fetch function: try/except → empty DataFrame + warning on failure. Never crash.

Note: CeFi competitors (Cluster 1) without DeFi Llama slugs use `manual_aum` from static_metadata as their TVL proxy. Tag with `tvl_source: "manual"` so the dashboard shows an asterisk `*` and footnote "Estimated AUM from research, not live API data."

---

## Dashboard Pages

### Shared across all pages

**Sidebar:**
- Cluster filter (multiselect, default=all)
- "Show Babylon TBV" toggle (overlays Babylon on charts)
- Refresh Data button (`st.cache_data.clear()` + `st.rerun()`)
- Data freshness timestamp
- CSV download button (full dataset)
- "Days to TBV Launch" countdown (compute from target Q2 2026 date)

**Data loading pattern:**
```python
import os

def get_secret(key):
    """Streamlit Cloud uses st.secrets, local dev uses env vars."""
    try:
        return st.secrets[key]
    except:
        return os.environ.get(key)

@st.cache_data(ttl=3600, show_spinner="Fetching data...")
def load_all_data():
    defillama = fetch_defillama_safe()
    thegraph = fetch_thegraph_safe()   # returns empty if no THEGRAPH_API_KEY
    yields = fetch_defi_yields_safe()
    dune = fetch_dune_safe()           # returns empty if no DUNE_API_KEY
    metadata = get_static_metadata()
    return aggregate_all(defillama, thegraph, yields, dune, metadata)
```

---

### Home.py — "Overview"

**Purpose:** Anyone opening this sees the full landscape in 30 seconds.

**Layout:**
- **Title:** "Babylon TBV — Competitor Intelligence"
- **KPI row (6 cards):**
  - Competitors tracked (count)
  - Total market TVL (formatted $X.XB) — uses `effective_tvl`
  - Cluster 3 TVL + 30d change (with ▲/▼ indicator)
  - Babylon staking TVL ($5B+)
  - Total unique holders (sum of `holders_count` from Dune, if available; else show "Dune API required")
  - High-threat competitors (count where `threat_level == "high"`)
- **Horizontal bar chart:** `effective_tvl` by protocol, sorted descending, colored by cluster. Top 15. If Babylon toggle on, show dashed line. Plotly interactive. Asterisk `*` on bars using `manual_aum`.
- **Cluster cards:** One card per cluster — competitor count, total TVL, one-line insight. Example: "CeFi: 7 players, dominated by Ledn ($2.8B originated). All custodial except SatsTerminal."
- **Full competitor table:** Name | Cluster | Custody | TVL | 30d% | Holders | Chains | Threat | Momentum | Description. Color-coded by cluster. Sortable. `st.dataframe` with column config.
  - Threat column: color-coded (red=high, yellow=medium, green=low)
  - Momentum column: arrow icons (▲ growing, → stable, ▼ declining)
  - TVL column: asterisk `*` for `tvl_source == "manual"`, footnote at bottom
- Any API warnings shown as `st.warning` at top.

---

### Page 1: On-Chain Deep Dive

**Purpose:** Prove which BTC assets are actually used, not just bridged. This is the "killer data" page.

**Guard:** If `THEGRAPH_API_KEY` not set → show setup instructions in `st.info`, explain what this page would show, and stop. No empty charts.

**Aave section:**
- **Grouped bar:** Supply vs Borrow per BTC asset — the gap shows capital efficiency
- **Utilization bars:** Simple horizontal bar, sorted. Higher = more productive capital
- **LTV comparison:** On-chain `baseLTVasCollateral` per asset — shows how much DeFi protocols trust each BTC variant
- **Table:** Symbol | Supplied | Borrowed | Utilization% | LTV | Liq.Threshold | Price
- **Auto-insight (`st.metric` or `st.info`):** auto-generated from data, e.g. "LBTC: $352M supplied, X% utilization. Most capital-efficient BTC asset on Aave."

**Uniswap section:**
- **Scatter:** Pool TVL (x) vs 24h Volume (y) per BTC asset. Bubble size = number of pools. Shows liquidity depth vs activity.
- **Table:** Top 10 pools by TVL — Token pair | TVL | Volume | Fee tier

**Dune Analytics section:**
**Guard:** If `DUNE_API_KEY` not set → show `st.info` with setup instructions. Still show Aave/Uniswap sections above.

- **Holder distribution bar chart:** Horizontal bars showing holder count per BTC asset (wBTC, cbBTC, tBTC, LBTC, SolvBTC, pumpBTC, sBTC). Sorted descending. Color by cluster.
- **Daily active addresses comparison:** Grouped bar chart — shows which assets have real usage vs dormant holders.
- **Bridge flow bar chart:** Bridge mint volume (30d) per asset in USD. Shows where new BTC is flowing into DeFi.
- **Table:** Asset | Holders | Active Addresses (30d avg) | Bridge Volume (30d) | Holder/TVL Ratio
- **Auto-insight:** e.g., "wBTC has 150K holders but declining active addresses. LBTC has 260K users with growing bridge inflows — fastest adoption."

---

### Page 2: Trust & Composability

**Purpose:** The strategic map. Where does each competitor sit on trust vs DeFi reach? This is THE chart for the boss.

**Trust Spectrum Scatter (main visualization):**
- X axis: Trust score — `custodial=1, semi-custodial=1.5, federated-multisig=2, trust-minimized=3, trustless=4`
- Y axis: DeFi integrations count (from yields API). If not available, use 0.
- **Bubble size toggle:** `st.radio` — "Size by TVL" / "Size by Holders" / "Size by TVL+Holders"
  - TVL: `log(effective_tvl)` — default
  - Holders: `log(holders_count)` — if Dune data available; disable with `st.info` if not
  - TVL+Holders: `log(effective_tvl * holders_count)` — combined metric
- Color: cluster
- Label each bubble with protocol name
- If Babylon toggle on: show Babylon TBV at (4, 1) with annotation "Projected: Aave V4 + future integrations"
- **This chart tells the whole story in one image.** Make it visually striking — large, centered, good spacing.

**DeFi integrations bar chart:** Horizontal, sorted descending. Shows raw composability.

**Trust comparison table:** Protocol | Custody Type | KYC | Self-Custodial | On-Chain LTV (Aave) | DeFi Integrations. Sorted by trust score (trustless at top).

**Expandable details:** `st.expander` per protocol — shows which DeFi protocols accept it (from yields data top_integrations list).

---

### Page 3: Babylon vs Competition

**Purpose:** "Here's why we win." Auto-generated from static_metadata.py. Zero manual input.

**Perspective selector:** `st.radio` horizontal — "BTC Holder" / "Custodian" / "DeFi Protocol"

**For selected perspective:**
- **Table:** Protocol | Cluster | Strengths | Weaknesses
- Babylon TBV row highlighted with orange/accent background
- Cluster 1 grouped together, then 2, 3, 4
- CeFi rows can be collapsed (`st.expander("CeFi Lending (7 competitors)")`)

**Radar chart:** Babylon TBV vs top competitors (LBTC, sBTC, tBTC, wBTC, SolvBTC) on 6 axes:
- Self-custody (0 or 1)
- DeFi composability (normalized 0-1 from integrations count)
- TVL scale (normalized 0-1 from `effective_tvl`, log scale)
- Adoption (normalized 0-1 from `holders_count` if Dune available; else fall back to TVL)
- Trust minimization (custody score / 4)
- Capital efficiency (on-chain LTV / 100, 0 if not on Aave)

**Interest Rate & LTV Benchmark (NEW):**
- **Comparison table:** Protocol | Custody | LTV (Max) | APR/Yield Range | Fees | KYC Required
- Show all competitors with known rates, sorted by LTV descending
- Babylon TBV row highlighted — show projected rates as "TBD" with note "Expected competitive with Aave variable rates"
- **Bar chart:** LTV comparison — horizontal bars per protocol. Babylon TBV shown as projected/dashed.
- **Purpose:** Directly answers "where does TBV win on rates?" for the team.

**Threat Matrix:**
- `st.dataframe` showing only `threat_level == "high"` competitors
- Columns: Name | Cluster | TVL | Holders | Momentum | Key Risk to Babylon
- Sorted by `effective_tvl` descending
- Purpose: Quick exec summary of who matters most

**Key takeaway (`st.success` box):** Auto-generated from data:
```python
top_threat = df[df.threat_level == "high"].sort_values("effective_tvl", ascending=False).iloc[0]
st.success(f"""
Babylon TBV is the only solution offering all three: trustless self-custody + native BTC (no wrapping) + DeFi composability (Aave V4).
Top threat: {top_threat['name']} at ${top_threat['effective_tvl']/1e9:.1f}B TVL ({top_threat['momentum']} momentum).
{len(df[df.threat_level == 'high'])} high-threat competitors identified. Pre-launch window: ~{days_to_launch} days.
""")
```

---

### Page 4: Market Dynamics

**Purpose:** "Here's where things are heading." Trend analysis, market share evolution, flow patterns. Forward-looking page for strategy discussions.

**Section 1 — Market Share Trends:**
- **Stacked area chart:** TVL over time by cluster (from DeFi Llama `tvl_history`). Time range selector: `st.radio` — 30d / 90d / 180d / 1Y.
- **Line chart:** Individual protocol TVL over time — top 5 by current TVL. Shows who's gaining/losing.
- **Table:** Protocol | TVL Now | TVL 30d Ago | TVL 90d Ago | 30d Change% | 90d Change% | Momentum
- **Auto-insight:** Identify largest gainer and largest decliner over 30d. e.g., "LBTC gained $200M (+18%) in 30d while wBTC lost $150M (-2%)."

**Section 2 — Holder Growth Trends (requires Dune):**
**Guard:** If no Dune data → `st.info` explaining what this section would display.
- **Bar chart with `st.metric` deltas:** Holder count per BTC asset with delta indicators (if Dune returns point-in-time data).
- **Holder-to-TVL ratio scatter:** X = TVL, Y = Holders. Protocols above the trendline have more "retail" distribution; below = whale-dominated. Label each point.
- **Auto-insight:** "LBTC has the highest holder-to-TVL ratio (260K holders / $1.4B = 186 holders per $1M), suggesting strong retail adoption."

**Section 3 — Bridge Flow Analysis (requires Dune):**
**Guard:** Same Dune guard.
- **Horizontal bar chart:** 30d bridge mint volume per asset, sorted descending. Shows where BTC is actively entering DeFi.
- **Net flow indicator:** Positive (net mints) = inflows, negative (net burns) = outflows per asset. Simple colored bars (green/red).
- **Cluster-level summary:** Total bridge volume by cluster. "Trust-Minimized BTC (Cluster 3) processed $X in bridge volume vs $Y for Centralized Wrapped (Cluster 2)."

**Section 4 — Competitive Momentum Dashboard:**
- **Traffic-light heatmap:** Rows = competitors (top 15 by TVL), Columns = metrics (TVL trend, Holder trend, Integration growth, Bridge volume). Cells colored green/yellow/red.
- Uses combination of `momentum` from static metadata + computed trends from API data.
- **Purpose:** One-glance view of who's winning and who's fading.

---

## Technical Requirements

- Python 3.11+, `uv` project
- Dependencies: `streamlit`, `requests`, `pandas`, `plotly`, `python-dotenv`
- API calls: `timeout=10`, 3 retries with exponential backoff
- `st.cache_data(ttl=3600)` for DeFi Llama/Graph/Yields — refresh via sidebar button
- `st.cache_data(ttl=7200)` for Dune — slower refresh due to rate limits
- `THEGRAPH_API_KEY` — optional, Pages 1 Graph sections hidden without it
- `DUNE_API_KEY` — optional, Dune sections show setup prompt without it. Rate limit: 10 req/min
- DeFi Llama + yields: no key needed
- **Streamlit Cloud deployment:**
  - Use `st.secrets` for API keys (configured in Streamlit Cloud UI)
  - Local dev: fall back to `os.environ` / `.env` via `python-dotenv`
  - Memory limit: avoid loading full history for all 25+ protocols at once — paginate or limit
- README: setup instructions + `uv run streamlit run Home.py` + Streamlit Cloud deploy guide

## What NOT to do
- Don't scrape websites
- Don't use Selenium/Playwright
- Don't require manual input
- Don't crash on API failure — always partial data
- Don't over-engineer
- Don't hardcode API keys in code — use `st.secrets` / env vars only

## Priority
1. Home.py + DeFi Llama + full competitor table with `effective_tvl` (minimum viable)
2. static_metadata (all new fields) + Babylon vs Competition (S/W + radar + threat matrix + rate benchmark)
3. DeFi yields + Trust & Composability (scatter plot with bubble size toggle)
4. The Graph + On-Chain Deep Dive (Aave/Uniswap sections)
5. Dune Analytics module + On-Chain Deep Dive Dune section + holder KPIs on Overview
6. Market Dynamics page (trends, flows, momentum dashboard)
7. Polish: sparklines, auto-insights, expanders, momentum heatmap
