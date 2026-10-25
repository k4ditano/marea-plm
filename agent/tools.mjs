//  What Marea's AI can ask for. Each tool only PROPOSES: the worker hands the
//  proposal to Marea's logic, which shows it to the user when it has to,
//  does it, and answers. The model never touches the machine.
//
//  `looks`: it changes nothing (listing, looking). Marea does those without
//  asking, and they do not count against the actions a turn may take.
//  `memory`: her own memory, kept by Marea in her folder. Never a card: what
//  she keeps is shown in the thread as she keeps it, and the user can make
//  her forget it in Settings.
//  `why`: every action that changes something says what for, in the user's
//  language; that is what the user reads on the card before allowing it.

import { Type } from "typebox";

//  A window, as desktop_windows names it: its process (4521), or one of a
//  program's several windows (4521.3).
const pid = Type.Union([Type.Integer(), Type.String({ pattern: "^[0-9]+(\\.[0-9]+)?$" })], { description: "The window, as desktop_windows names it: 4521, or 4521.3 for one of a program's several windows" });
//  A terminal's shell too: 4521:2.
const shellPid = Type.String({ pattern: "^[0-9]+(\\.[0-9]+)?(:[A-Za-z0-9_-]{1,16})?$", description: "The terminal, as desktop_windows names it: 4521, or 4521:2 for one of its shells" });
const why = Type.String({ description: "What this is for, in a few words, in the user's language: they read it before allowing it", maxLength: 160 });
//  `final` marks the step that sends, buys or deletes: it is asked on a card,
//  unless the user gave her free hands (then nothing is).
const final = Type.Optional(Type.Boolean({ description: "true when THIS step publishes, sends, buys, pays, deletes, follows, likes, accepts terms or changes a setting (the press of the button that does it): the user is asked first, unless they gave you free hands" }));
const x = Type.Number({ description: "Pixels from the left of desktop_look's picture of that window" });
const y = Type.Number({ description: "Pixels from the top of desktop_look's picture of that window" });

export const TOOLS = [
    {
        name: "desktop_windows",
        looks: true,
        description: "Lists the windows on the user's desktop —process number (pid), program, title, box, the monitor it is seen on, whether it has the user's keyboard, and «dialog of PID» for a dialog— and the monitors. A dialog (save, open, a confirmation) is a window of its own, often of another program.",
        parameters: Type.Object({}),
    },
    {
        name: "desktop_look",
        looks: true,
        description: "A picture of one window, as it is now. Its pixels are the coordinates the other desktop tools take. If the program has a dialog open (save, open, a confirmation), the picture is the dialog, and the actions on that pid go to it. Look again after anything that changes the page: what was at a point may not be there any more.",
        parameters: Type.Object({ pid }),
    },
    //  The window's own tree (the accessibility bus): what is on it, by name,
    //  without a picture. A page that has none (a game, a canvas, a program
    //  that does not publish one) is read with desktop_look.
    {
        name: "desktop_tree",
        looks: true,
        description: "Reads a window from its accessibility tree, as text, no picture: what can be acted on (buttons, links, fields) and the headings and texts that say something, one a line as «@24 button \"Save\" 120,40 80x24 focusable», under what they are in. The @24 names the element for desktop_press and desktop_fill; the numbers are in the same pixels as desktop_look. It is faster and surer than a picture: start here. A terminal window gives its screen's lines. «within» reads one part (an element and what it holds), «role» only the elements of one kind, «since» what changed since your last read. A page with no tree (a game, a canvas) shows only its frame: use desktop_look then.",
        parameters: Type.Object({
            pid,
            within: Type.Optional(Type.String({ pattern: "^@[0-9]+$", description: "One part: that element and what it holds, as @24" })),
            role: Type.Optional(Type.String({ pattern: "^[a-z_]{2,24}$", description: "Only the elements of this role: button, link, entry, heading, tree_item…" })),
            since: Type.Optional(Type.Boolean({ description: "Only what changed since your last read of this window" })),
            max: Type.Optional(Type.Integer({ minimum: 10, maximum: 400, description: "At most this many lines" })),
        }),
    },
    {
        name: "desktop_find",
        looks: true,
        description: "Finds what says a text in its name or content in a window's tree, under what it is in, with its @number. Cheaper than reading the whole tree when you know what you are after.",
        parameters: Type.Object({ pid, text: Type.String({ maxLength: 200 }) }),
    },
    {
        name: "desktop_press",
        description: "Presses an element of a window's tree: a button, a link, a menu item, a tab. By its @number from desktop_tree or desktop_find, or by its whole name (text; when several have it, the first). It scrolls it into view and answers what changed after, so you rarely need to look again. «action» 1, 2… is another action of it (its default is 0); with the user's pace on instant it does not even move your pointer.",
        parameters: Type.Object({
            pid,
            element: Type.Optional(Type.String({ pattern: "^@[0-9]+$", description: "The element, as @24" })),
            text: Type.Optional(Type.String({ maxLength: 200, description: "Instead of element: its whole name" })),
            button: Type.Optional(Type.Union([Type.Literal("right"), Type.Literal("middle")], { description: "A right click (a menu) or a middle one; left by default" })),
            why, final,
        }),
    },
    {
        name: "desktop_fill",
        description: "Types into a field of a window's tree by its @number (it gets the focus first). «replace»: its whole text is set at once, what was there goes. Without an element, it types where the caret is. Any text: accents, ñ and emoji too. Not for passwords (desktop_type_secret).",
        parameters: Type.Object({
            pid,
            element: Type.Optional(Type.String({ pattern: "^@[0-9]+$", description: "The field, as @24" })),
            text: Type.String({ maxLength: 4000 }),
            replace: Type.Optional(Type.Boolean({ description: "Set the whole text instead of typing at the caret" })),
            why, final,
        }),
    },
    {
        name: "desktop_steps",
        description: "Several steps in one window, in order, in one go (it stops at the first that fails and says which). Each is a line like `press @12`, `press --text \"Save\"`, `type @12 --set -- \"ana\"`, `key tab`, `hotkey ctrl+l`, `wait has --text \"Done\" 5s`. Use it for a sequence you are sure of, a form for instance: one call instead of ten. Not for what must be checked between steps.",
        parameters: Type.Object({
            pid,
            steps: Type.Array(Type.String({ maxLength: 400, pattern: "^[^\\n]+$" }), { minItems: 1, maxItems: 25 }),
            why, final,
        }),
    },
    {
        name: "desktop_wait",
        looks: true,
        description: "Waits (up to 30 s) until a window shows or stops showing a text, changes, settles, or opens a dialog, and answers when it does: for a page that loads, a download, a build.",
        parameters: Type.Object({
            pid,
            until: Type.Union(["has", "gone", "changed", "settled", "dialog"].map((t) => Type.Literal(t)), { description: "has / gone: some text is shown / no longer; changed: anything; settled: nothing moves for a moment; dialog: it opens one" }),
            text: Type.Optional(Type.String({ maxLength: 200, description: "For has and gone" })),
            seconds: Type.Optional(Type.Integer({ minimum: 1, maximum: 30 })),
        }),
    },
    {
        name: "terminal_wait",
        looks: true,
        description: "Waits until what runs in a terminal window finishes, and brings back what it printed. For an AI agent there (Claude Code, Codex…) it waits until it is done and ready again; for a command or any other program, until the terminal is quiet. Up to «seconds» (60 by default, 600 at most); if it is not done by then it says so and what is on the screen, and you can wait again. Use it after you type a task into a terminal, instead of ending your turn: the user expects the result, not «I sent it».",
        parameters: Type.Object({
            pid: shellPid,
            seconds: Type.Optional(Type.Integer({ minimum: 5, maximum: 600 })),
        }),
    },
    {
        name: "desktop_run",
        description: "Types a command in a terminal window's shell, presses Enter, waits until the shell is ready again (up to «seconds», 30 by default) and answers with what it printed. The window must be a terminal (desktop_windows says «does text»); pid can be PID:SHELL when it has several shells.",
        parameters: Type.Object({
            pid: shellPid,
            command: Type.String({ maxLength: 2000 }),
            seconds: Type.Optional(Type.Integer({ minimum: 1, maximum: 300 })),
            why, final,
        }),
    },
    {
        name: "desktop_click",
        description: "Clicks in a window with your own pointer (not the user's). Look first: the point must be on what you mean to press.",
        parameters: Type.Object({
            pid, x, y,
            button: Type.Optional(Type.Union([Type.Literal("left"), Type.Literal("right"), Type.Literal("middle")])),
            count: Type.Optional(Type.Integer({ minimum: 1, maximum: 3, description: "2 for a double click" })),
            why, final,
        }),
    },
    {
        name: "desktop_type",
        description: "Types text into a window with your own keyboard, where its caret is (click the field first). Any text: accents, ñ and emoji too.",
        parameters: Type.Object({ pid, text: Type.String({ maxLength: 4000 }), why, final }),
    },
    {
        name: "desktop_type_secret",
        description: "Types a password the user saved in Marea, by the name they gave it, into the field that has the caret (click it first). You never see the password: Marea types it. Only when the browser has no saved password to pick for that page; the names there are come with what you remember.",
        parameters: Type.Object({ pid, name: Type.String({ maxLength: 60, description: "The name it was saved under" }), why, final }),
    },
    {
        name: "secret_ask",
        description: "Asks the user to save a password in Marea under a name, in a field of Marea's own: the place where they write to you turns into it, what they type goes to their system keyring, and you never see it. Use it when a page needs a password that neither the browser nor Marea has, and when the user offers to give you one (never take it in the chat). It answers when they saved it or said no; then desktop_type_secret types it. Not in a «[Task]»: nobody is there to answer.",
        parameters: Type.Object({
            name: Type.String({ maxLength: 60, description: "What it will be called, short: the site or the account (Factorial, the bank)" }),
            why,
        }),
    },
    {
        name: "desktop_key",
        description: "Presses one key in a window: enter, tab, escape, backspace, space, up, down, left, right, delete, home, end, pageup, pagedown, f1…f12.",
        parameters: Type.Object({ pid, key: Type.String({ maxLength: 16 }), why, final }),
    },
    {
        name: "desktop_hotkey",
        description: "A key with modifiers in a window: ctrl+l (a browser's address bar), ctrl+t, ctrl+w, ctrl+f, alt+left…",
        parameters: Type.Object({ pid, keys: Type.String({ maxLength: 32, description: "Like ctrl+shift+t" }), why, final }),
    },
    {
        name: "desktop_scroll",
        description: "Scrolls a window with the wheel, at a point over what scrolls (the page, not a sidebar).",
        parameters: Type.Object({
            pid, x, y,
            direction: Type.Union([Type.Literal("up"), Type.Literal("down"), Type.Literal("left"), Type.Literal("right")]),
            steps: Type.Optional(Type.Integer({ minimum: 1, maximum: 30 })),
            why, final,
        }),
    },
    {
        name: "desktop_drag",
        description: "Presses at one point of a window, glides to another and lets go.",
        parameters: Type.Object({ pid, x1: x, y1: y, x2: x, y2: y, why, final }),
    },
    {
        name: "desktop_focus",
        description: "Gives a window the user's keyboard and shows its workspace. It moves what the user sees: only when a window you need is not seen, or other windows cover it (desktop_look shows them over it).",
        parameters: Type.Object({ pid, why, final }),
    },
    {
        name: "desktop_to_monitor",
        description: "Moves a window to another monitor (desktop_windows says where each one is, and lists the monitors by number). For when the user names one: «on the other monitor».",
        parameters: Type.Object({ pid, monitor: Type.Integer({ minimum: 0, maximum: 7, description: "The monitor's number, from desktop_windows" }), why, final }),
    },
    {
        name: "open_app",
        description: "Opens a program installed on the user's computer, by its name (Firefox, Dolphin, Calculator…) or what it is (a file manager, a terminal, a browser). If none matches, it answers with the programs there are. Its window opens on the monitor you work on —one the user is not on, unless you say which—, lit first so they see it coming, and without taking their keyboard: desktop_windows to find it.",
        parameters: Type.Object({
            name: Type.String({ maxLength: 80 }),
            monitor: Type.Optional(Type.Integer({ minimum: 0, maximum: 7, description: "Which monitor, from desktop_windows, when the user names one" })),
            why, final,
        }),
    },
    // ── her memory ──
    {
        name: "memory_save",
        memory: true,
        description: "Keeps a short fact about the user for future conversations: something they told you about themselves, a lasting preference, a name, or something they asked you to remember. One fact, in a sentence, in the user's language. Not secrets, passwords, payment details or health, and not the details of the task at hand. If it corrects one you have, forget the old one too.",
        parameters: Type.Object({ text: Type.String({ maxLength: 300 }) }),
    },
    {
        name: "memory_forget",
        memory: true,
        description: "Forgets one of the facts you keep about the user, by its id (as «[f12]» in what you remember): when it is wrong, out of date, or they ask you to.",
        parameters: Type.Object({ id: Type.String({ maxLength: 16 }) }),
    },
    {
        name: "memory_recall",
        memory: true,
        looks: true,
        description: "Searches the facts you keep about the user. You see the most recent ones in every conversation; if something sounds familiar and is not there, look here before saying you do not know.",
        parameters: Type.Object({ query: Type.String({ maxLength: 120 }) }),
    },
    {
        name: "memory_learn",
        memory: true,
        description: "Writes down HOW to do something on this desktop that took you several tries, or a detail you found that no guide said, so you do not work it out from scratch again. «when» decides whether the note will be found: describe the situation it is for. Writing one with a title you already have replaces it.",
        parameters: Type.Object({
            title: Type.String({ maxLength: 80 }),
            when: Type.String({ maxLength: 200, description: "The situation it is for" }),
            how: Type.String({ maxLength: 3000, description: "The steps, short and concrete" }),
        }),
    },
    {
        name: "memory_read",
        memory: true,
        looks: true,
        description: "Reads one of your notes on how to do things, by its title. You see their titles and when they apply in every conversation; read the steps when the situation fits.",
        parameters: Type.Object({ title: Type.String({ maxLength: 80 }) }),
    },
    {
        name: "memory_search",
        memory: true,
        looks: true,
        description: "Searches everything you and the user have talked about, earlier conversations included. Use it when they take something as known —«what I told you about the workshop», «that thing we set up»— instead of saying you do not remember. It answers with the turns that match, their date and what was said just before.",
        parameters: Type.Object({ query: Type.String({ maxLength: 200, description: "What to look for, two letters or more" }) }),
    },
    // ── her tasks: what she does on her own, at a time ──
    {
        name: "task_schedule",
        tasks: true,
        description: "Keeps a task to do on her own at a time, every day or on some days: «every day at 8:00 open my bank in Zen and tell me the balance». At that time it runs as a prompt of its own, in a conversation of its own, with the desktop tools and without asking the user each step (they are probably away). Write `what` as you would want to be told it then: the program, the page, the steps, and what to report. The user confirms it before it is kept, unless they gave her free hands; then it is kept at once.",
        parameters: Type.Object({
            what: Type.String({ maxLength: 1500, description: "The task, in the user's language, complete enough to do alone" }),
            time: Type.String({ pattern: "^([01]?[0-9]|2[0-3]):[0-5][0-9]$", description: "24-hour time, as 08:00" }),
            days: Type.String({ maxLength: 40, description: "daily, weekdays, weekends, some days as mon,wed,fri, or once:YYYY-MM-DD" }),
            why,
        }),
    },
    {
        name: "task_list",
        tasks: true,
        looks: true,
        description: "The tasks she does on her own: each with its id, when, what, and how it went last time.",
        parameters: Type.Object({}),
    },
    {
        name: "task_cancel",
        tasks: true,
        description: "Removes one of her tasks, by its id (as task_list gives it), when the user asks.",
        parameters: Type.Object({ id: Type.String({ maxLength: 16 }) }),
    },
];

//  What only one of her children has (logic/kids.luau does them, host-side: no hands on the desktop). A
//  watch is something it does again every so many minutes while it lives: it is kept in memory by that
//  child's logic and ends with the child (let go, its window closing, Marea restarting): never saved, never
//  a schedule of the system. Its notes are files in one folder (Documents/Marea) that Marea's logic
//  writes, never the worker.
export const KID_ONLY_TOOLS = [
    {
        name: "watch_start",
        description: "Starts a WATCH: you do something again every so many minutes, in your window, for as long as you live. Use it when the user asks for something recurring («check this page every 10 minutes for news about X and write what you find in a file»). `what` is the instruction as you will be given it each time, complete enough to do alone (what to look at, what counts as new, where to write it); each run you keep your conversation, so you can compare with what you noticed before. A watch lives and dies with you: if the user lets you go, closes the window or restarts Marea, every watch is gone and nothing is left saved. It also ends by itself after 12 hours. At most 3 at once. After starting one, tell the user in your answer what you set up (what, how often, where you will write) and that it stops if they let you go.",
        parameters: Type.Object({
            every_minutes: Type.Integer({ minimum: 1, maximum: 1440, description: "Every how many minutes (1 to 1440)" }),
            what: Type.String({ maxLength: 1500, description: "The instruction for each run, in the user's language, complete enough to do alone" }),
            why,
        }),
    },
    {
        name: "watch_list",
        looks: true,
        description: "Your watches: each with its id, how often, what, how many times it ran and when it runs next.",
        parameters: Type.Object({}),
    },
    {
        name: "watch_stop",
        description: "Stops one of your watches, by its id (as watch_list gives it), when the user asks or it is no longer needed.",
        parameters: Type.Object({ id: Type.String({ maxLength: 16 }) }),
    },
    {
        name: "notes_write",
        description: "Keeps what you found in a note: a file in the user's Documents/Marea folder (the only place you can write). `name` is the file's name (letters, digits, spaces, dots, dashes; .md is added). mode `append` adds a dated section to the end of the file (it is made if it is not there); `replace` overwrites a file that YOU made in this life of yours. Up to 64 KB at a time. It answers with the full path: tell the user where you wrote it. When the user says «anótalo donde quieras», use `<program>-<short topic>.md`.",
        parameters: Type.Object({
            name: Type.String({ maxLength: 60, description: "File name, without a folder" }),
            text: Type.String({ maxLength: 65536, description: "What to write (markdown)" }),
            mode: Type.Union([Type.Literal("append"), Type.Literal("replace")], { description: "append (default) or replace" }),
            why,
        }),
    },
    {
        name: "notes_read",
        looks: true,
        description: "Reads a note from the user's Documents/Marea folder (up to 20 000 characters), for example to compare with what you found before.",
        parameters: Type.Object({ name: Type.String({ maxLength: 60, description: "File name, without a folder" }) }),
    },
];

//  What she has while she builds a piece of the desktop with the user
//  (BUILDER.md): a creation's own files, pleamar's checks and documents,
//  and a look at what she made. Nothing else: no hands on the desktop, no
//  memory. Every file she writes goes through Marea, who keeps the version
//  before it, checks what it asks the system for, and answers with pleamar's
//  verdict on it.
const file = Type.String({ pattern: "^[a-z0-9_-]+\\.(plm|luau|svg)$", maxLength: 40, description: "A file of the creation: scene.plm, scene.luau, another .plm or .luau beside them, icon.svg" });

export const BUILDER_TOOLS = [
    {
        name: "creation_read",
        looks: true,
        description: "Reads a file of the creation as it is now. Read before changing a file you did not write in this conversation: the user may have edited it by hand.",
        parameters: Type.Object({ file }),
    },
    {
        name: "creation_write",
        writes: true,
        description: "Writes a whole file of the creation. scene.plm is painted again at once, live, on the user's screen: write a first version early (the shape and its place), then improve it in steps. Marea keeps the version before, checks the permissions it asks for (the user is asked for anything new; dangerous commands are refused), and answers with `pleamar --check`'s verdict. While a version does not compile, the screen keeps the last good one: fix it with the error's line and column.",
        parameters: Type.Object({
            file,
            content: Type.String({ maxLength: 60000 }),
            why: Type.String({ maxLength: 160, description: "What this version changes, in a few words, in the user's language: it names the version in its history" }),
        }),
    },
    {
        name: "creation_check",
        looks: true,
        description: "Runs `pleamar --check` on the creation's scene: ok, or the first error with its line and column.",
        parameters: Type.Object({}),
    },
    {
        name: "creation_look",
        looks: true,
        description: "A picture of the creation as it is on the screen now, with a margin around it. Look after a change that matters to the eye, and compare it with what the user asked for.",
        parameters: Type.Object({}),
    },
    {
        name: "creation_name",
        looks: true,
        description: "Gives the creation its name: what the user sees at the top of the chat, and an app's name in the finder and the dock. Short, in the user's language («Notas», «Consumo IA»).",
        parameters: Type.Object({ name: Type.String({ maxLength: 40 }) }),
    },
    {
        name: "creation_key",
        description: "Gives the creation a key of its own in the window manager (pleamar-wm's keys.conf, read at once): «open» opens it (an app), «emit EVENT» or «fact NAME VALUE» tell its scene something (show or hide a panel). The user is asked first. Use it when they ask for a shortcut, or offer one for something they will open often.",
        parameters: Type.Object({
            keys: Type.String({ maxLength: 40, description: "Like Super+u or Super+Shift+n" }),
            order: Type.String({ maxLength: 100, description: "open · emit toggle · fact open true" }),
            why: Type.String({ maxLength: 160 }),
        }),
    },
    {
        name: "creation_poke",
        looks: true,
        description: "Uses the creation as the user would, to try it: «press ZONE» (a zone's name), «fact NAME VALUE», «emit EVENT», «get NAME». Answers with what changed (its facts and events). Look after it to see the result; then put it back as it was if the user should not find it changed.",
        parameters: Type.Object({ order: Type.String({ maxLength: 200, description: "press toggle · fact open true · emit refresh · get open" }) }),
    },
    {
        name: "system_run",
        looks: true,
        description: "Runs a program on the user's computer and answers with what it printed (its first 24 KB), to find things out as a developer would: where some data lives, what a program prints, what is installed, how another app gets what it shows. Reading is done at once; anything that can change the system is asked of the user first, and what is dangerous is refused. Not for the creation itself: it runs its own programs with run() in its logic, declared in permissions {}.",
        parameters: Type.Object({
            program: Type.String({ maxLength: 200, description: "The program alone, by its name (ls, find, grep, cat, node…) or its path; its arguments go in args. No shell: sh -c has to be approved by the user every time" }),
            args: Type.Optional(Type.Array(Type.String({ maxLength: 1000 }), { maxItems: 40 })),
            why: Type.String({ maxLength: 160, description: "What you want to find out, in the user's language: they read it if they are asked" }),
        }),
    },
    {
        name: "system_read",
        looks: true,
        description: "Reads a text file on the user's computer (its first 64 KB): a configuration, a script, another app's code, a data file. Files that may hold passwords or keys are asked of the user first.",
        parameters: Type.Object({
            path: Type.String({ maxLength: 500, description: "A whole path; ~ is the user's home" }),
            why: Type.String({ maxLength: 160 }),
        }),
    },
    {
        name: "pleamar_docs",
        looks: true,
        description: "pleamar's own documents. topic: reference (the whole language: every element, property, layer, gesture, service), guide, recipes (whole scenes that work), logic (the .luau), desktop (shells, apps, the window manager). With `find`, only the parts that mention it (a keyword, a property): the reference is long, ask it like that.",
        parameters: Type.Object({
            topic: Type.Union(["reference", "guide", "recipes", "logic", "desktop", "grammar"].map((t) => Type.Literal(t))),
            find: Type.Optional(Type.String({ maxLength: 60, description: "A word to find: `anchor`, `reserve`, `service audio`, `kind: window`" })),
        }),
    },
];

export function toolNamed(name) {
    return TOOLS.find((t) => t.name === name) ?? BUILDER_TOOLS.find((t) => t.name === name) ?? KID_ONLY_TOOLS.find((t) => t.name === name) ?? null;
}
