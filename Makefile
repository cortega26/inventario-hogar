PYTHON := $(if $(wildcard .venv/bin/python),.venv/bin/python,python)

.PHONY: test run

test:
	$(PYTHON) -m unittest discover -s tests -v

run:
	$(PYTHON) main.py
