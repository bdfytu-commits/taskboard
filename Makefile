PY := .venv/bin/python
PIP := .venv/bin/pip

.PHONY: install run test test-ui seed clean

install:
	$(PIP) install -r requirements.txt

run:
	$(PY) run.py

test:
	$(PY) -m pytest -q

test-ui:
	bash tests/ui/run.sh

seed:
	$(PY) seed.py

clean:
	rm -rf instance *.pyc __pycache__ app/__pycache__ tests/__pycache__ .pytest_cache
