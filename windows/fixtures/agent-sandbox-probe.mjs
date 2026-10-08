import * as fs from "node:fs";
import { dirname, join } from "node:path";
import { spawnSync } from "node:child_process";
import { stateImage } from "./state-image.mjs";
console.error("probe: runtime loaded");
const request = JSON.parse(fs.readFileSync(0, "utf8"));
console.error("probe: request read");
const state = process.env.MAREA_AGENT_DIR;
const ownCode = new URL(import.meta.url);
const denied = (fn) => {
    try { fn(); return false; } catch (e) { return e.code === "EACCES" || e.code === "EPERM"; }
};
const stateFile = join(state, "owned.txt");
fs.writeFileSync(stateFile, "España 日本語");
const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jZxkAAAAASUVORK5CYII=", "base64");
const imageFile = join(state, "imagen 日本語.png");
fs.writeFileSync(imageFile, png);
console.error("probe: state written");
const report = {
    pid: process.pid,
    stateWrite: fs.readFileSync(stateFile, "utf8") === "España 日本語",
    codeRead: fs.readFileSync(ownCode, "utf8").includes("stateWrite"),
    codeWriteDenied: denied(() => fs.writeFileSync(new URL("./tampered.txt", ownCode), "denied")),
    permissionCacheWriteDenied: denied(() => fs.writeFileSync(join(dirname(process.execPath), "marea-agent-access.txt"), "denied")),
    outsideReadDenied: denied(() => fs.readFileSync(request.privateFile)),
    outsideWriteDenied: denied(() => fs.writeFileSync(request.outsideWrite, "denied")),
    cleanEnvironment: !Object.hasOwn(process.env, "MAREA_TEST_SECRET") && !Object.hasOwn(process.env, "NODE_OPTIONS"),
    imageRoundTrip: stateImage(state, {path:imageFile}, 1024).data === png.toString("base64"),
    memory: process.memoryUsage(),
};
console.error("probe: file restrictions checked");
if (request.children) {
    console.error("probe: starting child restriction check");
    const child = spawnSync(process.execPath, ["-e", "process.exit(0)"], {stdio:"ignore",windowsHide:true,timeout:3000});
    report.childDenied = child.error?.code === "EPERM" || child.error?.code === "EACCES";
    report.childError = child.error?.code ?? null;
    report.childStatus = child.status;
    console.error("probe: child restriction checked");
}
if (request.network) {
    try {
        const response = await fetch("https://example.com/", {signal:AbortSignal.timeout(15000)});
        report.network = response.ok;
        await response.body?.cancel();
    } catch (e) { report.network = false; report.networkError = e.message; }
}
fs.unlinkSync(stateFile);
fs.unlinkSync(imageFile);
console.log(JSON.stringify(report));
if (request.hold) setInterval(() => {}, 1000);
