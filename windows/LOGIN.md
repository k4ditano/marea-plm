# ChatGPT sign-in on Windows

Marea uses the bundled Pi SDK's device-code flow. Its isolated Windows worker
does not expose a localhost callback. Open **Chat**, choose **Sign in**, then
enter the displayed code on the OpenAI page. Keep the attempt open in Marea.
**Open sign-in page** reopens that page without discarding the current code;
the same control is available in **Settings > Talking with her**.

OpenAI requires device-code login to be enabled in ChatGPT's security settings,
or by the workspace administrator. See the official
[device-code authentication instructions](https://learn.chatgpt.com/docs/auth#preferred-device-code-authentication-beta).
This requirement applies after a code is displayed; it does not explain a
button which never starts the worker or never displays a code.

If the browser cannot open, Marea keeps the code and shows an error so the page
can be reopened. A worker that never reports ready is stopped after 60 seconds
and leaves a retryable error instead of an indefinitely preparing sign-in.
Cancelled, stopped and completed attempts clear their link and code; late
callbacks cannot reopen a cancelled attempt.

## Validation boundary

On 2026-10-08, the installed preview.57 host was exercised with both fresh
validation state and its production isolation profile. Each reached signed-out
ready, received a real device code from OpenAI in 0.25 seconds, cancelled the
attempt and exited with code 0. No browser was opened and no code or token was
retained in the evidence. This verifies startup and code delivery from the
worker, not successful account authorization, model entitlement or a reply.

Native CI reproduced a no-browser/no-code cause: the chat's drag zone covered
the sign-in button (`chat_login_btn is covered by chat_area`), intercepting its
press before the login event reached the worker. The sign-in and cancel events
also lacked the scene language's `->` export, so even an uncovered button could
not notify its Luau handler. These events now reach Luau; the drag zone sits
behind row actions and is disabled on the signed-out page. Shared logic tests cover browser failure/retry, cancelled callback
retirement and a silent worker followed by a new attempt. Native CI also checks
the visible chat/settings buttons and renders the translated code instructions
using isolated fixture data. A real account round trip remains pending.
