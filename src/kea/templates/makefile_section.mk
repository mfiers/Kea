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
