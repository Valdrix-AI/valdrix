# LLM Cost Control Policy

**Scope:** Internal and Customer-facing LLM Features

## 1. Goal
Maximize AI value while maintaining strict financial guardrails.

## 2. Controls
1. **Token Budgets**: Every tenant has an `LLMBudget` record. Requests are blocked once the budget is exceeded.
2. **Provider Waterfall**: A cost-optimized fallback strategy (Groq -> Gemini -> GPT-4o-mini) is implemented in `LLMFactory`.
3. **Token Estimation**: Rough estimation of tokens occurs before dispatching to provider to avoid over-limit calls.
4. **Analysis Complexity Levels**: Simple tasks use cheap models; complex tasks only use high-tier models if the customer is on a paid plan.
5. **Caching**: Future implementation will include prompt caching to reduce repeated token costs.

## 3. Monitoring
- Real-time LLM cost tracking is available via the `Usage Metering API`.
- Alerts are sent via Slack when a tenant's LLM budget reaches 80% and 100%.
