# Building the desktop by asking: plan

Working name: **Arrecife** (a reef: it grows in place, live). Status: phase 1 prototype working
in the headless test copy, 2026-10-17 (see «Prototype» at the end); not in the live Marea yet.

## The idea

With pleamar, you build your whole desktop. Turn on a mode, draw where something should go (a bar
along the top, a dock, a box for an app) and a small chat opens right there. Ask for it in your own
words: «dark glass, the time and the volume», «an app for my notes, with tags». It is painted
live while it is being made, because pleamar repaints a scene every time it is saved. When you
like it, you keep it.

The target user has never programmed. Everything has to work for them: what they are asked,
what they see, and how they get back to where they were.

## What already exists

| Piece | Where | Used for |
|---|---|---|
| Live reload, and the last good scene kept while a new one does not compile | pleamar `render.rs` | seeing it grow; the AI's mistakes never blank the screen |
| `pleamar --check`, `--grammar`, `--docs …` | pleamar | the AI checks its own work and reads the reference |
| The pleamar skill (`skill/SKILL.md`, `measuring.md`) | pleamar | what the model knows about the language |
| Per-scene permissions: `permissions { run: …; services: … }`; Luau has no `io`/`os` | pleamar `logic_luau.rs`, docs 10 | the base of the safety system |
| Plugin approval (`--approve`, back to unapproved when code or permissions change) | pleamar | the pattern for approving a creation |
| Chat engine: Pi SDK worker in a sandbox; tools only propose and Marea executes | marea-plm `agent/` | the builder's brain and its tools |
| Permission cards (allow / ask / never), the Stop button | marea-plm, pleamar-wm | the same look for every question |
| Picking a region (`slurp`) | marea-plm `logic/camera.luau` | the first, rectangular «drawing» |
| `kind: window`, `kind: panel` with anchor, margin, reserve | pleamar | apps and shells |
| `autostart`, `~/.config/pleamar/shells/` | pleamar, pleamar-wm | keeping a creation |
| Layer surfaces known with their namespace | pleamar-wm `nest.rs` | knowing what is already on screen |

## What a creation is

A folder in Marea's own: `~/.local/share/pleamar/marea/creations/<id>/`. pleamar's `files` service
writes there without new permissions, and nothing outside it can be touched.

- `<id>.plm` plus `<id>.luau`: what the AI writes, which it calls scene.plm and scene.luau.
  On disk they carry the id, because pleamar names a scene's socket and its files folder after
  its file;
- `icon.svg`: apps only;
- `creation.json`, the creation's record:
  - name and kind (bar, dock, widget, app);
  - the drawn region and its monitor;
  - the approved permissions;
  - the conversation (its rows and the history handed to the model);
  - whether it is kept or thrown away;
  - what it replaced;
- `versions/<n>-<file>`: every file as each write left it. «Undo» puts the one before back.
  No git: nothing to install, and nothing to explain.

`creations/index.json` lists them, with their regions, so a drawing over one edits it.

Only Marea writes in that folder (the model only proposes), so every change goes through her checks.
Someone who knows how can edit the files by hand; the AI reads them again before each change.

## The flow

1. **Start:** a shortcut or the finder («Build», «Construir»). The screen dims slightly.
2. **Draw:** a rectangle first (`slurp`); later a free stroke on a scene of our own. The shape
   tells the kind:
   - a strip against an edge is a bar (anchor, reserve);
   - low and centred is a dock;
   - a free box is a widget, or an app if asked for one.

   The region becomes the scene's size, anchor and margin. The user does not explain any of it.
3. **Placeholder:** a scene appears at once in the drawn place: the outline filling with water
   while the AI thinks.
4. **Chat:** a bubble born from the drawing. The model gets:
   - the skill;
   - the region and the kind;
   - the creation's files;
   - its tools.
5. **Building:** the model saves early and often: the shape first, then colour, then content, then logic.
   Each save that compiles enters with a ripple. When a save does not compile, `--check`'s message
   goes back to the model and the screen keeps the last good version.
6. **Looking:** the model sees its result (a capture of the region) and compares it with the request.
7. **Ending:** three choices.
   - **Keep it:** it goes on running, and Marea starts it with her from then on (no `autostart`
     edit: it survives a missing or hand-made autostart file). An app gets its `.desktop` and icon.
   - **Another round:** the chat goes on.
   - **Throw it away:** it is closed and its folder goes to the trash.

## Editing what was made

- Draw over it again in the same mode: a drawing that covers most of a creation opens that one
  (built). Later, pointing at it (needs «what is here» from pleamar-wm), or choosing it in
  «My creations» in the finder: the chat opens with its files and its conversation.
- Every change is a version. «Undo» goes back one; the list goes back to any.
- «My creations» (in Marea's finder `OWN` list, both languages) offers edit, versions, share
  and delete.

## What is already on screen

pleamar-wm answers «what is at x, y»: a window, a layer surface (namespace, process), a part
of its own scene (the dock), or nothing. There are three cases.

1. **A creation of yours:** it is edited.
2. **pleamar's but not yours** (the wm's dock, a part of Marea): the original is never edited, because
   `pleamar-update` would overwrite it. Your piece replaces it alone: the wm scene and Marea get one
   switch per part, so the rest keeps updating.
3. **Someone else's program** (waybar, Quickshell): it can only be replaced.

**While building, the old one is only hidden.** pleamar-wm stops showing it, without closing it,
and its reserved room passes to the new one. Cancelling brings it back as it was. «Keep it» makes
it permanent:

- the old program's `autostart` line is commented out with a note, never deleted;
- a pleamar part is switched off.

«Back to the bar from before» in «My creations» undoes it. If the old program starts from
somewhere we cannot change (a systemd unit, Hyprland's `exec-once`), the user is told plainly
and it stays hidden.

## Safety: for people who do not program

Luau cannot touch files or the network by itself; only `run`, `spawn` and the services reach
the system, and only what the scene's `permissions {}` declares. Safety is built on that.

1. **Permissions read like a phone's.** A creation declares what it needs. Before it runs it,
   Marea turns that into plain words: «This bar will: see the time, the battery and the volume ·
   change the volume». Approval is bound to the permissions' hash, as with plugins.
2. **No new permission goes live unapproved.** Live reload applies a scene's new permissions
   when it is saved. So Marea's write tool reads the `permissions` block of what the model wants to
   write before writing it; anything not yet approved gets its card first, and the file is
   written only after a yes.
3. **Every program is classified by fixed rules, never by the model.**
   - **Safe, no question:** an allowlist of known read-only or harmless programs and services:
     - `date`;
     - `playerctl` and `brightnessctl`;
     - the audio, network, battery, workspaces and apps services;
     - `notify-send`;
     - `xdg-open` on the creation's own files.
   - **Dangerous, refused, with an amber card that says what it would do:**
     - deleting or overwriting (`rm`, `shred`, `dd`, `mkfs*`, `truncate`);
     - root (`sudo`, `pkexec`, `su`, `doas`);
     - permissions and ownership (`chmod`, `chown`);
     - system services (`systemctl`, `loginctl`);
     - download-and-run;
     - changing shell start files.
   - **Unknown, and every interpreter or shell** (`sh`, `bash`, `python`, `node`, `perl`, `env`,
     `xargs`, `find`…), since through them anything is possible: asked, with an explanation. The
     model may write the explanation, but the rules decide. A prompt injection cannot talk its way
     past them.
4. **Later, in the engine:** a runtime guard on `run`/`spawn` that sees the real arguments. A
   scene started as a creation would ask its guard (Marea) before running anything outside its
   safe list. This covers what a static list cannot, such as arguments built at run time or
   obfuscated ones (base64, `eval`).
5. «Yes, always» is remembered per creation and per command shape; if the command changes, it is
   asked again. Every creation's permissions can be seen and taken back in Settings.

## Freedom to find things out

The model works like a developer on their own machine. `system_run` runs a program and
`system_read` reads a file, to find where some data lives or how another app on the desktop gets
it. Then the creation's logic runs what it needs, declared in `permissions {}`.

The same fixed rules guard both:
- **Free:** known readers (`ls`, `cat`, `grep`, `find` without actions…).
- **Refused:** the dangerous ones.
- **Asked, with the whole command:** everything else.
- **Asked even to read:** anything that touches files that may hold passwords or keys.

(Abel, 2026-10-17: «la ia debe tener libertad como tienes tú cuando creas algo en el sistema».)

## The model's tools

New tools in `agent/tools.mjs`. As now, they only propose; Marea does the work.

- `creation_read(file)`: looks.
- `creation_write(file, content, why)`: Marea checks permissions (above), commits the previous
  version, writes, runs `pleamar --check` and answers with its result.
- `creation_check()`: looks.
- `creation_look()`: a capture of the region, as an image.
- `pleamar_docs(topic)`: looks; `--docs reference|guide|recipes|logic`, `--grammar`.
- `creation_icon(svg)`, `creation_finish(name, kind)`: apps.

The system prompt holds the skill, the region, the kind and the rules:

- save early, shape first;
- ask for the fewest permissions;
- prefer services to commands;
- never a shell.

## Engine work this needs

| Where | What | When |
|---|---|---|
| pleamar | `app_id:` on `surface` (today `set_app_id("pleamar")` for every window), so an app has its own icon and its windows group in the dock | apps phase |
| pleamar | runtime command guard for creations | safety phase |
| pleamar-wm | `agent what X Y`, or a scene query: what is at a point | replace phase |
| pleamar-wm | hide or show a layer surface for a while (it keeps running) | replace phase |
| wm scene, Marea | one switch per part (dock, bar…) | replace phase |
| marea-plm | a drawing scene of its own (free stroke, the water outline) | polish phase |
| pleamar | `--docs skill`, `--docs desktop`: the skill printed, for Marea to hand it to the model | done (uncommitted) |
| pleamar | a reloaded scene that does not move painted its old list, without the texts the reload brought | fixed (uncommitted) |
| pleamar | a scene that started with no logic, plugins or services never starts the ones a reload adds | fixed (uncommitted): it starts them when the reload brings them |
| pleamar | a reload with another surface size, edge, margin, room or level kept the first ones until a restart | fixed (uncommitted): changed in place on the live layer |

## Phases

1. **Prototype (shells):**
   - region by `slurp`;
   - the folder and `creation.json`;
   - the placeholder;
   - the chat in builder mode with the tools above;
   - live reload;
   - versions and undo;
   - «Keep it» / «Throw it away»;
   - the static safety rules and permission cards;
   - «My creations» in the finder to edit.

   Built and tested in the headless test copy of Marea, first with the fake engine
   (`~/.cache/pleamar-games/chatscroll/`), then with the real model. Never in his live Marea
   until it passes.
2. **Apps:** `app_id`, `.desktop`, icon, the finder and the dock.
3. **Replacing what is there:** «what is here», hiding while building, part switches, «back to before».
4. **Safety in the engine:** the runtime guard.
5. **The wm's own scene:** creations that change how windows behave or look, previewed in a
   nested session first; applied only when they work.
6. **Polish and sharing:**
   - the free-stroke drawing;
   - the kind recognised from the shape;
   - the water animation;
   - sharing a creation as a folder (#share-you-creation).

## Open questions

- Which model by default. Writing pleamar well needs a strong one; Pi can use Claude or the
  user's Codex account.
- The shortcut (Super+Shift+B?) and the name in the finder.
- Whether creations are pleamar's (`~/.config/pleamar/creations`, usable without Marea) or Marea's.

## Prototype (phase 1), 2026-10-17

Built:
- `logic/builder.luau`;
- the builder mode in `agent/worker.mjs` and `agent/tools.mjs`;
- the hooks in `logic/chat.luau`;
- the head of the chat («BUILDING · name», Undo, Throw away, Keep it);
- «Build something» in the finder;
- Spanish texts.

Tested in the screenless session with `~/.cache/pleamar-games/build/`:

- **Fake engine** (`fake.py`, `inside.sh`): every path.
  - A broken version: its error goes back to the model, and the screen keeps the last good one.
  - A good one: on the screen at once.
  - `creation_look` returns a picture.
  - `rm` is refused, with a note for the user.
  - `sh` gets a card; allowed, it is written.
  - Undo goes back one version.
  - Keep keeps it, with the conversation saved in the creation.
- **Real model** (`inside-real.sh`, his account's model):
  - asked in Spanish for «a dark glass bar with the time in the middle, the volume on the right
    and the workspaces on the left»;
  - in about 40 s it read the reference, wrote it in four versions and looked at it twice;
  - it asked only for `clock`, `audio` and `workspaces`, with no commands;
  - it answered in Spanish with what it made.

Next:
- put it in the live Marea (her launcher must put pleamar on her PATH);
- the engine fix for logic that arrives with a reload;
- undo should also give back permissions only the undone version needed;
- check a creation's permissions again when it starts, in case its files were edited by hand;
- then phase 2 (apps).

