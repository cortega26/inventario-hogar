.PHONY: test run

test:
	python -m unittest discover -s tests -v

run:
	python main.py
