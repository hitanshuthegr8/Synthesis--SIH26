setup:
	pip install -r backend/requirements.txt && cd frontend && npm install
test:
	cd backend && python -m pytest tests/ -v
lint:
	cd backend && python -m pyflakes app/ 2>&1 || true
	cd backend && python -m pytest tests/regression/test_no_hardcoded_metrics.py -q
generate-demo:
	python scripts/generate_demo_data.py
seed:
	python scripts/seed_database.py
run:
	cd backend && start /b uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
	cd frontend && npm run dev
demo: generate-demo seed run
reset:
	cmd /c "if exist backend\data\synthesis.db del backend\data\synthesis.db"
	python scripts/seed_database.py
