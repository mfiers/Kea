# --- kea: documentation site and review cycle (kea init) ---
.PHONY: site serve feedback watch-comments cycle-status
# site: build report/site/ from doc/ (fails on broken links or schema violations)
site:
	uv run --locked kea build --strict
# serve: the site with comments (SITE_PASSWORD in .env); HOST and PORT default to kea.yaml
serve:
	uv run --locked kea serve $(if $(HOST),--host $(HOST)) $(if $(PORT),--port $(PORT))
# feedback: comments that need attention
feedback:
	uv run --locked kea list
# watch-comments: wait until there is work in the review cycle (DEADLINE = epoch seconds)
watch-comments:
	uv run --locked kea watch --deadline $(DEADLINE)
# cycle-status: where the review cycle stands
cycle-status:
	uv run --locked kea cycle status
# --- end kea ---
