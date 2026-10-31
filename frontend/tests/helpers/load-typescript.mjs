import {readFileSync, statSync} from 'node:fs';
import {createRequire} from 'node:module';
import {dirname, extname, resolve} from 'node:path';
import vm from 'node:vm';
import ts from 'typescript';

/** Load real local TypeScript dependencies while retaining a harness's globals and imports. */
export function loadTypeScript(filename, {imports = {}, globals} = {}) {
  const cache = new Map();
  const context = globals === undefined ? null : vm.createContext({...globals});
  function load(file) {
    if (cache.has(file)) return cache.get(file).exports;
    const loaded = {exports: {}};
    cache.set(file, loaded);
    const moduleRequire = createRequire(file);
    const require = name => {
      if (imports[name] !== undefined && imports[name] !== null) return imports[name];
      if (name.startsWith('.')) {
        const base = resolve(dirname(file), name);
        const local = [base, `${base}.ts`, `${base}.tsx`, resolve(base, 'index.ts'), resolve(base, 'index.tsx')]
          .find(candidate => {
            try { return statSync(candidate).isFile(); } catch { return false; }
          });
        if (local && /^\.tsx?$/.test(extname(local))) return load(local);
      }
      return moduleRequire(name);
    };
    const compiled = ts.transpileModule(readFileSync(file, 'utf8'), {compilerOptions: {
      module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022,
    }}).outputText;
    const args = ['require', 'module', 'exports', '__filename', '__dirname'];
    const execute = context === null
      ? new Function(...args, compiled)
      : vm.runInContext(`(function(${args.join(',')}) {\n${compiled}\n})`, context, {filename: file});
    execute(require, loaded, loaded.exports, file, dirname(file));
    return loaded.exports;
  }
  return load(resolve(filename));
}
