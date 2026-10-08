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
const why = Type.String({ description: "What this is for, in a few words, in the user's language: they read it before allowing it", maxLength: 160 });
//  When the user lets her use the computer without asking each step, the
//  steps marked `final` still ask: that is how the line is kept.
const final = Type.Optional(Type.Boolean({ description: "true when THIS step publishes, sends, buys, pays, deletes, follows, likes, accepts terms or changes a setting (the press of the button that does it): the user is always asked first" }));
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

export function toolNamed(name) {
    return TOOLS.find((t) => t.name === name) ?? null;
}
