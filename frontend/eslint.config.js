import js from '@eslint/js'
import prettier from 'eslint-config-prettier'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import globals from 'globals'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  { ignores: ['dist/', 'node_modules/'] },
  js.configs.recommended,
  // Type-aware rules for the TypeScript covered by tsconfig.json.
  {
    files: ['src/**/*.{ts,tsx}', 'vite.config.ts'],
    extends: [tseslint.configs.recommendedTypeChecked],
    languageOptions: {
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
    },
    rules: {
      // React event props accept async handlers; React ignores the returned promise.
      '@typescript-eslint/no-misused-promises': ['error', { checksVoidReturn: { attributes: false } }],
      // `const { omitted: _omitted, ...rest } = value` is the idiom for dropping a key.
      '@typescript-eslint/no-unused-vars': ['error', { ignoreRestSiblings: true }],
    },
  },
  // Browser app code.
  {
    files: ['src/**/*.{ts,tsx}'],
    extends: [reactHooks.configs.flat.recommended, reactRefresh.configs.vite],
    languageOptions: { globals: globals.browser },
    rules: {
      // Shared non-component exports that predate this config. Fast Refresh falls back to a full
      // reload for these modules; move them to plain .ts modules before removing names here.
      'react-refresh/only-export-components': [
        'error',
        {
          allowConstantExport: true,
          allowExportNames: [
            'useAccount',
            'fallbackCountries',
            'statusOf',
            'stepOf',
            'price',
            'secureLink',
            'amountText',
            'safetyNeeds',
            'requirementPayload',
            'validRequirements',
            'sellerName',
            'validSpec',
            'specPayload',
          ],
        },
      ],
    },
  },
  // Runtime config script served to the browser.
  {
    files: ['public/**/*.js'],
    languageOptions: { globals: globals.browser, sourceType: 'script' },
  },
  // Node: production server, node:test suites, tool configs.
  {
    files: ['*.mjs', '*.js', 'vite.config.ts'],
    languageOptions: { globals: globals.node },
  },
  prettier,
)
