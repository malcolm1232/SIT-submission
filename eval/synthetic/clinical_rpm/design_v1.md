# HPHC Remote Patient Monitoring Platform — Detailed Design

**Harbourfront Public Healthcare Cluster · Digital Health Platforms**

Architecture, requirements, and validation criteria for build

| | |
|---|---|
| Version | 1.0 |
| Status | Design phase — build not started |
| Last updated | 2026-08-14 (architecture) · consolidated 2026-08-21 |
| Prepared by | HPHC Digital Health Platforms Team, with the Clinical Informatics Office |
| Clinical sponsor | Chair, HPHC Clinical Safety Board (CSB) |
| Companion documents | HPHC RPM Conceptual Design v1.2; HPHC RPM Clinical Safety Case (draft) |

---

## Table of Contents

1. Purpose and Scope
2. Requirements
3. Foundational Principles
4. Clinical Alerting Model
5. Target Architecture
6. Device Fleet and Message Envelope
7. Ingestion Layer
8. Stream Processing and Rule Evaluation
9. ML Early-Warning Service (EWS-ML)
10. Alert Management and Notification
11. Clinician Dashboards
12. EMR Integration (HL7 FHIR R4)
13. Data Model and Storage
14. Device Lifecycle Management
15. Security Architecture
16. Identity, Access Control and Break-Glass
17. Data Governance and Privacy
18. Availability, Resilience and Disaster Recovery
19. Prior Art and Reference Architecture
20. Confirmed Decisions
21. Pending Backlog
22. Validation and Acceptance Criteria
23. Build Readiness Assessment
24. Build Phases

---

## 1. Purpose and Scope

This document describes the architecture of the Harbourfront Public Healthcare Cluster (HPHC) Remote Patient Monitoring Platform (RPM-P) — a cluster-wide platform that receives continuous vital signs from wearable and bedside IoT devices, evaluates them against clinically governed rules and a machine-learning early-warning model, and routes alerts to the right clinician at the right time. It is written to a level of technical detail sufficient for an engineering team to begin implementation. Section 23 gives an explicit assessment of where that is and is not yet true.

RPM-P is not a replacement for bedside monitor alarms in high-acuity areas. It is a cluster-level platform that provides:

- Continuous monitoring of general-ward inpatients wearing biosensor patches, and of virtual-ward patients at home under the Mobile Inpatient Care@Home (MIC@Home) programme.
- Rule-based alerting (per-parameter thresholds and a partial NEWS2 score) and ML-based deterioration alerting.
- Alert routing, acknowledgement, and escalation to nurses and doctors via the cluster clinician mobile app and ward paging.
- Clinician dashboards: ward overview, patient trend view, and alert inbox.
- HL7 FHIR R4 integration with the cluster EMR for observations, ADT context, and manual observations.
- Device lifecycle management from receipt to decommissioning, including patient-device binding.
- Audit trails for every access to patient data, supporting PDPA and MOH data-governance obligations.

### In scope

- General wards across the cluster's three acute hospitals (Harbourfront General Hospital, Telok Kurau Hospital, and Bukit Panjang Regional Hospital) and two community hospitals.
- MIC@Home virtual-ward patients managed by the cluster's virtual ward teams.
- Approximately 8,000 concurrently streaming devices at steady state: ~5,600 ward biosensor patches, ~1,400 bedside vital-signs monitors on step-down beds, and ~1,000 home monitoring kits.
- 24/7 operation.

### Out of scope

- Intensive care units, high-dependency units, and operating theatres. These are served by vendor central stations with their own validated alarm systems; RPM-P does not ingest from them in this release (Pending Backlog B-1).
- Patient-facing mobile application for home patients (Pending Backlog B-5). Home kits are pre-paired and require no patient app.
- Any treatment-recommendation functionality. RPM-P raises alerts; it does not recommend treatment.

---

## 2. Requirements

Requirements are grouped into Functional Requirements (what the platform must do) and Non-Functional Requirements (the quality attributes it must exhibit). Each requirement carries an ID that is used again in Section 22 (Validation and Acceptance Criteria) and Section 23 (Build Readiness Assessment).

### 2.1 Functional Requirements

| ID | Requirement |
|---|---|
| FR-1 | The platform shall ingest vital signs from registered devices over MQTT 3.1.1 secured with TLS: heart rate, SpO2, respiratory rate, skin temperature, posture/activity, and (bedside monitors only) non-invasive blood pressure. |
| FR-2 | Every telemetry message shall carry device_id, a per-device monotonically increasing sequence number, the device timestamp, and the gateway receive timestamp; the platform shall additionally record the IoT Hub enqueue timestamp. |
| FR-3 | A device shall be associated with a patient only through a positive binding event that scans two identifiers (patient wristband or MIC@Home enrolment barcode, and device QR code). Telemetry from an unbound device shall never be attributed to a patient. |
| FR-4 | The platform shall evaluate per-parameter threshold rules and a partial NEWS2 score (pNEWS2) for every bound patient, as defined in Section 4. |
| FR-5 | The ML Early-Warning Service (EWS-ML) shall compute a deterioration risk score for every bound patient at least every 5 minutes and raise an alert when the score crosses the configured threshold for that patient's cohort. |
| FR-6 | Every alert shall carry exactly one priority — High, Medium, or Low — assigned according to the mapping in Section 4.3. |
| FR-7 | The Alert Service shall suppress duplicate alerts for the same patient within a 5-minute window, so that clinicians are not repeatedly re-notified for an ongoing condition. |
| FR-8 | Unacknowledged alerts shall escalate: High priority to the charge nurse at 60 s and to the ward doctor on call at 120 s; Medium priority to the charge nurse at 5 minutes. These escalation intervals are mandated by IEC 60601-1-8, clause 6.11 (distributed alarm systems). |
| FR-9 | The platform shall raise technical alerts for device disconnection, sensor detachment, low battery, and poor signal quality, with the priorities given in Section 4.4. |
| FR-10 | Clinicians shall be able to view a ward overview, a per-patient trend view, and an alert inbox, and shall acknowledge alerts under their own authenticated identity. |
| FR-11 | The platform shall publish device-derived vital-sign observations to the EMR as HL7 FHIR R4 Observation resources, as specified in Section 12. |
| FR-12 | The platform shall consume ADT events (admit, transfer, discharge) from the cluster integration engine to maintain care-team assignment and to unbind devices automatically on discharge. |
| FR-13 | Every read of patient-identifiable data, every alert state change, every binding/unbinding event, and every configuration change shall be written to an immutable audit store recording actor, patient, action, timestamp, outcome, and reason (where applicable). |
| FR-14 | Devices shall be managed through the lifecycle states defined in Section 14; no device may stream patient data unless it is in the Bound state. |
| FR-15 | The platform shall produce anonymised extracts for model development and service evaluation, as specified in Section 17.4. |
| FR-16 | Device firmware updates shall be cryptographically signed, deployed in stages, and applied only to devices not currently bound to a patient. |

### 2.2 Non-Functional Requirements

| ID | Requirement |
|---|---|
| NFR-1 | The platform shall support 8,000 concurrently streaming devices at steady state, with capacity for a 25% surge (10,000 devices) during outbreak or surge-bed activation, without architectural change. |
| NFR-2 | For High-priority physiological alerts, the time from sensor measurement to the alert being presented on the assigned clinician's device shall be ≤ 10 s at p95. For Medium priority, ≤ 30 s at p95. |
| NFR-3 | The alert pipeline (ingestion → evaluation → notification) shall achieve ≥ 99.95% monthly availability. |
| NFR-4 | The alert pipeline shall remain available through the loss of a single availability zone with no alert loss, and through the loss of the entire cloud region with an RTO of ≤ 15 minutes. |
| NFR-5 | The clinician dashboard shall reflect new readings within 5 s of ingestion and support 500 concurrent clinician sessions. |
| NFR-6 | All transport shall use TLS 1.2 or higher. Devices shall authenticate individually to the platform; no anonymous device connections shall be accepted. |
| NFR-7 | All PHI at rest shall be encrypted with customer-managed keys (CMK) held in Azure Key Vault Managed HSM, rotated at least annually, so that the cluster can revoke the platform's access to data independently of the cloud provider. |
| NFR-8 | Audit records shall be immutable (write-once) and retained for the period set by the cluster records retention schedule. |
| NFR-9 | All patient-identifiable data, including telemetry, backups, and logs, shall be stored and processed only within Singapore, as required by Section 26 of the Personal Data Protection Act 2012 (PDPA). |
| NFR-10 | A new device model shall be onboarded by publishing a device adapter profile (parameter mapping, units, sampling rate) without code changes to the rule engine, Alert Service, or dashboards. |
| NFR-11 | Clinical rule content (thresholds, pNEWS2 mapping, escalation timings) shall be versioned, CSB-approved before activation, and changeable without redeployment. |
| NFR-12 | Every alert shall be traceable to the raw readings, rule or model version, and notification attempts that produced it. |

---

## 3. Foundational Principles

These principles govern every design decision in the platform. Where a later section appears to conflict with one of these, the principle wins.

| # | Principle |
|---|---|
| P1 | **Bedside alarms stay primary for inpatients.** On wards with bedside monitors, the monitor's own audible alarm is the primary alarm. RPM-P is a secondary, remote notification layer. For MIC@Home patients, RPM-P is the primary monitoring channel and is designed accordingly. |
| P2 | **Clinicians own the thresholds.** Every threshold, score mapping, and escalation timing is clinical content, approved by the CSB, versioned, and auditable. Engineers implement; they do not choose clinical values. |
| P3 | **The EMR is the legal medical record.** RPM-P is a monitoring system, not a system of record. Anything that becomes part of the medical record lives in the EMR. |
| P4 | **Clinician validates before charting.** Device-derived observations enter the EMR as preliminary data and become part of the legal medical record only after a nurse has validated them. Unvalidated device data is never presented as charted observation. |
| P5 | **No attribution without positive binding.** A reading belongs to a patient only if a two-identifier binding event exists for that device and time. |
| P6 | **Care-team scoped access.** Clinicians see patients they are caring for; anything else is break-glass and audited. |
| P7 | **Configuration, not code.** New devices, new rules, and new wards are onboarded by configuration under change control. |
| P8 | **Minimum necessary data leaves the platform.** Extracts, integrations, and logs carry only the fields their purpose needs. |
| P9 | **Every alert is explainable.** From any alert, a clinician or auditor can trace back to the readings, rule or model version, and every delivery attempt. |

---

## 4. Clinical Alerting Model

This section defines what the platform alerts on and at what priority. It was developed with the Clinical Informatics Office and approved by the CSB (decision CSB-2026-014). It is the clinical specification that Sections 8–10 implement.

### 4.1 Alert classes

| Class | Source | Examples |
|---|---|---|
| Physiological — threshold | Rule engine (Section 8) | SpO2 sustained below threshold; HR sustained above threshold |
| Physiological — score | Rule engine (Section 8) | pNEWS2 aggregate or single-parameter red score |
| Physiological — predictive | EWS-ML (Section 9) | Deterioration risk above cohort threshold |
| Technical | Device and connectivity monitoring | Disconnected, sensor off, low battery, poor signal |

### 4.2 Partial NEWS2 (pNEWS2)

NEWS2 (Royal College of Physicians, 2017) aggregates seven parameters: respiration rate, SpO2 (Scale 1 or Scale 2), supplemental oxygen, systolic blood pressure, pulse, level of consciousness (ACVPU), and temperature. Wearable patches measure only some of these continuously, so the platform computes a partial score with explicit rules rather than presenting a full NEWS2 it cannot measure.

| NEWS2 parameter | Source in RPM-P | Freshness rule |
|---|---|---|
| Respiration rate | Patch (continuous) | Rolling 2-minute median |
| SpO2 | Patch or bedside monitor (continuous) | Rolling 2-minute median; Scale 2 only if prescribed (see below) |
| Supplemental oxygen | Manual observation from EMR (FHIR) | Most recent within 4 h |
| Systolic BP | Bedside monitor NIBP or manual observation | Most recent within 4 h |
| Pulse | Patch or bedside monitor (continuous) | Rolling 2-minute median |
| Consciousness (ACVPU) | Manual observation from EMR (FHIR) | Most recent within 4 h |
| Temperature | Manual observation from EMR (FHIR) | Most recent within 4 h. Skin temperature from patches is **not** used for NEWS2 because it is not a validated surrogate for core temperature. |

Rules:

- If every manually sourced parameter is within its freshness window, the platform computes the aggregate pNEWS2 and labels it "pNEWS2 (complete)".
- If any manually sourced parameter is stale, the platform does **not** compute an aggregate. It evaluates single-parameter scores only for the continuously measured parameters and raises a Low-priority "observations due" task for the ward nurse. The dashboard displays "pNEWS2 incomplete — manual observations due", never a number.
- SpO2 Scale 2 (target 88–92%, for patients with hypercapnic respiratory failure) is used only when a doctor has prescribed it in the EMR, as NEWS2 requires. The prescription is read through FHIR and has an expiry; on expiry the patient reverts to Scale 1.

### 4.3 Priority mapping

Platform priorities follow the alarm-priority semantics of IEC 60601-1-8: High requires immediate response, Medium requires prompt response, and Low requires awareness.

| Condition | NEWS2 clinical risk | Platform priority |
|---|---|---|
| pNEWS2 (complete) aggregate ≥ 7 | High | High |
| pNEWS2 (complete) aggregate 5–6 | Medium | Medium |
| Any single continuous parameter scoring 3 | Low–medium | Medium |
| Hard threshold breach (Table 4.3b) | — | High |
| EWS-ML risk above cohort threshold | — | Medium |
| pNEWS2 aggregate 1–4 | Low | No alert; shown on dashboard |

**Table 4.3b — hard thresholds (CSB-2026-014, default adult values; per-patient overrides permitted by a doctor, with mandatory expiry ≤ 72 h):**

| Parameter | High-priority threshold | Persistence |
|---|---|---|
| SpO2 (Scale 1) | < 85% | 10 s window |
| Heart rate | < 40 or > 140 bpm | 10 s window |
| Respiratory rate | < 8 or > 30 /min | 10 s window |

The persistence window exists to suppress artefact (motion, probe displacement) and is deliberately part of the clinical definition of the alert condition.

### 4.4 Technical alert priorities

| Technical condition | Ward patient | MIC@Home patient |
|---|---|---|
| No data from bound device > 60 s | Low | Medium (after 5 min) |
| Sensor detached / no skin contact | Low | Medium (after 5 min) |
| Battery < 15% | Low | Low |
| Poor signal quality > 2 min | Low | Low |

Technical alerts for MIC@Home are higher priority because there is no bedside alarm or nearby nurse to notice a disconnected patient.

---

## 5. Target Architecture

Every telemetry message, from every device, for every patient, flows through the same governed path. No clinician-facing component reads from a device directly.

```
+-----------------------------------------------------------------------+
| DEVICES                                                               |
|  Ward biosensor patches (BLE) -> Ward IoT Edge gateways (transparent) |
|  Bedside vital-signs monitors (Wi-Fi, MQTT direct)                    |
|  MIC@Home kits: patch (BLE) -> cellular home hub                       |
+-----------------------------------+-----------------------------------+
                                    | MQTT 3.1.1 over TLS (8883)
+-----------------------------------v-----------------------------------+
| INGESTION — Azure IoT Hub (Southeast Asia)  + Device Provisioning Svc |
|  Message routing: (a) raw -> Event Hub "vitals-raw" -> ADX            |
|                   (b) built-in endpoint -> Stream Analytics           |
+-----------------+-------------------------------------+---------------+
                  |                                     |
+-----------------v-------------+     +-----------------v---------------+
| STREAM EVALUATION             |     | TIME-SERIES STORE               |
|  Azure Stream Analytics       |     |  Azure Data Explorer (ADX)      |
|  thresholds, pNEWS2, tech     |     |  hot: 90 days; export -> ADLS   |
+-----------------+-------------+     +-----------------+---------------+
                  |                                     | features
                  |                   +-----------------v---------------+
                  |                   | EWS-ML (Azure ML online endpt)  |
                  |                   +-----------------+---------------+
+-----------------v-------------------------------------v---------------+
| ALERT SERVICE (AKS) -> ALERT DISPATCHER (AKS)                         |
|  persist, dedup, route, escalate   -> Notification Hubs (mobile app)  |
|  Alert store: PostgreSQL Flexible  -> Ward paging gateway (on-prem)   |
+-----------------------------------+-----------------------------------+
                                    |
+-----------------------------------v-----------------------------------+
| CLINICIAN EXPERIENCE: Dashboard web app (AKS, SignalR), mobile app    |
+-----------------------------------------------------------------------+
| INTEGRATION: FHIR Publisher / ADT Consumer <-> Cluster integration    |
|              engine <-> EMR                                           |
+-----------------------------------------------------------------------+
| CONTROL PLANE: Device Registry & Lifecycle, Rule Content Service,     |
|                Audit Store (immutable ADLS), Key Vault Managed HSM    |
+-----------------------------------------------------------------------+
```

*Figure 1 — Target architecture. Raw telemetry is persisted independently of evaluation, so a stream-job failure does not lose data.*

### Layer responsibilities

- **Devices and gateways** — measure, timestamp, buffer during link loss, and publish batched telemetry.
- **Ingestion** — device authentication, MQTT termination, message routing to storage and evaluation.
- **Stream evaluation** — windowed threshold rules, pNEWS2, technical-condition detection.
- **Time-series store** — raw and derived vitals for trend views, ML features, and FHIR publication.
- **EWS-ML** — periodic risk scoring per bound patient.
- **Alert Service and Dispatcher** — alert persistence, deduplication, routing to the responsible clinician, escalation, acknowledgement.
- **Clinician experience** — dashboard and mobile app.
- **Integration** — FHIR publication to the EMR; ADT and manual-observation consumption from the EMR.
- **Control plane** — device registry and lifecycle, CSB-approved rule content, audit, keys. The control plane is not in the real-time telemetry path.

---

## 6. Device Fleet and Message Envelope

### 6.1 Device classes

| Class | Count (steady state) | Connectivity | Parameters | Publish interval |
|---|---|---|---|---|
| Ward biosensor patch | ~5,600 | BLE to ward IoT Edge gateway | HR, SpO2, RR, skin temp, posture | Batched, every 5 s |
| Bedside vital-signs monitor | ~1,400 | Hospital Wi-Fi, MQTT direct | HR, SpO2, RR, NIBP (on cycle) | Batched, every 5 s |
| MIC@Home kit (patch + hub) | ~1,000 | BLE to cellular home hub (4G) | HR, SpO2, RR, skin temp, posture | Batched, every 5 s |

Each batched message carries the 1 Hz samples accumulated since the previous publish (five samples per parameter) and is ≤ 2 KB.

**Buffering.** Patches buffer up to 30 minutes of samples on-device when the BLE link to the gateway or home hub is lost, and replay them in order on reconnection. Home hubs buffer up to 4 hours when cellular connectivity is unavailable.

**Clocks.** Patches set their clock from the gateway or home hub at each BLE connection. The vendor specifies drift of ≤ 2 s per day between synchronisations. Ward gateways synchronise to the hospital NTP servers; home hubs use network-provided time (NITZ) with NTP fallback.

### 6.2 Message envelope

```json
{
  "schema": "rpm.telemetry.v1",
  "device_id": "HGH-PATCH-004211",
  "model": "patch-vendorA-gen3",
  "fw": "3.4.1",
  "seq": 1048213,
  "device_ts": "2026-08-14T09:12:05.000+08:00",
  "gw_id": "HGH-W12-GW02",
  "gw_rx_ts": "2026-08-14T09:12:05.180+08:00",
  "samples": {
    "hr":   [{"t": 0, "v": 92}, {"t": 1, "v": 93}, ...],
    "spo2": [{"t": 0, "v": 95, "q": 0.98}, ...],
    "rr":   [{"t": 0, "v": 18, "q": 0.91}, ...]
  },
  "battery_pct": 64,
  "contact": true
}
```

Design notes:

- **seq** is a per-device monotonic counter persisted across reboots. Consumers use (device_id, seq) as the idempotency key, so replayed or duplicated publishes are discarded deterministically regardless of timestamps.
- **Three timestamps** are kept: device_ts (when measured), gw_rx_ts (when the gateway received it), and the IoT Hub enqueue time (added by the platform). The gap between them is recorded with every reading so clock problems and buffering are visible in the data rather than hidden.
- **Sample quality (q)** is passed through from the device's signal-quality index; readings with q below the device adapter profile's floor are stored but excluded from rule evaluation.
- **Patient identity is not in the envelope.** Devices do not know which patient they are on. Attribution happens in the platform, by joining on the binding table (Section 14.3). A device that is lost or reused never carries patient identifiers.
- **schema** is versioned; device adapter profiles (NFR-10) map vendor fields into this canonical envelope at the gateway.

---

## 7. Ingestion Layer

### 7.1 MQTT and topics

Devices and gateways connect to Azure IoT Hub using MQTT 3.1.1 over TLS 1.2 on port 8883. Ward patches connect through Azure IoT Edge gateways configured as transparent gateways, so each patch keeps its own device identity in IoT Hub and is individually addressable, revocable, and audited. Telemetry uses the standard IoT Hub device-to-cloud topic `devices/{device_id}/messages/events/` with message properties `schema`, `class`, and `site`.

### 7.2 Routing

| Route | Condition | Endpoint | Purpose |
|---|---|---|---|
| raw-to-store | all telemetry | Event Hub `vitals-raw` → ADX streaming ingestion | Persist every accepted message |
| eval | all telemetry | Built-in endpoint (Event Hubs-compatible) | Stream Analytics input |
| lifecycle | `class = lifecycle` | Service Bus queue `device-lifecycle` | Battery, contact, firmware, error events |

IoT Hub's built-in endpoint retains messages for 7 days, allowing replay into a rebuilt Stream Analytics job.

### 7.3 Capacity sizing

| Metric | Value |
|---|---|
| Devices (steady state / surge) | 8,000 / 10,000 |
| Message rate per device | 1 per 5 s |
| Aggregate message rate (steady / surge) | 1,600 / 2,000 msg/s |
| Daily messages (steady state) | 8,000 × 17,280 = ~138 M/day |
| Message size | ≤ 2 KB (one 4 KB metering unit) |
| IoT Hub tier | S2, 3 units |
| Tier capacity | 60 M messages/day per S2 unit → 180 M/day |
| Headroom over steady state | ~30% |

At the S2 tier the device-to-cloud throttle is not a binding constraint at this message rate; the daily message quota is the sizing driver. Surge to 10,000 devices (~173 M/day) remains within the 3-unit allocation.

---

## 8. Stream Processing and Rule Evaluation

### 8.1 Job design

A single Azure Stream Analytics (ASA) job reads from the IoT Hub built-in endpoint and joins three reference inputs:

- **binding** — active device-to-patient bindings, refreshed from PostgreSQL every 60 s and on every binding change event.
- **rules** — the active, CSB-approved rule-content version (thresholds, overrides, pNEWS2 mapping).
- **manualobs** — latest manual observations per patient (BP, ACVPU, supplemental O2, temperature) fed by the FHIR consumer.

The job emits three outputs: physiological alert candidates and technical alert candidates to the Alert Service (via Service Bus topic `alert-candidates`), and pNEWS2 values to ADX for dashboard display.

### 8.2 Event-time configuration

| Setting | Value | Rationale |
|---|---|---|
| Timestamp | `TIMESTAMP BY device_ts` | Rules must evaluate readings in the order they were measured, not the order they arrived |
| Out-of-order tolerance | 5 s | Covers reordering across gateway and IoT Hub partitions |
| Late-arrival tolerance | 5 s | Keeps window outputs timely for the latency target |
| Action for events outside tolerance | Drop | Avoids re-timestamping readings into the wrong window, which would distort persistence rules |

### 8.3 Rule evaluation

- **Threshold rules** use a 10-second tumbling window per patient and parameter (the persistence window of Table 4.3b). A candidate is emitted when the window median crosses the threshold, and evaluation is on samples with quality at or above the profile floor.
- **pNEWS2** is evaluated every 30 s from 2-minute rolling medians of continuous parameters and the manual-observation reference input, applying the freshness rules of Section 4.2.
- **Technical conditions** use the absence of any message for a bound device for > 60 s (a left outer join of the binding reference against per-device message counts in a 60-second hopping window), contact flags, battery level, and quality indices.

Every candidate carries rule_id, rule-content version, the window boundaries, and the contributing sample sequence numbers (NFR-12).

---

## 9. ML Early-Warning Service (EWS-ML)

### 9.1 Model

| Aspect | Specification |
|---|---|
| Task | Probability of clinical deterioration within 24 h (composite: rapid-response activation, unplanned ICU transfer, or death) |
| Algorithm | Gradient-boosted trees (LightGBM) |
| Features | 1-, 4- and 12-hour summaries (median, slope, variability) of HR, SpO2, RR; most recent manual BP and ACVPU; age; Charlson comorbidity index from EMR problem list |
| Training data | HPHC general-ward inpatient admissions, 2021–2025 (~410,000 admissions) |
| Retrospective performance | AUROC 0.86 on a temporally held-out 2025 test set (inpatients) |
| Operating point | Cohort-specific threshold; inpatient threshold set at sensitivity 0.80, yielding 0.6 alerts per patient-day on the test set |

### 9.2 Serving

EWS-ML runs as an Azure Machine Learning managed online endpoint (three instances across zones). A scheduler on AKS queries ADX feature views for every bound patient every 5 minutes and calls the endpoint in batches. Scores above the cohort threshold produce an alert candidate on the same Service Bus topic as rule-based candidates, carrying model name, version, and the top five feature contributions (SHAP) so the clinician can see why the alert was raised (P9).

### 9.3 Model governance

- Models are registered in the Azure ML registry with lineage to the training data snapshot and code commit.
- A model version becomes active only on CSB approval; activation is a rule-content change (NFR-11).
- Weekly monitoring reports alert rate per cohort, score distribution drift (population stability index), and outcome-linked performance once 24-hour outcomes are available.
- On drift beyond the agreed band, the Clinical Informatics Office reviews and may revert to the previous version.

### 9.4 Cohort use

For the inpatient cohort, EWS-ML alerts complement the rule-based alerts of Section 4. For the MIC@Home cohort, EWS-ML is the primary deterioration alert from Phase 4 (Decision D-15); rule-based hard thresholds remain active for MIC@Home as a safety net.

---

## 10. Alert Management and Notification

### 10.1 Alert Service

The Alert Service (AKS deployment, three replicas across zones) consumes `alert-candidates`, enriches each candidate with patient, location, and care-team context, persists it in the alert store (PostgreSQL), and passes it to the Alert Dispatcher. Persisting before dispatch means no candidate is acknowledged off the topic until it is durable.

### 10.2 Alert states

```
RAISED -> NOTIFIED -> ACKNOWLEDGED -> RESOLVED
            |              ^
            +-> ESCALATED -+
RAISED -> SUPPRESSED (duplicate, per FR-7)
```

All transitions are audited (FR-13), with actor, timestamp, and device used.

### 10.3 Alert Dispatcher

The Alert Dispatcher determines who should receive each alert and drives escalation.

- **Routing.** The responsible nurse is resolved from the ADT-driven care-team assignment (bed → nurse for the current shift). MIC@Home alerts route to the virtual-ward nurse on duty.
- **Channels.** The cluster clinician mobile app via Azure Notification Hubs (APNs/FCM), and the ward paging system via the on-premises paging gateway for High priority.
- **Deduplication.** Duplicate alerts are suppressed per FR-7 before notification.
- **Escalation.** Escalation timers per FR-8 start when the alert is NOTIFIED and are cancelled on acknowledgement.
- **Deployment.** The Dispatcher runs as a single replica (Kubernetes Deployment, `replicas: 1`). Deduplication state and escalation timers are held in process memory, which guarantees strict ordering of escalation steps and avoids the coordination cost of distributed timers. A liveness probe restarts the pod on failure, typically within 30 s.

### 10.4 Latency budget (NFR-2)

| Segment | p95 budget |
|---|---|
| Sensor → device BLE notification to gateway / hub | 0.5 s |
| Gateway or hub → IoT Hub (MQTT/TLS over hospital WAN or 4G) | 0.7 s |
| IoT Hub → Stream Analytics input | 1.0 s |
| Stream Analytics evaluation and output | 1.0 s |
| Alert Service persist + Dispatcher routing | 0.3 s |
| Notification Hubs → APNs/FCM → clinician device | 1.5 s |
| **Total** | **5.0 s** |

NFR-2 (≤ 10 s at p95) is therefore met with 5 s (50%) headroom.

### 10.5 Acknowledgement

Acknowledgement is performed in the mobile app or dashboard by the authenticated clinician, never by a shared account. Acknowledging stops escalation; resolving requires a reason code (treated, false alarm — artefact, false alarm — patient-specific, transferred). Reason codes feed the alert-fatigue review in Section 9.3 and Backlog B-8.

---

## 11. Clinician Dashboards

| View | Content | Refresh |
|---|---|---|
| Ward overview | Bed grid with patient initials, latest HR/SpO2/RR, pNEWS2 or "incomplete", EWS-ML band, open alerts, device status | Push (SignalR), ≤ 5 s |
| Patient trend | 1 h / 12 h / 72 h trends from ADX, alert markers, manual observations overlaid, binding history | On open, then push |
| Alert inbox | Open alerts for the clinician's patients, sorted by priority then age; acknowledge and resolve actions | Push |
| Virtual ward | MIC@Home patients with connectivity status, last reading age, and technical alerts | Push |

The dashboard web app runs on AKS behind an in-region Azure Application Gateway (WAF v2) and is reachable only from the cluster network and the managed mobile app. Patient lists are scoped by care-team assignment (Section 16).

---

## 12. EMR Integration (HL7 FHIR R4)

### 12.1 Inbound

| Data | Mechanism | Use |
|---|---|---|
| ADT (admit, transfer, discharge) | HL7 v2 ADT A01/A02/A03/A08 from the cluster integration engine, converted to FHIR Encounter | Care-team assignment, location, auto-unbind on discharge |
| Manual observations (BP, ACVPU, supplemental O2, temperature) | FHIR Subscription (rest-hook) on Observation, filtered to bound patients | pNEWS2 inputs |
| SpO2 Scale 2 prescription | FHIR ServiceRequest / flowsheet order, read on binding and on change | pNEWS2 scale selection |
| Problem list, age | FHIR Condition, Patient | EWS-ML features |

### 12.2 Outbound

Every 15 minutes, the FHIR Publisher posts a transaction Bundle per bound patient containing one Observation per vital sign (the median of the interval), with `status = final`, conforming to the FHIR R4 vital-signs profile. The EMR files these directly to the inpatient flowsheet, so they appear alongside nurse-entered observations without a nurse re-keying them.

| Vital | LOINC | Unit (UCUM) |
|---|---|---|
| Heart rate | 8867-4 | /min |
| Oxygen saturation (pulse oximetry) | 2708-6 + 59408-5 | % |
| Respiratory rate | 9279-1 | /min |
| Blood pressure panel | 85354-9 (8480-6, 8462-4) | mm[Hg] |

Each Observation carries `device` (reference to the FHIR Device for the patch or monitor), `effectivePeriod` (the 15-minute interval), and a `meta.tag` identifying RPM-P as source. Skin temperature is not published, for the reason given in Section 4.2.

### 12.3 Error handling

Failed posts are retried with exponential backoff for up to 2 hours, then raised to the integration support queue. Because the time-series store is the platform's source for publication, a retry always posts the same medians for the same interval (idempotent on patient + code + effectivePeriod).

---

## 13. Data Model and Storage

### 13.1 Store summary

| Data | Store | Retention | Encryption at rest |
|---|---|---|---|
| Raw and derived vitals | Azure Data Explorer, hot cache 30 days, retention 90 days | 90 days hot, then export to ADLS | Microsoft-managed keys |
| Vitals archive | ADLS Gen2 (Parquet), cool tier | Per cluster records schedule | CMK (Managed HSM) |
| Alerts, bindings, device registry, rule content | Azure Database for PostgreSQL Flexible Server, zone-redundant HA | Alerts per records schedule | CMK (Managed HSM) |
| Audit | ADLS Gen2 immutable container (time-based retention policy, locked) | Per records schedule (NFR-8) | CMK (Managed HSM) |
| Model artefacts and features | Azure ML registry / ADX feature views | Per model lifecycle | Platform default |

### 13.2 ADX vitals table

```kql
.create table Vitals (
    device_id: string,
    patient_id: string,        // joined at ingestion via binding update policy
    encounter_id: string,
    param: string,             // hr | spo2 | rr | skin_temp | nibp_sys | nibp_dia | posture
    value: real,
    unit: string,
    quality: real,
    seq: long,
    device_ts: datetime,
    gw_rx_ts: datetime,
    hub_enq_ts: datetime
)
```

An update policy joins incoming rows to the binding table on device_id and device_ts within the binding interval. Rows with no matching binding are written to `VitalsUnattributed` with patient_id empty, for device-quality analysis only (P5).

### 13.3 PostgreSQL schema (core tables)

```sql
CREATE TABLE device (
    device_id      TEXT PRIMARY KEY,
    model          TEXT NOT NULL,
    class          TEXT NOT NULL,       -- patch | bedside | home_kit
    state          TEXT NOT NULL,       -- see Section 14.1
    fw_version     TEXT,
    site           TEXT,
    updated_at     TIMESTAMPTZ NOT NULL
);

CREATE TABLE device_binding (
    binding_id     UUID PRIMARY KEY,
    device_id      TEXT NOT NULL REFERENCES device(device_id),
    patient_id     TEXT NOT NULL,       -- cluster MRN
    encounter_id   TEXT NOT NULL,
    bound_at       TIMESTAMPTZ NOT NULL,
    unbound_at     TIMESTAMPTZ,
    bound_by       TEXT NOT NULL,       -- clinician user id
    unbind_reason  TEXT,                -- discharge | manual | swap | fault
    EXCLUDE USING gist (device_id WITH =, tstzrange(bound_at, unbound_at) WITH &&)
);

CREATE TABLE alert (
    alert_id       UUID PRIMARY KEY,
    patient_id     TEXT NOT NULL,
    encounter_id   TEXT NOT NULL,
    class          TEXT NOT NULL,       -- threshold | score | predictive | technical
    rule_id        TEXT NOT NULL,
    content_ver    TEXT NOT NULL,       -- rule-content or model version
    priority       TEXT NOT NULL,       -- HIGH | MEDIUM | LOW
    state          TEXT NOT NULL,
    raised_at      TIMESTAMPTZ NOT NULL,
    evidence       JSONB NOT NULL       -- window bounds, seq list, SHAP top-5
);

CREATE TABLE alert_event (
    alert_id       UUID REFERENCES alert(alert_id),
    event          TEXT NOT NULL,       -- NOTIFIED | ESCALATED | ACK | RESOLVED | SUPPRESSED
    actor          TEXT,
    channel        TEXT,
    at             TIMESTAMPTZ NOT NULL,
    detail         JSONB
);
```

The exclusion constraint on `device_binding` makes it impossible for one device to be bound to two patients over overlapping intervals.

---

## 14. Device Lifecycle Management

### 14.1 Lifecycle states

```
RECEIVED -> REGISTERED -> AVAILABLE -> BOUND -> UNBOUND -> CLEANING -> AVAILABLE
                              |          |                    |
                              |          +-> FAULT -> QUARANTINED -> AVAILABLE | DECOMMISSIONED
                              +-> FW_UPDATING -> AVAILABLE
```

| State | Entry condition | Streaming permitted? |
|---|---|---|
| RECEIVED | Goods receipt by Biomedical Engineering | No |
| REGISTERED | Identity created (Section 15.2), acceptance test passed | Test data only, to quarantine stream |
| AVAILABLE | Cleaned, charged, firmware current | No |
| BOUND | Two-identifier binding event (14.3) | Yes |
| UNBOUND | Discharge (ADT A03), manual unbind, or swap | No (data routed to unattributed table) |
| CLEANING | Returned to ward store | No |
| FAULT / QUARANTINED | Self-test failure, repeated quality failures, damage, or suspected tampering | No |
| FW_UPDATING | Staged firmware rollout (14.4) | No |
| DECOMMISSIONED | End of life, loss, or unrecoverable fault | No; identity disabled |

### 14.2 Registration

Biomedical Engineering registers each device by scanning its QR code at goods receipt. Registration creates the device record (Section 13.3), the device identity (Section 15.2), and runs an acceptance test: connection, timestamp sanity (device_ts within 2 s of gw_rx_ts after sync), and a reference-signal check against a simulator.

### 14.3 Patient-device binding

- The nurse scans the patient wristband (inpatient) or MIC@Home enrolment barcode, then the device QR code, in the mobile app. Both identifiers are required (FR-3); manual typing of either is not permitted.
- The app displays the patient's full name, date of birth, and bed, and requires the nurse to confirm.
- The binding is written to PostgreSQL and pushed to the ASA binding reference input and the ADX binding table.
- On discharge (ADT A03), all bindings for the encounter are closed automatically. On transfer (A02), bindings persist and the care-team assignment follows the new location.
- A device swap (fault, battery) is a single transaction: unbind old, bind new, with the reason recorded.

### 14.4 Firmware updates

- Firmware images are signed by the vendor and countersigned by HPHC Biomedical Engineering; devices verify both signatures before applying (FR-16).
- Rollout uses IoT Hub automatic device management in stages: 5% of AVAILABLE devices, then 25%, then 100%, with automatic halt if the post-update self-test failure rate exceeds 1% at any stage.
- Updates are applied only to devices in AVAILABLE. A BOUND device is never updated mid-monitoring; it receives the update after it next passes through CLEANING.

### 14.5 Decommissioning

Decommissioning disables the device identity in DPS and IoT Hub, records the reason, and triggers a factory reset that wipes buffered samples. Lost devices are decommissioned immediately on report. Because the envelope never carries patient identifiers (Section 6.2), a lost device exposes no patient identity; buffered samples on it are unattributed physiological values.

---

## 15. Security Architecture

### 15.1 Network

- All PaaS services use private endpoints; public network access is disabled except IoT Hub, which accepts device connections from the internet for MIC@Home hubs over TLS 1.2 with IP filtering for ward gateways.
- AKS is a private cluster; egress goes through Azure Firewall with an allow-list.
- The on-premises paging gateway and integration engine are reached over ExpressRoute.
- The dashboard is exposed only through Application Gateway WAF v2 with cluster network and managed-device conditional access.

### 15.2 Device identity

Device identities are created through the IoT Hub Device Provisioning Service (DPS) using a symmetric-key group enrollment per device class. Each device's key is derived from the group enrollment key by HMAC-SHA256 over the device's registration ID. To allow devices to self-provision on first boot without a per-device manufacturing step, the group enrollment key is included in the signed firmware image and the device derives its own key at first boot. This avoids a separate key-injection step at the vendor factory and lets Biomedical Engineering register devices by QR scan alone. Ward IoT Edge gateways and home hubs use X.509 certificates issued by the cluster's private CA.

### 15.3 Data protection

- TLS 1.2+ everywhere (NFR-6); TLS 1.3 where the service supports it.
- Encryption at rest as in Section 13.1.
- Secrets and keys in Azure Key Vault Managed HSM; workload identities for AKS pods; no secrets in configuration files.

### 15.4 Threat model highlights

| Threat | Control |
|---|---|
| Spoofed clinician acknowledges alert | Entra ID with MFA; acknowledgement bound to authenticated user; audit |
| Compromised ward gateway | X.509 identity revocable per gateway; transparent gateway cannot alter per-device authentication |
| Tampering with rule content | Rule content changes require CSB approval workflow with two-person rule; versioned and audited |
| Replay of telemetry | (device_id, seq) idempotency |
| Data exfiltration from analytics | Private endpoints, egress allow-list, extract governance (Section 17.4) |

---

## 16. Identity, Access Control and Break-Glass

### 16.1 Authentication

Clinicians authenticate with the cluster Entra ID tenant using MFA. The mobile app runs only on cluster-managed devices (Intune), with app-level PIN or biometric re-authentication after 5 minutes of inactivity. Shared ward workstations use the cluster's existing tap-and-go badge session, so each action is attributable to an individual.

### 16.2 Authorisation

| Role | Access |
|---|---|
| Ward nurse | Patients in care-team assignment for current shift; acknowledge and resolve alerts; bind and unbind devices |
| Charge nurse | All patients on the ward; escalation target |
| Doctor | Patients under their team; per-patient threshold overrides (with expiry) |
| Virtual-ward nurse / doctor | MIC@Home patients assigned to their virtual-ward team |
| Biomedical Engineering | Device registry and lifecycle; no patient identifiers |
| Clinical Informatics | Rule content authoring (activation requires CSB approval) |
| Platform operations | Infrastructure and logs; no patient identifiers in operational logs |

Care-team assignment is derived from ADT location plus the shift roster, refreshed on every ADT event and at shift change.

### 16.3 Break-glass

A clinician who needs to view a patient outside their care-team scope may invoke break-glass by selecting a reason (emergency response, cross-cover, consult) and free text. Access is time-boxed to the remainder of the shift (maximum 12 hours), is shown with a visible banner, and generates an entry in the Data Protection Office review queue. Every break-glass event is reviewed retrospectively within 7 days; unjustified use is referred under the cluster's acceptable-use policy. Break-glass does not grant the ability to change thresholds or rule content.

### 16.4 Audit

Every patient-data read, alert action, binding change, override, and break-glass event is written to the immutable audit store (FR-13, NFR-8). Patients' data-access requests can be answered with a per-patient access report generated from the audit store.

---

## 17. Data Governance and Privacy

### 17.1 Legal and policy basis

- **PDPA 2012** — notification and consent for monitoring (obtained at MIC@Home enrolment and documented in the EMR; for inpatients, under the admission notice), purpose limitation, protection, retention limitation, access and correction, and the transfer limitation and data residency requirement captured in NFR-9.
- **Data breach notification** — PDPA Part 6A: notifiable breaches are reported to the PDPC as soon as practicable and no later than 3 calendar days after the cluster assesses a breach to be notifiable; affected individuals are notified where required.
- **MOH and cluster policy** — the cluster Data Governance Policy, Information Security Policy, and records retention schedule.

### 17.2 Purpose limitation

| Purpose | Data | Access |
|---|---|---|
| Direct clinical care | Identified, full | Care team (Section 16) |
| Device and service operations | Device-level, no patient identifiers | Biomedical Engineering, platform operations |
| Model development and service evaluation | Anonymised extract (17.4) | Clinical Informatics, approved ML partners |

### 17.3 Retention

Raw vitals are held in ADX for 90 days for trend review and model features, then exported to the ADLS archive and retained per the cluster records schedule. Charted observations live in the EMR (P3). Alerts and audit are retained per the records schedule.

### 17.4 Anonymised extracts

Extracts for model development and service evaluation are produced by a governed pipeline:

1. Direct identifiers are removed: NRIC/FIN, name, MRN, contact details, and free-text notes.
2. patient_id is replaced with a random study ID, unique per extract.
3. Retained fields: full vitals time series with timestamps to the second, ward and bed, age, sex, ethnicity, home postal code (MIC@Home cohort, used for the travel-time-to-hospital feature), diagnosis codes, and outcome labels.
4. The extract is written to the model-development workspace.

Because direct identifiers are removed, extracts are anonymised data and fall outside the PDPA's obligations. They may therefore be shared with approved ML partners in the partner's own development tenancy under the partner agreement, without further approval per extract.

---

## 18. Availability, Resilience and Disaster Recovery

### 18.1 Zone redundancy

All tiers are deployed across the three availability zones of the Azure Southeast Asia region:

| Component | Zone posture |
|---|---|
| IoT Hub, DPS | Zone-redundant (platform-managed) |
| Event Hubs, Service Bus (Premium) | Zone-redundant |
| Stream Analytics | Zone-redundant job placement |
| ADX | Zone-redundant cluster |
| PostgreSQL Flexible Server | Zone-redundant HA (synchronous standby in another zone) |
| AKS | Node pools across 3 zones; Alert Service 3 replicas |
| Azure ML endpoint | 3 instances across zones |

### 18.2 Region outage

The platform is deployed in a single region (Decision D-1). On a full regional outage:

- Inpatients: bedside monitor alarms remain primary (P1); wards revert to manual observation rounds per the cluster downtime procedure.
- MIC@Home: the virtual-ward team switches to scheduled telephone checks per the MIC@Home downtime procedure; patients follow the escalation instructions in their care plan.
- Platform recovery: redeploy from infrastructure-as-code and restore from zone-redundant backups when the region returns; estimated 4–8 hours after region availability.

### 18.3 Backups

PostgreSQL automated backups (35-day retention, zone-redundant storage); ADX follower and export to ADLS; infrastructure-as-code in the cluster repository. Backups remain in-region (NFR-9).

---

## 19. Prior Art and Reference Architecture

There is no single off-the-shelf platform that covers multi-vendor wearables, a cluster-wide alert routing model, and EMR integration under Singapore governance requirements. The closest references are standards and established patterns.

| Reference | What it covers | Concept match | Gap |
|---|---|---|---|
| IHE Patient Care Device (PCD) — Device Enterprise Communication (DEC) | Transmission of device observations to enterprise systems | Observation payload, device identity, time semantics | HL7 v2-centric; we use FHIR R4 for outbound |
| IHE PCD — Alert Communication Management (ACM) | Alert dissemination to clinicians, status feedback | Alert lifecycle, delivery and acknowledgement status | Profile, not product; escalation logic is ours |
| IEEE 11073 SDC | Service-oriented device connectivity at point of care | Device semantic model | Acute-care device networks; wearables do not implement it |
| HL7 FHIR R4 vital-signs profile and Device resources | Observation and device representation | Outbound observations, device references | Does not address streaming or alerting |
| NEWS2 (RCP 2017) | Aggregate early-warning score | pNEWS2 design | Designed for intermittent manual observation, hence the partial-score rules in Section 4.2 |
| Vendor central stations | Single-vendor monitoring and alarms in high-acuity areas | Alarm priority, central display | Single vendor; no wearable or home coverage; out of scope (B-1) |

### What we borrow

| From | Borrowed for RPM-P |
|---|---|
| IHE PCD ACM | Alert states and delivery-status feedback model (Section 10.2) |
| IHE PCD DEC | Three-timestamp time semantics and device identity in observations |
| FHIR R4 | Outbound Observation and Device representation |
| NEWS2 | Score structure, Scale 2 rules, clinical-risk bands |
| IEC 60601-1-8 | Alarm-priority semantics (High/Medium/Low) |

### What is specific to HPHC

- A single alert model spanning inpatient wards and home patients, with priorities adjusted for the absence of a bedside alarm at home.
- pNEWS2 with explicit freshness rules rather than imputing unmeasured parameters.
- Binding-based attribution so that devices never carry patient identity.

---

## 20. Confirmed Decisions

| ID | Decision | Answer |
|---|---|---|
| D-1 | Cloud and region | Azure Southeast Asia (Singapore), zone-redundant across 3 AZs; single region, no secondary region |
| D-2 | Ingestion | Azure IoT Hub, S2 tier × 3 units, with DPS |
| D-3 | Device protocol | MQTT 3.1.1 over TLS 1.2, port 8883 |
| D-4 | Device credentials | DPS symmetric-key group enrollment per device class; gateways and hubs on X.509 |
| D-5 | Ward patch connectivity | BLE to IoT Edge transparent gateways |
| D-6 | Stream evaluation | Azure Stream Analytics, event time = device_ts, out-of-order and late events outside tolerance dropped |
| D-7 | Time-series store | Azure Data Explorer, 90-day retention, export to ADLS |
| D-8 | Encryption at rest | ADX: Microsoft-managed keys (CMK deferred to reduce key-management overhead on the ingestion cluster); PostgreSQL, ADLS, audit: CMK in Managed HSM |
| D-9 | Alert store | PostgreSQL Flexible Server, zone-redundant HA |
| D-10 | Alert Dispatcher topology | Single replica, in-memory dedup and escalation timers, liveness-probe restart |
| D-11 | Deduplication window | 5 minutes (FR-7) |
| D-12 | Escalation timings | High: 60 s / 120 s; Medium: 5 min (FR-8) |
| D-13 | Notification channels | Clinician mobile app via Notification Hubs; on-prem paging gateway for High priority |
| D-14 | Outbound EMR integration | FHIR R4 Observation Bundle every 15 min per bound patient, status final, filed to flowsheet |
| D-15 | EWS-ML for MIC@Home | EWS-ML replaces pNEWS2 aggregate alerting as the primary deterioration alert for the MIC@Home cohort from Phase 4; hard thresholds retained |
| D-16 | pNEWS2 | Partial score with freshness rules (Section 4.2), CSB-2026-014 |
| D-17 | Skin temperature | Displayed as trend only; not used in NEWS2 or published to EMR |
| D-18 | Attribution | Binding table join; devices carry no patient identifiers |
| D-19 | Research extracts | Anonymised per Section 17.4; shareable with approved ML partners |
| D-20 | Firmware | Dual-signed, staged rollout, AVAILABLE devices only |

---

## 21. Pending Backlog

Items confirmed as in scope but not yet fully designed:

| ID | Item | Owner |
|---|---|---|
| B-1 | Integration with vendor central stations in ICU/HDU (read-only alarm forwarding) | Clinical Informatics |
| B-2 | Paging gateway API contract and delivery-receipt semantics with the paging vendor | Platform Integration |
| B-3 | Regulatory determination for EWS-ML under HSA's framework for software as a medical device (classification and whether product registration or an exemption applies), and the prospective silent-mode validation protocol for the MIC@Home cohort | Clinical Safety Board / Regulatory Affairs |
| B-4 | Alignment of outbound Observation profiles with the cluster FHIR implementation guide v2 when published | Integration Architecture |
| B-5 | Patient-facing app for home patients (symptom entry, device status) | Digital Health Products |
| B-6 | Archive tiering and cost optimisation for ADLS vitals archive | Platform Engineering |
| B-7 | Multilingual patient onboarding materials for MIC@Home kits | Virtual Ward Programme |
| B-8 | Alert-fatigue study design (post-go-live, using reason codes) | Nursing Informatics |

---

## 22. Validation and Acceptance Criteria

Each requirement from Section 2 is validated by a specific method with a concrete pass/fail acceptance criterion. This table is the basis for the test plan in Phase 6 (Section 24).

### 22.1 Functional requirements

| ID | Validation method | Acceptance criteria |
|---|---|---|
| FR-1 | Device conformance test | Each device class publishes all listed parameters; each is ingested and visible in ADX with correct unit and value within the simulator's reference tolerance. |
| FR-2 | Envelope contract test | Messages missing any of device_id, seq, device_ts, gw_rx_ts are rejected at the gateway adapter; stored rows carry all three timestamps. |
| FR-3 | Binding safety test | Telemetry from an AVAILABLE (unbound) device appears only in `VitalsUnattributed`; a binding attempt with manual entry of either identifier is refused. |
| FR-4 | Rule evaluation test | Simulator scripts for each Table 4.3b threshold and each pNEWS2 band produce exactly the expected candidates; stale manual observations produce "incomplete" and an observations-due task, never an aggregate. |
| FR-5 | Scoring cadence test | Over a 2-hour run with 500 simulated patients, every bound patient receives a score at intervals ≤ 5 min. |
| FR-6 | Priority mapping test | Every candidate type in Section 4.3 yields the specified priority. |
| FR-7 | Deduplication test | Two identical SpO2 alerts for the same patient 2 minutes apart: the second is SUPPRESSED. A third identical alert at 6 minutes is delivered. |
| FR-8 | Escalation timing test | Unacknowledged High alert escalates to charge nurse at 60 s ± 5 s and doctor at 120 s ± 5 s; acknowledgement before 60 s produces no escalation. |
| FR-9 | Technical alert test | Disconnect, contact loss, low battery, and low quality each produce the Section 4.4 priority for both cohorts. |
| FR-10 | Dashboard functional test | Each view renders for a ward of 40 patients; acknowledgement records the authenticated user. |
| FR-11 | FHIR contract test | Bundles validate against the FHIR R4 vital-signs profile and are accepted by the EMR test environment. |
| FR-12 | ADT simulation | A01/A02/A03/A08 messages produce the expected care-team changes; A03 closes all bindings for the encounter. |
| FR-13 | Audit completeness test | A scripted session of reads, acknowledgements, binding changes, and a break-glass yields exactly one audit record per action with all fields populated. |
| FR-14 | Lifecycle state test | A device in any state other than BOUND that publishes telemetry has its data routed to the unattributed table. |
| FR-15 | Extract pipeline test | Extracts contain no field from the direct-identifier list in Section 17.4. |
| FR-16 | Firmware test | An unsigned or singly-signed image is refused by the device; a BOUND device is not offered an update. |

### 22.2 Non-functional requirements

| ID | Validation method | Acceptance criteria |
|---|---|---|
| NFR-1 | Load test | 10,000 simulated devices at 1 msg/5 s for 24 h; no throttling errors, no message loss between IoT Hub and ADX. |
| NFR-2 | Alert latency test | A test harness in Azure Southeast Asia publishes synthetic threshold-crossing messages directly to IoT Hub at 1,600 msg/s; time from IoT Hub enqueue timestamp to the alert row being committed in the alert store is ≤ 10 s at p95 (High) and ≤ 30 s at p95 (Medium). |
| NFR-3 | Availability monitoring | Monthly availability computed from synthetic transactions ≥ 99.95% over the first three production months. |
| NFR-4 | Zone failure drill | With one zone's resources made unavailable, alert candidates continue to be produced and delivered; no alert row lost. |
| NFR-5 | Dashboard performance test | 500 concurrent sessions; new reading visible ≤ 5 s after ingestion at p95. |
| NFR-6 | Transport security scan | No endpoint accepts TLS < 1.2; a device connection without valid credentials is refused. |
| NFR-7 | Key management review | Every store in Section 13.1 marked CMK shows a Managed HSM key; rotation date within 12 months. |
| NFR-8 | Immutability test | An attempt to modify or delete an audit blob within the retention period fails. |
| NFR-9 | Residency audit | All resources and backups are deployed in Southeast Asia; no geo-redundant storage is enabled. |
| NFR-10 | Onboarding dry run | A new patch model is onboarded by publishing an adapter profile with zero code changes in rule engine, Alert Service, or dashboards. |
| NFR-11 | Rule-content change test | A threshold change takes effect without redeployment only after CSB approval is recorded; unapproved content cannot be activated. |
| NFR-12 | Traceability test | For 100 random alerts, the evidence field resolves to stored raw readings and a rule or model version, and every delivery attempt is in alert_event. |

---

## 23. Build Readiness Assessment

This section answers whether an engineering team could build each component from this document without further design decisions.

| Component | Ready? | What remains to decide |
|---|---|---|
| Device envelope and adapter profiles | Ready | Envelope and design notes are concrete (Section 6.2). |
| Ingestion (IoT Hub, DPS, routing) | Ready | Tier, routes, and identity model specified (Sections 7, 15.2). |
| Stream evaluation (ASA) | Ready | Inputs, event-time settings, and rules specified (Section 8). |
| Clinical alerting model | Ready | CSB-approved (Section 4). |
| EWS-ML serving | Ready | Serving pattern specified; model trained (Section 9). |
| Alert Service and Dispatcher | Ready | Topology, states, routing, escalation specified (Section 10). Paging delivery receipts depend on B-2. |
| Dashboards | Mostly ready | Views specified; detailed UX to be produced with Nursing Informatics. |
| FHIR integration | Mostly ready | Outbound and inbound specified; profile alignment pending (B-4). |
| Device lifecycle | Ready | States, binding, firmware, decommissioning specified (Section 14). |
| Security and access | Ready | Sections 15–16. |
| Data governance and extracts | Ready | Section 17. |
| DR | Ready | Single-region posture with downtime procedures (Section 18). |

**Overall conclusion.** The platform is buildable from this document for Phases 1–5. The remaining items in Section 21 are either out of the initial scope (B-1, B-5, B-7), integration details that do not change the architecture (B-2, B-4, B-6), or post-go-live activities (B-8). B-3 runs in parallel with Phase 4 build.

---

## 24. Build Phases

| # | Phase | Scope | Depends on open items? |
|---|---|---|---|
| 1 | Foundation | Landing zone, networking, IoT Hub, DPS, ADX, PostgreSQL, Key Vault, audit store | No — ready |
| 2 | Devices and lifecycle | Adapter profiles, IoT Edge gateways, registration, binding app, firmware pipeline | No — ready |
| 3 | Rules, alerts, dashboard — pilot | ASA job, Alert Service and Dispatcher, mobile app notifications, dashboards; pilot on 2 wards at Harbourfront General Hospital | No — ready |
| 4 | EWS-ML and EMR integration | EWS-ML serving; MIC@Home go-live with EWS-ML as primary deterioration alert; FHIR outbound and inbound | No — ready |
| 5 | Cluster scale-out | All in-scope wards and full MIC@Home cohort; paging integration | Partially — B-2 |
| 6 | Validation and hardening | Section 22 test plan, zone failure drills, security testing, clinical safety case finalisation | Follows Section 22 |

This document, together with the companion Conceptual Design and Clinical Safety Case, represents the design phase in full. No implementation has begun.
