"""Exercise notification access controls without requesting desktop permissions."""
from pathlib import Path
import argparse
from logic_test import runner_arguments, run_checks

parser = argparse.ArgumentParser(description=__doc__)
runner_arguments(parser)
args = parser.parse_args()
module = Path(__file__).with_name('notifications.luau').read_text(encoding='utf-8')
checks = '''
local fact, text = {}, {}
local handlers, requests, notices = {}, {}, {}
local listener, live
local reject = false
local function on(name, callback) handlers[name] = callback end
local function notice(error) notices[#notices + 1] = error end
local sys = {
    watch = function(name, callback)
        if name == "notifications.state" then listener = callback else assert(name == "notifications"); live = callback end
        return true
    end,
    call_async = function(name, args, callback)
        if reject then error("queue full") end
        assert(name == "notifications.request_access" and #args == 0)
        requests[#requests + 1] = callback
    end,
}
local install = (function()
''' + module + '''
end)()
local watch, refresh, age = install(sys, notice)
assert(age(nil, 1000, "now") == "")
assert(age(1200, 1000, "now") == "now")
assert(age(1000, 1059, "now") == "now")
assert(age(1000, 1060, "now") == "1 min")
assert(age(1000, 8200, "now") == "2 h")
assert(age(1000, 173800, "now") == "2 d")
assert(#requests == 0)
local received = 0
watch(function(list)
    received += 1
    assert(fact.windows_notifications_sync == (received == 1))
    assert(list[1] == received)
end)
live({1}); assert(not fact.windows_notifications_sync)
live({2}); assert(not fact.windows_notifications_sync)
local row = { id = 4, app = "NOTICE", title = "title", detail = "body", icon = "", actions = {} }
local update = { app = "Mail", title = "title", body = "body", icon = "windows-app:mail", actions = {{ key = "open-app" }} }
assert(refresh(row, update, "notice"))
assert(row.id == 4 and row.app == "MAIL" and row.actions[1].key == "open-app")
assert(not refresh(row, update, "notice"))
listener({access = "unspecified"})
assert(fact.windows_notifications_requestable and not fact.windows_notifications_allowed)
handlers.windows_notifications_enable()
handlers.windows_notifications_enable()
assert(#requests == 1 and fact.windows_notifications_requesting)
requests[1]("", 0)
listener({access = "allowed"})
assert(fact.windows_notifications_allowed and not fact.windows_notifications_requestable)
handlers.windows_notifications_enable(); assert(#requests == 1)
listener({access = "denied"})
assert(not fact.windows_notifications_allowed and not fact.windows_notifications_requestable)
handlers.windows_notifications_enable(); assert(#requests == 1)
listener({access = "unspecified"})
handlers.windows_notifications_enable(); assert(#requests == 2)
requests[2]("request failed", 1)
assert(fact.windows_notifications_requestable and not fact.windows_notifications_requesting and #notices == 1)
reject = true; handlers.windows_notifications_enable()
assert(fact.windows_notifications_requestable and not fact.windows_notifications_requesting and #notices == 2)
listener({access = "unavailable", error = "capability missing"})
assert(text.windows_notifications_status == "capability missing" and not fact.windows_notifications_allowed)
log("PASS: notification consent, revocation, duplicate request, denied/unavailable and queue failures")
'''
run_checks(args, checks, 'PASS: notification consent', 'notifications')
