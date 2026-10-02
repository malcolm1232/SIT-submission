# Meridian Order Management and Returns Platform

## Design Document

| Field | Value |
|---|---|
| Document ID | ENG-OMS-DD-014 |
| Version | 0.9 (for pre-build design review) |
| Status | Draft for Architecture Review Board |
| Owning team | Commerce Platform, Order and Returns squad |
| Contributing teams | Payments Gateway, Fulfilment Integration, Customer Identity, Data Platform |
| Reviewers requested | Architecture Review Board, Information Security, Data Protection Office, Finance Systems, Customer Operations, Legal (Consumer) |
| Last updated | 2026-09-28 |

---

## 1. Purpose and Scope

### 1.1 Purpose

This document describes the target design of **Meridian**, the replacement order management system (OMS) and returns platform for Halden & Rowe Retail Group ("H&R"). Meridian replaces the order capture, order orchestration, cancellation, returns and refund-orchestration functions currently performed by the legacy OMS ("Atlas"), an on-premise Java and Oracle monolith that has been in service since 2014.

The document is written ahead of build. Its purpose is to (a) give reviewers enough detail to challenge the architecture, data model and key flows before significant code is written, (b) record the decisions already taken and their rationale, and (c) define the acceptance criteria and rollout plan against which the programme will be governed.

### 1.2 In scope

1. Order capture from all H&R digital channels: web storefront, iOS and Android apps, contact-centre assisted ordering, and the B2B Trade Portal used by hospitality customers.
2. Order orchestration: fraud screening, inventory reservation, splitting into shipments, release to warehouse, tracking through to delivery.
3. Cancellation of orders and order lines, including warehouse intercept requests.
4. Returns: self-service initiation, eligibility, carrier label generation, home collection booking, store drop-off, receipt and inspection at the returns centre, and disposition.
5. Refund orchestration: refund calculation, deductions, instruction of refunds through the Payments Gateway, and issue of store credit.
6. Customer-facing order and return status (web, app, email, push).
7. Publication of order and return domain events to downstream consumers (Finance ERP, CRM, marketing, analytics, customer service tooling).

### 1.3 Out of scope

1. Payment authorisation, capture and the PSP relationship. These are owned by the Payments Gateway team; Meridian is a client of the Payments Gateway and never handles card data.
2. Warehouse management system (WMS) internals, pick and pack logic, and labour planning.
3. Product catalogue, pricing and the promotions engine. Meridian consumes price and promotion allocations as supplied in the basket.
4. Tax determination. The external tax engine returns a tax quote at basket time; Meridian stores and re-applies it.
5. In-store point-of-sale returns for store-originated purchases. These remain on the POS platform and are planned for a later phase.
6. Marketplace (third-party seller) orders. H&R does not currently operate a marketplace.

### 1.4 Audience and conventions

The primary audience is the Architecture Review Board and the specialist reviewers listed above. Requirement identifiers use the prefixes FR (functional), NFR (non-functional) and CMP (compliance). Decisions use DEC, open items OI, and acceptance criteria AC. Monetary examples are in GBP unless stated; the same logic applies to EUR. "Market" means one of the five countries in which H&R trades online: United Kingdom (UK), Ireland (IE), Germany (DE), Netherlands (NL) and France (FR).

---

## 2. Background and Context

### 2.1 Current state

Atlas runs on a pair of on-premise Oracle 12c database servers and a cluster of six WebLogic application servers in the Milton Keynes data centre. Its main characteristics, as they affect this programme, are:

- **Batch-oriented refunds.** Refunds are calculated by a batch job that runs twice daily and submits a file to the PSP. A failed file requires manual resubmission and has twice in the last 18 months caused duplicate refunds that were recovered manually.
- **Assisted returns only.** Customers initiate returns by calling the contact centre or by filling in a paper form enclosed with the parcel. There is no self-service return journey in DE, NL or FR.
- **Poor visibility.** "Where is my refund?" (WISMR) contacts account for 38% of contact-centre volume in the returns period after peak trading.
- **Peak fragility.** On Black Friday 2025, the Atlas order intake queue backed up for just over three hours; orders were accepted by the storefront but not visible to customers or released to the warehouse until the backlog cleared.
- **Licence pressure.** The Oracle support contract ends in December 2027 and will not be renewed.

### 2.2 Business drivers

| Driver | Measure of success |
|---|---|
| Reduce returns-related contact volume | WISMR contacts down 50% against FY2025 baseline within six months of full rollout |
| Self-service returns in all markets | 85% of returns initiated without agent involvement |
| Support B2B growth | Trade Portal orders of up to 500 lines processed without manual splitting |
| Consistent handling of statutory consumer rights across UK and EU | Zero upheld regulator or ombudsman complaints related to returns handling |
| Peak resilience | No customer-visible order backlog at 2027 forecast peak |
| Decommission Atlas | Atlas switched off before Oracle support end (December 2027) |

### 2.3 Volumes and growth

| Metric | FY2025 actual | 2027 forecast |
|---|---|---|
| Orders per year (all channels) | 14.2 million | 16.8 million |
| Average lines per consumer order | 2.7 | 2.8 |
| Return rate (orders with at least one return) | 22% | 24% |
| Return rate, apparel category | 31% | 33% |
| Peak day orders (Black Friday) | 610,000 | 720,000 |
| Peak minute orders | 1,050 | 1,200 |
| B2B Trade Portal orders per year | 180,000 | 230,000 |
| B2B average lines per order | 46 | 50 |
| B2B maximum lines observed | 412 | 500 (portal cap) |
| Refunds issued per year | 3.4 million | 4.1 million |
| Fulfilment centres | Northampton (UK), Venlo (NL) | Northampton, Venlo, Erfurt (DE, from Q3 2027) |
| Returns centres | Northampton, Venlo | Northampton, Venlo |

### 2.4 Related systems

- **Storefront BFFs** (web and app back-ends for front-ends) assemble the basket, obtain a tax quote and a payment authorisation, and then submit the order to Meridian.
- **Payments Gateway** is H&R's internal service that fronts the PSP. It exposes authorise, capture, void and refund operations and returns PSP references.
- **FraudShield** is a third-party fraud-screening SaaS used today by Atlas.
- **Inventory Availability Service (IAS)** owns stock positions per fulfilment node and exposes a reservation API.
- **WMS** is a commercial warehouse management system deployed per fulfilment centre and integrated via an H&R-owned integration layer.
- **Carrier Hub** is an H&R-owned integration service in front of the carrier aggregator. It issues outbound and return labels and relays tracking scans as webhooks.
- **Finance ERP** receives order, invoice, credit-note and refund events for revenue recognition and reconciliation against PSP settlement reports.
- **CRM** (contact-centre case management) shows agents the order and return timeline.

---

## 3. Requirements

### 3.1 Functional requirements

#### 3.1.1 Order capture and orchestration

| ID | Requirement |
|---|---|
| FR-ORD-01 | Meridian shall accept orders from all digital channels through a single Order API. |
| FR-ORD-02 | Order placement shall be idempotent with respect to a client-supplied `Idempotency-Key`; a retried submission shall return the original result and shall not create a second order. |
| FR-ORD-03 | Meridian shall support orders of up to 500 lines (the Trade Portal cap). |
| FR-ORD-04 | Every order shall be screened by FraudShield before it is released to fulfilment. |
| FR-ORD-05 | Meridian shall reserve inventory for every line at placement and release the reservation on cancellation or when the reservation expires. |
| FR-ORD-06 | Meridian shall split an order into shipments by fulfilment node and shall support backordered lines with a promised dispatch date of up to 28 days after placement. |
| FR-ORD-07 | A change in order, shipment or return status shall be visible to the customer within 60 seconds. |
| FR-ORD-08 | Meridian shall publish a domain event for every state change of an order, shipment, return or refund. |
| FR-ORD-09 | Contact-centre agents shall be able to view the complete timeline of an order, including events originating in WMS and Carrier Hub. |

#### 3.1.2 Cancellation

| ID | Requirement |
|---|---|
| FR-CAN-01 | A customer shall be able to cancel any order line that has not yet been released to warehouse picking. |
| FR-CAN-02 | For a line already released to picking, a cancellation request shall become an intercept request to the WMS. If the intercept fails, the customer shall be told that the item will be delivered and shown how to return it. |
| FR-CAN-03 | Cancellation shall void the payment authorisation for uncaptured amounts and trigger a refund for captured amounts. |

#### 3.1.3 Returns

| ID | Requirement |
|---|---|
| FR-RET-01 | A customer may initiate a return for any eligible item within 30 days of the delivery of that item (H&R commercial returns policy). Where an order is delivered in more than one shipment, the window runs separately for each shipment from its delivery date. |
| FR-RET-02 | Return methods: prepaid carrier label for drop-off (all markets), home collection (UK and DE), and store drop-off (UK and IE). |
| FR-RET-03 | The following items are excluded from return unless faulty: personalised or made-to-measure items, and hygiene-sealed items (pillows, duvets, mattress protectors, pierced jewellery) where the seal has been broken after delivery. The exclusion shall be shown on the product page and in the order confirmation. |
| FR-RET-04 | A customer shall be able to see the status of a return online without contacting the contact centre. |
| FR-RET-05 | The returns centre shall record receipt and an inspection outcome per returned item: `OK`, `DAMAGED_IN_TRANSIT`, `HANDLED_BEYOND_NECESSARY`, `WRONG_ITEM` or `MISSING`. |
| FR-RET-06 | Exchanges for a different size or colour of the same product shall be supported in phase 1 as a return plus a linked replacement order at zero charge. |
| FR-RET-07 | A customer who has expressly informed H&R of a withdrawal decision by other means (email, letter, contact centre) shall be able to have that withdrawal recorded by an agent with the date on which it was communicated. |

#### 3.1.4 Refunds

| ID | Requirement |
|---|---|
| FR-REF-01 | Refunds shall be made to the original payment method. Store credit (with a 5% bonus) shall be offered as an alternative and used only where the customer expressly selects it. |
| FR-REF-02 | A refund shall be issued within 14 calendar days of the returned item passing warehouse inspection. |
| FR-REF-03 | Refund amounts shall be calculated per line, including the line's share of any order-level discount, and shall reconcile exactly to the amounts captured. |
| FR-REF-04 | A deduction for diminished value may be applied only where the inspection outcome is `HANDLED_BEYOND_NECESSARY`, shall be capped at 40% of the line value, and requires approval by a returns supervisor. |
| FR-REF-05 | The customer shall be notified by email and push when a refund is issued, with the amount and a per-line breakdown. |
| FR-REF-06 | Contact-centre agents may issue goodwill refunds of up to 50 GBP/EUR per order; larger amounts require team-leader approval recorded in Meridian. |
| FR-REF-07 | Each refund shall be executed exactly once at the PSP, including when calls are retried after timeouts or failures. |

### 3.2 Non-functional requirements

| ID | Category | Requirement |
|---|---|---|
| NFR-01 | Availability | The order placement endpoint shall achieve 99.95% monthly availability. The returns and status endpoints shall achieve 99.9%. Availability is measured as the proportion of valid requests that receive a non-5xx response within 5 seconds. |
| NFR-02 | Latency | Order placement shall complete with p95 ≤ 400 ms and p99 ≤ 900 ms measured at the Meridian edge, at the 2027 forecast peak of 1,200 orders per minute. Payment authorisation is performed by the BFF before submission and is excluded. |
| NFR-03 | Throughput | Meridian shall sustain 1,200 orders per minute for two hours with 30% headroom on every component, including asynchronous processing. |
| NFR-04 | Event propagation | A state change shall be delivered to every subscribed downstream consumer within 60 seconds at p99. |
| NFR-05 | Durability | No accepted order and no recorded state change may be lost. In-region RPO is zero; cross-region RPO is ≤ 5 minutes. |
| NFR-06 | Recovery | Regional failover shall complete within 60 minutes (RTO). |
| NFR-07 | Scalability | The design shall scale to twice the 2027 forecast peak by configuration only. |
| NFR-08 | Accessibility | Customer-facing order, return and refund journeys shall conform to WCAG 2.2 level AA. |
| NFR-09 | Observability | Every request and event shall carry a correlation ID; all services shall emit structured logs, RED metrics and traces to the central observability platform. |
| NFR-10 | Security | Internet-facing APIs shall meet OWASP ASVS 4.0 Level 2. |
| NFR-11 | Data retention | Personal data shall be retained no longer than required by the retention schedule in section 8.5. |
| NFR-12 | Cost | Steady-state run cost shall not exceed 70% of the current Atlas run cost (infrastructure plus licences). |

### 3.3 Compliance requirements

| ID | Requirement |
|---|---|
| CMP-01 | Meridian shall comply with the UK GDPR, the Data Protection Act 2018 and the EU GDPR, including data subject rights of access and erasure, storage limitation and data minimisation. |
| CMP-02 | Meridian shall honour the statutory right of withdrawal for distance contracts under Directive 2011/83/EU (Consumer Rights Directive) as transposed in IE, DE, NL and FR, and under the UK Consumer Contracts (Information, Cancellation and Additional Charges) Regulations 2013. For goods, the withdrawal period is 14 days from the day the consumer acquires physical possession of the goods, or of the last item where items of one order are delivered separately. |
| CMP-03 | Financial records (invoices, credit notes, refund records) shall be retained for the statutory period of the market concerned: UK 6 years, IE 6 years, NL 7 years, DE 10 years, FR 10 years. |
| CMP-04 | Meridian shall remain outside the PCI DSS cardholder data environment. It shall not store, process or transmit primary account numbers; it shall hold only PSP tokens and references. |
| CMP-05 | Customer-facing journeys in EU markets shall meet the accessibility requirements of the European Accessibility Act, which applies to e-commerce services from 28 June 2025. |

---

## 4. Design Principles

**P1. The order is the aggregate.** All state for an order (header, lines, shipments, payment references and status) is owned by a single aggregate with a single writer, the Order Orchestrator. Other services read it through events or the read model and request changes through commands.

**P2. Events are facts and are never lost.** Every state change produces exactly one domain event. Delivery to consumers is at-least-once; consumers are idempotent on event ID.

**P3. Idempotency on every external side-effect.** Any call that changes state outside Meridian (PSP, WMS, carrier, email) carries an idempotency key and can be safely retried.

**P4. Statutory rights are policy, not code paths.** Eligibility, windows, exclusions and deductions are expressed in a versioned policy module per market, reviewed by Legal (Consumer), and unit-tested against a catalogue of scenarios.

**P5. Degrade gracefully.** A dependency that is not essential to taking an order must not prevent an order from being taken. Essential dependencies are explicitly listed (section 5.3).

**P6. Personal data in as few places as practical.** Personal data is held in the order aggregate and the customer identity platform; other stores hold references wherever practical.

**P7. Managed services first.** Prefer AWS managed services over self-managed infrastructure unless a specific requirement cannot be met.

**P8. Everything as code.** Infrastructure, pipelines, dashboards, alarms and policy rules are defined in version control and deployed through the standard H&R delivery pipeline.

---

## 5. Architecture

### 5.1 Context

Meridian sits between the customer-facing channels and the operational back office. Channels submit orders and return requests to Meridian. Meridian calls FraudShield and IAS synchronously during placement, and the Payments Gateway, WMS integration layer and Carrier Hub asynchronously thereafter. Meridian publishes domain events that Finance ERP, CRM, marketing and the analytics lake consume.

```
 Web / App BFF   Contact-centre CRM   Trade Portal
        \              |                /
         \             |               /
          +---- API Gateway + WAF ----+
                       |
        +--------------+------------------------------+
        |              MERIDIAN (eu-west-1)           |
        |  Order API   Order Orchestrator   Returns   |
        |  Refund Svc  Notification Svc   Status API  |
        |  Fulfilment Adapter   Carrier Adapter       |
        +---------------------------------------------+
          |  sync          |  async (SNS/SQS)     |
     FraudShield, IAS   Payments Gateway, WMS,   Finance ERP, CRM,
                        Carrier Hub              Analytics, Marketing
```

### 5.2 Components

| Component | Responsibility | Runtime |
|---|---|---|
| Order API | Validates and accepts orders, cancellations and order queries from channels. Enforces idempotency on placement. | ECS on Fargate behind API Gateway |
| Order Orchestrator | Single writer of the order aggregate. Applies commands (fraud result, reservation result, WMS events, carrier events, cancellation) and publishes domain events. | ECS on Fargate, SQS consumers |
| Fulfilment Adapter | Translates release, intercept and cancellation commands into WMS integration-layer messages; translates WMS pick/pack/despatch messages into commands. | ECS on Fargate |
| Carrier Adapter | Receives tracking webhooks from Carrier Hub; requests outbound and return labels; books home collections. | ECS on Fargate |
| Returns Service | Return initiation, eligibility (policy module), label and collection orchestration, receipt and inspection recording, disposition. Owner of return records. | ECS on Fargate, Aurora PostgreSQL |
| Refund Service | Refund calculation, deductions, approvals, store credit, instruction of refunds through the Payments Gateway, refund status tracking. Owner of refund records. | ECS on Fargate, Aurora PostgreSQL |
| Notification Service | Emails (via the H&R messaging platform) and push notifications for order, shipment, return and refund milestones. | ECS on Fargate |
| Status API and read model | Denormalised, query-optimised view of orders and returns for customers and agents. | ECS on Fargate, DynamoDB |
| Event Archive | Durable archive of all domain events for audit, replay and analytics. | Kinesis Data Firehose to S3 |

### 5.3 Synchronous dependencies at order placement

Order placement makes two synchronous calls. They are classified as follows.

| Dependency | Purpose | Contracted or measured availability | Latency (p95) | Classification | Behaviour when unavailable |
|---|---|---|---|---|---|
| IAS reservation API | Reserve stock per line | 99.95% (internal SLO, measured 99.97% over last 12 months) | 45 ms | Essential | Reject with 503; BFF shows retry message |
| FraudShield screening API | Fraud score and decision | 99.5% monthly (contractual SLA) | 180 ms | Essential (see DEC-07) | Reject with 503; BFF shows retry message |
| Tax engine | Not called at placement; the basket tax quote is carried in the request and verified by signature | n/a | n/a | n/a | n/a |
| Payments Gateway | Not called at placement; the authorisation token is verified locally by signature | n/a | n/a | n/a | n/a |

FraudShield returns one of `ACCEPT`, `REVIEW` or `REJECT`. `REVIEW` orders are accepted and held in `PENDING_REVIEW` until a fraud analyst decides; they are not released to fulfilment. `REJECT` orders are refused and the authorisation is voided by the BFF.

### 5.4 Asynchronous messaging

Meridian uses Amazon SNS topics with Amazon SQS subscriptions for asynchronous messaging. There are two families of topics.

**Order event stream.** All order, shipment, return and refund domain events are published to an SNS FIFO topic, `order-events.fifo`, with one SQS FIFO queue per consumer (Order Orchestrator command queue, Refund Service, Status read-model projector, CRM connector, Finance connector, Event Archive). FIFO was chosen because Finance ERP reconciliation requires events in sequence and because several consumers apply state transitions that are only valid in order (for example `Shipped` before `Delivered`).

- `MessageDeduplicationId` is set to the event ID, so that a re-publish of the same event within the five-minute deduplication interval is discarded by SNS.
- `MessageGroupId` is set to the constant `order-events`. This gives every consumer a single total order of all events, which the Finance connector relies on because it maintains a single high-water mark sequence number across all orders.

**Notification stream.** Customer notifications are triggered from a standard (non-FIFO) SNS topic, `customer-notifications`, with a standard SQS queue for the Notification Service. Ordering is not required for notifications: each message is self-contained and carries the milestone it relates to. The Notification Service deduplicates on `(eventId, channel)` in a DynamoDB table with a 7-day TTL, so duplicate deliveries do not result in duplicate emails or pushes. Standard queues give effectively unlimited throughput at peak.

### 5.5 Payments Gateway integration for refunds

The Refund Service instructs refunds through the Payments Gateway, which forwards them to the PSP and returns the PSP refund reference. The Payments Gateway passes through the `Idempotency-Key` header to the PSP unchanged; the PSP retains idempotency keys for 24 hours.

1. The Refund Service creates a `refund` record in state `READY` with the calculated amount.
2. A refund worker picks up `READY` refunds, creates a `refund_attempt` record with a new `attempt_id` (UUID v4), and calls `POST /v2/refunds` on the Payments Gateway with `Idempotency-Key: {attempt_id}`. Using a distinct key per attempt means each attempt appears separately in the PSP dashboard, which Finance Operations asked for to make investigation of failures easier.
3. On a `2xx` response the refund moves to `SUBMITTED` and the PSP reference is stored. Final confirmation (`SETTLED` or `FAILED`) arrives later via the PSP webhook relayed by the Payments Gateway.
4. On a timeout, connection error or `5xx`, the attempt is marked `ERROR` and the refund remains `READY`. The worker retries with exponential backoff (initial 30 seconds, factor 2, maximum interval 1 hour) for up to 24 hours, after which the refund moves to `MANUAL_REVIEW`.
5. On a `4xx` response other than `409` or `429`, the refund moves to `MANUAL_REVIEW` immediately.

### 5.6 Deployment topology

- **Primary region:** AWS eu-west-1 (Ireland), three Availability Zones. All ECS services run a minimum of two tasks per AZ.
- **Standby region:** AWS eu-central-1 (Frankfurt), warm standby. ECS services are deployed with a desired count of one task per service and are scaled up during failover.
- **DynamoDB:** global tables replicating eu-west-1 to eu-central-1. Writes are directed only to the active region; the standby replica is read-only by convention (enforced through IAM in the standby).
- **Aurora PostgreSQL 16:** Aurora Global Database with the writer in eu-west-1, one reader per AZ, and a secondary cluster in eu-central-1. Typical replication lag is under one second.
- **SNS/SQS:** deployed in both regions; the standby region's topics are idle until failover.
- **Edge:** Amazon API Gateway (regional) behind AWS WAF; Route 53 failover records for the API hostname.

### 5.7 Technology choices

| Concern | Choice | Notes |
|---|---|---|
| Language and framework | Kotlin 2.x on JVM 21, Spring Boot 3 | Matches the H&R commerce platform standard |
| Order store | Amazon DynamoDB, on-demand capacity | See DEC-02 |
| Returns and refunds store | Amazon Aurora PostgreSQL 16 | See DEC-03 |
| Messaging | Amazon SNS and SQS | See DEC-04 |
| Event archive | Kinesis Data Firehose to S3 | See DEC-05 |
| Policy module | Embedded rules library (Kotlin DSL), versioned per market | See DEC-06 |
| Infrastructure as code | Terraform with the H&R module library | |
| CI/CD | H&R standard pipeline (GitHub Actions to AWS CodeDeploy, blue/green for ECS) | |
