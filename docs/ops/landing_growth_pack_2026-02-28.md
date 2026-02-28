# Landing Growth Pack (2026-02-28)

## Objective
Position Valdrics as an economic control plane (not a dashboard product), improve first-session conversion to signup intent, and tighten handoff from landing CTA -> auth -> onboarding.

## Positioning Guardrails
- Category: Economic control plane for cloud and software spend.
- Promise: Detect risk early, assign ownership fast, execute safely, and prove financial outcomes.
- Homepage rule: no internal artifact IDs, trace IDs, test counts, or implementation-file marketing.

## Audience + Outcome Map
| Buyer | Primary Trigger | Landing Outcome to Sell |
| --- | --- | --- |
| CTO | Spend spikes slow roadmap | Keep delivery velocity while controlling cloud/software cost risk |
| FinOps | Visibility without action | Move from reporting to governed remediation decisions |
| Security | Cost actions bypass policy | Enforce policy gates without becoming a bottleneck |
| CFO | Margin volatility | Protect margin with accountable ownership and auditable decisions |

## Messaging Stack
1. Problem hook: teams lose money when ownership/action arrives too late.
2. Category claim: Valdrics is an economic control plane.
3. Product moment: realtime signal -> owner assignment -> guardrail check -> approved action.
4. Buyer proof: persona tabs + cross-surface coverage (cloud, SaaS, ITAM/license, platform tooling).
5. Conversion: Start Free / ROI pathway with context-preserving auth handoff.

## UTM Taxonomy
- Required fields:
  - `utm_source`: channel source (`linkedin`, `newsletter`, `partner`, `community`, `x`, `google`)
  - `utm_medium`: channel type (`paid_social`, `organic_social`, `email`, `referral`, `organic_search`, `ppc`)
  - `utm_campaign`: campaign key (`launch_q1`, `roi_calc`, `cfo_board_story`, `finops_control_plane`)
- Optional fields:
  - `utm_term`: keyword or audience cluster
  - `utm_content`: creative or variant id

### Channel Matrix
| Channel | Example URL Params | Goal |
| --- | --- | --- |
| LinkedIn paid | `utm_source=linkedin&utm_medium=paid_social&utm_campaign=launch_q1&utm_content=hero_control` | High-intent executive demand |
| Newsletter | `utm_source=newsletter&utm_medium=email&utm_campaign=roi_calc&utm_content=cta_roi` | Activate ROI-qualified traffic |
| Partner co-marketing | `utm_source=partner&utm_medium=referral&utm_campaign=finops_control_plane` | Trust transfer from partner audience |
| Community launch thread | `utm_source=community&utm_medium=organic_social&utm_campaign=launch_q1` | Early adopter pull + sharing |

## Experiment Backlog (Public-safe)
| ID | Variant | Hypothesis | Primary Metric |
| --- | --- | --- | --- |
| EXP-HERO-01 | `Control every dollar...` vs `From metrics to control` | Control-first language increases hero CTA | Hero CTA click-through |
| EXP-CTA-01 | `Start Free` vs `Book Executive Briefing` | Executive CTA improves CFO/leadership traffic quality | Signup intent rate |
| EXP-ORDER-01 | Problem-first vs workflow-first section order | Problem-first improves first-time engagement | Engaged/view rate |
| EXP-AUTH-01 | Password-first vs magic-link-first emphasis | Magic-link reduces drop-off for net-new visitors | Signup completion rate |

## Realtime Signal Map Improvement Track
1. Add lane-level “next best action” hint to each selected lane (1 line max).
2. Add quick diff chip when snapshot changes (`what changed`) to improve comprehension.
3. Add per-lane confidence marker (`stable`, `watch`, `critical`) with plain-language tooltips.
4. Add mobile-safe collapse behavior so no labels can overlap/crop in narrow viewports.

## Asset Kit For Launch
- Desktop hero screenshot (`.landing-hero`)
- Mobile hero screenshot (`.landing-hero` on 390x844)
- Cloud hook comparison screenshot (`#cloud-hook`)
- Trust section screenshot (`#trust`)
- 20-second product moment GIF (signal map + demo strip + CTA click)

## Go-Live Checklist
1. Confirm copy and CTA consistency across landing, pricing, and auth pages.
2. Validate conversion handoff: CTA -> `/auth/login` with preserved intent/persona/UTM context.
3. Run public a11y gate and fix any blocking violations before release.
4. Run visual regression snapshots for hero/hook/trust sections.
5. Run performance gate on desktop + mobile budgets.
6. Verify telemetry ingest endpoint accepts landing/auth events and bounds timestamps.
7. Confirm post-closure sanity report is updated with exact command evidence.

## Owner Map
- Product messaging: Marketing + Product
- UX/UI implementation: Frontend
- Conversion telemetry + auth handoff: Frontend + Platform
- Validation gates (a11y/perf/visual): Frontend Engineering
- Post-closure sanity + release evidence: Ops/Engineering
