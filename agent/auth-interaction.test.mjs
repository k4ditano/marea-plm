import assert from "node:assert/strict";
import { test } from "node:test";
import { authInteraction } from "./auth-interaction.mjs";

test("Windows selects device OAuth; Linux keeps browser OAuth", async () => {
    const prompt = {type:"select",options:[{id:"browser"},{id:"device_code"}]};
    const signal = new AbortController().signal;
    assert.equal(await authInteraction(signal, () => {}, true).prompt(prompt), "device_code");
    assert.equal(await authInteraction(signal, () => {}, false).prompt(prompt), "browser");
    await assert.rejects(authInteraction(signal, () => {}, true).prompt({type:"select",options:[{id:"browser"}]}), /login_method_unavailable/);
});

test("device codes reach the UI and arbitrary launch targets are rejected", () => {
    const events = [];
    const interaction = authInteraction(new AbortController().signal, (e) => events.push(e));
    interaction.notify({type:"device_code",verificationUri:"https://auth.openai.com/codex/device",userCode:"ABCD-EFGH"});
    assert.deepEqual(events, [{type:"login_url",url:"https://auth.openai.com/codex/device",code:"ABCD-EFGH"}]);
    for (const url of ["file:///C:/Windows/notepad.exe", "https://auth.openai.com.evil.test/", "https://user@auth.openai.com/", "http://auth.openai.com/", "https://auth.openai.com:1455/"]) {
        assert.throws(() => interaction.notify({type:"auth_url",url}), /unexpected_sign_in_url/);
    }
    assert.throws(() => interaction.notify({type:"device_code",verificationUri:"https://auth.openai.com/codex/device",userCode:"bad\ncode"}), /invalid_sign_in_code/);
});

test("manual-input waits abort from either signal, including an earlier cancellation", async () => {
    for (const which of ["session", "request", "already"]) {
        const session = new AbortController();
        const request = new AbortController();
        if (which === "already") session.abort();
        const pending = authInteraction(session.signal, () => {}).prompt({type:"input",signal:request.signal});
        if (which === "session") session.abort();
        if (which === "request") request.abort();
        await assert.rejects(pending, /cancelled/);
    }
});
