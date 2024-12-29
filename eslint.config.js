import js from '@eslint/js'
import globals from 'globals'
import tseslint from 'typescript-eslint'
import { glob } from 'glob'

const files = glob.sync('./**/*.{ts,tsx,css}', {ignore: ["./**/*.d.ts"]})

export default tseslint.config(
    { ignores: ['dist', 'node_modules', '.turbo'] },
    {
        extends: [js.configs.recommended, ...tseslint.configs.recommendedTypeChecked],
        files: files,
        languageOptions: {
            ecmaVersion: 2020,
            globals: globals.browser,
            parserOptions: {
                project: ['./tsconfig.node.json', './tsconfig.app.json'],
                tsconfigRootDir: import.meta.dirname,
            },
        },
        settings: {
            'import/parsers': {
                '@typescript-eslint/parser': ['.ts', '.tsx']
            },
            'import/resolver': {
                node: {
                    paths: ['.'],
                    extensions: ['.js', '.jsx', '.ts', '.d.ts', '.tsx'],
                },
                typescript: {
                    alwaysTryTypes: true,
                    project: ['./tsconfig.json']
                },
            }
        },
    },
)
