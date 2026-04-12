

.PHONY: package release test test-unit mypy

all: package

package:
	rm -f dist/*
	python3 setup.py sdist bdist_wheel

install: package
	pip3 install --no-deps --force dist/*.whl

release: package
	twine upload dist/*

test: test-unit mypy

test-unit:
	pytest test/

mypy:
	cd pcbdraw && mypy .

clean:
	rm -rf dist build
