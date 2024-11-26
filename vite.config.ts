import {defineConfig, PluginOption} from 'vite'
// @ts-expect-error 'types could not be resolved when respecting package.json "exports"'
import eslint from 'vite-plugin-eslint'
import dts from 'vite-plugin-dts'
import {resolve} from "path"

const plugins: PluginOption[] = [
  dts({
    rollupTypes: true,
    outDir: 'dist',
    tsconfigPath: './tsconfig.app.json',
  }),
]
// vite-plugin-eslint[2] is incompatible with turbo
if (process.env.TURBO_HASH === undefined) {
  // eslint-disable-next-line @typescript-eslint/no-unsafe-argument,@typescript-eslint/no-unsafe-call
  plugins.push(eslint())
}

// https://vitejs.dev/config/
export default defineConfig({
  plugins: plugins,
  root: resolve(__dirname),
  base: "/space-data-api/",
  build: {
    lib: {
      entry: resolve(__dirname, "src/space-data-service.ts"),
      name: "space-data-service",
      formats: ["es"],
      fileName: "space-data-service"
    },
  },
})
