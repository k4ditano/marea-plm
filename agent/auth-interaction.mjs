// LPAC deliberately has no loopback exemption. Device-code OAuth lets the
// user's browser authenticate without exposing a local callback listener.
export function authInteraction(signal, send, windows = process.platform === "win32") {
    return {
        signal,
        prompt(p) {
            if (p.type === "select") {
                const method = windows ? "device_code" : "browser";
                const choice = p.options?.find((option) => option.id === method);
                if (!choice) return Promise.reject(new Error(`login_method_unavailable:${method}`));
                return Promise.resolve(choice.id);
            }
            return new Promise((_, reject) => {
                const signals = [...new Set([signal, p.signal].filter(Boolean))];
                const stop = () => {
                    for (const source of signals) source.removeEventListener("abort", stop);
                    reject(new Error("cancelled"));
                };
                if (signals.some((source) => source.aborted)) return stop();
                for (const source of signals) source.addEventListener("abort", stop, { once: true });
            });
        },
        notify(event) {
            if (event.type !== "auth_url" && event.type !== "device_code") return;
            const url = new URL(event.type === "auth_url" ? event.url : event.verificationUri);
            if (url.protocol !== "https:" || url.hostname !== "auth.openai.com" || url.port || url.username || url.password) {
                throw new Error("unexpected_sign_in_url");
            }
            const result = { type: "login_url", url: url.href };
            if (event.type === "device_code") {
                if (typeof event.userCode !== "string" || !/^[A-Z0-9-]{4,32}$/i.test(event.userCode)) {
                    throw new Error("invalid_sign_in_code");
                }
                result.code = event.userCode;
            }
            send(result);
        },
    };
}
