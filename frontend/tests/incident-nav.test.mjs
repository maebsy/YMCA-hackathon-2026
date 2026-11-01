import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import ts from 'typescript';

const require = createRequire(import.meta.url);
const source = readFileSync(new URL('../src/app/incident/page.tsx', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: {
  module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX,
} }).outputText;
const element = (type, props) => ({ type, props });

test('incident return link follows the actual result, including zero findings and restoration', () => {
  for (const [repository, href, label] of [
    [{ result: null, restored: false }, '/', '저장소 입력으로'],
    [{ result: null, restored: true, resultRepo: 'https://github.com/test/repo' }, '/', '저장소 입력으로'],
    [{ result: { items: [] }, restored: true, findings: [] }, '/report', '검사 결과로'],
    [{ result: { items: [{}] }, restored: true, isScanning: true }, '/report', '검사 결과로'],
  ]) {
    const loaded = { exports: {} };
    const imports = {
      'react/jsx-runtime': { jsx: element, jsxs: element },
      'next/link': { default: 'a' },
      '@/components/incident-workspace': { default: 'incident-workspace' },
      '@/components/repository-provider': { useRepository: () => repository },
    };
    new Function('require', 'module', 'exports', compiled)(name => imports[name] ?? require(name), loaded, loaded.exports);
    const page = loaded.exports.default();
    const link = page.props.children[0];
    assert.equal(link.type, 'a');
    assert.equal(link.props.href, href);
    assert.equal(link.props.children[1], label);
    assert.equal(page.props.children[2].type, 'incident-workspace');
  }
});
