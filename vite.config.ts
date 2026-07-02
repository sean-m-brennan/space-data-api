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

import {defineConfig, PluginOption} from 'vite'
// @ts-expect-error 'types could not be resolved when respecting package.json "exports"'
import eslint from 'vite-plugin-eslint'
import dts from 'vite-plugin-dts'
import {resolve} from "path"
import * as fs from "node:fs"

const plugins: PluginOption[] = [
  dts({
    rollupTypes: true,
    outDir: 'dist',
    tsconfigPath: './tsconfig.app.json',
  }),
]
// vite-plugin-eslint is incompatible with turbo
if (process.env.TURBO_HASH === undefined && !fs.existsSync('.turbo')) {
  // eslint-disable-next-line @typescript-eslint/no-unsafe-argument,@typescript-eslint/no-unsafe-call
  plugins.push(eslint())
}

// https://vitejs.dev/config/
export default defineConfig({
  plugins: plugins,
  root: resolve(__dirname),
  build: {
    sourcemap: true,
    lib: {
      entry: resolve(__dirname, "index.ts"),
      name: "space-data-service",
      fileName: "index",
      formats: ["es", "cjs"],
    },
  },
})
