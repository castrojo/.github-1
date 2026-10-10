#!/usr/bin/env node

// Unit tests for the ASD-STE100 linter.
//
// The rules are only worth having if they are accurate. A checker that reports
// correct prose as a violation gets switched off, and then nothing is checked
// at all — so about half of these tests are for what must NOT be reported.
//
// Usage:
//   node ste-lint.test.mjs   (from the repository being checked)

import {strict as assert} from 'node:assert';
import {execFileSync} from 'node:child_process';
import {existsSync, mkdirSync, mkdtempSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {basename, dirname, join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {
  splitSentences, countWords,
  checkSentenceLength, checkPassiveVoice, checkGerunds,
  checkUnapprovedWords, checkNounCluster, checkParagraphLength,
} from './ste-rules.mjs';
import {stripNonProse, blocks, lintText, generatedDirs, annotationFor, parseAddedLines, inAddedLines} from './ste-lint.mjs';
import {pathToFileURL} from 'node:url';

// Optional: present only in the docs aggregator. See the guarded section below.
let sync = null;
try {
  sync = await import(pathToFileURL(join(process.cwd(), 'scripts', 'sync-org-docs.mjs')).href);
} catch {
  // Not the aggregator.
}

// generatedDirs takes a root, so the tests can build trees instead of asserting
// against whatever the last sync happened to leave on disk.
// The linter now ships beside this test inside the action; the repository
// being checked is the workspace the action runs in.
const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = process.cwd();

let passed = 0;
let failed = 0;

function test(name, fn) {
  try {
    fn();
    passed++;
  } catch (e) {
    failed++;
    console.error(`  FAIL: ${name}\n    ${e.message}`);
  }
}

const has = (findings, fragment) =>
  findings.some((f) => f.message.includes(fragment));

// ── sentence splitting ────────────────────────────────────────────────────────

test('splits on sentence ends', () => {
  assert.equal(splitSentences('Install it. Then start it.').length, 2);
});

test('a version number does not end a sentence', () => {
  const s = splitSentences('Use version 2.4 of the tool.');
  assert.equal(s.length, 1, `got ${JSON.stringify(s)}`);
  assert.ok(s[0].includes('2.4'), 'the version number survives the split');
});

test('an abbreviation does not end a sentence', () => {
  const s = splitSentences('Use a container, e.g. podman, to build it.');
  assert.equal(s.length, 1, `got ${JSON.stringify(s)}`);
});

test('counts hyphenated compounds as one word', () => {
  assert.equal(countWords('a bootc-based system'), 3);
});

// ── rule 3.1 / 3.2, sentence length ───────────────────────────────────────────

test('an instruction over 20 words is reported', () => {
  const long = Array.from({length: 22}, (_, i) => `word${i}`).join(' ');
  assert.ok(checkSentenceLength(long, {procedural: true}));
});

test('an instruction of 20 words is not reported', () => {
  const ok = Array.from({length: 20}, (_, i) => `word${i}`).join(' ');
  assert.equal(checkSentenceLength(ok, {procedural: true}), null);
});

test('descriptive text gets the longer limit', () => {
  const s = Array.from({length: 22}, (_, i) => `word${i}`).join(' ');
  assert.equal(checkSentenceLength(s, {procedural: false}), null);
  assert.ok(checkSentenceLength(s, {procedural: true}));
});

// ── rule 3.4, active voice ────────────────────────────────────────────────────

test('passive voice is reported', () => {
  assert.ok(has(checkPassiveVoice('The image is published to the registry.'), 'passive voice'));
});

test('an adjectival participle is not passive', () => {
  assert.equal(checkPassiveVoice('The tool is based on podman.').length, 0);
  assert.equal(checkPassiveVoice('The feature is supported.').length, 0);
});

test('active voice is not reported', () => {
  assert.equal(checkPassiveVoice('The workflow publishes the image.').length, 0);
});

// ── rule 4.1, -ing forms ──────────────────────────────────────────────────────

test('a gerund is reported', () => {
  assert.ok(has(checkGerunds('Building the image takes ten minutes.'), '-ing'));
});

test('an established adjective is not a gerund', () => {
  // These would otherwise dominate the report and teach the reader to ignore it.
  for (const s of [
    'Use an existing installation.',
    'The following steps apply.',
    'Report a missing dependency.',
    'Install the tools, including podman.',
  ]) {
    assert.equal(checkGerunds(s).length, 0, `reported on: ${s}`);
  }
});

test('a noun that ends in -ing is not a gerund', () => {
  assert.equal(checkGerunds('Change the setting in the file.').length, 0);
});

test('code spans are not checked for gerunds', () => {
  assert.equal(checkGerunds('Run `docker build --pulling` now.').length, 0);
});

// ── rule 1.5, approved words ──────────────────────────────────────────────────

test('a non-approved word is reported with its replacement', () => {
  assert.ok(has(checkUnapprovedWords('Utilize the tool.'), 'use "use"'));
});

test('a phrase is reported once, not as its parts', () => {
  const findings = checkUnapprovedWords('Run the check in order to see the result.');
  assert.equal(findings.length, 1, `got ${JSON.stringify(findings)}`);
  assert.ok(findings[0].message.includes('in order to'));
});

test('a filler word is reported as deletable', () => {
  assert.ok(has(checkUnapprovedWords('This is very simple.'), 'delete it'));
});

test('code spans are not checked for approved words', () => {
  assert.equal(checkUnapprovedWords('Run `utilize --very` now.').length, 0);
});

// ── rule 1.4, noun clusters ───────────────────────────────────────────────────

test('a four-noun cluster is reported', () => {
  assert.ok(has(checkNounCluster('The desktop environment flavor list is long.'), 'noun cluster'));
});

test('three nouns are allowed', () => {
  assert.equal(checkNounCluster('The desktop environment flavor is set.').length, 0);
});

// These are the false positives that made the first version of this rule
// useless: punctuation and markup have to end a run.
test('punctuation ends a noun cluster', () => {
  assert.equal(checkNounCluster('**DX (Developer Experience)**: Pre-configured for use.').length, 0);
  assert.equal(checkNounCluster('Tromso (KDE), XFCE Linux, and Dakota (GNOME) ship now.').length, 0);
  assert.equal(checkNounCluster('It orchestrates USBs, disk images, and ISOs.').length, 0);
});

test('a preposition or verb ends a noun cluster', () => {
  assert.equal(checkNounCluster('It works without sacrificing system stability.').length, 0);
  assert.equal(checkNounCluster('We now offer specialized desktop flavors.').length, 0);
});

// ── rule 3.6, paragraph length ────────────────────────────────────────────────

test('a paragraph over six sentences is reported', () => {
  assert.ok(checkParagraphLength(Array(7).fill('A sentence.')));
  assert.equal(checkParagraphLength(Array(6).fill('A sentence.')), null);
});

// ── extraction ────────────────────────────────────────────────────────────────

test('front matter is not prose', () => {
  const out = stripNonProse('---\ntitle: "Utilize"\n---\n\nThe text.\n');
  assert.ok(!out.includes('title'), out);
});

test('fenced code is not prose', () => {
  const out = stripNonProse('Text.\n\n```sh\nutilize --very\n```\n\nMore text.');
  assert.ok(!out.includes('utilize'), out);
});

test('tables and headings are not prose', () => {
  const out = stripNonProse('# Utilize\n\n| a | b |\n|---|---|\n| utilize | x |\n\nReal text.');
  assert.ok(!out.includes('Utilize'), out);
  assert.ok(out.includes('Real text'), out);
});

test('a link keeps its text and drops its target', () => {
  const out = stripNonProse('See [the guide](https://example.com/utilize).');
  assert.ok(out.includes('the guide'), out);
  assert.ok(!out.includes('utilize'), out);
});

test('list items are treated as instructions', () => {
  const found = blocks('- Do the thing\n- Do the other thing');
  assert.equal(found.length, 2);
  assert.ok(found.every((b) => b.procedural), JSON.stringify(found));
});

test('a paragraph is not an instruction', () => {
  const found = blocks('This is a description of the system.');
  assert.equal(found[0].procedural, false);
});

test('a list stuck to a paragraph is split from it', () => {
  // Markdown needs no blank line between them, and joining the two produced a
  // finding for a seven-word noun cluster that was really three bullets.
  const found = blocks('Give these three items:\n- Full name\n- Username\n- Password');
  assert.equal(found.length, 4, JSON.stringify(found));
  assert.equal(found[0].procedural, true, 'items come first, and are instructions');
  const lead = found.find((b) => !b.procedural);
  assert.ok(lead && lead.text.startsWith('Give these'), JSON.stringify(found));
  assert.ok(found.every((b) => !b.text.includes('Username Password')),
    'bullets must not be concatenated: ' + JSON.stringify(found));
});

// ── generated-tree detection (docs aggregator only) ──────────────────────────
//
// generatedDirs answers "is this tree written here, or synced from another
// repo's README?", which is a question only tuna-os/docs has. Everywhere else
// sync-org-docs.mjs does not exist, generatedDirs is empty by construction,
// and these tests would be asserting against a fixture of nothing. They run
// where the aggregator is, and announce themselves as skipped where it is not
// -- silently skipping is how a suite ends up testing nothing.
if (sync) {
  const {frontmatter, subFrontmatter, HAND_AUTHORED} = sync;
  // ── generated-tree detection ──────────────────────────────────────────────────
  //
  // Whether a tree is generated decides whether its findings are this repo's debt
  // or another repo's, so the cases below cover both ways of getting it wrong.
  // Under-detection puts prose nobody here may edit into the budget (#102);
  // over-detection takes prose this repo does own out of the checker entirely,
  // which is the quieter and worse failure.

  // A tree fixture: docs/<slug>/ holding the named files, under a temp root.
  function fixture(trees) {
    const root = mkdtempSync(join(tmpdir(), 'ste-lint-'));
    for (const [slug, files] of Object.entries(trees)) {
      mkdirSync(join(root, 'docs', slug), {recursive: true});
      for (const [name, body] of Object.entries(files)) {
        writeFileSync(join(root, 'docs', slug, name), body);
      }
    }
    return root;
  }

  const slugsOf = (root) => [...generatedDirs(root)].map((d) => basename(d)).sort();

  // What the sync writes into a tree it creates.
  const syncedIndex = frontmatter('Widget', 1, 'widget', 'alpha') + 'The widget starts.\n';
  const syncedPage = subFrontmatter('Contributing', 2) + 'Open a pull request.\n';

  test('a tree is generated when its index page came from the sync', () => {
    const root = fixture({widget: {'index.md': syncedIndex}});
    assert.deepEqual(slugsOf(root), ['widget']);
  });

  test('a synced tree with no rewritten links at all is still found', () => {
    // The #102 regression. Seven synced files held no relative link, so the old
    // fingerprint never landed anywhere in their trees and 28 findings against
    // prose owned by another repo sat in this repo's budget.
    const root = fixture({
      'dakota-iso': {'index.md': syncedIndex, 'CONTRIBUTING.md': syncedPage},
    });
    assert.deepEqual(slugsOf(root), ['dakota-iso']);
  });

  test('the whole tree is claimed, not only the marked file', () => {
    const root = fixture({
      widget: {'index.md': syncedIndex, 'guide.md': 'Plain prose, no front matter.\n'},
    });
    const dirs = [...generatedDirs(root)];
    assert.equal(dirs.length, 1);
    assert.ok(existsSync(join(dirs[0], 'guide.md')));
  });

  test('a hand-written page that links to GitHub is not a generated tree', () => {
    // docs/faq.md and docs/community.md link to tunaOS/blob/main/CONTRIBUTING.md
    // by hand. Reading that as "the sync wrote this" is how prose this repo owns
    // stopped being checked.
    const root = fixture({
      guides: {'index.md': 'See [CONTRIBUTING](https://github.com/tuna-os/tunaOS/blob/main/CONTRIBUTING.md).\n'},
    });
    assert.deepEqual(slugsOf(root), []);
  });

  test('front matter a person typed is not the sync template', () => {
    // docs/mariner/index.md: the same three keys, no blank line before status.
    const handWritten = '---\nsidebar_position: 1\nsidebar_label: "Mariner"\nstatus: alpha\n---\n\nMariner is a file manager.\n';
    const root = fixture({mariner2: {'index.md': handWritten}});
    assert.deepEqual(slugsOf(root), []);
  });

  test('a HAND_AUTHORED tree is never generated', () => {
    // The sync refuses to overwrite these, so this repo is answerable for their
    // prose. Both lists come from sync-org-docs.mjs, so they cannot disagree.
    const slug = [...HAND_AUTHORED][0];
    const root = fixture({[slug]: {'index.md': syncedIndex}});
    assert.deepEqual(slugsOf(root), [], `${slug} is hand-authored and must be checked`);
  });

  test('this repo\'s own synced trees are found', () => {
    const found = new Set(slugsOf(REPO));
    assert.ok(found.size > 0, 'no generated trees found in a repo that syncs org docs');
    // The seven files from #102, by tree.
    for (const slug of ['dakota-iso', 'dakota-x13s', 'xfce-linux-iso', 'bonito-x13s',
      'ubuntu-26-04-iso', 'tromso-iso']) {
      assert.ok(found.has(slug), `docs/${slug}/ is synced and must not be in the budget`);
    }
    for (const slug of HAND_AUTHORED) {
      assert.ok(!found.has(slug), `docs/${slug}/ is hand-authored and must be checked`);
    }
  });

} else {
  console.log('skipped: generated-tree tests (no scripts/sync-org-docs.mjs — not the docs aggregator)');
}

// ── end to end ────────────────────────────────────────────────────────────────

test('clean STE prose produces no findings', () => {
  const clean = [
    '---', 'title: "Test"', '---', '',
    'The system starts the container.', '',
    '1. Open the file.',
    '2. Change the value.',
    '',
  ].join('\n');
  const findings = lintText(clean);
  assert.equal(findings.length, 0, JSON.stringify(findings, null, 2));
});

test('non-conformant prose produces findings', () => {
  const findings = lintText('Building the image is performed in order to utilize the cache.');
  assert.ok(findings.length >= 2, JSON.stringify(findings));
});

// A hand-written page that links to a file on GitHub must still be checked.
//
// This is the #123 regression, and it is a property of the run rather than of
// any exported helper: main() used to skip any file whose text matched the
// absolute-GitHub-link shape the sync leaves behind, which hid 110 findings in
// prose this repo answers for while the printed total said 14. The check lived
// nowhere but that loop, so the test drives the checker the way CI does — as a
// process, against a fixture root — instead of asserting against a helper.
test('a hand-written page that links to GitHub is still checked (#123)', () => {
  const root = mkdtempSync(join(tmpdir(), 'ste-lint-cli-'));
  mkdirSync(join(root, 'docs'), {recursive: true});
  writeFileSync(join(root, 'docs', 'community.md'),
    '# Community\n\n' +
    'See the [Contributor Guide](https://github.com/tuna-os/tunaOS/blob/main/CONTRIBUTING.md).\n\n' +
    'Building the image is performed in order to utilize the cache.\n');

  const out = execFileSync(process.execPath, [join(HERE, 'ste-lint.mjs')],
    {cwd: root, encoding: 'utf8'});

  assert.match(out, /docs\/community\.md/,
    'the page carries findings and must be reported, not skipped:\n' + out);
  assert.doesNotMatch(out, /generated file\(s\) skipped/,
    'nothing in this fixture is generated:\n' + out);
});

// ── hints: file:line, annotations, delta ────────────────────────────────────
// A finding without a location is a total, not a hint. These cover the
// machinery that points the author — human or agent — at the prose to fix.

test('stripping preserves line numbers across code fences', () => {
  const md = '# Title\n\n```sh\nutilize this\nmore code\n```\n\nReal text here.\n';
  const stripped = stripNonProse(md);
  assert.equal(stripped.split('\n').length, md.split('\n').length,
    'every removed line leaves a newline behind');
  assert.ok(!stripped.includes('utilize'), 'fence content is still removed');
});

test('blocks remember their starting line', () => {
  const found = blocks('First line.\n\n- Do the thing\n- Do the other thing\n\nLast line here.');
  const byText = new Map(found.map((b) => [b.text, b.line]));
  assert.equal(byText.get('First line.'), 1, JSON.stringify(found));
  assert.equal(byText.get('Do the thing'), 3, JSON.stringify(found));
  assert.equal(byText.get('Do the other thing'), 4, JSON.stringify(found));
  assert.equal(byText.get('Last line here.'), 6, JSON.stringify(found));
});

test('findings carry the file line of their prose', () => {
  const md = '# Title\n\n```sh\nutilize this\n```\n\nYou should leverage the dashboard to commence work.\n';
  const findings = lintText(md);
  assert.ok(findings.length > 0, 'expected findings');
  assert.ok(findings.every((f) => f.line === 7), JSON.stringify(findings));
});

test('annotations escape workflow-command syntax', () => {
  // Colons and commas end properties, so file/title escape them; the message
  // body only needs %, CR and LF escaped — a colon there is legal text.
  const line = annotationFor('docs/a,b.md', {line: 3, rule: 'STE 1.5', message: '100% off: use "y"\nnow'});
  assert.ok(line.startsWith('::warning file=docs/a%2Cb.md,line=3,title=STE 1.5::'),
    'file and title are property-escaped: ' + line);
  assert.ok(line.includes('100%25 off: use "y"%0Anow'),
    'data escapes %, CR and LF but keeps colons: ' + line);
});

test('added-line ranges cover exactly the added lines', () => {
  // Genuine `git diff -U0` shape: no context lines, zero-count hunks for
  // pure deletions.
  const diff = [
    'diff --git a/docs/a.md b/docs/a.md',
    '--- a/docs/a.md',
    '+++ b/docs/a.md',
    '@@ -1,0 +1,2 @@',
    '+added one',
    '+added two',
    '@@ -10,0 +12 @@',
    '+single',
    '@@ -20,2 +21,0 @@',
    '-removed',
    '-removed',
  ].join('\n');
  const ranges = parseAddedLines(diff);
  assert.ok(inAddedLines(ranges.get('docs/a.md'), 1));
  assert.ok(inAddedLines(ranges.get('docs/a.md'), 2));
  assert.ok(!inAddedLines(ranges.get('docs/a.md'), 3), 'outside the hunk');
  assert.ok(inAddedLines(ranges.get('docs/a.md'), 12));
  assert.ok(!inAddedLines(ranges.get('docs/a.md'), 11), 'zero-context gap is not added');
  assert.ok(!inAddedLines(ranges.get('docs/a.md') || [], 21), 'a pure-deletion hunk adds no lines');
});

test('--format json keeps stdout parseable', () => {
  const root = mkdtempSync(join(tmpdir(), 'ste-lint-json-'));
  mkdirSync(join(root, 'docs'), {recursive: true});
  writeFileSync(join(root, 'docs', 'a.md'), 'You should leverage the dashboard.\n');
  const out = execFileSync(process.execPath, [join(HERE, 'ste-lint.mjs'), '--format', 'json', 'docs/a.md'],
    {cwd: root, encoding: 'utf8'});
  const parsed = JSON.parse(out);
  assert.ok(parsed.length > 0, 'expected findings');
  assert.equal(parsed[0].file, 'docs/a.md', JSON.stringify(parsed[0]));
  assert.equal(parsed[0].line, 1, JSON.stringify(parsed[0]));
  assert.ok(parsed[0].rule && parsed[0].message, JSON.stringify(parsed[0]));
});

test('--changed-only reports only what the branch added', () => {
  const root = mkdtempSync(join(tmpdir(), 'ste-lint-delta-'));
  const git = ( ...a) => execFileSync('git', a, {cwd: root, encoding: 'utf8'});
  git('init', '-q', '.');
  git('config', 'user.email', 't@t');
  git('config', 'user.name', 't');
  mkdirSync(join(root, 'docs'), {recursive: true});
  writeFileSync(join(root, 'docs', 'a.md'), 'Building the image is performed in order to utilize the cache.\n');
  git('add', '-A');
  git('commit', '-qm', 'base');
  writeFileSync(join(root, 'docs', 'a.md'),
    'Building the image is performed in order to utilize the cache.\n\nYou should leverage the dashboard.\n');
  git('add', '-A');
  git('commit', '-qm', 'change');
  const out = execFileSync(process.execPath,
    [join(HERE, 'ste-lint.mjs'), '--changed-only', '--base', 'HEAD~1', '--format', 'json', 'docs/a.md'],
    {cwd: root, encoding: 'utf8'});
  const parsed = JSON.parse(out);
  assert.ok(parsed.length > 0, 'expected the new line to be reported');
  assert.ok(parsed.every((f) => f.line === 3), JSON.stringify(parsed));
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
