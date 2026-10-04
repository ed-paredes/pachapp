import type { AltLook } from '@/components/today/AltLookCard';
import type { LookPiece, LookProposal, LookReason } from '@/components/today/types';
import type { ApiProposal } from '@/hooks/useGenerateOutfits';
import type { fetchGarmentDetail } from '@/hooks/useGarments';

import { garmentName } from './garment-name';
import { imageUrl } from './image-url';
import { STYLE_LABELS } from './labels';

type Garment = Awaited<ReturnType<typeof fetchGarmentDetail>>;

/** Garments by id, as the proposals refer to them. */
export type GarmentIndex = ReadonlyMap<string, Garment>;

const SPARKLES = { ios: 'sparkles', android: 'auto_awesome', web: 'auto_awesome' } as const;

function pieceOf(item: ApiProposal['items'][number], garment: Garment): LookPiece {
  return {
    garmentId: garment.id,
    role: item.slot,
    name: garmentName(garment),
    imageUri: imageUrl(garment.img_cutout ?? garment.img_thumb),
    color: garment.colors?.[0]?.hex ?? null,
  };
}

/** "Casual · Formalidad 2/5": the most common style tag and the mean formality of the look. */
export function formalityLabel(garments: Garment[]): string | undefined {
  const levels = garments.flatMap((g) => (g.formality == null ? [] : [g.formality]));
  const tags = new Map<string, number>();
  garments.forEach((g) => g.style_tags?.forEach((tag) => tags.set(tag, (tags.get(tag) ?? 0) + 1)));
  const [lead] =
    [...tags.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))[0] ?? [];
  const parts: string[] = [];
  if (lead && lead in STYLE_LABELS) parts.push(STYLE_LABELS[lead as keyof typeof STYLE_LABELS]);
  if (levels.length) {
    const mean = levels.reduce((sum, level) => sum + level, 0) / levels.length;
    parts.push(`Formalidad ${Math.round(mean)}/5`);
  }
  return parts.length ? parts.join(' · ') : undefined;
}

/**
 * The engine's one-or-two-sentence explanation as "why this look" lines: each sentence is a line
 * (the bold lead of the card), so no text is invented on the client.
 */
export function reasonsOf(explanation: string): LookReason[] {
  const sentences = explanation.match(/[^.!?]+[.!?]+/g) ?? [explanation];
  return sentences
    .map((sentence) => sentence.trim())
    .filter(Boolean)
    .map((title) => ({ icon: SPARKLES, title, text: '' }));
}

function garmentsOf(proposal: ApiProposal, index: GarmentIndex): Garment[] | null {
  const found = proposal.items.map((item) => index.get(item.garment_id));
  return found.every((garment) => garment !== undefined) ? (found as Garment[]) : null;
}

/**
 * A proposal as Hoy shows it, or `null` while one of its garments is not known yet. No match
 * percentage (the score is uncalibrated) and no name (no template gives a meaningful one).
 */
export function toLookProposal(proposal: ApiProposal, index: GarmentIndex): LookProposal | null {
  const garments = garmentsOf(proposal, index);
  if (!garments) return null;
  return {
    pieces: proposal.items.map((item, i) => pieceOf(item, garments[i])),
    formalityLabel: formalityLabel(garments),
    reasons: reasonsOf(proposal.explanation),
  };
}

/** Alternatives have no meaningful name: the card is titled by its two lead pieces. */
export function toAltLook(id: string, proposal: ApiProposal, index: GarmentIndex): AltLook | null {
  const look = toLookProposal(proposal, index);
  if (!look) return null;
  const lead = look.pieces.filter((piece) => piece.role !== 'shoes' && piece.role !== 'accessory');
  return {
    id,
    name: (lead.length ? lead : look.pieces)
      .slice(0, 2)
      .map((piece, i) =>
        i === 0 ? piece.name : piece.name.charAt(0).toLowerCase() + piece.name.slice(1),
      )
      .join(' y '),
    pieces: look.pieces,
  };
}
