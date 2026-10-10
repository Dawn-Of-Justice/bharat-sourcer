# Landing journey preview

All three source tabs use `src/YoutubeJourney.tsx` and `src/youtube-journey.css`.
These are illustrative walkthroughs, with no backend requests or saved demo projects.

The original source card stays visible throughout a continuous 22-second sequence:
source scanning, parts extraction, a user question, an updated part, seller
options, and a saved project. The final state stays visible until Replay.

Pause and Play control the shared animation timeline. Playback pauses when less
than 35% of the card is visible or the browser tab is hidden. Reduced motion
shows the completed layout. There are no slides or step-navigation buttons.

Each source has a distinct example:

- YouTube: automatic night light, cartoon circuit, glowing LED and moving current.
  The play button fades when scanning starts.
- Project links: plant watering, animated droplets, a question about three pots.
- Document: a quieter desk fan with animated blades and speed-control discussion.
  Document uploads remain unavailable and the preview is labelled as planned.

The before/after part descriptions share a grid cell. Reduced motion explicitly
hides the old description to prevent overlapping text.

Articles, supported maker blogs, and GitHub are grouped under Project links.
Existing URL detection and backend intake remain responsible for the source type.
The combined option accepts either supported article hosts or github.com.
The three source buttons use equal-width columns. Project links uses a chain
icon; Document uses the folded-page icon from `LandingIcons.tsx`.

## Branding

The header uses `public/brand-mark.svg`, with the same artwork in
`public/favicon.svg`: a recognizable B formed from angular teal circuit traces,
terminal pads, and warm orange nodes. The inline wordmark retains the Bharat Sourcer name. Keep these two
SVG assets synchronized when changing the logo.

Run `npm run dev` from `frontend/` to preview. Build with `npm run build` and
check lint with `npm run lint`.
