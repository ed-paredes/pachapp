import type { IconName } from '@/components/ui/icons';

/** Slot a piece fills in a look; same values as the outfit engine's `OutfitSlot` (ENG-REQ-016). */
export type LookRole =
  'outerwear' | 'mid_layer' | 'top' | 'one_piece' | 'bottom' | 'shoes' | 'accessory';

/** One garment of a proposed look, already resolved for display. */
export type LookPiece = {
  garmentId: string;
  role: LookRole;
  /** Composed garment name (`garmentName`). */
  name: string;
  /** Cutout or thumbnail URL; the piece is not drawn without it. */
  imageUri: string | null;
  /** Dominant colour (hex) used to tint thumbnails. */
  color?: string | null;
};

/** One line of the "why this look" list (built from the engine's `explanation`/`score_breakdown`). */
export type LookReason = { icon: IconName; title: string; text: string };

/** Display shape of an outfit proposal, mirroring the planned engine response (ENG-REQ-014/018). */
export type LookProposal = {
  /** Look name; hidden when absent. */
  name?: string;
  pieces: LookPiece[];
  /** e.g. "Casual · Formalidad 2/5"; the tag is hidden when absent. */
  formalityLabel?: string;
  /** Score as a whole percentage; the badge is hidden when absent. */
  matchPercent?: number;
  reasons?: LookReason[];
};

export function matchLabel(percent: number): string {
  return `${Math.round(percent)}% match`;
}
