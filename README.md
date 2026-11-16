# academic_papex

Modular Markdown-to-LaTeX academic paper template built on Quarto, TinyTeX, and LaTeX. Write prose, math, and figure/citation tags in `chapters/*.qmd`, and compile a publication PDF alongside a standalone `.tex` source and arXiv bundle.

## Setup

Clone the template and install dependencies (Quarto, TinyTeX, required LaTeX packages, Poppler, and Pillow):

```bash
git clone https://github.com/JPacoch/academic_papex.git my-paper
cd my-paper
make setup
make build
```

`make build` writes `build/index.pdf` and `build/index.tex`.

## Commands

| Command | Description |
| :--- | :--- |
| `make setup` | Install dependencies and generate placeholder figure |
| `make check` | Check figure paths, DPI (>= 300), width, and file sizes |
| `make build` | Run image checks and compile `build/index.pdf` and `build/index.tex` |
| `make watch` | Start local preview server on `http://127.0.0.1:4242` with auto-rebuild |
| `make arxiv` | Package `index.tex`, `references.bib`, and used images into `build/submission_bundle.zip` |
| `make clean` | Remove build artifacts and temporary LaTeX/Quarto files |

## Writing Guide

### Structure and Chapters
Edit `title`, `author`, `abstract`, and `keywords` in [index.qmd](index.qmd). Write section content in `chapters/` (`01_introduction.qmd`, `02_methodology.qmd`, `03_results.qmd`). Use `#` for top-level sections, `##` for subsections, and `###` for sub-subsections. To add a new chapter, create a file under `chapters/` and include it in [index.qmd](index.qmd) with `{{< include chapters/04_conclusion.qmd >}}`.

### References and Citations
Add BibTeX entries to [references.bib](references.bib) and cite them in prose:

- Single citation: `[@example2026key]` -> `[1]`
- Multiple citations: `[@key1; @key2]` -> `[1], [2]`
- With page range: `[@example2026key, pp. 4--6]`
- Narrative citation: `@example2026key showed that...`

References are formatted automatically using [ieee.csl](ieee.csl).

### Figures and Images
Place figures in `images/`. Export raster figures (`.png`, `.jpg`) at >= 300 DPI (at least 1050 px wide) and under 15 MB, and keep vector PDFs under 10 MB. `make check` warns if any figure is missing, low-DPI, or oversized.

Single figure:

```markdown
![Descriptive caption.](images/my_figure.png){#fig-myfig width="85%"}
```

Reference in text with `@fig-myfig`.

2x2 subfigure grid:

```markdown
::: {#fig-maps layout-ncol=2}
![Panel A](images/map_a.png){#fig-map-a}

![Panel B](images/map_b.png){#fig-map-b}

![Panel C](images/map_c.png){#fig-map-c}

![Panel D](images/map_d.png){#fig-map-d}

Overall figure caption.
:::
```

Reference the grid with `@fig-maps` or individual panels with `@fig-map-a`.

### Math, Theorems, Algorithms, and Tables

Numbered equation (reference with `@eq-linear`):

```markdown
$$
\mathbf{y} = \mathbf{X}\boldsymbol{\beta} + \boldsymbol{\varepsilon}
$$ {#eq-linear}
```

Theorem and proof (reference with `@thm-bound`):

```markdown
::: {#thm-bound}
## Runtime Bound
For $n$ points, the solver runs in $\mathcal{O}(n \log n)$ time.
:::

::: {.proof}
Proof details here.
:::
```

Algorithm block (reference with `\Cref{alg:myalgo}`):

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

Markdown table rendered with `booktabs` (reference with `@tbl-bench`):

```markdown
| Method | RMSE (m) | Runtime (s) |
|:-----------------------|---------:|------------:|
| Baseline | 0.42 | 1.8 |
| **Proposed** | **0.16** | **3.4** |

: Benchmark comparison. {#tbl-bench}
```

## Citation Styles and Journal Templates

By default, [_quarto.yml](_quarto.yml) uses `cite-method: citeproc` with `csl: ieee.csl`. To change citation styles, point `csl:` to another `.csl` file, or switch to native BibTeX via `cite-method: natbib` and `biblio-style: IEEEtran`.

To target a specific journal class, update `format: pdf:` in [_quarto.yml](_quarto.yml):

- IEEE: `documentclass: IEEEtran`, `classoption: [journal]` (or `[conference]`), `geometry: []`
- ACM: `documentclass: acmart`, `classoption: [sigconf]` (or `[acmsmall]`), `geometry: []`
- Elsevier: `documentclass: elsarticle`, `classoption: [preprint]` (or `[5p, twocolumn]`), `geometry: []`
- Copernicus: `documentclass: copernicus`, `classoption: [manuscript]`, `geometry: []`

You can also install official Quarto journal extensions with `quarto use template quarto-journals/ieee` and copy your `{{< include chapters/... >}}` lines into the generated root `.qmd`.
