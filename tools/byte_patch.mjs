import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const specPath = path.resolve(process.argv[2]);
const { default: patches } = await import(`${pathToFileURL(specPath).href}?t=${Date.now()}`);

for (const patch of patches) {
  const filePath = path.resolve(patch.file);
  const original = fs.readFileSync(filePath);
  const eol = original.includes(Buffer.from("\r\n")) ? "\r\n" : "\n";
  let text = original.toString("latin1");
  const oldText = patch.old.replaceAll("\n", eol);
  const newText = patch.new.replaceAll("\n", eol);
  const count = text.split(oldText).length - 1;
  if (count !== (patch.count ?? 1)) {
    throw new Error(`${patch.file}: expected ${patch.count ?? 1} matches, found ${count}`);
  }
  text = text.replace(oldText, newText);
  fs.writeFileSync(filePath, Buffer.from(text, "latin1"));
  console.log(`patched ${patch.file}`);
}
