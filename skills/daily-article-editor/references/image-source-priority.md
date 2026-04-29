# Image Source Priority

## Source Routing By Slot

Do not use one universal source order.
Route by slot type instead.

- `hero`
  - media event or person photos
  - official event photos
  - official person photos
  - archive material

- `process`
  - media or interview coverage
  - official working-scene photos
  - original social posts
  - archive material

- `object`
  - official product or project images
  - media close-ups or clean documentary photos
  - release or launch coverage

- `achievement`
  - media event photos
  - official event photos
  - result screenshots only when they add proof

- `archive`
  - historical material
  - older media coverage
  - original post screenshots

## Selection Rules

- Prefer the image that best matches the paragraph, not the easiest source.
- Prefer event and documentary photos over polished brand graphics for `hero` and `achievement`.
- Prefer official product images for `object`.
- Prefer original working-scene images for `process`.
- Use screenshots only when the page itself is evidence.
- Leave the slot empty if no candidate is strong enough.

## Automatic Down-Ranks

- Full-page website screenshots
- Images with strong page chrome or navigation
- Marketing banners with large slogans
- Images with heavy UI noise
- Repeated use of the same image across slots
- Repeated use of the same source page across adjacent slots

## Screenshot Rules

Use screenshots only when:

- the page or post itself is the fact being cited
- the result table or post is the proof point
- there is no better documentary photo

Do not use screenshots when:

- a clean news or documentary image exists
- the screenshot would carry navigation, branding, or unrelated page elements
- the same point can be shown with a better image asset

## Paper / Report Figures (`好论文` Special Rules)

A `好论文` article must source charts, figures, and diagrams **from the
underlying paper or report itself** whenever possible. Generic illustrations
or stock images are a downgrade — the column's promise is mechanism, and
mechanism reads through figures.

### Where the figures live

Most modern research-blog publishers (Anthropic, Google DeepMind, OpenAI,
Hugging Face, Cohere, Microsoft Research, etc.) ship their post images
through a CDN (often `*-cdn.<domain>.com/images/...`). The source page
references them in two ways:

1. **Direct `<img src="...">`** — easiest to find with `grep`
2. **Next.js / image-optimization wrappers** — the real URL is encoded
   inside `src="/_next/image?url=..."`. Use `grep -oE 'src="[^"]+"'` and
   then URL-decode anything that contains `/_next/image?url=`.

### Extract pattern (one-shot)

```bash
# For an Anthropic / Next.js-style page:
curl -sL "$URL" -A "Mozilla/5.0" -o /tmp/page.html
grep -oE 'src="[^"]*\.(png|jpg|svg|webp)' /tmp/page.html | sort -u
# Plus, for /_next/image-wrapped sources:
grep -oE 'url=https?%3A%2F%2F[^"&]+\.(png|jpg|svg|webp)' /tmp/page.html | \
  sed -e 's/^url=//' -e 's/%3A/:/g' -e 's/%2F/\//g' | sort -u
```

Each candidate URL should:

- HEAD-check return `200` with `content-type: image/...`
- Be at the highest resolution available (`-1920x1080.png` over `-800x450`)
- Have a textual caption / alt text in the source page that you can quote
  in the article (don't invent captions)

### Selection by paragraph

When the article cites a specific number or claim, the paragraph that makes
that claim should be **adjacent to the figure that visualizes it**. Follow
this mapping:

| article makes claim about | figure to use |
|---|---|
| a regression / elasticity / correlation | scatter / line plot from the source |
| a group comparison (group A vs group B %) | bar chart from the source |
| a distribution / breakdown / where-it-goes | pie / stacked-bar from the source |
| a step-by-step mechanism | mechanism diagram from the source / paper |
| a benchmark result | benchmark table screenshot from the paper |

### Don't

- Don't recreate the figure from scratch unless the original is unusable
  (broken link, wrong language, missing axes labels). Recreating loses the
  source's authority.
- Don't use the page's OG share illustration as the hero of a `好论文`
  article. The hero of a `好论文` article should be the most important
  chart of the report — the one that, if the reader sees only this one
  image, still tells them what the report found.
- Don't crop figures. If a figure is hard to read at body-text width, use
  the source's own image-optimization endpoint (`?w=1920` or similar) and
  let the frontend handle responsive sizing.
- Don't forget the caption credit. Required form:
  `*图注：……来源：[Publisher](https://...)*`

### Fallback

If the source post's figures are unusable (e.g. a press release with only a
logo, or a paper that uses figures behind a paywall), the next-best option
is a `data-piece` self-rendered chart using the article's own data table.
Use a small, headless tool (matplotlib / Vega-Lite) and **always include
the source data table in the article body so the chart is reproducible**.

A blank slot beats a fabricated chart every time.
