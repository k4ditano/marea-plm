import { closeSync, fstatSync, lstatSync, openSync, readSync, realpathSync } from "node:fs";
import { isAbsolute, join, relative, sep, toNamespacedPath } from "node:path";

const PNG = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
function checkedPath(state, name) {
    const windows = process.platform === "win32";
    if (!isAbsolute(state) || !isAbsolute(name)) throw new Error("image_not_absolute");
    // LPAC cannot resolve drive/ancestor metadata used by Node's realpath.
    // Its root is already canonicalized by the native host. Walk only inside
    // that root, reject junctions, and verify the opened file's identity below.
    const root = windows ? toNamespacedPath(state) : realpathSync(state);
    const path = windows ? toNamespacedPath(name) : realpathSync(name);
    const inside = relative(root, path);
    if (inside === ".." || inside.startsWith(".." + sep) || isAbsolute(inside)) {
        throw new Error("image_outside_state");
    }
    let metadata;
    if (windows) {
        let current = root;
        for (const part of ["", ...inside.split(sep).filter(Boolean)]) {
            current = join(current, part);
            metadata = lstatSync(current, {bigint:true});
            if (metadata.isSymbolicLink()) throw new Error("image_outside_state");
        }
    } else metadata = lstatSync(path, {bigint:true});
    return {path, metadata};
}

// Canonical paths handle Windows separators, drive letters and directory links.
// The OS sandbox remains the access boundary; this validates Marea's protocol.
export function stateImage(state, image, limit) {
    // Native captures travel over the existing bounded pipe. No temporary file
    // or additional filesystem grant is needed inside the Windows sandbox.
    if (image && typeof image.data === "string") {
        if (image.path !== undefined) throw new Error("image_ambiguous");
        if (image.data.length > 4 * Math.ceil(limit / 3)) throw new Error("image_too_big");
        const bytes = Buffer.from(image.data, "base64");
        if (bytes.length > limit) throw new Error("image_too_big");
        if (bytes.toString("base64") !== image.data) throw new Error("image_invalid_base64");
        if (!bytes.subarray(0, PNG.length).equals(PNG)) throw new Error("image_not_png");
        return {type: "image", data: image.data, mimeType: "image/png"};
    }
    if (!image || typeof image.path !== "string") return null;
    const {path, metadata} = checkedPath(state, image.path);
    const file = openSync(path, "r");
    try {
        const stat = fstatSync(file, {bigint:true});
        if (stat.dev !== metadata.dev || stat.ino !== metadata.ino) throw new Error("image_changed");
        if (stat.nlink !== 1n) throw new Error("image_link_not_allowed");
        if (!stat.isFile()) throw new Error("image_not_file");
        if (stat.size > limit) throw new Error("image_too_big");
        // A concurrently growing file must not turn a size check into an
        // unbounded allocation/read. Keep the opened handle through encoding.
        const bytes = Buffer.alloc(limit + 1);
        let size = 0;
        while (size < bytes.length) {
            const n = readSync(file, bytes, size, bytes.length - size, null);
            if (n === 0) break;
            size += n;
        }
        if (size > limit) throw new Error("image_too_big");
        if (!bytes.subarray(0, PNG.length).equals(PNG)) throw new Error("image_not_png");
        return { type: "image", data: bytes.subarray(0, size).toString("base64"), mimeType: "image/png" };
    } finally {
        closeSync(file);
    }
}
