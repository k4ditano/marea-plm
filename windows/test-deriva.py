"""Exercise Deriva's Windows adapter and generated logic with a mocked worker.

This is protocol/interaction coverage. test-deriva-native.py tests the real store.
"""
from pathlib import Path
import argparse
from logic_test import runner_arguments, run_checks

parser = argparse.ArgumentParser(description=__doc__)
runner_arguments(parser)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
module = (root / 'windows/deriva-worker.luau').read_text(encoding='utf-8')
preview_module = (root / 'windows/deriva-preview.luau').read_text(encoding='utf-8')
generated = (root / 'marea-desktop.luau').read_text(encoding='utf-8')
scene = (root / 'marea-desktop.plm').read_text(encoding='utf-8')
assert 'She builds it herself when she starts, if Rust (cargo) is installed.' not in scene
assert scene.index('zone box drift_area') < scene.index('for d in drift { DriftCard('), 'scroll zone blocks card clicks'
checks = r'''
-- The isolated runner has no service/JSON globals. Mock the serialization
-- boundary as well as the process; the native rehearsal covers launch failure.
local encoded, serial = {}, 0
local json = {
    encode=function(value) serial += 1; local key = tostring(serial); encoded[key] = value; return key end,
    decode=function(value) assert(encoded[value], "invalid JSON fixture"); return encoded[value] end,
}
local install_deriva_worker = (function()
__MODULE__
end)()
local install_deriva_preview = (function()
__PREVIEW__
end)()
local pending, reject = {}, false
local function native_run(command, args, done, options)
    if reject then error("missing worker") end
    assert((command == "deriva-worker" or command == "node") and options.cwd == ".")
    pending[#pending + 1] = {args=args, done=done}
end
local invoke, path = install_deriva_worker(native_run)
assert(path("file:///C:/Fotos%20%C3%B1/%E6%B5%B7%20%F0%9F%9A%80.png") == "C:/Fotos ñ/海 🚀.png")
assert(path("FILE://localhost/D:/a%231%25%2B.txt") == "D:/a#1%+.txt")
assert(path("file://server/share/a%20b.txt") == "//server/share/a b.txt")
assert(path([[file://\\?\C:\Fotos ñ\a #1%.png]]) == "C:/Fotos ñ/a #1%.png")
assert(path([[file://\\?\UNC\server\share\a b.txt]]) == "//server/share/a b.txt")
for _, value in ipairs({"file:///tmp/file.txt", "file:///C:/a%GG", "file:///C:/a%", "file:///C:/a%00.txt",
    "file:///C:/a%0A.txt", "file:///C:/a%FF.txt", "file://server/", "file://user@server/share/a", "file:///C:/a?x"}) do
    assert(path(value) == nil, value)
end
local function response(args, data, code)
    local answer, message
    invoke(args, function(r, err) answer, message = r, err end)
    pending[#pending].done(type(data) == "string" and data or json.encode(data), code or 0)
    return answer, message
end
assert(response({"where"}, {blobs="C:/Store ñ/blobs"}).blobs == "C:/Store ñ/blobs")
assert(response({"where"}, {blobs="//server/share/blobs"}))
assert(not response({"where"}, {blobs="/home/test/blobs"}))
assert(not response({"list"}, "not JSON"))
assert(not response({"list"}, {ok=false, error={message="locked"}}))
local _, failure = response({"list"}, {ok=false, error={message="locked"}}, 1)
assert(failure:find("locked") and not failure:find("PATH"))
_, failure = response({"list"}, "stderr only", 2)
assert(failure:find("código 2") and not failure:find("PATH"))
assert(not response({"list"}, {result={items={"invalid"}}}))
assert(not response({"list"}, {result={items={a={title="wrong keys"}}}}))
assert(not response({"list"}, {result={items={{source={}}}}}))
assert(not response({"list"}, {result={items={{captured_at=1e100}}}}))
assert(not response({"list"}, {}))
assert(not response({"ingest"}, {result={saved="1"}}))
assert(not response({"ingest"}, {result={saved=-1}}))
assert(not response({"ingest"}, {result={saved=0}}))
assert(response({"ingest"}, {result={saved=1, duplicates=0}}).saved == 1)
assert(response({"ingest"}, {result={failed=1}}).failed == 1)
reject = true
local delivered = false
invoke({"where"}, function(r, err) assert(not r and err:find("PATH")); delivered = true end)
assert(delivered)
reject = false
local count = 0
invoke({"where"}, function() count += 1 end)
pending[#pending].done(json.encode({blobs="C:/store"}), 0)
pending[#pending].done('bad', 1)
assert(count == 1)

do
    local requests, received = {}, 0
    local preview = install_deriva_preview(function(command, args, done)
        assert(command == "node" and args[1] == "tools/deriva-preview.mjs")
        requests[#requests + 1] = {id=args[3], done=done}
    end)
    local a = {id="0123456789abcdef0123456789ab", source="youtube"}
    local b = {id="abcdef0123456789abcdef01234", source="youtube"}
    preview(a, function() received += 1 end)
    preview(a, function() error("duplicate enrichment") end)
    preview(b, function() received += 1 end)
    assert(#requests == 1, "preview downloads must be serialized")
    requests[1].done("offline", 1)
    assert(#requests == 2 and received == 0)
    requests[1].done("offline", 1)
    requests[2].done(json.encode({ok=true,result={item={id=b.id, title="second", preview_path="C:/preview"}}}), 0)
    assert(received == 1)
    preview(a, function() error("immediate failure retry") end)
    assert(#requests == 2)
end

local valid = {id="123", type="text", captured_at=0, spaces={"inspiracion"}}
assert(response({"call","home"}, {result={items={valid}, stats={captures=1,trashed=0}, sections={{kind="space",id="inspiracion",name="Folder",count=1}}}}))
assert(not response({"call","home"}, {result={items={valid},stats={captures=-1,trashed=0},sections={}}}))
assert(not response({"call","search"}, {result={items={{id="123",blob_path={}}}}}))
assert(not response({"call","get"}, {result={item={id="123",favorite="yes"}}}))
assert(not response({"call","home"}, {result={items={},stats={captures=1,trashed=0},sections={{kind="space",id="x",name="x",count="1"}}}}))
print("PASS: Deriva Windows URIs, protocol validation, one-shot callbacks, capture fields and library folder/count validation")
'''.replace('__MODULE__', module).replace('__PREVIEW__', preview_module)
run_checks(args, checks, 'PASS: Deriva Windows URIs', 'deriva')
