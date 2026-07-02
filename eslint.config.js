/*
  Copyright 2024 Sean M. Brennan and contributors

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

     http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
*/

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
