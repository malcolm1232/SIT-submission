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
