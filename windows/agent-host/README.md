# Native Windows AI worker host (integration in progress)

This launcher replaces `agent/sandbox` for the generated Windows profile. It
requires Windows x64 and the MSVC toolchain. It does not start WSL or a shell,
and there is no unsandboxed fallback. Its intended installed layout is:

```text
bin/marea-agent.exe
bin/node.exe
app/agent/worker.mjs
app/agent/node_modules/...
```

The pinned Pi SDK is installed at packaging time with `npm ci --ignore-scripts`.
The normal state directory is `%LOCALAPPDATA%/Marea/Agent`. The dedicated test
entry point uses `--probe --state <owned bundle>/state` and is not an alternative
way to grant arbitrary directories. `--remove-profile` removes only the
AppContainer identity associated with this bundle path. It must run after the
worker exits; it does not remove the separate Marea state directory.

Setup invokes `--prepare` after copying the package. This prepares permissions
without starting the worker. `--validate-worker` runs the production entry
point under a separate `.Validation` identity and `Marea/AgentValidation`
state; the package checks redirect that state into a fresh temporary directory.
`--remove-validation-profile` cleans only that identity and its permission
cache. Both removal commands are idempotent, following the documented
[DeleteAppContainerProfile behavior](https://learn.microsoft.com/en-us/windows/win32/api/userenv/nf-userenv-deleteappcontainerprofile).

## Boundary

- A Less Privileged AppContainer (LPAC), with Internet Client and Windows'
  `registryRead` capability. Winsock needs the latter to initialize its provider
  catalogue. This is not a claim that the worker can access no system resources:
  it can access the Windows resources authorized by those capabilities and its
  own AppContainer profile.
- Read/execute access to bundled Node and agent code; read/write access to the
  dedicated state directory. Permissions are added without replacing existing
  user/system ACEs. Writable state is marked low integrity.
- ACL updates use validated handles opened without following reparse points.
  Hard links and junctions are rejected before any ACL changes. Updates do not
  recursively propagate into untrusted state. Validated code permissions are
  cached in `bin/marea-agent-access.txt`, which the worker cannot modify. The
  identity, executable and package metadata invalidate this optimization when
  the bundle moves or is replaced. State is checked on every launch.
- Clean environment, only three inherited protocol handles, detached execution
  and a private desktop that is never displayed. No change to the interactive
  desktop's ACL or active input desktop is required.
- Child-process creation is prohibited, and the launcher verifies that policy
  before resuming the worker. A kill-on-close job limits it to one process and
  512 MiB committed process memory. Node also has a 128 MiB old-space limit.
- `TokenIsAppContainer` plus positive explicit-package and negative
  ALL APPLICATION PACKAGES access checks verify the requested access semantics.
  `GetTokenInformation` class 46 returned error 87 on the tested Windows build;
  it is not used as a successful LPAC check.

`CREATE_NO_WINDOW` initially failed during `KERNELBASE` initialization when
creating the restricted worker. `DETACHED_PROCESS` avoids console creation and
uses the explicitly inherited pipes. Node's `--preserve-symlinks` options avoid
module-loader enumeration of inaccessible ancestors; the package itself is
validated before permissions are assigned. Image requests validate containment,
reject Windows reparse points and hard links, and compare file identities across
the open before performing a bounded read.

The host itself uses the Windows GUI subsystem, with explicitly redirected
protocol streams. It creates no window or console: a console-subsystem host
started with `CREATE_NO_WINDOW` still kept an extra `conhost.exe` alive for the
whole chat session (about 7.9 MiB working set in the observed native run).
Pleamar keeps its console subsystem for the engine's command-line interface.
After this change, the thirteen native boundary checks passed again. A native
UI run on DISPLAY2 completed seven 90-second samples with three real signed-out
SDK reopen/retirement cycles; all owned processes exited. This covers idle
lifecycle/resource use, not authenticated work or physical interaction.

A sharing violation while locking a sandbox path now retries for at most three
seconds. Immediate restarts exposed error 32 in Windows CI; the log did not
identify the process retaining the file. The retry retains the original access
and sharing flags, and validates links and permissions through the acquired
handle. Persistent locks stop startup with the affected path in the error;
other errors return immediately. Native regression tests reproduce temporary
and persistent contention, including denial of writes while the lock is held.
The boundary test also runs five consecutive worker restarts.

The implementation follows Microsoft's [LPAC launch contract](https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer),
[AccessCheck](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-accesscheck)
and the documented non-propagating `MAXIMUM_ALLOWED` behavior of
[SetSecurityInfo](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-setsecurityinfo).

## Reproducible checks

From the Marea repository in PowerShell:

```powershell
cargo test --locked --manifest-path windows/agent-host/Cargo.toml
cargo build --release --locked --manifest-path windows/agent-host/Cargo.toml --features test-fixtures
node --test agent/state-image.test.mjs agent/auth-interaction.test.mjs
python windows/test-agent-sandbox.py `
  --host windows/agent-host/target/release/marea-agent.exe `
  --node (Get-Command node).Source `
  --child-probe windows/agent-host/target/release/marea-agent-child-probe.exe
```

The native test creates only its own Unicode-path fixtures. It checks actual
file access/denials, PNG handling, rejection of junctions and hard links without
changing outside ACLs, clean environment, exact Windows error 367 on attempted
child creation, and worker termination when its owner exits. Add `--network`
to test HTTPS against `example.com`; CI does not require that request. The
test-only child executable is not a release dependency.

## Evidence and remaining work, October 5, 2026

Executed on native Windows: the two Rust unit tests, four Node tests, the shared
chat login lifecycle suite, and all thirteen boundary checks (including HTTPS)
pass. The real pinned SDK starts in an isolated bundle, reports `signed_out`
without reading another application's credentials, and exits on `shutdown`.
A native pleamar scene on `\\.\DISPLAY2` exercised Luau persistent stdin,
`ready`, refusal of a prompt without a model, and clean exit; its UI timer kept
running and a native first frame was recorded. This was an owned test scene,
not validation of all Marea chat/settings visuals or a model conversation.

First-launch package permission preparation is more expensive than a cached
launch. Cached SDK launches observed locally were around 4 seconds; this is not
a sustained performance benchmark. The small isolation fixture's approximately
30 MiB RSS must not be presented as the full Pi agent's memory use.

Windows now selects device-code OAuth, exposes its code in the shared chat UI
and cancels queued sign-in requests before the SDK is ready. Tests cover those
transitions without contacting an account. Actual sign-in and a model response
are still unverified. The installer and source installers now include the host,
locked SDK and dependency licenses. Signed-out SDK preflight, independent
validation/production profiles, repeat provisioning/removal and state
preservation passed on an owned package. Setup prepares permissions before
first use. A cold SDK tree took about 116 seconds to prepare, versus 4.6 seconds
on a repeated preparation; allow up to three minutes for the bounded preflight.
Set `MAREA_AGENT_TRACE=1` when diagnosing startup to print stage timings to
stderr; paths, credentials and conversations are not printed by that trace.
Positive desktop-agent input, a model conversation and broader
performance/hardware checks remain required. Six native layout states have
been reviewed with fixture data. Full Setup lifecycle passed in Windows CI
at Marea `91b6240` / pleamar `7c0edeb`; it is not graphical acceptance.
The installed package is still `0.2.15-preview.13`; this work is not installed
and is not a claim of complete parity. See [the current evidence](../AGENT.md).

Developed with Codex.

## Repeated permission setup (October 6, 2026)

The host still validates each writable object through its locked, non-reparse
handle. It now compares the complete current/requested ACL and integrity label
before writing them. Unchanged descriptors require no writes; new files or
changed access still receive the required permissions. File labels omit the
inheritance flags that Windows already discards on files. No sandbox rights are
expanded and no recursive permission operation is introduced.

Three native unit tests and the real LPAC isolation suite pass, including zero
security writes after adopting newly created state, read/write denials, child
creation denial, owner-exit cleanup and link rejection without outside ACL
changes. This run did not test network access or a signed-in model.

An alternating five-sample comparison on an owned 500-file state tree measured
median warm preparation of 0.208 s before and 0.114 s after; the latter made zero
security writes. This measures only permission setup, not UI startup, full SDK
preparation, steady-state memory, or model response time. The previously observed
cold SDK preparation/timeout remains a separate issue. Reproduce with:

```powershell
python windows/measure-agent-permissions.py --before <old-marea-agent.exe> --after <new-marea-agent.exe> --node <node.exe> --output <new-directory>
```
