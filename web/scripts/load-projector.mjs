/** Test/demo tooling only: load trusted local TS projectors with relative imports. */
import fs from 'node:fs';
import path from 'node:path';
import {Buffer} from 'node:buffer';
import {URL, pathToFileURL} from 'node:url';
import ts from 'typescript';
export async function loadProjector(file) {
  const location = pathToFileURL(path.resolve(file));
  const compiled = ts.transpileModule(fs.readFileSync(file, 'utf8'), {compilerOptions: {target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022}}).outputText
    .replace(/from (['"])(\.[^'"]+)\1/g, (_match, quote, reference) => `from ${quote}${new URL(reference + '.ts', location).href}${quote}`);
  return import('data:text/javascript;base64,' + Buffer.from(compiled).toString('base64'));
}
