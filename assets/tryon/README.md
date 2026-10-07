# Try-on assets

Tracked inputs for the virtual try-on (docs/specs/09-virtual-tryon.md):
`mannequins/<id>/` holds a mannequin photo (`person.png`, 768x1024), its
precomputed CatVTON masks (`mask_upper.png`, `mask_lower.png`, `mask_overall.png`)
and a `meta.json` with source and licence.

Masks are computed once per mannequin with `make tryon-masks MANNEQUIN=<dir>`
(white = area to repaint).

CatVTON and its weights are NOT in this repo (CC BY-NC-SA 4.0, personal use only).
CatVTON is an external pinned clone (`make tryon-setup`); the weights are downloaded
into the ML cache dir.
