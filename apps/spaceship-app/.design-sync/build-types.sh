#!/bin/sh
# design-sync buildCmd: the app has no library build, so emit real prop types for the converter.
# Run from apps/spaceship-app. Writes dist/types/ and a root index.d.ts (both gitignored).
set -e
npx tsc -p tsconfig.json --noEmit false --emitDeclarationOnly --declaration --rootDir src --outDir dist/types
for f in src/components/*.tsx; do echo "export * from './dist/types/components/$(basename "$f" .tsx)';"; done > index.d.ts
