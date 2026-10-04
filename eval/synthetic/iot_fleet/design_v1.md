# Rimbun Logistics: ArusFleet Telematics and Cold-Chain Platform

## Detailed Design

*Architecture, requirements, and validation criteria for build*

| | |
|---|---|
| **Version** | 1.0 |
| **Status** | Design phase, build not started |
| **Last updated** | 2026-09-11 (architecture) · consolidated 2026-09-18 |
| **Prepared by** | Rimbun Logistics Digital Engineering, Fleet Platforms Team |
| **Companion documents** | ArusFleet Conceptual Design v0.9; Cold-Chain Quality Manual QM-07; Gateway Hardware Specification GW-400 rev C |

---

## Table of Contents

1. Purpose and Scope
2. Requirements
3. Foundational Principles
4. Markets, Fleet and Customers
5. Cold-Chain Obligations
6. Target Architecture
7. Devices: Gateways and Sensors
8. Streaming Backbone
9. Message Envelope, Time and Deduplication
10. Connectivity, Offline Buffering and Backfill
11. Driver Behaviour and Scoring
12. Geofencing
13. Remote Commands
14. Firmware Build and Image Verification
15. Firmware Rollout Waves and Rollback
16. Cold-Chain Excursion Rules and Mean Kinetic Temperature
17. Alert Service and Alert Routing
18. Quality Review and Audit Pack
19. Dispatcher Console, Customer Portal and Consignee Tracking
20. Data Model and Storage
21. Data Retention
22. Identity, Access and Device Security
23. Resilience, Availability and Disaster Recovery
24. Capacity and Cost Budget
25. Observability and Operations
26. Confirmed Decisions
27. Pending Backlog
28. Validation and Acceptance Criteria
29. Implementation Readiness Assessment
30. Build Phases

---

## 1. Purpose and Scope

This document describes the architecture of ArusFleet, the telematics and cold-chain monitoring platform of Rimbun Logistics Berhad. ArusFleet collects position, vehicle and driving data from every Rimbun truck and temperature data from every refrigerated trailer, turns that data into live operational views for dispatchers, alerts people when a temperature-controlled load is at risk, scores driving behaviour, updates gateway firmware over the air, and produces the cold-chain records that customers and regulators inspect. It is written to a level of detail sufficient for an engineering team to begin implementation, and Section 29 assesses where that is and is not yet true.

ArusFleet replaces three systems: a vendor telematics portal used for the dry fleet in Malaysia and Singapore, a separate data-logger service used for reefer trailers, whose loggers are downloaded by cable at the depot, and a set of spreadsheets that the quality team uses to assemble temperature evidence for pharmaceutical customers. None of these share vehicle identities, and the reefer loggers give no live view at all.

### In scope

Device connectivity and ingestion, offline buffering, the streaming backbone, live position and geofencing, driver behaviour events and scores, remote commands, over-the-air (OTA) firmware updates, cold-chain excursion detection and alerting, the quality review workflow and audit pack, the dispatcher console, the customer portal, consignee tracking links, storage, retention and the security model, for the fleet in Section 4.

### Out of scope

Transport management (orders, route planning, billing), which remains in the existing TMS and is integrated through the trip feed in Section 6; workshop and maintenance management; the driver mobile app (a separate design consumes the ArusFleet API); and fuel-card reconciliation.

### Volume baseline

| Metric | 2026 actual | Design target (2028) |
|---|---|---|
| Trucks (prime movers and rigid) with a gateway | 5,100 | 6,400 |
| Reefer trailers with a gateway | 1,800 | 2,300 |
| Total connected gateways | 6,900 | 8,700 |
| Average driving hours per truck per day | 10.4 | 11 |
| Cold-chain trips per month | 21,000 | 29,000 |
| Share of cold-chain trips carrying pharmaceutical product | 31% | 38% |
| Customer and depot geofences | 24,000 | 38,000 |

---

## 2. Requirements

Requirements are numbered for traceability to the acceptance criteria in Section 28.

### 2.1 Functional Requirements

| ID | Requirement |
|---|---|
| FR-1 | Ingest position and vehicle data from every truck gateway: while the truck is moving, a drive message every 10 seconds carrying ten 1 Hz frames; while the ignition is on and the truck is stationary, a position every 30 seconds; while the ignition is off, a position every 15 minutes. |
| FR-2 | Ingest a cold-chain reading every 60 seconds from every reefer gateway: four load-space probes, return-air and supply-air temperature, setpoint, door state and reefer unit status. |
| FR-3 | Buffer readings on the gateway for up to 72 hours without connectivity and deliver them to the platform on reconnection. |
| FR-4 | Show every vehicle's live position, status and current trip on the dispatcher console map. |
| FR-5 | Raise entry and exit events for depot, customer-site and restricted-zone geofences. |
| FR-6 | Detect cold-chain excursions using the rules in Section 16. |
| FR-7 | Alert an excursion to the dispatcher assigned to the trip and to the driver within 2 minutes of detection. |
| FR-8 | Detect driver behaviour events (harsh braking, harsh acceleration, harsh cornering, speeding and excessive idling) and compute a daily driver score. |
| FR-9 | Publish a monthly driver score to the HR system for the safe-driving incentive. |
| FR-10 | Update gateway firmware over the air in waves, with automatic rollback. |
| FR-11 | Send remote commands to gateways: reefer setpoint change, trailer door lock and unlock, and vehicle immobilisation. |
| FR-12 | Give customers a portal with trip history, temperature charts, excursion summaries and proof of delivery. |
| FR-13 | Give consignees a tracking link that shows the live position and estimated arrival of their delivery. |
| FR-14 | Produce an audit pack per shipment: the continuous temperature record, excursions and their dispositions, mean kinetic temperature, any corrections, and the chain of custody. |
| FR-15 | Provide a quality review workflow in which a quality officer reviews each excursion and records a disposition. |
| FR-16 | Apply the retention and deletion rules in Section 21. |

### 2.2 Non-Functional Requirements

| ID | Requirement |
|---|---|
| NFR-1 | Ingestion availability of 99.9% per calendar month, measured as the share of minutes in which the platform accepts device messages. |
| NFR-2 | Completeness: at least 99.99% of the cold-chain readings taken by reefer gateways reach the cold-chain store, including after connectivity gaps of up to 72 hours. |
| NFR-3 | Alert latency: 99% of excursion alerts are delivered within 2 minutes of the reading that completes the excursion rule reaching the platform. |
| NFR-4 | Position freshness: for 99% of moving vehicles, the position shown on the dispatcher console is no more than 30 seconds old. |
| NFR-5 | Record integrity: cold-chain records are complete, attributable and unaltered from capture to audit; an audit pack can be regenerated identically at any time within the retention period. |
| NFR-6 | Device security: every gateway has a unique X.509 identity and all device traffic uses TLS 1.2 or later with mutual authentication. |
| NFR-7 | Privacy: driver personal data is processed in line with the personal data protection laws of Malaysia, Singapore, Thailand and Indonesia. |
| NFR-8 | Retention as set out in Section 21. |
| NFR-9 | Recovery: RPO of zero on loss of an Availability Zone; on loss of the region, RPO of 5 minutes for operational data and no permanent loss of cold-chain readings; RTO of 4 hours. |
| NFR-10 | Run cost no more than USD 95,000 per month at the 2028 fleet size, including cellular data. |
| NFR-11 | Scale to 12,000 gateways without architectural change. |
| NFR-12 | The dispatcher console map loads within 3 seconds for a dispatcher's full vehicle list (up to 600 vehicles). |

---

## 3. Foundational Principles

| # | Principle | Implication |
|---|---|---|
| P1 | **The gateway is the source of truth for what happened on the road.** | Readings and events are timestamped and sequenced on the device; the platform never invents or interpolates a reading. |
| P2 | **At-least-once everywhere, idempotent consumers.** | Every message may arrive more than once; every consumer deduplicates on the envelope key in Section 9. |
| P3 | **Cold-chain records are immutable from capture to audit.** | A reading, once stored, is never altered; anything added later is recorded alongside it with who, when and why. |
| P4 | **Safety first.** | The platform never degrades the driver's control of the vehicle. |
| P5 | **Least privilege for people, services and devices.** | Each identity can reach only the data and actions its job needs. |
| P6 | **Driver location serves fleet operation only.** | Driver location is visible only to Rimbun staff with an operational need and, while a delivery is under way, to the receiving customer for that delivery. |
| P7 | **Managed services before self-managed ones.** | The team operates no broker, database or stream cluster it could buy as a managed service in the region. |
| P8 | **Design for poor coverage.** | Rural routes in Malaysia, Thailand and Indonesia lose coverage for hours; every device-facing flow tolerates long disconnection. |

---

## 4. Markets, Fleet and Customers

Rimbun operates line-haul and distribution in Malaysia (about 58% of trips), Singapore (11%), Thailand (18%) and Indonesia (13%), with cross-border line-haul between Malaysia and both Singapore and southern Thailand. Depots are in Shah Alam, Johor Bahru, Penang, Kuantan, Kuching, Kota Kinabalu, Singapore (Tuas), Bangkok (Lat Krabang), Hat Yai, Jakarta (Cikarang) and Surabaya.

The truck fleet is mixed: about 70% prime movers pulling Rimbun or customer trailers and 30% rigid trucks used for urban distribution. Reefer trailers are moved between prime movers several times a week, so each reefer trailer carries its own gateway and is never assumed to be paired with the same truck. Drivers on regional routes keep their prime mover at home between trips, a long-standing practice that saves a depot return of up to 200 km.

Cold-chain customers fall into three groups: pharmaceutical and vaccine distributors (2 to 8 °C), fresh and chilled food (0 to 4 °C) and frozen food (minus 18 °C or below). The pharmaceutical group drives most of the compliance requirements in Section 5.

---

## 5. Cold-Chain Obligations

Rimbun's pharmaceutical customers hold wholesale and distribution licences under which they must follow Good Distribution Practice (GDP) guidelines issued by the health-product regulator in each market. Their quality agreements with Rimbun pass the following obligations to Rimbun as their transport provider.

1. **Continuous monitoring.** The temperature of the load space is recorded throughout every trip at intervals of no more than 5 minutes, from loading to delivery, with no unexplained gaps.
2. **Calibrated probes.** Each probe is calibrated at least yearly against a reference traceable to a national standard, and the calibration certificate is linked to every reading the probe produced.
3. **Excursion handling.** Any excursion is reported to the customer's quality contact, and corrective action (re-icing, transfer to a backup vehicle, or diversion to the nearest approved depot) begins within 30 minutes of the excursion being detected.
4. **Record integrity.** Records are complete, consistent and accurate; original records are retained; any correction is attributable, dated and justified, and keeps the original value visible.
5. **Audit access.** On request from the customer or a regulator's GDP inspector, Rimbun produces the complete temperature record for any shipment within the last five years within two working days.

ArusFleet applies the same monitoring to food customers, whose contracts are less demanding, so that there is one cold-chain process.

---

## 6. Target Architecture

ArusFleet runs in AWS ap-southeast-1 (Singapore) across three Availability Zones, with backups and an archive copy in ap-southeast-5 (Malaysia).

```
  Truck gateways (GW-400T)          Reefer gateways (GW-400R)
          |   MQTT 3.1.1 over TLS, port 8883, LTE-M / LTE Cat 1   |
          +--------------------------+------------------------------+
                                     v
                         AWS IoT Core (device gateway, rules engine, jobs)
                                     |  IoT rule: Apache Kafka action
                                     v
                       Amazon MSK  (telemetry.v1, events.v1, coldchain.v1)
          +------------+-------------+--------------+-------------+-------------+
          v            v             v              v             v             v
     Position     Geofence      Driver-event    Excursion     Cold-chain     Archive
     writer       service       scorer          / alert svc   writer         writer
          |            |             |              |             |             |
          v            v             v              v             v             v
     Aurora PostgreSQL (PostGIS)  <---------------------------+  S3 (Object Lock)
          ^                                                      ap-southeast-1, copy
          |                                                      to ap-southeast-5
   ArusFleet API (ECS Fargate) <---- Dispatcher console, Customer portal, Consignee link
          |
          +----> TMS trip feed (in), HR incentive feed (out), SMS and push (SNS, FCM)
```

*Figure 1: Logical architecture. Commands and OTA jobs flow from the API through AWS IoT Core to gateways.*

### Layer responsibilities

| Layer | Responsibility |
|---|---|
| Devices | Sample sensors, detect driving events, timestamp and sequence, buffer offline, execute commands and firmware updates. |
| AWS IoT Core | Device authentication, MQTT broker, rules engine routing to MSK, device shadow for command state, IoT Jobs for OTA. |
| Amazon MSK | Durable, ordered per-vehicle streams; decouples ingestion from processing; seven-day replay window. |
| Stream services | Stateless or state-rebuilding consumers on ECS Fargate: position writer, geofence service, driver-event scorer, excursion and alert service, cold-chain writer, archive writer. |
| Aurora PostgreSQL | Operational store: vehicles, trips, positions, readings, geofences, events, excursions, users. PostGIS for spatial queries. |
| S3 archive | Write-once copy of cold-chain readings and audit packs, held under Object Lock in compliance mode. |
| ArusFleet API | Single API for the console, the portal, consignee links, the driver app and integrations. |

The TMS publishes trip assignments (trip, truck, trailer, driver, customer, consignee, planned stops and temperature range) to the API, which is how ArusFleet knows which load a reefer gateway is carrying.

---

## 7. Devices: Gateways and Sensors

Both gateway variants come from one hardware platform supplied by Halcyon Telematics, a regional manufacturer: an ARM Cortex-A7 application processor running an embedded Linux build, a secure element holding the device private key, an LTE-M and LTE Cat 1 modem with a multi-network SIM, a GNSS receiver, a 6-axis inertial unit, 512 MB of flash and a 72-hour backup battery.

| Variant | Installed in | Interfaces | Data produced |
|---|---|---|---|
| GW-400T | Truck cab | CAN bus (J1939) read-only tap, fuel-pump relay output, ignition sense, GNSS, IMU | Drive frames, positions, driver events, ignition and engine status |
| GW-400R | Reefer trailer | Reefer controller serial port, four wireless load-space probes (BLE), door sensor, door-lock actuator, GNSS | Cold-chain readings, door events, reefer alarms, positions |

The truck gateway reads the CAN bus through a read-only tap and controls a single relay in series with the fuel-pump supply, which is how immobilisation works (Section 13). The reefer gateway talks to the reefer controller over its documented serial protocol, which allows it to read status and change the setpoint.

Load-space probes are battery-powered BLE sensors with a resolution of 0.1 °C and an accuracy of ±0.3 °C between minus 30 and plus 30 °C. Each probe has a serial number that links it to its calibration certificate in the probe register (Section 20).

---

## 8. Streaming Backbone

All device data passes through Amazon MSK after AWS IoT Core. An IoT rule per message type uses the Apache Kafka rule action to produce to MSK, so no custom bridge runs between the broker and the stream.

| Topic | Key | Partitions | Content |
|---|---|---|---|
| telemetry.v1 | vehicle_id | 48 | Drive messages and positions from truck gateways |
| events.v1 | vehicle_id | 24 | Driver events, ignition, geofence events, command acknowledgements |
| coldchain.v1 | trailer_id | 24 | Cold-chain readings with the trailer's position, door events, reefer alarms and trailer geofence events |

Every topic has replication factor 3 across three Availability Zones, `min.insync.replicas = 2`, and producers use `acks = all` with idempotence enabled. Keying by vehicle or trailer gives per-device ordering within a partition, which the stream services rely on. Load is spread evenly because each partition carries the messages of about a hundred or more devices, so the differences between moving, stationary and parked vehicles average out; at the 2028 target the busiest topic (`telemetry.v1`) carries about 560 messages per second at peak, well inside the capacity of a three-broker `kafka.m7g.large` cluster, which the NFR-11 load test in Section 28 (1,800 messages per second for 4 hours) is to confirm.

Consumers are idempotent (Section 9) rather than relying on Kafka transactions, because the IoT rule action cannot take part in a consumer-to-producer transaction and messages can be duplicated before they reach MSK. Topic retention is seven days, which lets any consumer rebuild its state or replay after a failure. Schemas are registered in the AWS Glue Schema Registry with backward-compatible evolution enforced.

---

## 9. Message Envelope, Time and Deduplication

Every device message carries the same envelope:

| Field | Meaning |
|---|---|
| device_id | IoT thing name of the sending gateway |
| boot_id | Random 64-bit value generated at every gateway boot |
| seq | Monotonic sequence number, starting at 0 for each boot_id |
| device_ts | Time the reading was taken, UTC, from the GNSS-disciplined clock |
| clock_state | GNSS_LOCKED, HOLDOVER (no fix for up to 24 h) or FREE_RUNNING |
| type | Message type |

The gateway's real-time clock is disciplined by GNSS whenever a fix is available. In holdover the oscillator drifts by less than 2 seconds per day, which is negligible against the 60-second reading interval. Readings taken while FREE_RUNNING are kept and flagged so that the audit pack can show them as such. On ingestion the platform adds `ingest_ts`; a message whose `device_ts` is more than 5 minutes ahead of `ingest_ts` is stored, flagged CLOCK_AHEAD, and excluded from live alerting until reviewed.

MQTT QoS 1 means a message can arrive twice, and a gateway that resends its buffer after a reconnect can resend messages the platform already holds. Every consumer therefore deduplicates on `(device_id, boot_id, seq)`. Writers use an `INSERT ... ON CONFLICT DO NOTHING` on a unique key over these three columns plus `device_ts`, which a resent message carries unchanged and which the month-partitioned tables of Section 20.2 must include in every unique key. In-memory consumers keep, per device and `boot_id`, a bitmap of the sequence numbers seen in the last 72 hours of device time, rebuilt from the store when a partition is assigned, and drop a message whose `seq` is already in it, so a backfilled reading below the newest `seq` is still processed. Ordering for business logic is by `device_ts` within a device, never by arrival order, so backfilled readings slot into place in the record.

---

## 10. Connectivity, Offline Buffering and Backfill

Gateways connect to AWS IoT Core with MQTT 3.1.1 over TLS on port 8883, a keep-alive of 300 seconds, and a persistent session so that commands queued while a gateway is offline are delivered on reconnection. Reconnection uses exponential backoff from 2 seconds to 10 minutes with full jitter, so that a fleet-wide reconnection after a regional network event is spread out.

Every message is first written to a ring buffer in flash and then published. In normal operation a message leaves the buffer's pending set when its PUBACK is received; the reefer gateway keeps acknowledged readings in flash until they are overwritten, so that it can resend them on a RESEND_FROM command (Section 23.2). The truck gateway's buffer holds 72 hours of its own messages; the reefer gateway's buffer holds 72 hours of readings, which at one reading a minute is 4,320 readings.

When a reefer gateway has been offline for more than 10 minutes, it switches to backfill mode on reconnection. It sends new readings live as usual and, alongside them, uploads the buffered readings. The reefer gateway packs the whole buffered backlog into one gzip-compressed MQTT message, typically about 150 KB after a full day without coverage and at most about 420 KB for a full 72-hour buffer, which is within the 512 KB maximum MQTT payload size that AWS IoT Core accepts. The archive writer and cold-chain writer unpack the batch into individual readings, each with its original envelope, so deduplication and ordering work exactly as for live readings. The batch leaves the buffer when its PUBACK is received; until then the gateway retries it after each reconnection.

Truck gateways backfill in the same way, but at most 200 messages per minute so that a long-offline truck does not compete with its own live drive messages.

Cellular coverage is good on the main corridors (North-South Expressway, the Singapore causeway and the Bangkok to Hat Yai route) and weak or absent on parts of the Pan-Borneo Highway, the Kuantan to Kota Bharu coast road and the trans-Sumatra feeder routes used for Indonesian deliveries. Rimbun's 2025 logger data shows that 6% of cold-chain trips had at least one gap longer than 2 hours and 0.8% had a gap longer than 24 hours.

---

## 11. Driver Behaviour and Scoring

### 11.1 Events

The truck gateway detects driving events on the device from the 100 Hz IMU and the CAN speed signal, so that event detection does not depend on coverage.

| Event | Rule |
|---|---|
| Harsh braking | Longitudinal deceleration above 0.35 g for at least 0.5 s |
| Harsh acceleration | Longitudinal acceleration above 0.30 g for at least 0.5 s |
| Harsh cornering | Lateral acceleration above 0.30 g for at least 0.5 s |
| Speeding | Travelling above the speed limit for more than 10 consecutive seconds |
| Excessive idling | Engine running with speed 0 for more than 10 minutes outside a depot geofence |

### 11.2 Score

Each driver starts every driving day at 100 points. Each harsh event deducts 2 points, each speeding event deducts 1 point per started 10 seconds over the limit, and each excessive-idling event deducts 1 point. The daily score is floored at 0 and normalised per 100 km driven, so that long-haul drivers are not penalised for distance. Scores are computed per driving day, defined as 00:00 to 24:00 in the local time of the driver's home depot. The monthly score is the distance-weighted mean of the daily scores.

### 11.3 Use of scores

The monthly score feeds the safe-driving incentive, which pays up to MYR 400 (or the local equivalent) a month to drivers scoring 85 or more. Drivers see their events and daily scores in the driver app and can dispute an event within 14 days; a fleet supervisor reviews disputed events using the drive frames around the event.

### 11.4 Pipeline

The driver-event scorer consumes `events.v1` and `telemetry.v1`, attributes each event to the driver logged in on the gateway (by driver card), and writes events to Aurora as they arrive. A nightly scoring job computes the daily scores from the stored events and distance, and the monthly job runs on the first day of each month. Its schedule is in Section 25.

---

## 12. Geofencing

Geofences are polygons (depots, customer sites, ports, border posts) or corridors (restricted roads for heavy vehicles), stored in Aurora with PostGIS in EPSG:4326 and edited in the console. There are about 38,000 at the 2028 target, with a median of 12 vertices.

The geofence service consumes truck positions from `telemetry.v1` and trailer positions from `coldchain.v1` and evaluates each position against an in-memory R-tree of geofence bounding boxes, followed by an exact point-in-polygon test on the candidates. The full set of geofences takes about 60 MB in memory, and the service reloads changed geofences every 60 seconds from a change table. Each service instance owns a set of MSK partitions and keeps the inside or outside state of each vehicle for each nearby geofence; on partition reassignment it rebuilds that state from the last stored geofence events of the vehicles it now owns before it processes new positions.

GNSS fixes jitter, especially in container yards and under elevated roads. To avoid flapping, a vehicle enters a geofence only after two consecutive fixes inside the polygon, and leaves only after two consecutive fixes outside the polygon buffered by 50 metres. Fixes with a horizontal dilution of precision above 5 are used for the map but not for geofence state changes. Entry and exit events are written to `events.v1` with the `device_ts` of the first qualifying fix, so dwell times are not inflated by the confirmation rule. A trailer's entry and exit events are also written to `coldchain.v1`, keyed by trailer, so that the excursion service sees them alongside the readings (Section 16.2, rule 4).

---

## 13. Remote Commands

### 13.1 Command set

| Command | Target | Who may send it | Effect |
|---|---|---|---|
| SET_SETPOINT | Reefer gateway | Dispatcher, Quality officer | Changes the reefer setpoint within the trip's temperature range |
| DOOR_LOCK / DOOR_UNLOCK | Reefer gateway | Dispatcher | Operates the trailer door-lock actuator |
| IMMOBILISE / RELEASE | Truck gateway | Security controller | Opens or closes the fuel-pump relay |

### 13.2 Delivery

The API publishes each command at QoS 1 on the gateway's command topic (`rimbun/v1/<device_id>/cmd`) and also writes it to the device shadow's desired state, which the gateway reads on every reconnection, so a command survives a disconnection longer than the persistent session. The gateway reports the outcome in the shadow's reported state and on `events.v1`. Every command carries a command ID, the sender's user ID and an expiry; a gateway ignores a command received after its expiry, which is 30 minutes for setpoint and door commands and 24 hours for immobilisation.

### 13.3 Immobilisation

Immobilisation exists for vehicle theft and for unauthorised use, which together caused 14 incidents in 2025. A security controller in the 24x7 operations centre raises IMMOBILISE after a police report or after confirming unauthorised use with the driver's supervisor. The truck gateway executes IMMOBILISE as soon as it receives the command, opening the fuel-pump relay so that the engine stops and the truck cannot be driven further. RELEASE closes the relay. Both are recorded in the command audit log with the sender, reason and police report number where there is one.

### 13.4 Setpoint changes

The reefer gateway accepts a setpoint only inside the trip's temperature range from the TMS, confirms the new setpoint by reading it back from the reefer controller, and reports both values. A setpoint change during a trip is shown on the temperature chart and in the audit pack.

---

## 14. Firmware Build and Image Verification

### 14.1 Build

Gateway firmware is a Yocto-based Linux image plus the ArusFleet agent. Releases are built by the firmware pipeline in Rimbun's CI from tagged commits in the firmware repository, produce a full image and a binary delta against each of the two previous releases, and are stored in the `arusfleet-firmware` S3 bucket. A release is promoted for rollout only after the hardware-in-the-loop test rig (20 gateways on a bench with simulated CAN, reefer serial and probes) passes for 48 hours.

### 14.2 Image verification

An OTA update is an AWS IoT Job whose document gives the image location (a pre-signed S3 URL valid for 24 hours), the image size and its SHA-256 digest. The gateway downloads the image over HTTPS into the inactive slot of its A/B partition layout. Before switching slots, the bootloader computes the SHA-256 digest of the downloaded image and compares it with the digest in the job document, and a match proves that the image is the authentic release built by the firmware pipeline. A mismatch discards the image and reports DOWNLOAD_CORRUPT.

### 14.3 Who can release

Fleet Operations, the 24x7 operations team of 22 engineers, creates and schedules IoT Jobs for firmware rollouts and uploads approved images to the firmware bucket, following the wave plan in Section 15.

---

## 15. Firmware Rollout Waves and Rollback

Every release goes through five waves:

| Wave | Devices | Minimum soak | Selection |
|---|---|---|---|
| 0 | 20 test vehicles in the Shah Alam depot | 48 h | Fixed list |
| 1 | 1% of the fleet (about 87) | 48 h | Random, stratified by market and variant |
| 2 | 10% | 48 h | Random, stratified |
| 3 | 50% | 72 h | Random, stratified |
| 4 | Remaining fleet | n/a | All |

A gateway installs an update only when it is safe to do so: a truck gateway only with the ignition off for at least 10 minutes, and a reefer gateway only when the TMS shows no active trip for the trailer and the reefer unit is off. Neither installs below 30% battery.

After switching slots the gateway must reach the health check within 10 minutes of boot: connected to AWS IoT Core, GNSS fix or holdover, all sensors present, and a successful publish. If it does not, the bootloader marks the new slot bad and boots the previous slot, which reports ROLLED_BACK. The rollout halts automatically at any wave if the rollback rate exceeds 0.5%, if the disconnected share of the wave rises more than 2 percentage points above the rest of the fleet, or if the median gap between expected and received readings per device rises by more than 10%. A halted rollout needs a release manager's decision to continue or abandon it.

Deltas are about 6 MB and full images about 48 MB. With deltas the whole fleet's download fits within one day of the cellular pool, and a gateway that misses a delta (three or more releases behind) falls back to the full image.

---

## 16. Cold-Chain Excursion Rules and Mean Kinetic Temperature

### 16.1 Product temperature

The product temperature for a reading is the mean of the load-space probes that reported in that minute. Return-air and supply-air temperatures are recorded and charted but are not product temperature, since supply air is routinely below the range during pull-down. If fewer than two load-space probes report in a minute, the reading is flagged PROBE_DEGRADED and product temperature is taken from the probes that did report; if none reports, the reading carries no product temperature and counts as missing for the data-gap rule (rule 5 of Section 16.2).

### 16.2 Excursion rules

For a trip with a range [L, H], from the trip's temperature range in the TMS:

1. **Range excursion:** product temperature, or any single load-space probe, outside [L, H] for 15 consecutive minutes.
2. **Freeze excursion (2 to 8 °C loads only):** any single probe at or below 0 °C for one reading, which starts an excursion immediately because freezing can destroy vaccines and biologics.
3. **Heat excursion:** any single probe above H + 10 °C for one reading.
4. **Door allowance:** while the door sensor shows the door open inside a depot or customer-site geofence, the 15-minute timer of rule 1 is extended by up to 20 minutes for that door event. The allowance is recorded on the excursion record and in the audit pack; it never applies to rules 2 and 3, and it never applies outside a site geofence.
5. **Data gap:** no reading for 10 minutes while the trailer is on an active trip and the gateway is not known to be in an offline stretch raises a monitoring alert, not an excursion; when the backfill arrives the rules are evaluated over it.

An excursion ends when product temperature and every load-space probe are back inside [L, H] for 10 consecutive minutes. Excursions found during backfill are raised retrospectively with their true start time.

### 16.3 Mean kinetic temperature

For each trip and for each excursion the platform computes the mean kinetic temperature (MKT) over the product temperatures:

T_MK = (ΔH/R) / ( −ln( (1/n) · Σ exp(−ΔH / (R · T_i)) ) )

with T_i in kelvin, ΔH = 83.144 kJ/mol and R = 8.3144 J/(mol·K), so ΔH/R = 10,000 K. MKT weights warm readings more heavily than an arithmetic mean, which reflects the faster degradation of product at higher temperatures. It is reported alongside, never instead of, the minimum, maximum and time outside range, because quality officers decide disposition on time and temperature against the product's stability data, not on MKT alone.

---

## 17. Alert Service and Alert Routing

### 17.1 Alert service runtime

The excursion and alert service consumes `coldchain.v1` and applies the rules in Section 16 per trailer. It runs as three ECS tasks in one consumer group, each owning a share of the 24 partitions. Open-excursion state (start time, running timer, door allowance used, running MKT terms) is held in each task's memory for the trailers it owns. The service does not commit Kafka offsets; on start it joins its partitions at the latest offset, which avoids replaying old readings and sending duplicate alerts after a deployment. Excursions are written to Aurora when they open and when they close.

### 17.2 Alert content

An alert names the trailer, the truck it is coupled to, the driver, the trip, the customer, the rule that fired, the current product temperature and the start time, and links to the live chart. The same alert is sent to the customer's quality contact for pharmaceutical trips.

### 17.3 Routing

Excursion alerts go by push notification to the console of the dispatcher assigned to the trip and by SMS to the driver's phone through Amazon SNS. For pharmaceutical trips the alert also goes by email to the customer's quality contact. Each dispatcher covers up to 600 vehicles on the day shift and the whole of a market on the night shift, when one dispatcher per market is on duty.

The driver's remedial actions are set out in the driver handbook: check the reefer unit, check that the doors are closed, call the dispatcher, and follow the dispatcher's instruction to re-ice, transfer or divert.

---

## 18. Quality Review and Audit Pack

### 18.1 Review workflow

Every closed excursion opens a review task for the quality officer of the customer's account. The officer reviews the chart, the MKT and the actions taken, and records a disposition: RELEASE (no impact on product), RELEASE_WITH_NOTE, QUARANTINE (customer to assess) or REJECT. The disposition, officer, time and justification are stored on the excursion record. For pharmaceutical customers the disposition is a recommendation that the customer's own quality person confirms in the portal.

### 18.2 Corrections

Occasionally a probe is found faulty after a trip, for example when its post-trip check against a reference thermometer is out of tolerance or it reports a physically impossible jump. Where a probe is found faulty, a quality officer corrects the affected readings by updating them in place in the `cold_chain_reading` table, entering the reason in the `correction_note` column and their user ID in `corrected_by`. The audit pack lists every corrected reading with its note.

### 18.3 Audit pack

An audit pack is a PDF with a machine-readable CSV annex, generated per shipment on request from the customer portal or by the quality team. It is generated from the `cold_chain_reading`, `excursion`, `probe` and `trip` tables in Aurora and contains: trip and chain-of-custody details (each coupling and uncoupling of the trailer, each driver), the full reading series with flags, excursions with dispositions, MKT for the trip and for each excursion, the setpoint history, probe serial numbers with calibration certificate references, and corrections. Generated packs are stored in the S3 archive.

### 18.4 Archive

The archive writer consumes `coldchain.v1` and writes the readings, unchanged and with their envelopes, as hourly Parquet files per market to the `arusfleet-coldchain-archive` bucket under S3 Object Lock in compliance mode with a five-year retention. Replication copies the bucket to ap-southeast-5. The archive is the long-term, tamper-evident copy; day-to-day queries use Aurora.

---

## 19. Dispatcher Console, Customer Portal and Consignee Tracking

### 19.1 Dispatcher console

A single-page web application with a live map (vector tiles), a vehicle list filtered to the dispatcher's assignment, trip timelines, alerts, and command actions according to role. Positions stream to the console over WebSocket from the API, which subscribes to a Redis stream (Amazon ElastiCache) fed by the position writer. The map shows each vehicle's age of position, greyed after 2 minutes.

### 19.2 Customer portal

Customer users see their own trips: history, the temperature chart, excursions and dispositions, proof of delivery and audit packs. Access is scoped to the customer account and, within it, by role (viewer, quality, administrator). Customer users authenticate through the Rimbun identity provider with mandatory multi-factor authentication for quality and administrator roles.

### 19.3 Consignee tracking link

When a trip is dispatched, the TMS sends the consignee an SMS or email containing a tracking link so the receiving site can plan its dock. A consignee tracking link is an unauthenticated URL carrying a random 128-bit token, it stays valid for 30 days from dispatch, and it shows the vehicle's live position and estimated arrival on a map. The page shows the vehicle plate and the first name of the driver, so that the receiving dock can identify the truck at the gate. Tokens are stored hashed; a link can be revoked by the dispatcher.

---

## 20. Data Model and Storage

### 20.1 Main tables (Aurora PostgreSQL 16 with PostGIS)

| Table | Key | Notes |
|---|---|---|
| vehicle | vehicle_id | Truck or trailer, plate, market, gateway device_id, variant |
| driver | driver_id | Name, home depot, licence class, driver card ID |
| trip | trip_id | From TMS: truck, trailer, driver, customer, consignee, temperature range, planned stops |
| coupling | coupling_id | Trailer to truck couplings with start and end times (chain of custody) |
| vehicle_position | (device_id, boot_id, seq, device_ts) unique | device_ts, ingest_ts, geography(Point), speed, heading, HDOP |
| drive_frame | (device_id, boot_id, seq, device_ts) unique | 1 Hz frames, stored for 30 days for event disputes |
| cold_chain_reading | (device_id, boot_id, seq, device_ts) unique | trip_id, device_ts, probe values, supply and return air, setpoint, door, flags, correction_note, corrected_by |
| probe | probe_serial | Calibration date, certificate reference, tolerance |
| excursion | excursion_id | trip, rule, start, end, peak, MKT, door allowance, disposition |
| driver_event | (device_id, boot_id, seq, device_ts) unique | Event type, magnitude, driver_id, position |
| driver_score_daily | (driver_id, day) | Score, distance, events |
| geofence | geofence_id | geography(Polygon), type, owner |
| command | command_id | Type, target, sender, reason, outcome |

### 20.2 Physical design

`cold_chain_reading`, `driver_event` and `drive_frame` are declaratively partitioned by month on `device_ts`. The `vehicle_position` table is a single table without partitioning, with a B-tree index on `(device_id, device_ts)` and a GiST index on the position, because the console's track and nearest-vehicle queries are the hot path and partition pruning would not help them. At the 2028 fleet size the position writer stores about 31 million rows a day (one row per drive message, per stationary position and per off-ignition position from trucks, plus one position per minute from reefer gateways).

Aurora runs as one writer (`db.r7g.4xlarge`) and two readers in different Availability Zones. The console and portal read from the readers; stream services write to the writer.

---

## 21. Data Retention

| Data | Store | Retention | Basis |
|---|---|---|---|
| Cold-chain readings, excursions, dispositions, audit packs | Aurora and S3 archive | 5 years after the trip | Customer quality agreements (Section 5) |
| Probe calibration records | Aurora | 6 years | Linked to readings |
| Positions | Aurora | 13 months | Operations, incident and claims investigation |
| Drive frames | Aurora | 30 days | Event disputes (Section 11.3) |
| Driver events and scores | Aurora | 24 months | Incentive disputes and audits |
| Command log | Aurora | 5 years | Security investigation |
| Raw MSK topics | MSK | 7 days | Replay |

Retention is enforced by scheduled jobs. Partitioned tables drop whole monthly partitions once every row in them is past retention. Expired positions are removed by a nightly job at 02:00 MYT that runs a single `DELETE FROM vehicle_position WHERE device_ts < now() - interval '13 months'` statement on the writer. When a driver leaves Rimbun, their personal details are removed from the `driver` table after 24 months and their events and scores are kept against a pseudonymous ID.

---

## 22. Identity, Access and Device Security

### 22.1 Device identity and provisioning

Each gateway's private key is generated inside its secure element at the factory and never leaves it. Halcyon registers the certificate signing request with Rimbun's private CA (AWS Private CA), and the signed certificate is registered as an AWS IoT thing with the same name as the `device_id` printed on the gateway label. A gateway removed from service has its certificate revoked and its thing deleted.

### 22.2 Device authorisation

Every gateway's IoT policy allows `iot:Connect` with its own client ID, `iot:Publish` on `rimbun/v1/*/telemetry` and `rimbun/v1/*/events`, and `iot:Subscribe` and `iot:Receive` on `rimbun/v1/*/cmd`. Topics carry the device ID in the second segment (for example `rimbun/v1/GW4R-018872/telemetry`), and the IoT rules copy that segment into the envelope's `device_id` field before producing to MSK.

### 22.3 People and services

Staff authenticate through the Rimbun identity provider (SAML) with mandatory multi-factor authentication. Roles: Dispatcher, Senior dispatcher, Security controller, Quality officer, Fleet supervisor, Fleet Operations, Data analyst (read-only, pseudonymised driver data), Administrator. Service identities are IAM task roles per ECS service with access only to their own topics, tables and buckets. Customer users are described in Section 19.2.

### 22.4 Data protection

All stores are encrypted at rest with AWS KMS customer-managed keys per data class. Driver personal data (name, phone number, driver card ID, home depot) is in the `driver` table only; events and positions reference the driver by `driver_id`. A privacy notice explains to drivers what is collected and why, and access to a driver's position history is logged.

---

## 23. Resilience, Availability and Disaster Recovery

### 23.1 Within the region

AWS IoT Core, MSK, Aurora and ECS all span three Availability Zones. The loss of one zone causes an Aurora failover (typically under 60 seconds) and an MSK leader election; gateways retry with backoff and nothing is lost, because a message leaves a gateway's buffer only after its PUBACK. Each IoT rule has an error action that writes any message its Kafka action could not deliver to an S3 bucket, and a redrive job produces those messages to MSK once MSK is healthy; the redrive count is alarmed. Stream services are stateless or rebuild their state from MSK and Aurora (Sections 12 and 17).

### 23.2 Region loss

ArusFleet does not run active in a second region. Aurora is an Aurora Global Database with a headless secondary cluster in ap-southeast-5 (replication lag typically under one second), and the S3 archive is replicated continuously. On loss of ap-southeast-1, the secondary is promoted and the rest of the platform is rebuilt in ap-southeast-5 from infrastructure code within the 4-hour RTO. Gateways keep buffering for up to 72 hours and reconnect through a DNS name controlled by Rimbun. Readings that were acknowledged in the lost region but had not yet replicated are recovered from the gateways: after the rebuild the platform sends every reefer gateway a RESEND_FROM command for the last 6 hours, and deduplication (Section 9) discards what the store already holds.

### 23.3 Dependencies

| Dependency | If unavailable |
|---|---|
| TMS trip feed | New trips cannot be assigned; readings are stored without a trip and attached when the trip arrives |
| SNS SMS | Alerts still reach the console; SMS retried for 30 minutes |
| Identity provider | Existing console sessions continue for up to 8 hours |
| Map tiles | Console shows the vehicle list and last-known coordinates without the base map |

---

## 24. Capacity and Cost Budget

### 24.1 Message volume

At the 2028 target and peak hour (about 85% of trucks moving):

| Source | Rate | Messages per second |
|---|---|---|
| Moving trucks (5,440) | 1 per 10 s | 544 |
| Stationary trucks, ignition on (600) | 1 per 30 s | 20 |
| Ignition-off trucks (360) | 1 per 15 min | 0.4 |
| Reefer gateways (2,300) | 1 per 60 s plus events | 45 |
| Driver events and other events | | about 30 |
| Total | | about 640 |

Backfill after a regional outage can double this for an hour. AWS IoT Core and MSK both have more than ten times this headroom at the configured sizes.

### 24.2 Cellular data

Each gateway has a multi-network SIM on a regional IoT plan with a pooled allowance of 60 MB per SIM per month at USD 0.95 per SIM; usage above the pool is billed at USD 0.015 per MB. At 350 bytes per 1 Hz frame and an average of 11 driving hours a day, the driving stream comes to about 28 MB per truck per month. Adding positions while stationary or parked, events, MQTT and TLS overhead and firmware deltas brings a truck to about 40 MB a month; a reefer gateway uses about 12 MB a month. The fleet therefore stays within the pooled allowance.

### 24.3 Monthly run cost at the 2028 fleet size

| Item | USD per month |
|---|---|
| AWS IoT Core connectivity, messaging, rules and jobs (AWS Pricing Calculator, September 2026) | 4,100 |
| Amazon MSK (3 brokers, storage) | 3,900 |
| Aurora PostgreSQL (writer, two readers, I/O-optimised storage) | 11,800 |
| ECS Fargate (stream services, API) | 6,200 |
| S3, replication and archive | 1,300 |
| SNS SMS and email | 2,400 |
| Map tiles and geocoding | 3,600 |
| Monitoring and logs | 2,100 |
| Cellular data (8,700 SIMs at USD 0.95, within pool) | 8,265 |
| Halcyon device management licence | 13,050 |
| Support and contingency (25% of the above) | 14,179 |
| **Total** | **70,894** |

This is within NFR-10 with about 25% headroom.

---

## 25. Observability and Operations

### 25.1 Telemetry about the platform

Every service emits metrics to Amazon CloudWatch and traces to AWS X-Ray, and logs to CloudWatch Logs. Dashboards show messages per second by type, ingest lag (`ingest_ts` minus `device_ts`) percentiles by market, consumer lag per group, excursion counts, alert delivery latency, command outcomes and OTA wave progress.

### 25.2 Device health

The platform tracks per device: last seen, clock state, buffer depth reported in every heartbeat, battery, signal quality, probe battery and firmware version. A device not seen for 24 hours while assigned to a trip opens a ticket for the depot.

### 25.3 Scheduled jobs

| Job | Schedule | Purpose |
|---|---|---|
| Daily driver scores | 00:30 MYT (UTC+8) every day, all markets | Compute the daily score for every driver for the driving day just ended |
| Monthly driver scores and HR feed | 03:00 MYT on day 1 | Monthly score and incentive feed |
| Position retention | 02:00 MYT daily | Section 21 |
| Partition maintenance | 01:00 MYT daily | Create next month's partitions, drop expired ones |
| Probe calibration check | 06:00 MYT daily | Flag probes within 30 days of calibration expiry |

### 25.4 On-call

Fleet Operations is on call 24x7 for the platform, with a secondary from Digital Engineering. Runbooks cover IoT Core throttling, MSK broker loss, consumer lag, Aurora failover, a halted OTA wave and a mass disconnection in a market.

---

## 26. Confirmed Decisions

| ID | Decision | Rationale |
|---|---|---|
| DEC-01 | AWS ap-southeast-1 as primary region, ap-southeast-5 for backup and archive copy | Latency to all four markets; Malaysian copy for customer comfort |
| DEC-02 | AWS IoT Core as MQTT broker | Managed, integrated identity and jobs (P7) |
| DEC-03 | MQTT 3.1.1 with QoS 1 and persistent sessions | Supported by the GW-400 agent; at-least-once with deduplication (P2) |
| DEC-04 | Amazon MSK as the streaming backbone, keyed per device | Ordering per device, replay, managed (P7) |
| DEC-05 | Aurora PostgreSQL with PostGIS as the operational store | Spatial queries, team skills |
| DEC-06 | GW-400 gateways with LTE-M and LTE Cat 1 only (no 2G or 3G fallback); purchase order for 9,000 units placed in Phase 1 | 2G and 3G networks are being switched off in all four markets; one hardware platform for both variants |
| DEC-07 | Driving events detected on the device | Works without coverage; reduces data |
| DEC-08 | S3 Object Lock in compliance mode for the cold-chain archive | Tamper-evident long-term copy |
| DEC-09 | A/B partitions and five-wave rollout for firmware | Safe rollback (Section 15) |
| DEC-10 | Consignee tracking via tokenised link, no consignee accounts | Consignees are thousands of small receiving sites |
| DEC-11 | Single region with rebuild for disaster recovery | Gateway buffering covers the 4-hour RTO |
| DEC-12 | Excursion rules as in Section 16 | Agreed with three pharmaceutical customers' quality teams |

---

## 27. Pending Backlog

| ID | Item | Owner | Due |
|---|---|---|---|
| PB-01 | Map data licence for heavy-vehicle restrictions in Thailand and Indonesia | Fleet Platforms | Phase 2 |
| PB-02 | Driver app design (separate document) | Mobile team | Phase 2 |
| PB-03 | Confirm LTE-M and LTE Cat 1 coverage and roaming with carriers on the Pan-Borneo Highway (Sabah and Sarawak) and the Kalimantan border routes | Procurement | Phase 3 |
| PB-04 | Union consultation on the driver incentive scheme in Thailand | HR | Phase 3 |
| PB-05 | Customer API for temperature data (push) | Fleet Platforms | Phase 4 |
| PB-06 | Integration with Halcyon's device management portal for hardware faults | Fleet Operations | Phase 2 |
| PB-07 | Probe supplier second source | Procurement | Phase 4 |

---

## 28. Validation and Acceptance Criteria

### 28.1 Functional requirements

| Req | Acceptance criterion |
|---|---|
| FR-1, FR-2 | On the bench rig and on 20 pilot vehicles, every message type is received with the correct envelope and stored; drive frames reconcile with CAN logs taken by a reference logger. |
| FR-3 | A reefer gateway disconnected for 24 hours and for 72 hours (RF shield box) delivers every buffered reading after reconnection, with no duplicates in the store. |
| FR-5 | Replay of 30 days of recorded pilot positions produces geofence events matching a manually labelled set (precision and recall at least 98%). |
| FR-6 | Scripted temperature profiles covering every rule in Section 16, including door allowance and backfill, produce the expected excursions with correct start and end times. |
| FR-7 | In the pilot, excursions induced by switching off a test reefer unit are alerted to the dispatcher and driver within 2 minutes. |
| FR-8 | Test-track runs with a calibrated reference IMU: each event type is detected with at least 95% recall and no more than 5% false events. |
| FR-10 | A release goes through all five waves on the pilot fleet, with an induced failing image rolled back automatically on every device. |
| FR-11 | Each command type executes on the bench rig and on pilot vehicles and is recorded in the command log. |
| FR-14 | Audit packs for 50 pilot trips are checked by Rimbun's quality team against the reference loggers carried in the same trailers. |

### 28.2 Non-functional requirements

| Req | Acceptance criterion |
|---|---|
| NFR-1 | Monthly availability computed from synthetic device probes that publish every minute from each market. |
| NFR-2 | Over the 3-month pilot, readings in the store compared with the gateways' local logs: at least 99.99% present. |
| NFR-3 | Alert latency percentiles from the alert service's traces over the pilot. |
| NFR-4 | In UAT, run the device simulator with 500 simulated vehicles sending positions every 10 seconds and confirm that all simulated vehicles appear on the console map. |
| NFR-6 | Penetration test of device and API interfaces by an external firm; certificate uniqueness checked across the fleet register. |
| NFR-9 | Restore test in ap-southeast-5 from infrastructure code and snapshots, timed. |
| NFR-11 | Load test at 12,000 simulated gateways (1,800 messages per second, twice the scaled peak) for 4 hours with no consumer lag growth. |
| NFR-12 | Console load time measured with 600 vehicles on a mid-range laptop over a 20 Mbps link. |

---

## 29. Implementation Readiness Assessment

| Area | Status | Notes |
|---|---|---|
| Device connectivity and envelope | Ready | Sections 9 and 10 |
| Streaming backbone | Ready | Section 8 |
| Geofencing | Ready | Section 12 |
| Driver scoring | Ready | Rules agreed with fleet supervisors; Thai union consultation pending (PB-04) |
| Remote commands | Ready | Section 13 |
| OTA | Ready | Sections 14 and 15 |
| Cold-chain rules and alerting | Ready | Agreed with customers (DEC-12) |
| Quality review and audit pack | Ready | Section 18 |
| Console and portal | Ready for build | Visual design in progress |
| Data model and retention | Ready | Sections 20 and 21 |
| Security | Ready | Section 22; penetration test in Phase 4 |
| Cost | Ready | Within NFR-10 |

### Overall conclusion

The design is ready for build. Remaining open items (PB-01 to PB-07) do not block Phase 1 and are scheduled in the phases below.

---

## 30. Build Phases

| Phase | Months | Scope | Exit criteria |
|---|---|---|---|
| 1 | 1 to 3 | Device agent, IoT Core, MSK, envelope and deduplication, position writer, console map; gateway purchase order (DEC-06) | 20 bench gateways and 20 pilot vehicles streaming; FR-1 and FR-4 criteria met |
| 2 | 4 to 6 | Reefer gateways, cold-chain writer and archive, excursion rules and alert service, geofencing | FR-2, FR-3, FR-5, FR-6, FR-7 criteria met on pilot |
| 3 | 7 to 9 | Driver events and scoring, remote commands, OTA and waves, quality review and audit pack | FR-8 to FR-11, FR-14, FR-15 met; 3-month pilot starts |
| 4 | 10 to 12 | Customer portal, consignee links, penetration test, load test, DR test, fleet rollout | All acceptance criteria met; rollout to the full fleet by market |
