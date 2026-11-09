# --- kea: documentation site and review cycle (kea init) ---
.PHONY: site serve feedback watch-comments cycle-status pdf
# site: build report/site/ from doc/ (fails on broken links or schema violations)
site:
	uv run --locked kea build --strict
# serve: the site with comments (SITE_PASSWORD in .env); HOST and PORT default to kea.yaml
serve:
	uv run --locked kea serve $(if $(HOST),--host $(HOST)) $(if $(PORT),--port $(PORT))
# pdf: one PDF of all pages in report/pdf/ (needs Typst; no data-file contents)
pdf:
	uv run --locked kea pdf
# feedback: comments that need attention
feedback:
	uv run --locked kea list
# watch-comments: wait until there is work in the review cycle (DEADLINE = 3d, 12h, an ISO date/time or epoch
#   seconds); exit 10: comments to plan, 20: Implement pressed, 30: deadline reached. `kea watch --status` checks it
watch-comments:
	uv run --locked kea watch --deadline $(DEADLINE)
# cycle-status: where the review cycle stands
cycle-status:
	uv run --locked kea cycle status
# --- end kea ---

# test: the Kea test suite (tests/)
test:
	uv run --locked pytest -q

# publish: build the site and send it to the hub named in kea.yaml (https://kea.fie.rs/p/kea/; KEA_REMOTE_KEY in .env)
publish: site
	uv run --locked kea publish
.PHONY: test publish

# dev: local development server, independent of the hub.
#   Serves report/site/ on $(DEV_HOST):$(DEV_PORT) (the VPN address; SITE_PASSWORD from .env; DEV_HOST=127.0.0.1
#   for no password), and rebuilds (no PDF) whenever doc/,
#   src/kea/ or kea.yaml change, and restarts the server when src/kea/*.py changes (src/dev_serve.sh). Comments go to data/feedback/dev/ so they never mix with the hub's mirror.
DEV_PORT ?= 8211
DEV_HOST ?= 127.0.0.1          # e.g. make dev DEV_HOST=10.42.0.3 to listen on the VPN
dev:
	DEV_HOST=$(DEV_HOST) DEV_PORT=$(DEV_PORT) ./src/dev_serve.sh
.PHONY: dev

# web: docs/index.html (https://mfiers.github.io/Kea/) generated from README.md, so the web page mirrors GitHub
web:
	uv run --locked python src/build_web.py
.PHONY: web
