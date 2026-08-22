const markdownIt = require("markdown-it");
const markdownItFootnote = require("markdown-it-footnote");

module.exports = function (eleventyConfig) {
  // Raw inline HTML (<u>, <sup>) must survive: the conversion script uses
  // HTML passthrough for rend=underline/superscript, which have no native
  // Markdown syntax (confirmed absent from TEI Publisher's own Markdown
  // exporter too -- see sveltia-migration-assessment.md). Sveltia's own
  // RichText editor doesn't document support for raw HTML passthrough or
  // footnote syntax either (only bold/italic/strikethrough/code/link/
  // headings/lists/quote are confirmed toolbar buttons) -- per the
  // maintainer directly (github.com/sveltia/sveltia-cms/discussions/560),
  // the documented fallback for anything else is the editor's raw-
  // Markdown mode, which is why `letters.body` keeps that mode available
  // in admin/config.yml rather than gambling on WYSIWYG round-tripping.
  //
  // markdown-it-footnote: CommonMark (and markdown-it core) has no native
  // [^n] footnote syntax -- without this plugin, [^1] renders as literal
  // bracket text (confirmed by inspecting the built output before adding
  // this). The [^n]/[^n]: convention was already chosen deliberately in
  // convert.py to match this plugin and the wider footnote convention
  // used across most Markdown toolchains, not invented ad hoc.
  const md = markdownIt({ html: true, breaks: false }).use(markdownItFootnote);
  eleventyConfig.setLibrary("md", md);

  eleventyConfig.addPassthroughCopy("content/**/*.{png,jpg,jpeg,svg}");
  // admin/ lives outside the `content` input dir, so it needs an explicit
  // passthrough to land at _site/admin/ (Sveltia's entry point + config.yml).
  eleventyConfig.addPassthroughCopy({ admin: "admin" });

  eleventyConfig.addCollection("letters", (api) =>
    api.getFilteredByGlob("content/letters/*.md").sort((a, b) => {
      const da = a.data.correspondence?.date || "";
      const db = b.data.correspondence?.date || "";
      return da.localeCompare(db);
    })
  );
  eleventyConfig.addCollection("people", (api) =>
    api.getFilteredByGlob("content/people/*.md").sort((a, b) => (a.data.name || "").localeCompare(b.data.name || ""))
  );
  eleventyConfig.addCollection("places", (api) =>
    api.getFilteredByGlob("content/places/*.md").sort((a, b) => (a.data.name || "").localeCompare(b.data.name || ""))
  );
  eleventyConfig.addCollection("works", (api) =>
    api.getFilteredByGlob("content/works/*.md").sort((a, b) => (a.data.name || "").localeCompare(b.data.name || ""))
  );

  // GitHub Pages project sites are served from /<repo-name>/, not the
  // domain root -- but every internal link in this project is root-
  // absolute, including ones baked directly into converted Markdown by
  // scripts/convert.py (e.g. "[Ezra Pound](/people/poun85/)"), which
  // Eleventy's own pathPrefix/url filter has no reach into. Rather than
  // re-run the conversion with a deploy-specific prefix baked into the
  // content (which would break local dev at "/"), rewrite root-absolute
  // href/src attributes in the rendered HTML at build time instead --
  // keeps content portable, only the build output changes.
  const pathPrefix = process.env.PATH_PREFIX || "/";
  if (pathPrefix !== "/") {
    const prefix = pathPrefix.replace(/\/$/, "");
    eleventyConfig.addTransform("path-prefix", (content, outputPath) => {
      if (!outputPath || !outputPath.endsWith(".html")) return content;
      return content.replace(/(href|src)="\/(?!\/)/g, `$1="${prefix}/`);
    });
  }

  return {
    pathPrefix,
    dir: {
      input: "content",
      includes: "_includes",
      output: "_site",
    },
    markdownTemplateEngine: "njk",
    htmlTemplateEngine: "njk",
  };
};
