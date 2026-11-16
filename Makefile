SHELL := /bin/bash
PYTHON := python3
QUARTO := quarto
BUILD_DIR := build
ENTRY_QMD := index.qmd
OUTPUT_PDF := $(BUILD_DIR)/index.pdf
OUTPUT_TEX := $(BUILD_DIR)/index.tex
ARXIV_ZIP := $(BUILD_DIR)/submission_bundle.zip
PREVIEW_PORT ?= 4242

# Ensure TinyTeX binaries are visible even in non-interactive shells
export PATH := $(HOME)/.TinyTeX/bin/x86_64-linux:$(HOME)/.TinyTeX/bin/aarch64-linux:$(PATH)

.PHONY: help setup check build watch arxiv clean

help:
	@echo "Academic Paper Compilation Pipeline"
	@echo ""
	@echo "Targets:"
	@echo "  make setup   Install Quarto, TinyTeX, LaTeX packages, and generate sample figures"
	@echo "  make check   Validate figure paths, DPI (>=300), pixel width, and file sizes"
	@echo "  make build   Run image checks and compile PDF + standalone .tex into $(BUILD_DIR)/"
	@echo "  make watch   Live auto-recompile preview server (configured for WSL2)"
	@echo "  make arxiv   Package .tex, .bib, and ONLY used images into $(ARXIV_ZIP)"
	@echo "  make clean   Remove build artifacts and temporary LaTeX/Quarto caches"

setup:
	@chmod +x scripts/setup_ubuntu.sh scripts/check_images.py scripts/generate_placeholders.py
	@./scripts/setup_ubuntu.sh
	@$(PYTHON) scripts/generate_placeholders.py

check:
	@$(PYTHON) scripts/check_images.py

build: check
	@command -v $(QUARTO) >/dev/null 2>&1 || { \
		echo "[ERROR] 'quarto' not found on PATH. Run 'make setup' first."; \
		exit 1; \
	}
	@mkdir -p $(BUILD_DIR)
	@$(QUARTO) render $(ENTRY_QMD)
	@if [ -f index.tex ]; then mv -f index.tex $(OUTPUT_TEX); fi
	@echo ""
	@echo "[OK] Build complete:"
	@echo "  PDF : $$(pwd)/$(OUTPUT_PDF)"
	@echo "  TeX : $$(pwd)/$(OUTPUT_TEX)"

watch:
	@command -v $(QUARTO) >/dev/null 2>&1 || { \
		echo "[ERROR] 'quarto' not found on PATH. Run 'make setup' first."; \
		exit 1; \
	}
	@echo "Starting Quarto live preview (WSL2 mode) at http://127.0.0.1:$(PREVIEW_PORT)"
	@echo "Watching $(ENTRY_QMD), chapters/*.qmd, latex/*.tex, references.bib, and _quarto.yml..."
	@( \
		last_state=""; \
		while true; do \
			curr_state=$$(stat -c '%Y' chapters/*.qmd latex/*.tex references.bib _quarto.yml 2>/dev/null | tr '\n' ' '); \
			if [ -n "$$last_state" ] && [ "$$curr_state" != "$$last_state" ]; then \
				touch $(ENTRY_QMD); \
			fi; \
			last_state="$$curr_state"; \
			sleep 1; \
		done \
	) & \
	WATCH_PID=$$!; \
	trap "kill $$WATCH_PID 2>/dev/null || true" EXIT INT TERM; \
	$(QUARTO) preview $(ENTRY_QMD) --no-browser --host 127.0.0.1 --port $(PREVIEW_PORT)

define ARXIV_SCRIPT
import pathlib
import re
import sys
import zipfile

tex_path = pathlib.Path(sys.argv[1])
build_dir = pathlib.Path(sys.argv[2])
zip_path = pathlib.Path(sys.argv[3])
bib_path = pathlib.Path("references.bib")
bbl_path = build_dir / "index.bbl"

tex_text = tex_path.read_text(encoding="utf-8")
active_lines = "\n".join(
    line for line in tex_text.splitlines()
    if not line.lstrip().startswith("%")
)
raw_imgs = re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", active_lines)

used_imgs = []
seen = set()
exts = ("", ".pdf", ".png", ".jpg", ".jpeg", ".eps")

for raw in raw_imgs:
    clean = raw.strip().lstrip("/")
    found = None
    for ext in exts:
        cand = pathlib.Path(clean + ext)
        if cand.is_file():
            found = cand
            break
        cand_build = build_dir / (clean + ext)
        if cand_build.is_file():
            found = cand_build
            break
    if found is None:
        raise SystemExit(f"[ERROR] Referenced image not found for arXiv bundle: {raw}")

    try:
        arc = found.relative_to(build_dir)
    except ValueError:
        arc = pathlib.Path(clean)
        if arc.suffix == "" and found.suffix:
            arc = arc.with_suffix(found.suffix)

    if arc not in seen:
        seen.add(arc)
        used_imgs.append((found, arc))

zip_path.parent.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    zf.write(tex_path, arcname="index.tex")
    if bib_path.is_file():
        zf.write(bib_path, arcname="references.bib")
    if bbl_path.is_file():
        zf.write(bbl_path, arcname="index.bbl")
    for src, arc in used_imgs:
        zf.write(src, arcname=str(arc))

print(f"[OK] Created arXiv/journal bundle: {zip_path.resolve()}")
print(f"     Size: {zip_path.stat().st_size / 1024:.1f} KB")
print("     Contents:")
with zipfile.ZipFile(zip_path, "r") as zf:
    for info in zf.infolist():
        print(f"       - {info.filename} ({info.file_size} bytes)")
endef
export ARXIV_SCRIPT

arxiv: build
	@$(PYTHON) -c "$$ARXIV_SCRIPT" "$(OUTPUT_TEX)" "$(BUILD_DIR)" "$(ARXIV_ZIP)"

clean:
	@rm -rf $(BUILD_DIR)/* .quarto *_files
	@rm -f index.tex index.pdf *.aux *.bbl *.bcf *.blg *.fdb_latexmk *.fls *.lof *.log *.lot *.nav *.out *.run.xml *.snm *.synctex.gz *.toc *.vrb
	@mkdir -p $(BUILD_DIR)
	@echo "[OK] Cleaned build artifacts."
