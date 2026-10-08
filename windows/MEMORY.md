# Windows memory measurements

`measure-desktop.py` and `measure-agent.py` record distinct native counters:

| JSON field | Meaning |
| --- | --- |
| `working_set_mib` | Resident pages, including pages shareable with other processes |
| `private_commit_mib` | Private committed address space; some pages may not be resident |
| `private_mib` | Retained compatibility alias for `private_commit_mib` |
| `private_working_set_mib` | Resident private pages, when Windows provides this counter |
| `shared_commit_mib` | Shared committed memory, when Windows provides this counter |

The reader uses [PROCESS_MEMORY_COUNTERS_EX2](https://learn.microsoft.com/windows/win32/api/psapi/ns-psapi-process_memory_counters_ex2).
Older systems that provide only the EX prefix return `null` for the two extra
counters and identify the format in `memory_counter_format`. An access failure
fails the sample instead of reporting zero. These fields neither measure GPU
memory nor deduplicate shared pages across a process family.

Run `python windows/test-process-memory.py` from PowerShell to test an owned
16 MiB allocation and its release, invalid handles and older counter formats.
It opens no window and changes no process working-set limit. Linux runs the
structure checks and explicitly skips the native Windows cases.

The counters distinguish a resident-memory increase from private commit in
future recordings. They do not explain the previously observed long-run
resident-memory outlier by themselves. Whole-Marea sustained measurements and
their rendering/input checks remain necessary; no RAM reduction is claimed by
this diagnostic change.

## Repeatable renderer sample on disposable CI

The desktop-profile workflow accepts `measure_resources: true`. After the nine
native UI states it records the owned renderer's memory, CPU time, handles and
GDI/USER counts through six long-conversation/closed cycles, then captures the
control center again. `resources.json` retains one-second samples, each interval
and the change between the settled first/last closed states. CPU percentages
use one core; values over 100% are valid for a multithreaded renderer. Unknown
resident counters remain null, and a failed read aborts the measurement.

This fixture renders the generated Marea scene, with isolated Luau state and no
SDK, devices, account or physical input. It cannot establish sustained whole-app
RAM, physical-display FPS or GPU memory use. CI's adapter and rendering mode
must be considered when comparing runs. There is no arbitrary memory threshold
that turns these samples into a performance pass. The normal profile check
does not enable the extra cycles. Local execution of the visible fixture is
refused by the existing disposable-runner guard.

Each interval also requests the engine's existing `probe start` / `probe report`
and saves `renderer-LABEL.md`. These reports separate scene evaluation,
composition, painting and waiting, and identify the adapter. Their small,
bounded measurement buffers and timing overhead are part of that instrumented
run. Compare it separately from an uninstrumented performance baseline.

The [first six-cycle recording](https://github.com/SamuelHinestrosa/marea-plm/actions/runs/37606900754)
(Marea `fdd8b543`, engine `2e64d079`) collected 94 samples and ten inspected UI
images on Windows Server 2022's **Microsoft Basic Render Driver (Dx12)**.
Between the settled first/last closed samples, private commit changed from
233.477 to 234.492 MiB; resident working set changed from 170.617 to 126.035 MiB.
GDI/USER objects stayed at 8/15. Handles increased from 432 to 461, staying
between 460 and 463 after the first conversation cycle. This short sample does
not demonstrate a long-run leak or rule one out.

Conversation intervals consumed 367–372% of one CPU core; closed intervals
consumed 66–145%. This software-rendered run is not a hardware-GPU performance
result, and the observed resident-memory decline is not an optimization gain.
The [instrumented follow-up](https://github.com/SamuelHinestrosa/marea-plm/actions/runs/37608860736)
(Marea `98fd4fa3`, engine `49150679`) also passed Windows/Linux and retained
ten inspected PNGs, 94 resource samples and fourteen renderer reports. During
conversation intervals, mean painting costs 472–483 ms per round, versus
0.43–0.57 ms for rules and 0.88–0.99 ms for composition. Median frame times are
474–482 ms on the software adapter. Closed intervals have a 16.6 ms median,
mostly waiting, with occasional expensive repaints. Private commit changed
234.457→234.207 MiB between settled closed states; GDI/USER stayed at 8/15.
These runs contain no SDK, hardware services, account or physical input.

The [same-run retained comparison](https://github.com/SamuelHinestrosa/marea-plm/actions/runs/37613571984)
passed Windows/Linux at Marea `3af26181` / engine `d64e4d23`. Full repaint,
forced retention and full repaint used the same binary, scene and software
runner. Thirty PNGs, 282 resource samples and forty-two reports were inspected.

| Median across measured intervals | Full before | Retained | Full after |
| --- | ---: | ---: | ---: |
| Collected Marea CPU (% of one core) | 19.060 | 6.718 | 18.904 |
| Collected Marea paint (ms/round) | 0.605 | 0.150 | 0.530 |
| Conversation paint (ms/round) | 231.395 | 228.270 | 232.450 |
| Conversation CPU (% of one core) | 384.831 | 385.654 | 386.232 |
| Conversation working set (MiB) | 179.734 | 180.409 | 177.166 |
| Conversation private commit (MiB) | 237.430 | 235.828 | 226.240 |

The idle CPU saving supports the engine's software-adapter default. Conversation
painting improves only 1.35–1.80%, and no RAM reduction is established. Private
commit is not resident memory. These are software-renderer fixtures, not live
SDK, device/account, physical-GPU or whole-product measurements. Physical GPU
defaults stay unchanged; retained texture requests share a 32 MiB budget.

The workflow uses `retained_mode`: `auto` (default), `on` or `off`. Auto exercises
the normal renderer policy instead of silently forcing it off. Policy/adapter
and allocation traces must agree with the request; an ignored option cannot
pass as a successful comparison. With `measure_resources` and auto/on, two
full-repaint references bracket the measured mode on the same runner. Their
images and reports are in `marea-native-rendering-references`; the measured
mode is in `marea-native-profile-ui`. All three use the same timing diagnostics.
The initial controls capture waits for visible title glyphs, because populated
scene facts alone do not prove that asynchronous font loading has finished.

## SDK distribution size and initial preparation

Both Windows installers omit dependency type declarations (`.d.ts`, `.d.mts`,
`.d.cts`) and compiler source maps. Executable JavaScript and TypeScript,
arbitrary `.map` assets, prompts, manifests, native modules and license/notice
files remain. The source checkout and its development dependencies are unchanged.
The distribution therefore does not include SDK source-map debugging metadata.

For the pinned SDK 0.84.4 / Node 22.23.3 bundle, this removes 7,263 files and
50,762,864 uncompressed bytes (48.4 MiB). An owned, uninstalled comparison on
Windows on 2026-10-07 used identical host/worker/runtime bytes and fresh
validation profiles. Initial signed-out readiness was 90.953 s with the full
inventory and 45.531 s with the smaller inventory; the permission trace located
most of that cost in checking the package paths. The second launch in each
package was 1.625 s and 1.750 s respectively. These are individual local samples,
not a general startup-speed guarantee. Installation normally prepares package
permissions before interactive use.

Both SDK variants reached the real signed-out protocol state, exited their
owned Node child and removed their validation profile. In the two five-second
idle samples per variant, private resident memory remained around 65–67 MiB
and the process reported 114 handles. This packaging change reduces disk size
and initial preparation work; no steady-state RAM improvement is claimed.
Signed-in model flows and whole-Marea sustained measurements remain separate.

## Idle conversation repaint

The Windows profile hides `chat_tide` when `chat.stir <= 0.001`, matching the
shader's transparent early return. Otherwise its time dependency makes the
entire panel repaint even while the conversation is idle. The original
working/approval animation and its fade remain enabled above that threshold.
Upstream Linux scene files are unchanged.

With `measure_resources`, the profile workflow's `performance_comparison:
idle-chat` brackets the generated profile with two references that omit only
this visibility guard. All three use the same engine, runner, retention mode,
fixture data and sampling sequence. Reports identify the baseline explicitly;
working and resting chat screenshots are also retained.

The [paired native run](https://github.com/SamuelHinestrosa/marea-plm/actions/runs/37635871685)
passed Windows/Linux at Marea `3e736149` / engine `a4b5b504`. The three runs used
one binary and auto retention on Microsoft Basic Render Driver. The generated
scenes differ only in the visibility guard. Forty-two renderer reports and 282
resource samples were checked; all 36 PNG checksums were verified. Nine PNGs
covering chat, its working/resting states and final controls were inspected.

| Median across intervals | Reference before | Guard enabled | Reference after |
| --- | ---: | ---: | ---: |
| Conversation paint (ms/round) | 483.875 | 154.385 | 472.655 |
| Conversation CPU (% of one core) | 374.362 | 371.175 | 371.890 |
| Conversation working set (MiB) | 171.861 | 178.051 | 176.440 |

This improves paint time in the later cycles, not consistently from opening:
the six optimized intervals were 456.47, 460.54, 171.86, 136.91, 115.01 and 47.99
ms/round. CPU is nearly unchanged and no RAM saving is established. This is a
software-adapter fixture, not physical-GPU, authenticated-chat or steady-state
latency acceptance. Reinspection of the earlier and final resting references
shows readable messages 8–12, including accented Spanish and Japanese. All five
text blocks have a best vertical offset of about one pixel; this pair does not
establish the previously reported clipped-text defect. Animation phase is only
a hypothesis because capture pose was not recorded. The optimized and final
reference chat-body pixels match exactly. Broader text/transition validation
and the remaining slow early cycles are still open.
