// Markdown、公式和未受信任内容的安全渲染。
(function () {
  const math = {
    name: 'math', level: 'inline',
    start(src) { const m = /\$|\\[([]/.exec(src); return m ? m.index : undefined; },
    tokenizer(src) {
      const patterns = [
        [/^\$\$([\s\S]+?)\$\$/, true],
        [/^\\\[([\s\S]+?)\\\]/, true],
        [/^\\\(([\s\S]+?)\\\)/, false],
        [/^\$(?![\s$])([^\n$]+?)(?<!\s)\$(?!\d)/, false]
      ];
      for (const [pattern, display] of patterns) {
        const m = pattern.exec(src);
        if (m) return { type: 'math', raw: m[0], text: m[1], display };
      }
    },
    renderer(token) {
      return katex.renderToString(token.text, { displayMode: token.display, throwOnError: false, trust: false });
    }
  };
  if (window.marked && window.katex && window.DOMPurify) {
    marked.use({ gfm: true, breaks: true, extensions: [math] });
  }
  window.renderRich = function (element, text) {
    element.classList.add('rich');
    if (!window.marked || !window.katex || !window.DOMPurify) { element.textContent = text; return; }
    try {
      element.innerHTML = DOMPurify.sanitize(marked.parse(text), {
        USE_PROFILES: { html: true, mathMl: true, svg: true }, FORBID_TAGS: ['img', 'iframe', 'object', 'embed', 'form', 'style']
      });
      for (const a of element.querySelectorAll('a')) { a.target = '_blank'; a.rel = 'noopener noreferrer'; }
    } catch { element.textContent = text; }
  };
})();
