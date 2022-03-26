

.PHONY: package release test test-system test-unit mypy

all: package

package:
	rm -f dist/*
	python3 setup.py sdist bdist_wheel

install: package
	pip3 install --no-deps --force dist/*.whl

release: package
	twine upload dist/*

test: test-system test-unit mypy

build/test:
	mkdir -p $@

test-system: build/test $(shell find pcbdraw -type f)
	cd build/test && bats ../../test/system

test-unit:
	cd test/units && pytest

mypy:
	cd pcbdraw && mypy .

clean:
	rm -rf dist build
