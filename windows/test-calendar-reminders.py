"""Check delivery acknowledgement, retries and event lifetime without posting toasts."""
from pathlib import Path
import argparse
from logic_test import runner_arguments, run_checks
parser = argparse.ArgumentParser(description=__doc__)
runner_arguments(parser)
args = parser.parse_args()
module = Path(__file__).with_name('calendar-reminders.luau').read_text(encoding='utf-8')
checks = r'''
local time, minute = 1790753000, 9 * 60 + 30
local os = {time = function() return time end, date = function(format)
    return format == "*t" and {hour = minute // 60, min = minute % 60} or "2026-09-30"
end}
local tick, saved, requests, notices = nil, 0, {}, {}
local function every(delay, callback) assert(delay == 20000); tick = callback end
local function save() saved += 1 end
local function notice(message) notices[#notices + 1] = message end
local reject = false
local sys = {call_async = function(name, args, callback)
    if reject then error("queue full") end
    assert(name == "notifications.publish")
    requests[#requests + 1] = {args = args, done = callback}
end}
local event = {date = "2026-09-30", time = "09:30", title = "España & <海>"}
local cal = {events = {event,
    {date = "2026-09-30", time = "", title = "all day"},
    {date = "2026-09-30", time = "25:99", title = "malformed"},
    {date = "2026-09-29", time = "09:30", title = "yesterday"},
    {date = "2026-09-30", time = "09:29", title = "already sent", told = true}}}
local install = (function()
__MODULE__
end)()
install(sys, notice, cal, save, function(s) return s end)
tick(); tick()
assert(#requests == 1 and not event.told and saved == 1)
assert(requests[1].args[1] == "Calendar · España & <海>" and #event.notice_tag == 16)
local tag = event.notice_tag
requests[1].done("disabled", 1)
assert(not event.told and #notices == 1)
time += 20; tick(); assert(#requests == 1)
time += 40; tick(); assert(#requests == 2 and requests[2].args[3] == tag)
requests[2].done("", 0); tick()
assert(event.told and #requests == 2 and saved == 2)
event.told = nil; reject = true; tick()
assert(not event.told and #notices == 2)
reject = false; time += 60; tick()
assert(#requests == 3 and requests[3].args[3] == tag)
cal.events = {}; requests[3].done("", 0)
assert(not event.told and saved == 2, "deleted events must not be resurrected")
cal.events = {event}; minute += 5; tick()
assert(#requests == 3, "the original five-minute reminder window remains bounded")
minute -= 5
install(sys, notice, cal, save, function(s) return s end); tick()
assert(requests[4].args[3] == tag, "reload must keep the stable delivery tag")
requests[4].done("", 0); assert(event.told)
log("PASS: calendar delivery acknowledgement, pending deduplication, bounded retries, invalid times, deletion and reload")
'''.replace('__MODULE__', module)
run_checks(args, checks, 'PASS: calendar delivery acknowledgement', 'calendar-reminders')
