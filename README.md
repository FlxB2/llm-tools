# llm-tools

Small, self-contained tools that LLM agents can pick up and reuse across projects. Each tool lives
in its own folder with its own README, has no build step, and can be copied into a project as is.
Scripts declare their dependencies inline, so `uv` runs them directly.

## Tools

| Tool | What it does |
| --- | --- |
| [editHTML](editHTML/) | A floating bar for any web page: edit text in place, tune margin, padding and gap, and switch between design variants marked up with `data-variants`. |
| [flattenPdfFades](flattenPdfFades/) | Makes gradient fades (soft masks) in exported PDFs render the same in every reader, macOS Preview included. |

How agents should use and add tools is in [AGENTS.md](AGENTS.md).

## License

Apache 2.0, see [LICENSE](LICENSE).
