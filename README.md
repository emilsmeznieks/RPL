# RPL — Research Paper Layer

RPL turns research papers into the essential knowledge humans and AI agents need to understand and reuse.

The first prototype explores [Agentic ERP (arXiv:2607.17331v1)](https://arxiv.org/abs/2607.17331) as a visual learning page. It highlights the core idea, system architecture, evidence, limitations, and a machine-readable knowledge card.

## Run locally

Requires Node.js 22.13 or newer.

```bash
npm install
npm run dev
```

Then open `http://localhost:3000`.

## Current scope

- Visual, human-friendly paper explanation
- Evidence and limitations shown together
- Plain-language explanation of the key technical idea
- Structured JSON-style output for AI agents
- Responsive single-page prototype

## Roadmap

- Accept any arXiv URL
- Extract grounded knowledge from paper sections
- Compare related papers
- Export JSON, Markdown, and MCP resources
- Save personal research collections

## Contributing

Ideas and pull requests are welcome. Please open an issue before starting a large change so we can align on direction.

## License

[MIT](LICENSE)

