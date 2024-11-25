import js from '@eslint/js'
import globals from 'globals'
import tseslint from 'typescript-eslint'


export default tseslint.config(
    { ignores: ['dist', 'attic'] },
    {
        extends: [js.configs.recommended, ...tseslint.configs.recommendedTypeChecked],
        files: ['**/*.{ts,tsx}'],
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
                    paths: ['./src'],
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
