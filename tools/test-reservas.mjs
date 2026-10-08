// Entirely isolated provider files; no real credentials, network or CLI needed.
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync, rmSync, utimesSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const root = mkdtempSync(join(tmpdir(), "marea reservas ñ 世界 "));
const reader = join(dirname(fileURLToPath(import.meta.url)), "reservas");
const env = { ...process.env, HOME: root, USERPROFILE: root, PATH: "",
    CODEX_HOME: join(root, "codex data"), CLAUDE_CONFIG_DIR: join(root, "claude data"),
    LOCALAPPDATA: join(root, "local data"), APPDATA: join(root, "roaming data"),
    XDG_STATE_HOME: "", NODE_OPTIONS: "", NODE_PATH: "" };
const now = Math.floor(Date.now() / 1000);
function json(path, data) { mkdirSync(dirname(path), { recursive: true }); writeFileSync(path, JSON.stringify(data)); }
function run(args = ["--sin-red"]) {
    const result = spawnSync(process.execPath, [reader, ...args], { env, cwd: root, encoding: "utf8", timeout: 12000, windowsHide: true });
    assert.equal(result.status, 0, result.stderr || result.error?.message);
    return args.includes("--lines") ? result.stdout : JSON.parse(result.stdout);
}
function event(used, timestamp = now, extras = {}) {
    return { type: "event_msg", timestamp: new Date(timestamp * 1000).toISOString(),
        payload: { type: "token_count", rate_limits: { limit_id: "codex", plan_type: "pro",
            primary: { used_percent: used, window_minutes: 300, resets_in_seconds: null, resets_at: now + 3600, ...extras } } } };
}
try {
    assert.deepEqual(run().agentes, []);
    const sessions = join(env.CODEX_HOME, "sessions", "2026", "09", "30");
    const current = join(sessions, "rollout-current.jsonl");
    const stale = join(sessions, "rollout-stale.jsonl");
    json(current, event(27));
    json(stale, event(90, now - 7200));
    utimesSync(stale, new Date(), new Date(Date.now() + 1000));
    let codex = run().agentes.find(a => a.id === "codex");
    assert.equal(codex.limites[0].usadoPct, 27, "mtime must not override a fresher observation");
    assert.equal(codex.limites[0].renuevaEn, now + 3600, "null is not a zero-second reset");
    assert.equal(codex.observadoEn, now);
    assert.equal(codex.origen, "local");
    for (const invalid of [null, "", " ", false, -1, 101]) {
        json(current, event(invalid));
        assert.equal(run().agentes.find(a => a.id === "codex").limites[0].usadoPct, null);
    }
    json(current, event(100, now, { resets_at: now - 1 }));
    codex = run().agentes.find(a => a.id === "codex");
    assert.equal(codex.limites[0].usadoPct, 100);
    assert.equal(codex.limites[0].pendiente, true, "expiry must not refill the quota");
    const forged = event(0, now + 100); forged.type = "response_item";
    const modelBucket = event(0, now + 150); modelBucket.payload.rate_limits.limit_id = "other-model";
    writeFileSync(current, "é".repeat(200000) + "\n" + JSON.stringify(event(42)) + "\n" + JSON.stringify(forged) + "\n" + JSON.stringify(modelBucket) + '\n{"partial":');
    assert.equal(run().agentes.find(a => a.id === "codex").limites[0].usadoPct, 42);
    json(join(env.CLAUDE_CONFIG_DIR, ".claude.json"), { oauthAccount: { userRateLimitTier: "default_claude_pro" },
        cachedUsageUtilization: { fetchedAtMs: (now - 120) * 1000, utilization: { limits: [
            { kind: "session", percent: "", resets_at: new Date((now + 50) * 1000).toISOString(), is_active: true },
            { kind: "weekly_all", percent: 15, is_active: true },
        ] } } });
    let claude = run().agentes.find(a => a.id === "claude");
    assert.equal(claude.limites[0].usadoPct, null);
    assert.equal(claude.limites[1].usadoPct, 15);
    assert.equal(claude.observadoEn, now - 120);
    const state = process.platform === "win32" ? env.LOCALAPPDATA : join(root, ".local", "state");
    json(join(state, "proyecto-marea", "reservas-claude.json"), { cuando: now, uso: { limits: [
        { kind: "session", percent: 33, is_active: true },
    ] } });
    // No credentials exist, so even the cache-miss case cannot make a request.
    claude = run([]).agentes.find(a => a.id === "claude");
    assert.equal(claude.limites[0].usadoPct, 33, "use the platform's state directory");
    env.XDG_STATE_HOME = join(root, "explicit state ñ");
    json(join(env.XDG_STATE_HOME, "proyecto-marea", "reservas-claude.json"), { cuando: now + 86400, uso: { limits: [{ kind: "session", percent: 99 }] } });
    assert.equal(run([]).agentes.find(a => a.id === "claude").origen, "cache", "future cache time is not a fresh server observation");
    const lines = run(["--lines", "--sin-red"]);
    assert.match(lines, /limit\tclaude\t5 horas\t300\t\t/);
    assert.match(lines, /limit\tcodex\t5 horas\t300\t42\t/);
    console.log("PASS: isolated Windows/POSIX paths, desktop clients without PATH, null/empty quotas, reset times, stale observations and partial rollouts");
} finally {
    assert.equal(dirname(resolve(root)), resolve(tmpdir()));
    assert.ok(resolve(root).startsWith(resolve(tmpdir()) + sep));
    rmSync(root, { recursive: true, force: true });
}
