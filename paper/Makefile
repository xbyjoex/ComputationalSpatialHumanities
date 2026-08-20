PY := .venv/bin/python

.PHONY: all analysis figures paper test clean

all: figures paper

analysis:
	./analysis/extract.sh
	cd analysis && ../$(PY) run.py

figures:
	$(PY) figures/make_figures.py

paper:
	latexmk -pdf -quiet main.tex

test:
	.venv/bin/pytest tests -q

clean:
	latexmk -C
	rm -f main.bbl main.blg
