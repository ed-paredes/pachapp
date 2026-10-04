"""Tunable defaults of the outfit engine (docs/specs/05-outfit-engine.md).

Every value here is a "valor por defecto, ajustable" of the spec; the ones the
spec leaves open (the section "Preguntas abiertas") say so. Nothing in this
module is read from the environment: the engine stays pure (DEV-REQ-002).
"""

from __future__ import annotations

# --- Generation budget (D1, ENG-REQ-009, ENG-REQ-025) ----------------------
BASE_TOP_K = 300  # bases kept after stage 1
BASE_TOP_K_MAX = 2000  # safety cap when K is widened (ENG-REQ-025)
BASE_TOP_K_GROWTH = 2  # K is multiplied by this while fewer than 5 proposals
PROPOSAL_COUNT = 5
STAGE1_CHUNK_ROWS = 400_000  # base combinations scored per numpy block
STAGE2_CHUNK_ROWS = 200_000  # (base, candidate) rows scored per numpy block
MAX_ACCESSORIES_CAP = 10  # internal bound on accessory columns

# --- Hard filters (ENG-REQ-003, ENG-REQ-007) --------------------------------
MAX_FORMALITY_SPREAD = 1
MAX_NON_NEUTRAL_COLORS = 2  # fixed by D18, not configurable
DEFAULT_FORMALITY = 3  # a garment still missing `formality` counts as mid-range

# --- C_color (D18). Open item: "umbrales de matiz" ---------------------------
HUE_SCORE_ANALOGOUS = 0.9  # delta-h <= 30 degrees
HUE_SCORE_COMPLEMENTARY = 0.5  # delta-h between 150 and 210 degrees
HUE_SCORE_OTHER = 0.1
HUE_ANALOGOUS_MAX_DEG = 30.0
HUE_COMPLEMENTARY_MIN_DEG = 150.0  # delta-h is folded to [0, 180], so 210 -> 150
# 0 or 1 non-neutral colours: "puntuacion alta" (same level as analogous).
COLOR_SCORE_FEW_COLORS = 0.9
# Two or more loud patterns at once: "penalizacion fuerte"; the spec gives no
# magnitude (open item), subtracted from the colour score before clamping.
LOUD_PATTERN_PENALTY = 0.4
LOUD_PATTERN_MIN_COUNT = 2

# --- C_style. Open item: equal weight of the three terms ---------------------
# The variance term is normalised by the largest variance the formality
# filter allows for two garments (spread 1 -> variance 0.25).
FORMALITY_VARIANCE_NORM = 0.25

# --- C_novelty. Open item: pair penalty / forgotten bonus magnitudes ---------
NOVELTY_DECAY_DAYS = 7.0
NEVER_WORN_DAYS = 10_000  # "un numero de dias muy grande"
PAIR_PENALTY = 0.15
FORGOTTEN_AFTER_DAYS = 60
FORGOTTEN_BONUS = 0.1
FORGOTTEN_BONUS_CAP = 0.3

# --- C_preference. Open item: the normalisation is a placeholder -------------
PREFERENCE_NEUTRAL = 0.5
PREFERENCE_TANH_SCALE = 3.0  # net liked-minus-disliked pair count for ~0.88

# --- MMR (ENG-REQ-014, ENG-REQ-015) ------------------------------------------
MMR_LAMBDA = 0.7
MAX_GARMENT_APPEARANCES = 2

# --- Slots / layers (DAT-REQ-006) --------------------------------------------
LAYER_BY_SLOT = {
    "outerwear": 4,
    "mid_layer": 3,
    "top": 2,
    "one_piece": 2,
    "bottom": 1,
    "shoes": 0,
    "accessory": None,
}

# --- Numerical tolerances -----------------------------------------------------
IMPROVEMENT_EPS = 1e-9  # an addition must beat the current total by this much
TIE_EPS = 1e-9  # scores closer than this are ties, resolved by the seed

# --- Explanations (ENG-REQ-018). Open item: exact templates and thresholds ---
EXPLANATION_TIE_RATIO = 0.9  # 2nd component joins when >= this fraction of the 1st
PREFERENCE_EXPLAIN_MIN = 0.55  # preference only explains when clearly above neutral
