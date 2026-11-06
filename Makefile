.PHONY: install api web db-up db-down test build clean

install: api-install web-install

api-install:
	cd services/api && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

web-install:
	cd apps/web && npx -y npm@11 install

api:
	cd services/api && .venv/bin/uvicorn app.main:app --reload --port 8000

web:
	cd apps/web && npx -y npm@11 start

db-up:
	docker compose up -d db

db-down:
	docker compose down

test:
	cd services/api && .venv/bin/pytest
	cd apps/web && npx -y npm@11 test -- --watch=false

build:
	cd apps/web && npx -y npm@11 run build

clean:
	rm -rf apps/web/dist apps/web/.angular services/api/.pytest_cache
