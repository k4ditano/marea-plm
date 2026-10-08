// Regenerate the checked-in Windows icon from Marea's original vector artwork.
// Install sharp locally, or set MAREA_SHARP_MODULE to an existing sharp module.
const fs = require('node:fs/promises');
const path = require('node:path');
const sharp = require(process.env.MAREA_SHARP_MODULE || 'sharp');

async function main() {
  const assets = path.resolve(__dirname, '../assets');
  const svg = await fs.readFile(path.join(assets, 'marea-icon.svg'));
  const sizes = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256];
  const images = await Promise.all(sizes.map(size =>
    sharp(svg, { density: 384 }).resize(size, size).png().toBuffer()));
  const directory = Buffer.alloc(6 + images.length * 16);
  directory.writeUInt16LE(1, 2);
  directory.writeUInt16LE(images.length, 4);
  let offset = directory.length;
  for (let i = 0; i < images.length; i++) {
    const entry = 6 + i * 16;
    directory[entry] = directory[entry + 1] = sizes[i] % 256;
    directory.writeUInt16LE(1, entry + 4);
    directory.writeUInt16LE(32, entry + 6);
    directory.writeUInt32LE(images[i].length, entry + 8);
    directory.writeUInt32LE(offset, entry + 12);
    offset += images[i].length;
  }
  await fs.writeFile(path.join(assets, 'marea.ico'), Buffer.concat([directory, ...images]));
  await fs.writeFile(path.join(assets, 'marea-icon.png'), images[images.length - 1]);
  console.log('Rendered Marea icon at ' + sizes.join(', ') + ' px.');
}
main().catch(error => { console.error(error); process.exitCode = 1; });
