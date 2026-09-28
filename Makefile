.PHONY: install lint type test verify run

install:
	python -m pip install -e ".[dev]"

lint:
	ruff check .

type:
	mypy src

test:
	pytest --cov=contextplane --cov-report=term-missing

verify: lint type test

run:
	uvicorn contextplane.app:app --reload
