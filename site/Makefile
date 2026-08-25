# ABOUTME: Development commands for beadhub.ai marketing site
# ABOUTME: Run `make help` to see available targets

.PHONY: help check-hugo check-contract check dev dev-bg restart build clean stop

# Port chosen to avoid conflicts with sibling projects:
#   aweb-cloud site=1313  claweb site=4315
SITE_PORT ?= 4200
HUGO_VERSION ?= 0.164.0
ALLOW_HUGO_VERSION_MISMATCH ?= 0

help:
	@echo "beadhub.ai Development Commands"
	@echo ""
	@echo "  make dev        Start Hugo dev server (foreground, port $(SITE_PORT))"
	@echo "  make dev-bg     Start Hugo dev server (background)"
	@echo "  make restart    Stop then start in background"
	@echo "  make build      Build static site to public/"
	@echo "  make check      Verify source contract and build the site"
	@echo "  make clean      Remove build artifacts"
	@echo "  make stop       Stop dev server"
	@echo ""
	@echo "Port Allocation (across beadhub-all):"
	@echo "  aweb-cloud site=1313"
	@echo "  beadhub.ai site=4200"
	@echo "  claweb     site=4315"

check-hugo:
	@command -v hugo >/dev/null || { echo "hugo $(HUGO_VERSION) is required"; exit 1; }
	@actual="$$(hugo version | awk '{print $$2}' | sed -e 's/^v//' -e 's/+.*//')"; \
	if [ "$$actual" != "$(HUGO_VERSION)" ] && [ "$(ALLOW_HUGO_VERSION_MISMATCH)" != "1" ]; then \
		echo "expected hugo $(HUGO_VERSION), found $$actual"; \
		echo "set ALLOW_HUGO_VERSION_MISMATCH=1 to accept the stated reproducibility risk"; \
		exit 1; \
	fi

check-contract:
	python3 scripts/test_site_contract.py

check: build check-contract

dev: check-hugo
	hugo server --port $(SITE_PORT) --bind 127.0.0.1

dev-bg:
	@hugo server --port $(SITE_PORT) --bind 127.0.0.1 >/dev/null 2>&1 &
	@echo "Hugo dev server started on http://localhost:$(SITE_PORT)"

restart: stop dev-bg

build: check-hugo
	hugo --minify

clean:
	rm -rf public resources

stop:
	-@lsof -ti :$(SITE_PORT) | xargs kill 2>/dev/null || true
	@echo "Stopped dev server"
