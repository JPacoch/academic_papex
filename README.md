# Academic Markdown-to-LaTeX Writing Pipeline

A modular **Quarto + TinyTeX + LaTeX** blueprint for **Geoinformatics, Computer Science, and Applied Mathematics** papers on **Ubuntu 26.04 (WSL2)**.

Write pure Markdown prose, `$...$` / `$$...$$` math, and simple figure/citation tags in `chapters/*.qmd`; compilation, IEEE bibliography formatting, cross-referencing, standalone `.tex` export, image DPI checks, and arXiv packaging are automated.

---

## 1. Setup & Quick Start

1. On GitHub, click **Use this template → Create a new repository**, or clone locally:
   ```bash
   git clone <your-repo-url> my-new-paper
   cd my-new-paper
   ```
2. Install dependencies and generate the placeholder figure (idempotent):
   ```bash
   make setup
   ```
3. Compile the blueprint paper:
   ```bash
   make build
   ```
   Outputs in `build/`:
   - `build/index.pdf` — compiled PDF manuscript
   - `build/index.tex` — standalone LaTeX source for journal portals or co-authors

---

## 2. Writing Your Paper (Authoring Guide)

### Structuring Your Manuscript (`index.qmd` & `chapters/*.qmd`)
- **Metadata (`index.qmd`):** Edit `title`, `author`, `abstract`, and `keywords` in the YAML header of [index.qmd](index.qmd).
- **Writing prose:** Write each section in its own file under `chapters/` (`01_introduction.qmd`, `02_methodology.qmd`, `03_results.qmd`). Use `#` for top-level sections (`\section`), `##` for subsections (`\subsection`), and `###` for sub-subsections.
- **Adding or reordering chapters:** Create a new `.qmd` file (e.g., `chapters/04_conclusion.qmd`) and add `{{< include chapters/04_conclusion.qmd >}}` inside [index.qmd](index.qmd) above `# References {.unnumbered}`.

### Adding & Citing References (`references.bib`)
1. Paste BibTeX entries into [references.bib](references.bib) (from Google Scholar, Crossref, Zotero, or publisher pages):
   ```bibtex
   @article{smith2025lidar,
     author  = {Smith, Alice and Chen, Wei},
     title   = {Scalable Terrain Modeling},
     journal = {IEEE Transactions on Geoscience and Remote Sensing},
     year    = {2025},
     volume  = {63},
     pages   = {1--12},
     doi     = {10.1109/TGRS.2025.0000001}
   }
   ```
2. Cite anywhere in `chapters/*.qmd`:
   - Single citation: `[@smith2025lidar]` → `[1]`
   - Multiple citations: `[@smith2025lidar; @example2026key]` → `[1], [2]`
   - With page/section locator: `[@smith2025lidar, pp. 4--6]`
   - Narrative citation (author in sentence): `@smith2025lidar showed that...`
3. Quarto automatically formats the reference list at the end of the paper using [ieee.csl](ieee.csl).

### Adding & Referencing Images (`images/`)
1. Export figures to `images/` as:
   - **Raster maps / plots (`.png`, `.jpg`):** Export at **≥ 300 DPI** (at least ~1050 px wide for single-column or ~1950 px for full-width) and keep files under **15 MB**.
   - **Diagrams / charts (`.pdf`):** Vector PDFs are preferred for sharp text/lines; keep under **10 MB** (flatten ultra-dense GIS vector layers if needed).
2. Insert a **single figure** in any `chapters/*.qmd` file:
   ```markdown
   ![Descriptive figure caption.](images/my_map.png){#fig-mymap width="85%"}
   ```
   Reference it in prose as `As shown in @fig-mymap, ...`.
3. Insert a **2x2 subfigure map grid** (no raw `\begin{subfigure}` needed):
   ```markdown
   ::: {#fig-maps layout-ncol=2}
   ![Elevation (m)](images/map_a.png){#fig-map-a}

   ![Slope (deg)](images/map_b.png){#fig-map-b}

   ![NDVI](images/map_c.png){#fig-map-c}

   ![Uncertainty (m)](images/map_d.png){#fig-map-d}

   Overall caption for all four subfigures.
   :::
   ```
   Reference the whole grid with `@fig-maps` or individual panels with `@fig-map-a`.
4. Run `make check` anytime (or `make build`, which runs it automatically) to catch missing paths, low-DPI exports, or oversized files before compilation.

### Equations, Theorems, Algorithms & Tables (Copy-Paste Snippets)

- **Numbered Equation:**
  ```markdown
  $$
  \mathbf{y} = \mathbf{X}\boldsymbol{\beta} + \boldsymbol{\varepsilon}
  $$ {#eq-linear}
  ```
  Reference: `@eq-linear`.

- **Theorem & Proof:**
  ```markdown
  ::: {#thm-bound}
  ## Runtime Bound
  For $n$ points, the algorithm runs in $\mathcal{O}(n \log n)$ time.
  :::

  ::: {.proof}
  Proof details here...
  :::
  ```
  Reference: `@thm-bound`.

- **Algorithm Pseudocode (`algpseudocode`):**
  ````markdown
  ```{=latex}
  \begin{algorithm}[htbp]
  \caption{Algorithm Title}
  \label{alg:myalgo}
  \begin{algorithmic}[1]
  \Require Input $\mathbf{X}$
  \Ensure Output $\hat{\mathbf{y}}$
  \State Compute step \Comment{$\mathcal{O}(\log n)$}
  \State \Return $\hat{\mathbf{y}}$
  \end{algorithmic}
  \end{algorithm}
  ```
  ````
  Reference: `\Cref{alg:myalgo}`.

- **`booktabs` Table:**
  ```markdown
  | Method | RMSE (m) | Runtime (s) |
  |:-----------------------|---------:|------------:|
  | Baseline | 0.42 | 1.8 |
  | **Proposed** | **0.16** | **3.4** |

  : Benchmark comparison. {#tbl-bench}
  ```
  Reference: `@tbl-bench`.

---

## 3. Daily Commands (`Makefile`)

| Command | Purpose |
| :--- | :--- |
| `make watch` | Live preview server (`http://127.0.0.1:4242`) for WSL2; auto-recompiles when `index.qmd`, `chapters/*.qmd`, `latex/*.tex`, `references.bib`, or `_quarto.yml` is saved. |
| `make check` | Validates image references, DPI (`>= 300`), pixel width (`>= 1050 px`), and file sizes. |
| `make build` | Runs `make check` and compiles `build/index.pdf` + `build/index.tex`. |
| `make arxiv` | Builds the paper and packages `index.tex`, `references.bib`, and **only used images** into `build/submission_bundle.zip`. |
| `make clean` | Removes temporary LaTeX caches and `build/*` artifacts. |

> **WSL2 Tip:** `make watch` runs with `--no-browser --host 127.0.0.1 --port 4242`. Open `http://localhost:4242` in your Windows browser or view `build/index.pdf` in VS Code.

---

## 4. Swapping Citation Styles & Journal Templates

### Citation Style Options
This template uses `cite-method: citeproc` with `csl: ieee.csl` for zero-error compilation and a self-contained `.tex` output.
- **Swap CSL style:** Replace `csl: ieee.csl` in `_quarto.yml` with another `.csl` file (e.g., `acm-siggraph.csl`, `elsevier-with-titles.csl`, `copernicus-publications.csl`).
- **Switch to BibTeX / `natbib`:** Set `cite-method: natbib` and `biblio-style: IEEEtran` in `_quarto.yml`.

### Swapping `documentclass` for Camera-Ready Submission

Edit `format: pdf:` in [_quarto.yml](_quarto.yml):

- **IEEE (`IEEEtran`):** `documentclass: IEEEtran`, `classoption: [journal]` (or `[conference]`), `geometry: []`
- **ACM (`acmart`):** `documentclass: acmart`, `classoption: [sigconf]` (or `[acmsmall]`), `geometry: []`
- **Elsevier (`elsarticle`):** `documentclass: elsarticle`, `classoption: [preprint]` (or `[5p, twocolumn]`), `geometry: []`
- **Copernicus (`copernicus`):** `documentclass: copernicus`, `classoption: [manuscript]`, `geometry: []`

*(Or install an official Quarto journal template via `quarto use template quarto-journals/ieee` and copy your `{{< include chapters/... >}}` lines into its root `.qmd`.)*
