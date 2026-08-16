const agents = [
  { name: "Coordinator", role: "Routes work", tools: 7, color: "violet" },
  { name: "Sales", role: "Orders & customers", tools: 10, color: "blue" },
  { name: "Inventory", role: "Stock & locations", tools: 8, color: "cyan" },
  { name: "Purchasing", role: "Suppliers & POs", tools: 9, color: "amber" },
  { name: "Finance", role: "Cash & invoices", tools: 12, color: "rose" },
];

const agentCard = `{
  "paper": "arXiv:2607.17331v1",
  "core_idea": "Split ERP decisions across role-aligned agents, then gate risky writes with human approval.",
  "mechanism": ["plan", "execute", "reflect", "respond"],
  "evidence": {
    "simulation_days": 365,
    "orders_serviced": 639,
    "stockouts": 0,
    "rpa_stockouts": 302
  },
  "confidence": "promising, not production-proven",
  "limitations": ["synthetic data", "LLM-as-judge", "single SME setting"]
}`;

export default function Home() {
  return (
    <main>
      <nav className="nav shell" aria-label="Primary navigation">
        <a className="brand" href="#top" aria-label="RPL home">
          <span className="brand-mark">R</span>
          <span>Research, distilled.</span>
        </a>
        <div className="nav-links">
          <a href="#system">System</a>
          <a href="#evidence">Evidence</a>
          <a href="#agent-card">For agents</a>
        </div>
        <a className="source-link" href="https://arxiv.org/html/2607.17331v1" target="_blank" rel="noreferrer">
          Read original <span aria-hidden="true">↗</span>
        </a>
      </nav>

      <section className="hero shell" id="top">
        <div className="paper-meta">
          <span className="topic-pill">AI agents</span>
          <span>arXiv:2607.17331v1</span>
          <span>19 Jul 2026</span>
          <span>~8 min learn</span>
        </div>
        <div className="hero-grid">
          <div>
            <p className="eyebrow">The one thing to understand</p>
            <h1>What if your ERP could <em>run</em> the business—not just record it?</h1>
          </div>
          <div className="hero-summary">
            <p>
              This paper replaces one all-purpose AI with five specialists. A coordinator plans the work,
              agents act inside their roles, a reflector checks the result, and humans approve risky changes.
            </p>
            <div className="remember">
              <span>Remember this</span>
              <strong>Narrow roles make agent actions easier to choose, inspect, and control.</strong>
            </div>
          </div>
        </div>
      </section>

      <section className="section shell" id="system">
        <div className="section-heading">
          <div>
            <p className="eyebrow">01 · The system</p>
            <h2>Five specialists. One guarded loop.</h2>
          </div>
          <p>Each agent sees a smaller part of the company and only the tools needed for its job.</p>
        </div>

        <div className="system-map" aria-label="Agentic ERP system diagram">
          <div className="prompt-card">
            <span className="mini-label">Human request</span>
            <p>“A key supplier is late. Can we still fulfil our customer orders?”</p>
          </div>
          <div className="flow-arrow" aria-hidden="true">↓</div>
          <div className="orchestrator">
            <span className="mini-label">Orchestration loop</span>
            <div className="loop-steps">
              <div><b>1</b><span>Plan</span></div><i>→</i>
              <div><b>2</b><span>Execute</span></div><i>→</i>
              <div><b>3</b><span>Reflect</span></div><i>→</i>
              <div><b>4</b><span>Respond</span></div>
            </div>
            <p className="loop-note">If the check fails, replan once. If it still fails, ask a human.</p>
          </div>
          <div className="flow-arrow split" aria-hidden="true">↓</div>
          <div className="agent-grid">
            {agents.map((agent) => (
              <article className={`agent-card ${agent.color}`} key={agent.name}>
                <span className="agent-dot" />
                <h3>{agent.name}</h3>
                <p>{agent.role}</p>
                <small>{agent.tools} tools</small>
              </article>
            ))}
          </div>
          <div className="safety-bar">
            <span aria-hidden="true">◇</span>
            <div>
              <strong>Risk gate</strong>
              <p>High-value, unusual, or sensitive writes require human approval before reaching the ERP.</p>
            </div>
            <span className="status">Human in the loop</span>
          </div>
        </div>
      </section>

      <section className="section evidence-section" id="evidence">
        <div className="shell">
          <div className="section-heading inverse">
            <div>
              <p className="eyebrow">02 · What they found</p>
              <h2>Promising results—with a big asterisk.</h2>
            </div>
            <p>The strongest numbers come from a simulated tea-trading company, not a live enterprise.</p>
          </div>

          <div className="metric-grid">
            <article className="metric feature">
              <span>365-day simulation</span><strong>0</strong><p>stockouts with agentic AI</p>
              <div className="comparison"><b>302</b> with fixed RPA rules</div>
            </article>
            <article className="metric"><span>Orders serviced</span><strong>639</strong><p>vs. 300 with RPA</p></article>
            <article className="metric"><span>Ending cash</span><strong>+10.7%</strong><p>over the RPA baseline</p></article>
            <article className="metric"><span>Ablation</span><strong>−17 pts</strong><p>task completion when collapsed into one agent</p></article>
          </div>

          <div className="honesty-grid">
            <div>
              <p className="eyebrow">The honest reading</p>
              <h3>This is a useful architecture proposal, not proof that AI can safely run a real company.</h3>
            </div>
            <ul>
              <li><span>01</span>All evaluation data is synthetic.</li>
              <li><span>02</span>Response quality is judged by another LLM, not calibrated humans.</li>
              <li><span>03</span>It tests one simulated small business and one hosted model.</li>
            </ul>
          </div>
        </div>
      </section>

      <section className="section shell">
        <div className="section-heading">
          <div><p className="eyebrow">03 · The useful idea</p><h2>Why splitting agents might help</h2></div>
          <p>The paper’s central argument, translated from notation into plain language.</p>
        </div>
        <div className="formula-card">
          <div className="formula-visual">
            <div className="tool-cloud many">46 tools</div><span>becomes</span>
            <div className="tool-cloud few">≈ 9 tools<br /><small>per agent</small></div>
          </div>
          <div className="formula-copy">
            <span className="mini-label">Plain-language formula</span>
            <h3>Routing error + specialist tool error should be lower than choosing from every tool at once.</h3>
            <p>This depends on the router choosing the right specialist. The paper gives a structural argument and supporting ablation results, but not a universal mathematical guarantee.</p>
          </div>
        </div>
      </section>

      <section className="section shell" id="agent-card">
        <div className="agent-output">
          <div className="agent-output-copy">
            <p className="eyebrow">04 · Ready for agents</p>
            <h2>The same lesson, structured for a machine.</h2>
            <p>RPL does not hand another agent a vague paragraph. It exposes the idea, mechanism, evidence, confidence, and limitations as reusable data.</p>
            <div className="use-tags"><span>JSON</span><span>API</span><span>MCP</span><span>Markdown</span></div>
          </div>
          <pre aria-label="Machine-readable paper knowledge card"><code>{agentCard}</code></pre>
        </div>
      </section>

      <footer className="footer shell">
        <div><span className="brand-mark">R</span><strong>RPL</strong><span>Research Paper Layer</span></div>
        <p>Built to help humans and agents learn what matters.</p>
        <a href="https://github.com/emilsmeznieks/RPL" target="_blank" rel="noreferrer">Open source on GitHub ↗</a>
      </footer>
    </main>
  );
}
