# Worker note: synthetic item iot_fleet (synthetic-iot-fleet-001)

Date: 2026-10-04.
Brief: the SIT planner's S4 item-authoring brief under Malcolm's word of 4 Oct 2026 22:40 ("yes" to plan D: ten documents, five of them new), with the planner's later correction (key categories from spec/taxonomy.yaml legacy synthetic labels; run the converter as a black box).
Branch `s4/item-iot-fleet` from `origin/claude/happy-darwin-d0bl94` at 5f4eeb6.
Not opened: `eval/blind/`, `docs/live_runs/`, the clinical_rpm and research_lakehouse items.

## Process notes

- The planner's correction not to read `spec/convert_answer_keys.py` arrived after this worker had already read it in full (to learn how it registers items). It was not edited.
- `eval/build_pdfs.py` and `spec/convert_answer_keys.py` list items in code. Both were run unchanged on disk through scratchpad wrappers (`author_iot/build_iot_pdfs.py`, `author_iot/convert_iot.py`) that add this item to `ITEMS` (and `NEEDS_EXTERNAL = {"F03", "F15"}`) in memory only. The registering worker must add these entries for real.
- The converter run (`--tier synthetic --verify-anchors`, venv python of the demo6 worktree with `PYTHONPATH=agent` of this worktree) printed `60 flaws converted across 4 keys; 0 key(s) failed validation`; the other three canonical keys were rewritten byte-identical (git shows no change).
- Anchor pages were taken from `sit_review_agent.ingest.pdf.ingest` (exact, unique match for all 15).
- F03's external fact was checked on 2026-10-04 against https://docs.aws.amazon.com/general/latest/gr/iot-core.html ("Maximum MQTT payload size: 128 Kilobytes, Adjustable: No; AWS IoT Core rejects publish and connect requests larger than this size").
- `scripts/leakage_grep.py`: with this item present it first reported `D-03`, `P-04`, `Prometheus` and `OpenTelemetry` from this item; the item's decision and backlog IDs were renamed to `DEC-nn` and `PB-nn` and the two product names removed, after which only `'never leave' (tfidf; from eval/synthetic/payments_orchestration)` remains unresolved. Without this item the script prints PASS, so the extra item shifts the TF-IDF ranking of a generic payments phrase; it needs an allow-list entry when items are registered.
- Tests: no test enumerates `eval/synthetic/*` (grep of tests/ for synthetic, glob and iterdir); `tests/test_prompts.py::test_no_eval_leakage` uses a fixed word list. No test was run.

## Word counts (wc -w)

        8939 design_v1.md
        9481 design_v2.md
       18420 total

## No-label scan

    $ grep -ciE '\bF[0-9]{2}\b|flaw|planted|intentional|deliberate|bug|TODO|FIXME|incorrect|mistake|wrong|regression|known issue|answer key' design_v1.md design_v2.md
    design_v1.md:0
    design_v2.md:0

Em dash count (grep -c of U+2014) in both designs, the key, the canonical key and the README: 0 each.

## Per-flaw carrying sentences (v1) and their v2 state

Fixed in v2: F02, F03, F04, F06, F08, F10, F12. Unchanged: F01, F05, F07, F09, F11, F13, F14. New in v2: F15 (from the F03 change).

### F01

- v1: Before switching slots, the bootloader computes the SHA-256 digest of the downloaded image and compares it with the digest in the job document, and a match proves that the image is the authentic release built by the firmware pipeline.
- v2: Before switching slots, the bootloader computes the SHA-256 digest of the downloaded image and compares it with the digest in the job document, and a match proves that the image is the authentic release built by the firmware pipeline.

### F02

- v1: The truck gateway executes IMMOBILISE as soon as it receives the command, opening the fuel-pump relay so that the engine stops and the truck cannot be driven further.
- v2: The truck gateway never stops a running engine: on receiving IMMOBILISE it arms the immobiliser and opens the fuel-pump relay only once CAN speed has been 0 for at least 60 seconds and the ignition is off, so that the truck cannot be restarted.

### F03

- v1: The reefer gateway packs the whole buffered backlog into one gzip-compressed MQTT message, typically about 150 KB after a full day without coverage and at most about 420 KB for a full 72-hour buffer, which is within the 512 KB maximum MQTT payload size that AWS IoT Core accepts.
- v2: Each chunk is gzip-compressed to about 36 KB, well under the 128 KB maximum MQTT payload size of AWS IoT Core, so a full 72-hour buffer goes up in 12 chunks.

### F04

- v1: Where a probe is found faulty, a quality officer corrects the affected readings by updating them in place in the `cold_chain_reading` table, entering the reason in the `correction_note` column and their user ID in `corrected_by`.
- v2: Where a probe is found faulty, a quality officer records a correction as a new row in the `cold_chain_correction` table that references the original reading and gives the corrected value, the reason, the officer and the time; a second quality officer approves it.

### F05

- v1: Expired positions are removed by a nightly job at 02:00 MYT that runs a single `DELETE FROM vehicle_position WHERE device_ts < now() - interval '13 months'` statement on the writer.
- v2: Expired positions are removed by a nightly job at 02:00 MYT that runs a single `DELETE FROM vehicle_position WHERE device_ts < now() - interval '13 months'` statement on the writer.

### F06

- v1: The service does not commit Kafka offsets; on start it joins its partitions at the latest offset, which avoids replaying old readings and sending duplicate alerts after a deployment.
- v2: The service commits offsets only after the state for the processed readings has been checkpointed.

### F07

- v1: A consignee tracking link is an unauthenticated URL carrying a random 128-bit token, it stays valid for 30 days from dispatch, and it shows the vehicle's live position and estimated arrival on a map.
- v2: A consignee tracking link is an unauthenticated URL carrying a random 128-bit token, it stays valid for 30 days from dispatch, and it shows the vehicle's live position and estimated arrival on a map.

### F08

- v1: Every gateway's IoT policy allows `iot:Connect` with its own client ID, `iot:Publish` on `rimbun/v1/*/telemetry` and `rimbun/v1/*/events`, and `iot:Subscribe` and `iot:Receive` on `rimbun/v1/*/cmd`.
- v2: Every gateway's IoT policy allows `iot:Connect` only with a client ID equal to its thing name, and uses the `${iot:Connection.Thing.ThingName}` policy variable so that a gateway may publish only on `rimbun/v1/${iot:Connection.Thing.ThingName}/telemetry` and `.../events`, and subscribe and receive only on its own `.../cmd` topic.

### F09

- v1: Excursion alerts go by push notification to the console of the dispatcher assigned to the trip and by SMS to the driver's phone through Amazon SNS.
- v2: Excursion alerts go by push notification to the console of the dispatcher assigned to the trip and by SMS to the driver's phone through Amazon SNS.

### F10

- v1: At 350 bytes per 1 Hz frame and an average of 11 driving hours a day, the driving stream comes to about 28 MB per truck per month.
- v2: At 350 bytes per 1 Hz frame and an average of 11 driving hours a day, the driving stream comes to about 416 MB per truck per month (350 B × 3,600 s × 11 h × 30 days).

### F11

- v1: | Speeding | Travelling above the speed limit for more than 10 consecutive seconds |
- v2: | Speeding | Travelling above the speed limit for more than 10 consecutive seconds |

### F12

- v1: | NFR-4 | In UAT, run the device simulator with 500 simulated vehicles sending positions every 10 seconds and confirm that all simulated vehicles appear on the console map.
- v2: | NFR-4 | Over the 3-month pilot, a console probe records every 10 seconds, for every moving pilot vehicle, the age of the position shown (probe time minus `device_ts`); the 99th percentile is at most 30 seconds in each market.

### F13

- v1: | DEC-06 | GW-400 gateways with LTE-M and LTE Cat 1 only (no 2G or 3G fallback); purchase order for 9,000 units placed in Phase 1 | 2G and 3G networks are being switched off in all four markets; one hardware platform for both variants |
- v2: | DEC-06 | GW-400 gateways with LTE-M and LTE Cat 1 only (no 2G or 3G fallback); purchase order for 9,000 units placed in Phase 1 | 2G and 3G networks are being switched off in all four markets; one hardware platform for both variants |

### F14

- v1: | Daily driver scores | 00:30 MYT (UTC+8) every day, all markets | Compute the daily score for every driver for the driving day just ended |
- v2: | Daily driver scores | 00:30 MYT (UTC+8) every day, all markets | Compute the daily score for every driver for the driving day just ended |

### F15

- v1: (not present in v1; introduced in v2)
- v2: Backfill chunks are published at QoS 0, and the gateway marks a chunk's readings as delivered as soon as the chunk has been written to the socket, which keeps backfill short on weak links and saves the PUBACK traffic.

## Cold read

Date: 2026-10-04. A fresh-context reviewer read `design_v1.md` cold, listed every problem it saw, and only then opened the key.
Not opened: `eval/blind/`, `docs/live_runs/`, the other synthetic items, and the source of `spec/convert_answer_keys.py` and `eval/build_pdfs.py`.

### Flaws found cold

- Found from the document alone: F01, F02, F04, F05, F06, F07, F08, F09, F10, F12, F13, F14.
- F03 was found, but only with outside knowledge (the 128 KB AWS IoT Core payload limit); this is the item's planned external fact, so it stays as written.
- F14 needs the general knowledge that Thailand and Indonesia are on UTC+7; the document gives MYT as UTC+8 and names the depots, which is enough for a careful reader.
- Missed cold: F11 (the undefined "speed limit" in the speeding rule). It is plainly findable (PB-01 even shows that heavy-vehicle limit data is still pending); the miss was the reader's, not the item's. No wording change.

### Problems found in the sound sections (each would have made a correct finding a "key error")

1. Section 9 and Section 20.1: the unique key `(device_id, boot_id, seq)` was declared on tables partitioned by month on `device_ts`; PostgreSQL requires the partition key in every unique key of a partitioned table, so the stated deduplication could not be built. The key now includes `device_ts` (which a resend carries unchanged) in Section 9 and on all four tables of Section 20.1.
2. Section 9: in-memory consumers ignored anything at or below a high-water mark of `seq`, which drops backfilled readings that arrive after newer live ones (Section 10 sends both at once), contradicting the retrospective evaluation of backfill in Section 16.2. Now they keep a 72-hour bitmap of seen sequence numbers, rebuilt from the store on assignment, and drop only a number already seen.
3. Section 16.2: the range rule used only the mean of the four probes, so one probe out of range (a warm spot) was averaged away, with the heat rule firing only at H + 10 °C. Rule 1 now also fires on any single load-space probe, an excursion ends only when the mean and every probe are back in range, and a minute with no probe counts toward the data-gap rule.
4. Section 8: the even-load reason ("every device of a type reports at the same rate") was false (trucks report every 10 s, 30 s or 15 min by state), and the capacity test "confirms with a factor of four headroom" did not match Section 28 (1,800 messages per second, not yet run). Now: about a hundred or more devices per partition average out, and the NFR-11 load test is to confirm.
5. Section 12 and Section 8: the geofence service read only truck positions, and no topic carried trailer positions or trailer geofence events to the excursion service, so the door allowance of Section 16.2 rule 4 could not be evaluated. The geofence service now reads trailer positions from `coldchain.v1` and also writes trailer events there; the `coldchain.v1` row of Section 8 lists both.
6. Section 15: deltas are built against each of the two previous releases, yet a gateway "two releases behind" was said to have no delta. Now "three or more releases behind".

All six edits are identical in v1 and v2, so `v2_changes`, the v2 change list and `v2_changed_sections` are unaffected. The key's `why_sound` texts for Sections 8, 9, 12, 15 and 16 and the Section 9 trap were updated to match.

### Other fixes

7. Name: "FleetSense" is a real telematics product name (Telkomsel in Indonesia, and companies in the UK and South Africa). The platform is renamed "ArusFleet" (no match found) in both designs, the key, the README and the two bucket names. "Rimbun Logistics" and "Halcyon Telematics" have no exact real match.
8. F03 source: the key's quoted AWS wording was a paraphrase. Re-fetched https://docs.aws.amazon.com/general/latest/gr/iot-core.html on 2026-10-04: row "MQTT payload size", "The payload for every publish request can be no larger than 128 KB. AWS IoT Core rejects publish and connect requests larger than this size.", value 128 Kilobytes, Adjustable No. F03's `distractor_notes` and `external_fact` now quote it verbatim. (The same page lists 100 publish requests per second per connection, not adjustable; no claim in the item exceeds it.)

### Key consistency checked

- Severity and category of F01 to F15 match their substance; F02 as a failure mode (unsafe behaviour of the mechanism) is defensible, though it also reads as a P4 contradiction.
- Every number in the key was recomputed: F03 about 20 hours to 128 KB, F05 about 12 billion rows, F10 416 MB per truck, overage about USD 33,700 and total about USD 113,000, F14 00:30 MYT is 23:30 in UTC+7, v2 cost USD 88,894 with 6% headroom, F15 360 readings per chunk about 36 KB.
- `flaw_counts` match (4 / 6 / 4; 3 / 3 / 2 / 2 / 1 / 1 / 1 / 1). `v2_changes` match the diff line by line: the seven fixed flaws are gone in v2, the seven unchanged ones keep the same sentence, and F15 appears only in v2 Section 10, carried by the backfill change. `expected_v2_open_flaws` is right. No `distractor_notes` leak into the documents.

### Checks after the edits

- PDFs rebuilt through `coldread_iot/build_iot_pdfs.py`: `design_v1.pdf` 17 pages, `design_v2.pdf` 18 pages, all probe checks passed. The worktree has no `.venv`, so the venv of the `item-ledger` worktree (which has `markdown`) was used with `PYTHONPATH=agent` of this worktree.
- All 15 anchor quotes are exact and unique on their recorded pages (no page moved).
- Canonical key through `coldread_iot/convert_iot.py --tier synthetic --verify-anchors`: `60 flaws converted across 4 keys; 0 key(s) failed validation`; the other three canonical keys are unchanged.
- No-label scan: `design_v1.md:0`, `design_v2.md:0`. Em dash count 0 in both designs, both keys, the README and this note.
