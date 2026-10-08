import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync, symlinkSync, linkSync, unlinkSync, rmSync, realpathSync } from "node:fs";
import { dirname, join } from "node:path";
import { tmpdir } from "node:os";
import { test } from "node:test";
import { stateImage } from "./state-image.mjs";

test("inline native images preserve bytes and reject oversized, ambiguous and malformed payloads", () => {
    const data = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jZxkAAAAASUVORK5CYII=";
    assert.deepEqual(stateImage("unused", {data}, 1024), {type:"image", mimeType:"image/png", data});
    assert.throws(() => stateImage("unused", {data,path:"not-read"}, 1024), /ambiguous/);
    assert.throws(() => stateImage("unused", {data}, 8), /too_big/);
    assert.throws(() => stateImage("unused", {data:data+"\n"}, 1024), /invalid_base64/);
    assert.throws(() => stateImage("unused", {data:"e30="}, 1024), /not_png/);
});

test("native state paths preserve PNG bytes and reject escapes and non-images", () => {
    const folder = mkdtempSync(join(tmpdir(), "marea imagen ñ "));
    const owned = realpathSync(folder);
    assert.equal(dirname(owned), realpathSync(tmpdir()));
    const state = join(folder, "state");
    const sibling = join(folder, "state-other");
    mkdirSync(state); mkdirSync(sibling);
    const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jZxkAAAAASUVORK5CYII=", "base64");
    const image = join(state, "captura 日本語.png");
    writeFileSync(image, png);
    const outside = join(sibling, "outside.png");
    writeFileSync(outside, png);
    try {
        assert.deepEqual(stateImage(state, {path:image}, 1024), {type:"image", mimeType:"image/png", data:png.toString("base64")});
        assert.equal(stateImage(state, null, 1024), null);
        assert.throws(() => stateImage(state, {path:outside}, 1024), /image_outside_state/);
        assert.throws(() => stateImage(state, {path:join(state, "..", "state-other", "outside.png")}, 1024), /image_outside_state/);
        symlinkSync(sibling, join(state, "linked"), process.platform === "win32" ? "junction" : "dir");
        assert.throws(() => stateImage(state, {path:join(state, "linked", "outside.png")}, 1024), /image_outside_state/);
        assert.throws(() => stateImage(state, {path:image}, 8), /image_too_big/);
        const alias = join(state, "hard-link.png");
        linkSync(outside, alias);
        assert.throws(() => stateImage(state, {path:alias}, 1024), /image_link_not_allowed/);
        unlinkSync(alias);
        writeFileSync(join(state, "not.png"), '{"credential":"fixture-only"}');
        assert.throws(() => stateImage(state, {path:join(state, "not.png")}, 1024), /image_not_png/);
        assert.throws(() => stateImage(state, {path:state}, 1024));
    } finally {
        // This entire directory was freshly created above; no user paths enter cleanup.
        rmSync(owned, {recursive:true, force:true});
    }
});
