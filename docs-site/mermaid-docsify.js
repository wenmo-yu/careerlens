(() => {
  const mermaid = window.mermaid;
  mermaid?.initialize({
    startOnLoad: false,
    securityLevel: 'strict',
    flowchart: { useMaxWidth: false },
    sequence: { useMaxWidth: false },
    state: { useMaxWidth: false },
  });

  let nextDiagramId = 0;

  async function renderDiagram(block) {
    const code = block.querySelector('code');
    if (!code) return;

    const figure = document.createElement('figure');
    figure.className = 'mermaid-diagram';
    figure.textContent = '正在绘制流程图…';
    block.replaceWith(figure);

    // Mermaid computes text sizes from the DOM. A closed <details> has no layout.
    const staging = document.createElement('div');
    staging.className = 'mermaid-staging';
    staging.setAttribute('aria-hidden', 'true');
    document.body.append(staging);

    try {
      const id = `tutorial-diagram-${++nextDiagramId}`;
      const { svg, bindFunctions } = await mermaid.render(id, code.textContent, staging);
      if (!figure.isConnected) return;
      figure.innerHTML = svg;
      figure.tabIndex = 0;
      figure.setAttribute('aria-label', '流程图，可横向滚动');
      bindFunctions?.(figure);
    } catch {
      if (!figure.isConnected) return;
      const details = document.createElement('details');
      const summary = document.createElement('summary');
      summary.textContent = '流程图暂时无法显示，展开可查看图的源码';
      details.append(summary, block);
      figure.replaceWith(details);
    } finally {
      staging.remove();
    }
  }

  window.$docsify.plugins.push((hook) => {
    // Docsify replaces the article after every route change, including history navigation.
    hook.doneEach(() => {
      document.querySelectorAll('.markdown-section pre[data-lang="mermaid"]').forEach(renderDiagram);
    });
  });
})();
