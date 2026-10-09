# Routing validation for v0.27.0

The free live probe covered 17 part names across seven enabled sellers (119 combinations).
Search and a subsequent page verification pass used 200 HTTP requests in total, including
robots.txt, redirects and product JSON requests, below the 390-request cap. No AI calls
were made. Raw observations remain ignored under `backend/.data/`.

| Seller | Parts with a title-gate match in the first five results |
| --- | ---: |
| Robocraze | 14/17 |
| Quartz Components | 15/17 |
| ThinkRobotics | 11/17 |
| Zbotic | 11/17 |
| Sharvi Electronics | 11/17 |
| Rytronics | 10/17 |
| Compoindia | 10/17 |

These are automated relevance counts, **not verified accuracy**. The plan's baseline
used human judgement, so these numbers cannot establish a like-for-like improvement or
prove the target was met. For example, the gate can accept a Raspberry Pi Pico W for a
generic Pico name and adjacent modules mentioning Pico. The spec judge and compatibility
checks remain necessary; human review of all top-five sets is still needed for accuracy.

After integrating the page reader, one sampled page from each seller returned a structured
offer. Quartz's sampled Arduino page declared `2,650.00` INR and parsed successfully as
`2650.00`. This is a dated seller-declared observation, not a current price guarantee or
a purchase recommendation. Historical fixture excerpts are labelled separately; some are
truncated and are not treated as complete JSON-LD.

Local combined regression result: 1,248 passed, 3 skipped. The skips concern optional
integration/runtime dependencies. Ruff lint, formatting and OpenAPI drift are checked
separately. CI also validates each stacked PR with the Linux PDF runtime installed.

Run `python scripts/probe_routing.py` from `backend/` to reproduce the bounded probe.
`--verify-only` reuses saved candidate URLs and the cumulative request count.
