// Conventional Commits rules for EcoTrace. Types and scopes come from CONTRIBUTING.md.
// The same config checks commit messages and pull request titles in CI.

const types = ['feat', 'fix', 'docs', 'refactor', 'test', 'chore', 'ci', 'build', 'perf'];

const scopes = [
  'core',
  'gateway',
  'identity',
  'data',
  'storage',
  'workflow',
  'events',
  'ledger',
  'intake',
  'carbon',
  'purchase',
  'portal',
  'dashboard',
  'dxctl',
  'infra',
  'docs',
];

export default {
  extends: ['@commitlint/config-conventional'],
  rules: {
    'type-enum': [2, 'always', types],
    'scope-enum': [2, 'always', scopes],
    'scope-empty': [2, 'never'],
    'subject-case': [2, 'never', ['sentence-case', 'start-case', 'pascal-case', 'upper-case']],
  },
};
