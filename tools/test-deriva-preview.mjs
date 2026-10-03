import test from 'node:test';
import assert from 'node:assert/strict';
import {enrichPreview, youtubeId} from './deriva-preview.mjs';

const id = '0123456789abcdef0123456789ab';
const url = 'https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=example';
const jpeg = Buffer.from([255, 216, 255, 224, 0, 1, 255, 217]);
const capture = {id, source_url: url, title: url, source: 'youtube'};

function fixture(item = capture, fetcher = async u => u.includes('/oembed?')
  ? new Response(JSON.stringify({title: 'Video ñ 海', author_name: 'Author'})) : new Response(jpeg)) {
  const calls = [], urls = [];
  return {
    calls, urls,
    options: {
      exists: async () => {},
      invoke: async (args, payload) => { calls.push({args, payload}); return {item: {...item, ...payload}}; },
      fetcher: async (u, options) => {
        urls.push(u);
        assert.equal(options.redirect, 'error');
        assert.equal(options.credentials, 'omit');
        assert(options.signal instanceof AbortSignal);
        return fetcher(u);
      },
    },
  };
}

test('accepts watch, mobile, short, live and embed URLs with exact YouTube hosts', () => {
  for (const value of [url, 'https://youtu.be/dQw4w9WgXcQ?t=5', 'https://m.youtube.com/shorts/dQw4w9WgXcQ',
    'https://music.youtube.com/watch?v=dQw4w9WgXcQ', 'https://youtube.com/embed/dQw4w9WgXcQ/',
    'https://youtube.com/live/dQw4w9WgXcQ']) assert.equal(youtubeId(value), 'dQw4w9WgXcQ');
  for (const value of ['https://youtube.com.evil.test/watch?v=dQw4w9WgXcQ', 'file:///watch?v=dQw4w9WgXcQ',
    'https://youtube.com@evil.test/watch?v=dQw4w9WgXcQ', 'https://user@youtube.com/watch?v=dQw4w9WgXcQ',
    'https://youtube.com:8443/watch?v=dQw4w9WgXcQ', 'https://youtu.be/invalid', 'https://youtu.be/dQw4w9WgXcQ/extra'])
    assert.equal(youtubeId(value), null);
});

test('persists real metadata and JPEG through bounded stdin, retaining original link', async () => {
  const f = fixture();
  const {item} = await enrichPreview(id, f.options);
  assert.equal(item.title, 'Video ñ 海');
  assert.equal(item.source_url, url);
  assert.equal(f.calls[1].payload.preview_b64, jpeg.toString('base64'));
  assert.deepEqual(f.calls[1].args, ['enrich', '--request-stdin']);
  assert.equal(f.urls[1], 'https://i.ytimg.com/vi/dQw4w9WgXcQ/mqdefault.jpg');
});

test('cached preview and unsupported sites do not request network or write', async () => {
  for (const item of [{...capture, preview_path: 'C:/cache ñ/image'}, {...capture, source_url: 'https://example.com/'}]) {
    const f = fixture(item);
    await enrichPreview(id, f.options);
    assert.equal(f.urls.length, 0);
    assert.equal(f.calls.length, 1);
  }
});

test('offline/removed videos leave the saved card intact', async () => {
  for (const fetcher of [async () => { throw new Error('offline'); }, async () => new Response('', {status: 404})]) {
    const f = fixture(capture, fetcher);
    assert.deepEqual((await enrichPreview(id, f.options)).item, capture);
    assert.equal(f.calls.length, 1);
  }
});

test('invalid metadata, oversized streamed images and non-JPEG responses are ignored', async () => {
  for (const data of [Buffer.alloc(512 * 1024 + 1), Buffer.from('<html>not an image</html>')]) {
    const f = fixture(capture, async u => new Response(u.includes('/oembed?') ? 'invalid json' : data));
    await enrichPreview(id, f.options);
    assert.equal(f.calls.length, 1);
  }
});

test('a failed oEmbed request still permits the thumbnail', async () => {
  const f = fixture(capture, async u => u.includes('/oembed?') ? new Response('', {status: 403}) : new Response(jpeg));
  await enrichPreview(id, f.options);
  assert.equal(f.calls[1].payload.preview_b64, jpeg.toString('base64'));
  assert.equal(f.calls[1].payload.title, undefined);
});

test('invalid ids and mismatched worker replies cannot enrich another capture', async () => {
  const f = fixture({...capture, id: 'wrong'});
  await assert.rejects(enrichPreview('../elsewhere', f.options));
  assert.equal(f.calls.length, 0);
  await assert.rejects(enrichPreview(id, f.options));
  assert.equal(f.urls.length, 0);
});
