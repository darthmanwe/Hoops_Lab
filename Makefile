# Thin forwarder. All logic lives in the root package.json scripts, because
# `make` is not installed on the primary Windows development machine and a
# Makefile you cannot run is a Makefile that silently rots. Run `npm run <task>`
# directly if you do not have make; the target names are identical.

.PHONY: setup lint format type test dev build clean ml-lint ml-type ml-test help

help:
	@npm run

setup:      ; npm run setup
lint:       ; npm run lint
format:     ; npm run format
type:       ; npm run type
test:       ; npm run test
dev:        ; npm run dev
build:      ; npm run build
clean:      ; npm run clean
ml-lint:    ; npm run ml:lint
ml-type:    ; npm run ml:type
ml-test:    ; npm run ml:test
