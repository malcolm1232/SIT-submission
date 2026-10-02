# Fenwick Distribution Centre: Site Energy Management and Battery Storage Control System (SEMS)

**Design Document FDC-SEMS-DD-001, Revision C (baseline for Design Review DR-2)**

| Field | Value |
|---|---|
| Document owner | Site Energy Engineering |
| Contributors | Controls Engineering, Electrical Engineering, OT Security, Facilities Operations, EHS, Procurement |
| Status | For design review |
| Date | 2026-09-14 |
| Supersedes | Rev B (2026-07-30) |

**Revision summary.** Rev C incorporates the BESS supplier's final interface maps (PCS and EBMS), the utility's preliminary comments on the interconnection amendment, the revised design-day load profile from the 2025 summer metering campaign, and the outcome of the hazard identification workshop held 2026-08-21. Rev B comments not addressed here are tracked in Section 13.

---

## 1. Purpose and Scope

### 1.1 Purpose

This document defines the design of the Site Energy Management System (SEMS) and the associated battery energy storage system (BESS) controls for the Fenwick Cold-Chain Distribution Centre (FDC). It is the baseline against which the controls integrator, the BESS supplier, the electrical contractor and the OT security team will build, and against which site acceptance testing will be performed.

The document covers the control functions that coordinate the BESS, the existing rooftop photovoltaic (PV) array, site loads and the utility interface; the interfaces among those elements; the safety and security measures that apply to them; and how the system will be operated, maintained, governed and accepted.

The project has five business objectives:

1. Reduce on-peak demand charges by limiting site import during the utility's on-peak window.
2. Keep the site within the export limit of its interconnection agreement now that PV output frequently exceeds weekend and holiday load.
3. Provide backup power to critical refrigeration and IT loads during utility outages, reducing product-loss exposure in the freezer zones.
4. Participate in the utility's distributed energy resource (DER) demand response programme.
5. Produce measurement and verification (M&V) data that supports the investment case and programme settlement.

### 1.2 In scope

- The SEMS site controller pair, local HMI, supervisory servers and their software.
- Control integration of the new BESS: four battery enclosures, two power conversion systems (PCS), the enclosure battery management systems (EBMS) and enclosure auxiliary systems.
- Control integration of the existing PV inverters (power limiting and grid-support settings only).
- Integration with the new MV switchgear position for the BESS, the existing MV main and feeder breakers, and their protection relays.
- The utility communications gateway and the DER control interface to the utility's DER management system (DERMS).
- Safety-related interfaces: emergency stop, fire alarm, gas detection and explosion control interlocks for the BESS yard.
- OT network, cybersecurity controls, time synchronisation, data historian and enterprise data export.
- Commissioning, acceptance and the phased delivery plan.

### 1.3 Out of scope

- Life-safety systems (building fire alarm, emergency lighting, egress) other than the BESS-yard interfaces listed above.
- The existing 500 kW standby diesel generator and its automatic transfer switch (ATS), which continue to serve the life-safety panel. SEMS monitors their status only.
- The facility control system (FCS) that runs refrigeration, HVAC and dock equipment, other than the load-shed interface.
- Utility-owned equipment, including the revenue meter M-0.
- Tariff selection and the financial model, which are owned by Finance and referenced where they constrain the design.
- Physical modification of the PV array.

### 1.4 Terminology

| Term | Meaning |
|---|---|
| Area EPS | The utility's electric power system, as defined in IEEE 1547-2018 |
| BESS | Battery energy storage system: enclosures, racks, EBMS, PCS and step-up transformers |
| BMS / EBMS | Battery management system; EBMS is the enclosure-level BMS controller that aggregates its rack BMS units |
| FCS | Facility control system (building automation for refrigeration, HVAC, docks). Not to be confused with BMS |
| PCC | Point of common coupling with the Area EPS, at the 12.47 kV main breaker 52-PCC |
| SC | Site controller (SC-A / SC-B redundant pair) |
| SoC | State of charge, expressed as a percentage of nameplate energy |
| EFC | Equivalent full cycle: discharged energy divided by 4,000 kWh nameplate |
| MID | Microgrid interconnect device; at FDC the MID function is performed by 52-PCC and its relay R-PCC |

### 1.5 Reference documents

| Ref | Title |
|---|---|
| R1 | IEEE 1547-2018, Standard for Interconnection and Interoperability of DER with Associated Electric Power Systems Interfaces (incl. 1547a-2020) |
| R2 | IEEE 1547.1-2020, Conformance Test Procedures |
| R3 | UL 1741, Third Edition, including Supplement SB |
| R4 | UL 9540, Energy Storage Systems and Equipment |
| R5 | UL 9540A, Test Method for Evaluating Thermal Runaway Fire Propagation in BESS |
| R6 | UL 1973, Batteries for Use in Stationary and Motive Auxiliary Power Applications |
| R7 | NFPA 855 (2023), Standard for the Installation of Stationary Energy Storage Systems |
| R8 | NFPA 70 (NEC 2023), Articles 480, 705 and 706 |
| R9 | NFPA 69, Standard on Explosion Prevention Systems; NFPA 72, National Fire Alarm and Signaling Code |
| R10 | IEC 62443-3-3, System security requirements and security levels |
| R11 | IEEE 2030.5-2018, Smart Energy Profile Application Protocol; utility CSIP implementation guide |
| R12 | Modbus Application Protocol Specification V1.1b3; SunSpec DER Information Model Specification |
| R13 | IEC 62439-3, Parallel Redundancy Protocol (PRP) |
| R14 | ANSI/ISA-18.2, Management of Alarm Systems for the Process Industries |
| R15 | Utility Interconnection Handbook (current edition) and FDC interconnection agreement, amendment 2 (draft) |
| R16 | BESS supplier documents: PCS Modbus map v3.2, EBMS Modbus map v2.7, warranty terms WT-2026-04 |

---

## 2. Context

### 2.1 Site description

FDC is a 42,000 m² cold-chain distribution centre operating 24 hours a day, seven days a week. It has a freezer zone held at −25 °C, a chilled zone at +2 °C, an ambient zone and a dock area with 60 doors. Refrigeration is the dominant load and is weather-sensitive; the annual peak (3.4 MW) occurs on hot weekday evenings when outbound loading coincides with high condenser temperatures. The minimum load (about 1.1 MW) occurs at midday on weekends and holidays.

The site is supplied from a single 12.47 kV utility distribution feeder. The customer-owned MV switchgear SWG-1 contains the main breaker 52-PCC and four feeder breakers:

| Feeder | Breaker | Serves | Peak load | Notes |
|---|---|---|---|---|
| F-1 | 52-F1 | Dock, ambient warehouse, PV block 1 (0.9 MWac) | 0.8 MW | Non-critical |
| F-2 | 52-F2 | Refrigeration plant A (non-critical compressors, condensers) | 1.4 MW | Non-critical; FCS can shed in stages |
| F-3 | 52-F3 | Critical: freezer compressors (subset), IT room, controls, BESS auxiliaries | 380 kW | Served in island mode |
| F-4 | 52-F4 | Offices, EV charging, PV block 2 (0.9 MWac), life-safety panel via ATS | 0.9 MW | Non-critical; life-safety panel is backed by the diesel generator |

A new switchgear section adds breaker 52-B for the BESS, with its own protection relay R-B. Each of the two PCS connects to 52-B through a dedicated 1,250 kVA, 0.69/12.47 kV step-up transformer (T-A, T-B).

### 2.2 Tariff and interconnection context

The site is on a time-of-use tariff with an on-peak window of 16:00 to 21:00 on weekdays, part-peak windows of 06:00 to 09:00 and 21:00 to 23:00, and a demand charge assessed on the maximum 15-minute average import during on-peak hours in each billing month. The demand charge represents roughly 38% of the annual electricity bill.

The existing PV interconnection permits a maximum export of 500 kW at the PCC. The draft amendment for the BESS keeps this limit and adds two conditions: an exceedance of the export limit shall not persist for more than 2 seconds, and the BESS shall not be a net source of energy exported to the Area EPS. The utility will issue a DER settings file specifying the IEEE 1547 performance categories, voltage and frequency trip settings, ride-through settings and default grid-support functions for both the PV inverters and the PCS.

### 2.3 Stakeholders

| Stakeholder | Interest | Role in this design |
|---|---|---|
| Site General Manager | Cost, product protection | Approves operating policy and DR opt-out rules |
| Facilities Operations | Day-to-day operation | Operates HMI, first-line response, maintenance windows |
| Site Energy Engineering | Performance, M&V | Document owner, optimiser configuration |
| EHS | Personnel and fire safety | Owns hazard log, emergency response plan, AHJ liaison |
| Corporate OT Security | Cyber risk | Approves zones, conduits and remote access |
| BESS supplier | Warranty, performance | Supplies BESS, PCS, EBMS; 10-year service agreement |
| Controls integrator | Delivery | Builds SC, HMI, supervisory software; performs FAT/SAT |
| Utility | Grid safety, programme | Approves interconnection, issues settings, operates DERMS |
| Fire marshal (AHJ) | Code compliance | Approves BESS installation and emergency response plan |

### 2.4 Constraints

- **C-01** MV switchgear outages for integration work are limited to 8 hours and must fall on weekends between 22:00 Friday and 06:00 Monday.
- **C-02** Settings that affect grid protection or interconnection performance may only be changed with the utility's written approval.
- **C-03** BESS enclosures are installed outdoors in the north yard, at least 3 m (10 ft) from the building, lot lines and stored combustibles, subject to final AHJ approval.
- **C-04** The capital budget is fixed. Augmentation of battery capacity is provisioned for in year 8 of operation in the financial model.
- **C-05** The site has no on-site controls engineer outside business hours; out-of-hours response is by the facilities on-call technician with remote support from the integrator and the BESS supplier.

### 2.5 Assumptions

- **A-01** BESS energy: four outdoor enclosures (E1 to E4) of 1,000 kWh nameplate each, lithium iron phosphate (LFP) chemistry, ten racks of 100 kWh per enclosure. Total nameplate 4,000 kWh.
- **A-02** BESS power: two bidirectional PCS (PCS-A, PCS-B), each rated 1,000 kW / 1,100 kVA at the AC terminals. PCS-A serves E1 and E2; PCS-B serves E3 and E4. PCS-A is licensed for grid-forming operation; PCS-B operates grid-following only.
- **A-03** AC round-trip efficiency at 52-B, including transformer and auxiliary losses, is 88%.
- **A-04** Enclosure auxiliaries (HVAC, controls, gas detection, exhaust) draw up to 15 kW per enclosure and are fed from F-3.
- **A-05** The supplier's recommended SoC operating window is 5% to 95%.
- **A-06** Warranty (R16): 10 years or 4,000 EFC, whichever comes first. Annual throughput shall not exceed 365 EFC in any warranty year; exceeding this voids the capacity retention guarantee from that year onward.
- **A-07** Day-ahead and intraday PV and load forecasts are supplied by the enterprise analytics platform at 15-minute resolution.
- **A-08** Cellular coverage at the site supports a dual-carrier router for the utility link.
- **A-09** The design-day net load profile is as given in Table 2 (Section 7.2).
- **A-10** Critical load on F-3 peaks at 380 kW and averages 300 kW over a 24-hour period, including BESS auxiliaries.

---

## 3. Requirements

Requirements use "shall" for mandatory items. Each requirement is traced to acceptance criteria in Section 14.

### 3.1 Functional requirements

#### Peak shaving

- **FR-PS-01** During the on-peak window (16:00 to 21:00, weekdays), the SEMS shall limit the 15-minute average site import at the PCC to no more than 2,200 kW on any day whose net load profile does not exceed the design-day profile (Table 2).
- **FR-PS-02** The SEMS shall publish a discharge schedule for the coming on-peak window by 06:00 each weekday and revise it at least every 15 minutes during the day.
- **FR-PS-03** If the forecast shows that the 2,200 kW target cannot be met, the SEMS shall schedule discharge to minimise the maximum 15-minute on-peak import rather than abandon the target, and shall raise an advisory alarm.

#### Export management

- **FR-EXP-01** Net export at the PCC shall not exceed 500 kW.
- **FR-EXP-02** Any exceedance of the 500 kW export limit shall be corrected so that it does not persist for more than 2 seconds.
- **FR-EXP-03** The BESS shall not be a net source of energy exported to the Area EPS. While the site is in net export, the BESS discharge setpoint shall be zero.
- **FR-EXP-04** When the BESS cannot absorb surplus PV (SoC at upper limit, charge power limit, or BESS unavailable), the SEMS shall curtail the PV inverters through their active power limit setpoints.

#### Grid interface

- **FR-GRID-01** The PCS and PV inverters shall meet IEEE 1547-2018 as specified by the utility settings file: normal performance Category B and abnormal performance Category III.
- **FR-GRID-02** Default grid-support functions (volt-var, frequency-droop) shall be enabled as specified in the utility settings file. The SEMS shall not override them.
- **FR-GRID-03** The PCS and PV inverters shall ride through voltage and frequency disturbances as required for abnormal performance Category III.
- **FR-GRID-04** On formation of an unintentional island, site DER shall cease to energize the Area EPS and trip within 5 seconds, consistent with IEEE 1547-2018 clause 8.1.
- **FR-GRID-05** Return to service after a trip shall occur only after Area EPS voltage and frequency have been within the enter-service range for the enter-service delay (default 300 s), with sync-check supervision on any closing of 52-PCC while the site is energised.

#### Backup power

- **FR-BK-01** On unplanned loss of utility supply, the SEMS shall isolate the site from the Area EPS, shed non-critical feeders and restore F-3 from the BESS within 10 seconds of loss of supply.
- **FR-BK-02** While grid-connected, the SEMS shall maintain SoC at or above 35%, which provides a 1,200 kWh reserve above the 5% floor, sufficient for at least 3 hours at the 380 kW critical peak.
- **FR-BK-03** On operator command, the SEMS shall perform a planned transition to island mode without interrupting F-3.
- **FR-BK-04** On restoration of utility supply, the SEMS shall return the site to grid-parallel operation by closed transition through sync-check, in accordance with FR-GRID-05.
- **FR-BK-05** In island mode, the SEMS shall request staged load shedding within F-3 from the FCS when SoC falls below 15%, and shall stop the PCS in an orderly manner at 5%.

#### Demand response

- **FR-DR-01** The SEMS shall receive DER control events from the utility DERMS using IEEE 2030.5 in accordance with the utility's CSIP implementation guide.
- **FR-DR-02** The SEMS shall begin executing a DER control event within 60 seconds of its scheduled start and report event status and telemetry as required by the programme.
- **FR-DR-03** An authorised operator may opt out of a DR event through the HMI with a recorded reason. Opt-outs shall be logged and reported to the utility per programme rules.

#### Optimisation and scheduling

- **FR-OPT-01** The optimiser shall produce a day-ahead schedule by 18:00 for the following day and re-optimise every 15 minutes using intraday forecasts.
- **FR-OPT-02** Schedules shall respect SoC limits, the reserve in FR-BK-02, PCS and EBMS power limits, the export constraints, and the warranty throughput limits in A-06.
- **FR-OPT-03** If the optimiser is unavailable, the site controller shall continue executing the last valid schedule for up to 24 hours and then revert to a rule-based peak-shaving default.

#### Monitoring and reporting

- **FR-MON-01** The HMI shall display PCC power, feeder loads, PV output, BESS SoC and power, enclosure status, alarms and the active operating mode.
- **FR-MON-02** Alarms shall be rationalised and prioritised following ANSI/ISA-18.2, with no more than one priority-1 alarm per credible single initiating event.
- **FR-MON-03** The SEMS shall produce a monthly M&V report comparing actual demand and energy cost with a modelled no-BESS baseline.

### 3.2 Non-functional requirements

#### Performance

- **NFR-PERF-01** The site controller fast control loop shall execute with a 100 ms cycle.
- **NFR-PERF-02** Setpoint propagation from the site controller to each PCS shall take no more than 200 ms.
- **NFR-PERF-03** Rack-level BMS data shall be refreshed at the SEMS at least once per second.
- **NFR-PERF-04** HMI displays shall update within 2 seconds of a change in field state.

#### Availability and resilience

- **NFR-AV-01** Availability of the SEMS control function shall be at least 99.95% per calendar year, measured including planned maintenance. The control function is unavailable whenever the site controller is not issuing valid dispatch setpoints to the PCS.
- **NFR-AV-02** No single failure of a site controller, control network switch or control power supply shall cause loss of the control function for more than 2 seconds.
- **NFR-AV-03** Failure of the supervisory servers or the enterprise link shall not affect the fast control loop or any safety function.

#### Safety

- **NFR-SAF-01** Battery racks and enclosures shall be certified to UL 9540A. Battery modules shall be certified to UL 1973. PCS shall be certified to UL 1741 including Supplement SB.
- **NFR-SAF-02** The installation shall comply with NFPA 855 (2023) and NEC 2023 Articles 480, 705 and 706, as adopted by the AHJ.
- **NFR-SAF-03** Emergency stop stations shall be provided at the BESS yard gate, the MV switchroom and the control room. Activation of any station shall bring all BESS equipment to a safe state (PCS stopped, all DC contactors open) within 500 ms.
- **NFR-SAF-04** Gas detection and explosion control shall be provided for each enclosure in accordance with NFPA 855 and NFPA 69.
- **NFR-SAF-05** No safety function shall depend on the supervisory servers, the enterprise network or any external communication link.

#### Security

- **NFR-SEC-01** OT zones shall meet IEC 62443-3-3 target security level SL-T 2. The remote access conduit shall meet SL-T 3.
- **NFR-SEC-02** All communications leaving the OT DMZ shall be encrypted and mutually authenticated.
- **NFR-SEC-03** All interactive remote access shall use individual accounts with multi-factor authentication, be approved per session, and be recorded.
- **NFR-SEC-04** Security events from OT firewalls, servers and controllers shall be forwarded to the corporate SIEM.
- **NFR-SEC-05** Critical security patches shall be assessed within 7 days and applied within 35 days, or a documented compensating control shall be in place.

#### Observability and data

- **NFR-OBS-01** The historian shall record key analog values at 1-second resolution, with 100 ms resolution for fast-loop variables buffered in the site controller for 72 hours.
- **NFR-OBS-02** Sequence-of-events (SoE) timestamps from protection relays, PCS, EBMS and site controllers shall be aligned to within ±1 ms of each other.
- **NFR-OBS-03** One-second data shall be retained for 13 months; events, alarms and operator actions shall be retained for 7 years.

#### Maintainability

- **NFR-MNT-01** All controller logic, HMI configuration, device settings and network configuration shall be under version control with a documented baseline per release.
- **NFR-MNT-02** Replacement of any single rack, EBMS or PCS module shall be possible without shutting down the other enclosures.

---

## 4. Design Principles

- **P-01 Safety independent of optimisation software.** Protective functions that prevent harm to people or damage to equipment are implemented in certified device-level protection (rack BMS, EBMS, PCS, protection relays) and in hardwired interlocks. SEMS software optimises within the envelope those protections enforce and never needs to act for the site to be safe.
- **P-02 Fail to a known, conservative state.** On loss of supervisory control or communication, every device reverts to a predefined conservative behaviour that keeps the site within its interconnection and safety limits.
- **P-03 Time-scale separation.** Each control layer operates on a distinct time scale and owns a distinct concern, so faster layers never wait on slower ones (Section 5.3).
- **P-04 Defence in depth through zones and conduits.** Communication between zones passes only through defined conduits with firewalls. No connection initiated from outside the OT DMZ may reach the control zone or the device zone.
- **P-05 Utility settings authority.** The utility settings file is the master for grid-protective and grid-support settings. The SEMS reads and verifies these settings but cannot write them.
- **P-06 Measure what you bill.** Control decisions on import and export are made from measurements at the PCC, not from inferred quantities.
- **P-07 One source of truth for configuration.** Every setting has exactly one authoritative store, recorded in the configuration register (Section 10.3).

---

## 5. Architecture

### 5.1 Overview

The SEMS is a layered control system aligned with the Purdue reference model:

- **Device layer (Zone 1).** PCS-A and PCS-B; EBMS-1 to EBMS-4 and their rack BMS units; protection relays R-PCC, R-B and R-F1 to R-F4; meter gateway G-1 with check meter M-1 and sub-meters M-2 to M-9; PV gateway PVG-1 fronting the PV string inverters; gas detection controller GDC-1; the BESS-yard fire alarm control panel FACP-B (monitoring interface only); enclosure HVAC controllers.
- **Control layer (Zone 2).** Site controllers SC-A and SC-B, a redundant hot-standby pair of PLC-class controllers; a local operator panel in the MV switchroom.
- **Supervisory layer (Zone 3).** A two-host virtualisation cluster running the optimiser, historian, HMI server, alarm server and engineering workstation virtual machines.
- **OT DMZ.** Historian replica, utility communications gateway UCG-1 (IEEE 2030.5 client), remote access jump host, patch and antivirus staging server.
- **Enterprise (Level 4).** Enterprise analytics and forecasting platform, corporate SIEM, corporate identity provider.

### 5.2 Electrical architecture and ratings

The BESS connects to SWG-1 through 52-B. Each PCS feeds its own step-up transformer; both transformers connect to a common 12.47 kV bus section downstream of 52-B. Each enclosure has its own DC disconnect and DC contactors at each rack.

| Quantity | Value | Basis |
|---|---|---|
| Nameplate energy | 4,000 kWh | A-01 |
| Usable energy (5% to 95% SoC) | 3,600 kWh | A-05 |
| Reserve energy held for backup (5% to 35% SoC) | 1,200 kWh | FR-BK-02 |
| Power at PCS AC terminals | 2,000 kW / 2,200 kVA | A-02 |
| Power at 52-B (net of transformer and auxiliary loss) | ~1,940 kW | Supplier loss data |
| Island mode capability | 1,000 kW grid-forming (PCS-A) plus 1,000 kW grid-following (PCS-B) | A-02 |

In island mode PCS-A forms the voltage and frequency of the F-3 island and PCS-B follows. The PV blocks are on F-1 and F-4, which are shed in island mode, so the island contains no PV. This avoids the need for PV frequency-watt coordination in the island and limits island duration to the reserve energy, which is the intended behaviour.

### 5.3 Control hierarchy

| Layer | Where | Time scale | Concern |
|---|---|---|---|
| L-A Device protection | Rack BMS, EBMS, PCS, relays | < 10 ms to 1 s | Cell, rack and equipment protection; anti-islanding; IEEE 1547 trip and ride-through |
| L-B Fast control | SC-A / SC-B | 100 ms | Export control, import cap tracking, setpoint allocation between PCS, island sequencing, PV curtailment |
| L-C Schedule execution | SC-A / SC-B | 1 min | Applies optimiser schedule, enforces SoC limits and reserve, mode management |
| L-D Optimisation | Supervisory optimiser VM | 15 min / day-ahead | Schedules for peak shaving, DR, arbitrage; throughput management |
| L-E Enterprise | Analytics platform | Hours to months | Forecasting, M&V, fleet reporting |

Layers L-B and L-C run on the site controllers so that loss of the supervisory layer does not affect real-time control (NFR-AV-03). The site controller holds the last valid schedule and a rule-based default schedule (FR-OPT-03).

### 5.4 Network architecture

The control network in Zones 1 and 2 uses two independent managed switch networks (LAN-A and LAN-B) in a Parallel Redundancy Protocol (PRP, IEC 62439-3) arrangement. SC-A, SC-B, PCS-A, PCS-B and the protection relays are dual-attached. Single-attached devices (EBMS, G-1, PVG-1, GDC-1, HVAC controllers) connect through PRP redundancy boxes. Zone 1 and Zone 2 are separated by VLAN and by access control lists on the switches, with the industrial firewall FW-0 between Zone 2 and Zone 3.

Firewall FW-1 separates Zone 3 from the OT DMZ and FW-2 separates the OT DMZ from the enterprise network. The utility link uses a dual-carrier cellular router connected only to UCG-1 in the OT DMZ.

### 5.5 Redundancy and failover

- SC-A and SC-B operate as a hot-standby pair with a dedicated fibre synchronisation link. The active controller transfers its state to the standby every scan. The standby monitors a 50 ms heartbeat and takes over after three missed heartbeats. Measured switchover in the integrator's reference system is under 300 ms, and the design target is 500 ms, which meets NFR-AV-02.
- Each site controller has dual power supplies fed from UPS-1 (fed from F-4) and UPS-2 (fed from F-3), so control power survives the loss of either feeder or either UPS.
- The supervisory cluster runs on two hosts with automatic VM restart. Loss of the supervisory layer causes loss of optimisation and historian functions only; the site controllers buffer 72 hours of data.
- The relays, PCS and EBMS each retain their own protection functions independent of the SEMS.

### 5.6 Physical placement

The site controllers, PRP switches and UPS-2 are in a dedicated control cabinet in the MV switchroom. The supervisory hosts are in the site IT room in a separate rack fed from F-3. The BESS yard contains the four enclosures, two PCS skids with their transformers, the yard fire alarm panel FACP-B and a yard network cabinet housing a pair of PRP switches connected to the switchroom by two diverse fibre routes.

---

## 6. Interfaces

### 6.1 Interface summary

| ID | From / To | Protocol | Rate | Content |
|---|---|---|---|---|
| IF-PCS-01 | SC ↔ PCS-A, PCS-B | Modbus TCP, SunSpec DER models (700 series) | Setpoints 100 ms; status 200 ms | P/Q setpoints, mode, limits, measurements, alarms |
| IF-BMS-01 | SC ↔ EBMS-1..4 | Modbus TCP | 500 ms | Enclosure summary: SoC, power limits, alarms, contactor states |
| IF-BMS-02 | SC ↔ EBMS-1..4 (rack data) | Modbus TCP | 1 s per rack | Rack status block: cell min/max V and T, rack current, alarms |
| IF-MTR-01 | SC ↔ meter gateway G-1 | Modbus TCP (G-1 polls meters over Modbus RTU) | 5 s | PCC P/Q/V from M-1; feeder sub-meters M-2..M-9 |
| IF-RLY-01 | SC ↔ relays | IEC 61850 MMS (reports) and GOOSE | MMS 1 s; GOOSE event-driven | Breaker status, trips, open/close commands, protection pickups |
| IF-PV-01 | SC ↔ PVG-1 | Modbus TCP, SunSpec | 1 s | PV active power limit, measurements, inverter status |
| IF-FIRE-01 | FACP-B → PCS, EBMS, SC | Hardwired; Modbus status to SC | Event | Fire alarm, trouble, supervisory |
| IF-GAS-01 | GDC-1 → exhaust fans, FACP-B; GDC-1 → SC | Hardwired; Modbus status to SC | Event / 1 s | Gas levels, fan status, detector faults |
| IF-FCS-01 | SC ↔ FCS | BACnet/IP through FW-0 | 10 s | Load-shed requests and acknowledgements |
| IF-UTL-01 | UCG-1 ↔ utility DERMS | IEEE 2030.5 over cellular private APN | Event / programme | DER controls, telemetry, event responses |
| IF-ENT-01 | Historian replica → enterprise | HTTPS, mutual TLS | 1 min batches | Historian data, events, M&V data |
| IF-RA-01 | Remote users → jump host | TLS VPN with MFA | Session | Engineering and support access |
| IF-TIME-01 | Time source → all devices | NTP | Continuous | Time synchronisation |

### 6.2 PCS interface (IF-PCS-01)

The PCS exposes SunSpec DER information models covering nameplate, settings, measurements, DER control (active and reactive power setpoints, ramp rates, mode) and the IEEE 1547 function curves. The site controller writes:

- Active power setpoint (signed, kW; positive = discharge) every 100 ms per PCS.
- Reactive power setpoint only when the utility settings file selects constant reactive power mode; otherwise the PCS volt-var curve is active and the site controller does not write reactive power.
- Charge and discharge power limits, derived from EBMS limits.
- Operating mode (standby, grid-following, grid-forming), written only by the island sequencing logic.

The site controller reads IEEE 1547 settings from the PCS once per hour and compares them with the configuration register (P-05). A mismatch raises a priority-2 alarm. The site controller has no write access to the IEEE 1547 settings models; these are written by the supplier's commissioning tool under change control.

**Communication loss behaviour.** The PCS supports a communication watchdog with a configurable action: hold last setpoint, ramp to zero, or shut down. The design sets the action to "hold last setpoint" with no timeout. The rationale is to avoid interrupting peak shaving during transient network events and during controller switchover (Section 7.9). The PCS and EBMS internal protections remain active in all cases, so the batteries remain protected if communication is lost for an extended period.

### 6.3 Battery management interfaces (IF-BMS-01, IF-BMS-02)

Each EBMS presents an enclosure summary block (64 registers) and, for each of its ten racks, a rack status block of 200 holding registers containing per-module minimum and maximum cell voltage and temperature, rack current, insulation resistance, contactor state and alarm words.

- IF-BMS-01: the site controller reads the enclosure summary block from each EBMS every 500 ms. The summary includes the enclosure's present charge and discharge power limits, which the site controller uses to clamp PCS setpoints.
- IF-BMS-02: the site controller reads each rack status block in a single function code 0x03 (Read Holding Registers) request of 200 registers, once per second per rack. Across 40 racks this is 40 transactions per second, about 10 per EBMS. The supplier's measured EBMS response time is 15 to 25 ms per transaction, so each EBMS is busy for at most 250 ms of every second, leaving ample margin for the summary reads.

Modbus TCP is used without encryption within Zone 1. The EBMS and PCS do not support Modbus/TCP Security (TLS), and the compensating controls are described in Section 9.4 and decision D-03.

The EBMS acts autonomously on cell over-voltage, under-voltage, over-temperature, over-current and insulation faults by opening the affected rack contactors. The site controller does not participate in these protections; it reacts to the reduced power limits that result.

### 6.4 Metering (IF-MTR-01)

M-1 is a customer-owned class 0.2S check meter on the 12.47 kV side of 52-PCC, using the same instrument transformers as R-PCC through separate cores. M-1 and the feeder sub-meters M-2 to M-9 share an RS-485 Modbus RTU segment at 19,200 baud polled by gateway G-1. G-1 presents the latest values to the site controller over Modbus TCP. Because of the RS-485 segment loading, G-1 refreshes all values on a 5-second cycle.

M-1 is the measurement of record for the SEMS. It is used for PCC import tracking (peak shaving), export control (Section 7.3) and M&V. The utility revenue meter M-0 remains the billing meter; a monthly reconciliation between M-0 billing data and M-1 data is performed as part of M&V (FR-MON-03).

### 6.5 Protection relays (IF-RLY-01)

R-PCC provides functions 25 (sync-check), 27/59 (under/over-voltage), 81O/U (over/under-frequency), 32 (directional power), 50/51 and 67, and acts as the MID protection for the site. R-B protects the BESS bus section. Relay settings are issued by the utility (for R-PCC) and by the site protection engineer (for R-B and feeder relays), and are not writable by the SEMS.

The site controller subscribes to GOOSE messages for breaker status and trip events from all relays and publishes GOOSE open and close commands to 52-F1 to 52-F4 for load shedding and restoration. Closing of 52-PCC is always supervised by R-PCC function 25. MMS reports deliver measurements and settings group status every second.

### 6.6 Utility DER control interface (IF-UTL-01)

UCG-1 runs an IEEE 2030.5 client that registers with the utility's DERMS server as an aggregated site DER. It retrieves DERProgram and DERControl resources, posts DERStatus, DERAvailability and DERCapability, and posts telemetry (MirrorUsagePoint) at the programme interval of 5 minutes. Events received are translated into a constraint set (for example, maximum import, maximum export, or fixed active power at the PCC) and passed through FW-1 to the supervisory optimiser and to the site controller.

The link uses a private APN provisioned by the cellular carrier for the utility's DER programme. Because the APN is a closed network accessible only to programme participants and the utility, the IEEE 2030.5 client is configured to use HTTP on port 80, with TLS disabled. This avoids the certificate provisioning and renewal process for the client device certificate, which the utility's onboarding portal does not yet automate. The router enforces an allow-list containing only the DERMS server address.

### 6.7 Fire, gas and safety I/O (IF-FIRE-01, IF-GAS-01)

FACP-B serves the BESS yard. Each enclosure has smoke and heat detection and is connected to FACP-B. On fire alarm, FACP-B de-energises a normally energised output wired directly to the shutdown input of the associated PCS and to the enclosure trip input of the EBMS, which opens all DC contactors in the enclosure. FACP-B also reports to the building fire alarm panel and to the monitoring station under NFPA 72.

Each enclosure has two combustible gas detectors (hydrogen and carbon monoxide). GDC-1 starts the enclosure's explosion control exhaust fans directly by hardwired output at 10% of the lower flammable limit (LFL) and signals FACP-B, which treats a 25% LFL signal as an alarm. The exhaust system is sized to keep the enclosure atmosphere below 25% LFL under the release rate from the UL 9540A cell-level test data, as required by NFPA 69. Exhaust fans and GDC-1 are supplied from F-3 with a battery-backed control supply so that they operate during an outage.

The site controller receives the status of FACP-B and GDC-1 over Modbus for display and event recording. It does not take part in their interlocks.

### 6.8 Facility control system (IF-FCS-01)

The site controller sends load-shed requests to the FCS over BACnet/IP: stage 1 sheds non-essential refrigeration in plant A, stage 2 sheds chilled-zone compressors (F-2), and in island mode stages 3 and 4 shed lower-priority freezer compressors on F-3. The FCS acknowledges each request and may decline a stage if product temperature limits would be violated, in which case the site controller escalates to the operator.

### 6.9 Enterprise (IF-ENT-01)

The historian replica in the OT DMZ pushes data to the enterprise analytics platform over HTTPS with mutual TLS. Forecasts flow in the other direction: the enterprise platform publishes them to a file share in the OT DMZ, from which the optimiser pulls them. No enterprise system initiates a connection into Zone 3.

### 6.10 Time synchronisation (IF-TIME-01)

All Zone 1 and Zone 2 devices (site controllers, PCS, EBMS, relays, meter gateway and PV gateway) and the supervisory servers synchronise to the corporate NTP service. The corporate service consists of two stratum-2 servers in the enterprise data centre, referenced to the public pool.ntp.org service. An NTP relay on the OT DMZ serves the OT zones. The expected alignment across devices is ±1 ms, which meets NFR-OBS-02. The relays timestamp SoE records with 1 ms resolution.

---

## 7. Operating Modes and Key Flows

### 7.1 Operating modes

| Mode | Description | Entered by |
|---|---|---|
| Grid-parallel auto | Normal operation; schedule from optimiser, fast loop active | Operator, or automatically after island return |
| Grid-parallel manual | Operator sets BESS power directly within all limits; fast loop export and import protections remain active | Operator (privileged role) |
| Island | Site separated at 52-PCC; PCS-A grid-forming; F-3 only | Automatic on grid loss, or operator command |
| Standby | PCS at zero power, DC contactors closed, ready | Operator, schedule, or fault |
| Maintenance | SEMS outputs disabled; PCS in standby; devices under local control for maintenance | Operator with permit |
| Safe stop | PCS stopped, all DC contactors open | E-stop, fire alarm, or critical fault |

Transitions are managed by a mode state machine in the site controller. Each transition records the initiator, reason and preconditions checked.

### 7.2 Peak shaving and the energy budget

The optimiser builds a day-ahead discharge plan for the on-peak window from the load and PV forecast and refines it every 15 minutes. In the fast loop the site controller tracks the PCC import against a target of 2,150 kW (50 kW below the 2,200 kW requirement to allow for measurement and control error) and increases discharge when import exceeds the target, within the plan's energy allocation for each interval.

**Table 2. Design-day net load (summer weekday, net of PV, hourly averages)**

| Hour beginning | Net load (kW) | Excess above 2,200 kW (kWh) |
|---|---|---|
| 14:00 | 2,050 | 0 |
| 15:00 | 2,150 | 0 |
| 16:00 | 2,700 | 500 |
| 17:00 | 3,100 | 900 |
| 18:00 | 3,400 | 1,200 |
| 19:00 | 2,600 | 400 |
| 20:00 | 2,350 | 150 |
| 21:00 | 2,100 | 0 |
| **Total** | | **3,150** |

The maximum hourly excess is 1,200 kW. Short-term peaks within the hour, observed to be up to 8% above the hourly average, are within the 1,940 kW available at 52-B.

Energy check: the required discharge at the PCC on the design day is 3,150 kWh. Allowing for discharge-path losses of about 6% (half of the 12% round-trip loss), the DC energy required is about 3,350 kWh. This is within the 3,600 kWh usable energy (Section 5.2), a margin of about 7%. The design therefore meets FR-PS-01 on the design day. The BESS is recharged overnight at off-peak rates and, on sunny days, partly from midday PV surplus.

### 7.3 Export control flow

1. The site controller reads PCC active power from M-1 through G-1.
2. If net export exceeds 450 kW (a 50 kW margin below the 500 kW limit), the fast loop first increases BESS charging power up to the lesser of the PCS and EBMS charge limits.
3. If export still exceeds 450 kW after BESS charging is at its limit, the fast loop reduces the PV active power limit through PVG-1, in steps proportional to the excess.
4. While the PCC is in net export, the BESS discharge setpoint is forced to zero (FR-EXP-03).
5. When export falls below 350 kW for 60 seconds, the PV limit is released in 5% steps every 10 seconds.

The fast loop executes every 100 ms and the PCS responds to a new setpoint within 200 ms (NFR-PERF-02), so the loop reacts well within the 2-second limit of FR-EXP-02. PV inverters ramp to a new limit at their configured rate of 100% per second.

As a backstop, R-PCC function 32 is set to trip 52-F1 and 52-F4 (the PV feeders) if export exceeds 600 kW for 5 seconds. This protects against loss of the SEMS export control but is not relied upon to meet FR-EXP-02.

### 7.4 Grid support functions

The PCS and PV inverters are configured by the utility settings file for normal performance Category B and abnormal performance Category III (FR-GRID-01). Volt-var is enabled with the Category B default curve unless the utility specifies otherwise. The site controller's active power setpoints do not interfere with these functions: the PCS gives precedence to its local volt-var and frequency-droop responses over the remote active and reactive power setpoints, and reserves 100 kVA of reactive headroom at full active power because each PCS is rated 1,100 kVA for 1,000 kW.

### 7.5 Unplanned loss of utility supply

| Step | Time from loss of supply | Action |
|---|---|---|
| 1 | 0 | Utility supply lost. PCS and PV inverters detect the island through their active anti-islanding methods and cease to energize; R-PCC detects under-voltage or under-frequency |
| 2 | ≤ 5 s | R-PCC opens 52-PCC per utility settings (FR-GRID-04). F-3 is de-energised from the moment the PCS ceases to energize |
| 3 | 52-PCC open + 0.2 s | Site controller receives 52-PCC open by GOOSE and confirms loss of utility voltage from R-PCC. It opens 52-F1, 52-F2 and 52-F4 by GOOSE |
| 4 | + 0.5 s | Site controller confirms the feeder breakers are open and that 52-PCC is open and locked out against reclosing |
| 5 | + 1.0 s | PCS-A commanded to grid-forming mode; soft-energises the MV bus section and F-3 through T-A with a 2-second voltage ramp to limit transformer inrush |
| 6 | + 3.5 s | PCS-B synchronises to the island and enters grid-following mode; F-3 load is shared between PCS-A and PCS-B |
| 7 | + 4.0 s | FCS restarts critical compressors in a staggered sequence over 5 minutes |

The total time from loss of supply to F-3 restoration is at most 9 seconds, which meets FR-BK-01. During the island, the site controller enforces FR-BK-05 and records an event log.

**Return to grid (FR-BK-04).** When R-PCC reports utility voltage and frequency within the enter-service range for 300 s, the operator is prompted to return to grid. The site controller adjusts the island frequency and phase through PCS-A until R-PCC function 25 permits closing; 52-PCC closes, PCS-A transfers to grid-following, and feeders are restored in sequence F-2, F-1, F-4 with 30-second intervals. Automatic return is configurable but disabled at go-live.

### 7.6 Planned island transition (FR-BK-03)

On operator command, the site controller (1) requests stage 1 and 2 load shedding from the FCS; (2) opens 52-F1, 52-F2 and 52-F4 in turn while increasing BESS discharge to hold PCC flow near zero; (3) when PCC flow is within ±50 kW, places PCS-A in grid-forming-ready mode and opens 52-PCC; (4) PCS-A takes over voltage and frequency regulation without interruption to F-3. The utility is notified through the operator procedure before a planned island.

### 7.7 Demand response event flow

1. UCG-1 retrieves a DERControl event from the DERMS (for example, "limit site import to 1,500 kW from 17:00 to 19:00").
2. UCG-1 validates the event against the programme registration (event type, magnitude, duration) and passes a constraint to the optimiser and to the site controller through FW-1.
3. The optimiser re-plans to include the constraint, and the site controller applies the constraint as an additional import cap in the fast loop from the event start.
4. If an operator opts out (FR-DR-03), UCG-1 posts an opt-out response to the DERMS with the reason code.
5. UCG-1 posts event status (received, started, completed) and 5-minute telemetry.

DR constraints never override the reserve (FR-BK-02), the export constraints, or any protection. If a DR event cannot be met without breaching the reserve, the site controller meets it as far as possible and records a partial-performance event.

### 7.8 Optimiser and throughput management

The optimiser is a mixed-integer linear program over a 36-hour horizon at 15-minute resolution. Its objective is to minimise expected energy and demand cost plus a degradation cost per kWh discharged, subject to the constraints in FR-OPT-02. The SoC floor applied by the optimiser outside island mode is 35%.

Beyond peak shaving, the optimiser uses spare capacity for a part-peak discharge in the morning window (06:00 to 09:00) after overnight charging, and for absorbing midday PV surplus. Expected annual throughput from the supplier's and our own simulations:

| Day type | Days per year | EFC per day | EFC per year |
|---|---|---|---|
| Summer weekday | 85 | 1.6 | 136 |
| Other weekday | 176 | 1.3 | 229 |
| Weekend and holiday | 104 | 0.9 | 94 |
| **Total** | | | **~459** |

Throughput is tracked against the 4,000 EFC lifetime warranty limit with a pro-rata budget. At about 460 EFC per year the lifetime limit is reached in year 8.7, which aligns with the year-8 augmentation in the financial model (C-04). The degradation cost parameter will be tuned in Phase 3 if actual throughput runs ahead of the pro-rata budget.

### 7.9 Site controller failover

1. The active controller fails or loses its heartbeat.
2. After three missed 50 ms heartbeats, the standby controller assumes the active role with the synchronised state.
3. During switchover, the PCS continue at their last setpoints (Section 6.2).
4. The new active controller resumes writing setpoints and raises a priority-2 alarm for the failed controller.

### 7.10 Battery thermal event

1. A rack BMS detects a cell over-temperature or abnormal temperature rise and opens the rack contactors (L-A protection).
2. The EBMS reduces the enclosure power limits; the site controller redistributes power to the remaining enclosures.
3. If off-gas reaches 10% LFL, GDC-1 starts exhaust by hardwired output and signals FACP-B.
4. If FACP-B goes into alarm (smoke, heat, or 25% LFL), it trips the associated PCS and opens all DC contactors in the enclosure by hardwired outputs, notifies the monitoring station and the building fire alarm panel, and the site controller places the BESS in safe stop.
5. The emergency response plan (Section 8.3) governs subsequent actions by site staff and the fire service.

---

## 8. Safety

### 8.1 Hazard summary

The hazard identification workshop (2026-08-21) produced the hazard log FDC-SEMS-HL-001. The principal hazards and controls are:

| Hazard | Principal controls |
|---|---|
| Thermal runaway and fire propagation | LFP chemistry; rack BMS protections; enclosure spacing; UL 9540A test data; sprinkler system; FACP-B hardwired trips |
| Flammable gas accumulation and deflagration | Gas detection; explosion control exhaust per NFPA 69; deflagration vent panels on enclosures |
| Electric shock and arc flash (DC and AC) | Arc-flash study and labelling; DC disconnects lockable; LOTO procedures; restricted yard access |
| Unintended energisation of the Area EPS | IEEE 1547 anti-islanding in PCS and PV inverters; R-PCC protection |
| Back-feed into de-energised site circuits during maintenance | Lockout points include 52-B and PCS DC disconnects; maintenance mode procedure |
| Loss of refrigeration and product temperature | Backup power to F-3; FCS temperature alarms |

### 8.2 Emergency stop

Emergency stop stations are installed at the BESS yard gate, the MV switchroom and the control room (NFR-SAF-03). Each station has a latching, red mushroom-head pushbutton with two normally closed contacts. Both contacts are wired to dual-channel safety-rated digital inputs on both SC-A and SC-B. On activation, the active site controller executes the safe-stop sequence: it writes a shutdown command to both PCS over IF-PCS-01, writes an open-all-contactors command to each EBMS over IF-BMS-01, opens 52-B by GOOSE, and latches the safe-stop mode until the station is reset and an authorised operator acknowledges on the HMI. Measured execution in the integrator's test rig is under 300 ms against the 500 ms requirement.

Routing the E-stop through the redundant controller pair gives it the same redundancy as the control function, avoids additional field wiring across the yard, and records each activation in the SoE log.

### 8.3 Fire protection and emergency response

The enclosures are equipped with an automatic water-based sprinkler system (dry-pipe, for freeze protection) designed in accordance with NFPA 855 and the UL 9540A large-scale test results. A gaseous clean-agent system was considered and rejected (decision D-04) because clean agents do not provide cooling and cannot stop thermal runaway propagation in LFP modules.

The emergency response plan, prepared with the fire marshal, covers: notification and monitoring station procedure; the fire service's access route and standoff positions; the location of the remote status display at the yard gate showing enclosure gas, temperature and alarm status; a defensive firefighting strategy (no enclosure door opening while gas is present); and the post-incident procedure for stranded energy. Site staff are trained annually, and the fire service is offered a site familiarisation visit before energisation.

### 8.4 Electrical protection and arc flash

The protection study covers 52-PCC, 52-B, the feeder breakers and the PCS AC and DC protection. Fault current contribution from the PCS (limited to about 1.2 times rated current) is included in the coordination study for both grid-parallel and island configurations. In island mode the fault current available from PCS-A and PCS-B is low, so feeder protection on F-3 uses a settings group with reduced pickup, selected automatically by GOOSE when 52-PCC is open. The arc-flash study covers grid-parallel and island configurations, and labels show the higher of the two incident energies.

### 8.5 Safety lifecycle and management of change

EHS owns the hazard log. Any change to protection settings, interlocks, E-stop logic, fire or gas systems, or operating modes requires a management-of-change (MOC) review that includes EHS and, where grid settings are affected, the utility. The hazard log is reviewed at each design review gate, before energisation, and annually during operation.

---

## 9. Cybersecurity

### 9.1 Zones and conduits

| Zone | Contents | SL-T |
|---|---|---|
| Zone 1 Device | PCS, EBMS, relays, G-1, PVG-1, GDC-1, HVAC controllers | 2 |
| Zone 2 Control | SC-A, SC-B, local operator panel | 2 |
| Zone 3 Supervisory | Virtualisation hosts and VMs | 2 |
| OT DMZ | Historian replica, UCG-1, jump host, patch staging | 2 |

| Conduit | Path | Controls |
|---|---|---|
| CD-1 | Zone 2 ↔ Zone 1 | Switch ACLs; allow-listed protocols and addresses only (Modbus TCP, IEC 61850, BACnet to FCS via FW-0) |
| CD-2 | Zone 3 ↔ Zone 2 | FW-0; only SC data exchange, HMI traffic and engineering workstation sessions |
| CD-3 | OT DMZ ↔ Zone 3 | FW-1; historian replication (outbound from Zone 3), constraints from UCG-1, patch staging pull |
| CD-4 | Enterprise ↔ OT DMZ | FW-2; HTTPS with mutual TLS outbound from DMZ; forecast file share; remote access via jump host |
| CD-5 | Utility ↔ OT DMZ | Cellular router with allow-list; IEEE 2030.5 (Section 6.6) |

### 9.2 Identity and access

OT accounts are managed in a dedicated OT directory in Zone 3, separate from the corporate directory, with a one-way synchronisation of user identities from corporate HR data for joiners and leavers. Roles are viewer, operator, privileged operator (manual mode, DR opt-out), engineer and administrator. Shared accounts are not permitted except for device-local break-glass accounts, whose credentials are held in a sealed envelope in the control room safe and rotated after each use.

### 9.3 Remote access

The standard remote access path is through the jump host in the OT DMZ. Users connect from the enterprise network or the internet through the corporate TLS VPN with MFA, then to the jump host, which brokers RDP or SSH sessions to Zone 3 systems with session recording. Access is approved per session by the facilities on-call technician through the access workflow, and sessions are time-limited to 4 hours.

The PCS supplier's warranty and service agreement requires continuous connectivity to the supplier's fleet monitoring service and allows the supplier's 24/7 support desk to diagnose PCS and EBMS faults. To meet this, the supplier installs a managed router (VR-1) in the yard network cabinet, connected to Zone 1 and Zone 2 VLANs and to a dedicated broadband service. VR-1 maintains a persistent IPsec site-to-site tunnel to the supplier's network operations centre, authenticated with a pre-shared key managed by the supplier. Supplier engineers reach the PCS and EBMS management interfaces through this tunnel from the supplier's NOC. The supplier's own access controls govern who can use the tunnel.

### 9.4 Protocol security

Modbus TCP, IEC 61850 GOOSE and BACnet/IP do not offer authentication or encryption on the devices selected. Compensating controls for Zone 1 and Zone 2 are: physical security of cabinets and yard (locked, alarmed, under CCTV); switch port security with MAC binding and disabled unused ports; ACLs limiting each device to its peers; a passive OT network monitoring sensor on both PRP LANs alerting on new devices, new flows and Modbus write function codes from any source other than the site controllers; and controller configuration that rejects writes from addresses other than the engineering workstation.

### 9.5 Monitoring and patching

Firewalls, the jump host, supervisory servers and the OT network monitoring sensor forward logs to the corporate SIEM through a log collector in the OT DMZ. Patching follows NFR-SEC-05. Patches are staged in the OT DMZ, tested on the integrator's reference system, and installed in the monthly maintenance window (Section 11.2). Controller firmware is updated only in the maintenance window and only after FAT-equivalent regression testing on the reference system.

---

## 10. Governance and Data

### 10.1 Settings authority

| Settings | Authority | Written by | SEMS access |
|---|---|---|---|
| IEEE 1547 settings (PCS, PV) | Utility settings file | Supplier commissioning tool, under MOC | Read and verify |
| R-PCC settings | Utility | Site protection engineer | Read |
| R-B and feeder relay settings | Site protection engineer | Site protection engineer | Read |
| EBMS protection settings | BESS supplier | Supplier | Read |
| SEMS control parameters (targets, margins, ramp rates) | Site Energy Engineering | Integrator under MOC | Configuration |
| Optimiser parameters | Site Energy Engineering | Site Energy Engineering | Configuration |

### 10.2 Data ownership and retention

FDC owns all operational data. The BESS supplier receives the data needed for warranty administration under the service agreement. The utility receives DR telemetry and event data as required by the programme. Historian data is retained in line with NFR-OBS-03, with the enterprise platform holding the long-term archive. M&V reports are retained for the life of the asset.

### 10.3 Configuration and change management

All configuration items (controller programs, HMI projects, device settings files, firewall rule sets, network configurations, optimiser models) are held in the OT configuration repository in Zone 3, with a baseline per release (NFR-MNT-01). Each production change has an MOC record, a tested rollback, and post-change verification. The configuration register maps every setting to its authority (Table in 10.1) and is the reference for the hourly settings verification (Section 6.2).

---

## 11. Operations and Maintenance

### 11.1 Monitoring and response

During business hours, the facilities control room monitors the HMI. Out of hours, priority-1 and priority-2 alarms are sent to the on-call technician by SMS and voice call through the alarm server. The integrator provides remote support during the 2-year defects period, and the BESS supplier provides 24/7 support for BESS faults. Response targets: priority-1 acknowledged in 15 minutes and on site in 60 minutes; priority-2 acknowledged in 1 hour.

### 11.2 Maintenance windows

A planned maintenance window is held monthly on the second Sunday from 02:00 to 06:00 (4 hours). It is used for controller firmware and operating system patches, supervisory server updates, HMI releases and functional checks. During the window the SEMS is in maintenance mode and the PCS are in standby at zero power. Because PV output is zero at that time, export limiting is not required, and site import is low because of the time of day.

The 12 planned windows are counted within the NFR-AV-01 availability measure. With an allowance of 2 hours per year of unplanned outage, the design meets the NFR-AV-01 target of 99.95%.

Annual maintenance of the BESS (thermal imaging, torque checks, filter replacement, gas detector calibration, fire system testing) is carried out one enclosure at a time; the other three remain in service (NFR-MNT-02).

### 11.3 Spares

Spares held on site: one PCS power module, one rack BMS unit, two battery modules, one EBMS controller, one site controller CPU and I/O card set, one PRP switch, one RedBox and gas detector heads. The supplier holds further spares regionally with a 48-hour delivery commitment.

### 11.4 Procedures and training

Procedures required before energisation: normal operation, E-stop and reset, island and return-to-grid, DR opt-out, maintenance mode and LOTO, alarm response for each priority-1 alarm, emergency response (with the fire marshal), and cybersecurity incident response. Operators complete classroom and simulator training on the integrator's reference system, and competence is recorded before HMI accounts are granted operator or higher roles.

### 11.5 Performance monitoring

Site Energy Engineering reviews a weekly dashboard covering peak shaving performance against target, export compliance, SoC and reserve compliance, throughput against warranty budget, availability, and alarm rates per ISA-18.2 key performance indicators.

---

## 12. Decisions

| ID | Decision | Alternatives considered | Rationale |
|---|---|---|---|
| D-01 | LFP chemistry | NMC | Higher thermal runaway onset temperature and lower heat release; cycle life suits daily cycling; preferred by AHJ |
| D-02 | Redundant hot-standby PLC-class site controllers for fast control | Single controller; VM-based controller on supervisory cluster | Deterministic 100 ms cycle; independence from virtualisation layer; meets NFR-AV-02 |
| D-03 | Plain Modbus TCP and GOOSE inside Zones 1 and 2 with compensating controls | Encrypted protocols; serial links | Devices do not support secure variants; compensating controls (Section 9.4) are proportionate to SL-T 2 |
| D-04 | Water-based sprinkler system with explosion control exhaust; no clean-agent system | Clean agent (gaseous) suppression; no suppression with defensive strategy only | Clean agents do not stop thermal runaway propagation; water provides cooling; consistent with NFPA 855 and UL 9540A results; supported by AHJ |
| D-05 | Life-safety loads remain on the diesel generator and ATS; not served by the BESS | Serve life-safety from BESS island | Keeps the existing, listed emergency system unchanged; avoids NEC Article 700 requirements applying to the BESS |
| D-06 | IEEE 2030.5 for the utility interface | DNP3; OpenADR | Utility programme mandate |
| D-07 | PV on shed feeders only; no PV in island | Keep PV in island with frequency-watt control | Simpler island control; island duration bounded by reserve energy |
| D-08 | M-1 check meter as the control measurement for import and export | Use PCS-internal measurements; use utility meter M-0 pulses | P-06; M-1 measures the actual PCC quantity |
| D-09 | Accept lifetime throughput reaching 4,000 EFC in year ~8.7 | Restrict dispatch to peak shaving only | Additional value from part-peak discharge exceeds the cost of earlier augmentation |
| D-10 | PCS communication watchdog set to hold last setpoint | Ramp to zero; shut down | Avoids interrupting peak shaving on transient communication loss and during controller switchover |

---

## 13. Open Items

| ID | Item | Owner | Needed by |
|---|---|---|---|
| OI-01 | AHJ final approval of yard layout, separation distances and emergency response plan | EHS | Phase 1 construction start |
| OI-02 | Utility DER settings file and final R-PCC protection settings, following the utility's system impact study for amendment 2 | Electrical Engineering / Utility | Phase 3 |
| OI-03 | Utility onboarding of UCG-1 to the DERMS (registration, programme enrolment) | Site Energy Engineering | Phase 3 |
| OI-04 | Confirmation from the FCS vendor that BACnet load-shed objects support acknowledgement and decline responses | Controls Engineering | Phase 2 |
| OI-05 | Final supplier loss data for transformer no-load losses in standby | BESS supplier | Phase 1 FAT |
| OI-06 | Operator HMI style guide alignment with corporate standard | Controls integrator | Phase 1 FAT |
| OI-07 | Decision on whether to enable automatic return-to-grid after one year of operation | Site Energy Engineering / Operations | Post-Phase 3 |

---

## 14. Acceptance Criteria

Acceptance is performed in three stages: factory acceptance testing (FAT) of the site controller and supervisory software on the integrator's reference system with simulated devices; site acceptance testing (SAT) with live equipment; and a 30-day performance verification period. Unless stated otherwise, measurements are taken from the historian and verified against a temporary power quality analyser at the PCC sampling at 10 samples per second or faster.

| ID | Requirement(s) | Test | Pass criterion |
|---|---|---|---|
| AC-01 | FR-PS-01, FR-PS-02, FR-PS-03 | FAT: replay design-day profile (Table 2) through the simulated site with SoC at 95% at 16:00. SAT/30-day: record actual on-peak performance | FAT: 15-min import ≤ 2,200 kW throughout the on-peak window. 30-day: no on-peak 15-min interval above 2,200 kW on days within the design-day envelope |
| AC-02 | FR-EXP-01, FR-EXP-02, FR-EXP-04 | SAT: with PV above 1,200 kW, reduce site load by opening FCS stages to drive export above 500 kW; repeat with BESS at 95% SoC so PV curtailment is required | Export above 500 kW does not persist longer than 2 s in any trial (PQ analyser) |
| AC-03 | FR-EXP-03 | SAT: command BESS discharge in manual mode while site is in net export | Discharge setpoint forced to zero; no BESS contribution to export |
| AC-04 | FR-GRID-01, FR-GRID-02, FR-GRID-03 | Document review of UL 1741 SB certificates and utility settings file; read-back of settings from PCS and PV inverters | Settings match utility file exactly; certificates cover installed firmware versions |
| AC-05 | FR-GRID-04 | Document review of IEEE 1547.1 anti-islanding type test results for PCS and PV inverters; secondary injection test of R-PCC | Type tests demonstrate cease to energize within the required time; R-PCC opens 52-PCC within 5 s |
| AC-06 | FR-GRID-05, FR-BK-04 | SAT: return to grid from island with sync-check | 52-PCC closes only with sync-check permissive; no PCS trip on closure; feeders restored in sequence |
| AC-07 | FR-BK-02 | 30-day: SoC trace while grid-connected | SoC never below 35% while grid-connected |
| AC-08 | FR-BK-01, FR-BK-03 | SAT: operator-commanded planned island from HMI with site importing 1.5 MW, followed by return to grid | F-3 uninterrupted during planned transition; island stable for 30 min with F-3 load; return to grid per AC-06 |
| AC-09 | FR-BK-05 | FAT: simulated island with SoC falling through 15% and 5% | Load-shed requests issued at 15%; orderly PCS stop at 5% |
| AC-10 | FR-DR-01, FR-DR-02, FR-DR-03 | SAT: utility test event via DERMS test server; operator opt-out test | Event executed within 60 s of start; status and telemetry posted; opt-out posted with reason |
| AC-11 | FR-OPT-01, FR-OPT-02, FR-OPT-03 | FAT: optimiser runs over 30 simulated days; stop optimiser VM for 26 h | All constraints respected; last schedule used for 24 h, then rule-based default |
| AC-12 | NFR-PERF-01 to NFR-PERF-04 | FAT and SAT timing measurements | All timing requirements met at the 99th percentile |
| AC-13 | NFR-AV-02, NFR-AV-03 | SAT: power-off active SC; disconnect one PRP LAN; stop both supervisory hosts | Control function restored within 2 s for each single failure; fast loop unaffected by supervisory loss |
| AC-14 | NFR-SAF-01, NFR-SAF-02 | Document review: UL 9540A certificate for racks and enclosures, UL 1973 and UL 1741 SB certificates; AHJ inspection sign-off | Certificates present and current; AHJ sign-off obtained |
| AC-15 | NFR-SAF-03 | SAT: activate each E-stop station with BESS at 1,000 kW discharge | Safe state reached within 500 ms per SoE log; reset requires station reset and HMI acknowledgement |
| AC-16 | NFR-SAF-04, Section 6.7 | SAT: inject test gas at each detector; trigger FACP-B alarm inputs | Exhaust starts at 10% LFL; FACP-B alarm trips PCS and opens DC contactors by hardwired path |
| AC-17 | NFR-SEC-01 to NFR-SEC-05 | Independent OT security assessment against IEC 62443-3-3 SL-T 2; firewall rule review; remote access test | No high findings open; all conduits as Section 9.1 |
| AC-18 | NFR-OBS-01 to NFR-OBS-03 | SAT: injected events at relays, PCS and SC; check historian resolution and retention configuration | SoE alignment within ±1 ms; resolution and retention as specified |
| AC-19 | NFR-AV-01 | First 12 months of operation | Availability ≥ 99.95% |

---

## 15. Phased Plan

| Phase | Months | Scope | Exit criteria |
|---|---|---|---|
| Phase 0: Detailed design | 1 to 2 | Close DR-2 comments; finalise interface control documents; protection and arc-flash studies; FAT plan | DR-3 approval; IFC drawings issued |
| Phase 1: Grid-parallel BESS | 3 to 7 | Civil works, enclosure and PCS installation, 52-B switchgear section, SC and network installation, FAT, energisation of the BESS in grid-parallel operation, peak shaving and export control, historian and HMI | AC-01 (FAT part), AC-02, AC-03, AC-04, AC-07, AC-11, AC-12, AC-13, AC-14, AC-15, AC-16, AC-17; peak shaving in service |
| Phase 2: Backup power | 8 to 10 | PCS-A grid-forming licence activation, island sequencing, F-3 settings groups, FCS load-shed integration, planned island tests | AC-05, AC-06, AC-08, AC-09; procedures and training complete |
| Phase 3: Utility programme and optimisation | 11 to 13 | Utility settings file implementation and verification, UCG-1 onboarding, DR integration, optimiser tuning, 30-day performance verification | AC-10, AC-18, AC-01 (30-day), AC-07 (30-day); programme enrolment confirmed |
| Operation | 14 onward | Normal operation, annual hazard log review, availability measurement | AC-19 at month 26 |

**Dependencies.** Phase 1 energisation depends on AHJ approval (OI-01) and completion of FAT. Phase 2 depends on OI-04. Phase 3 depends on OI-02 and OI-03. The BESS supplier's commissioning team is booked for Phase 1 months 6 and 7 and Phase 2 month 9.

**Key risks.**

| Risk | Mitigation |
|---|---|
| Supply delays for MV switchgear section | Order placed at DR-2; factory witness test scheduled |
| Utility study timelines | Early engagement; settings file requested at DR-2 |
| Weekend outage window constraints (C-01) | Integration steps rehearsed on reference system; outage plans reviewed by Operations |
| FCS integration complexity | OI-04 tracked; manual load-shed fallback procedure |

---

## Appendix A. Abbreviations

AHJ: authority having jurisdiction. ATS: automatic transfer switch. CSIP: Common Smart Inverter Profile. DERMS: distributed energy resource management system. EFC: equivalent full cycle. FAT/SAT: factory/site acceptance test. GOOSE: Generic Object Oriented Substation Event. HMI: human-machine interface. LFL: lower flammable limit. LOTO: lockout/tagout. MID: microgrid interconnect device. MMS: Manufacturing Message Specification. MOC: management of change. NOC: network operations centre. PRP: Parallel Redundancy Protocol. SIEM: security information and event management. SL-T: target security level. SoE: sequence of events. UPS: uninterruptible power supply.
