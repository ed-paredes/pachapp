import type { ApiProposal } from '../src/hooks/useGenerateOutfits';
import { formalityLabel, reasonsOf, toAltLook, toLookProposal } from '../src/lib/look-mapper';

const garment = (id: string, overrides: Record<string, unknown> = {}) =>
  ({
    id,
    category: 'top',
    subcategory: 'camiseta',
    colors: [{ name: 'blanco', hex: '#FFFFFF', lab: [100, 0, 0], proportion: 1 }],
    img_thumb: `thumb/${id}.webp`,
    img_cutout: `cutout/${id}.png`,
    formality: 2,
    style_tags: ['casual'],
    material: null,
    ...overrides,
  }) as never;

const proposal = (explanation = 'Marino y camel: neutros clásicos.'): ApiProposal => ({
  items: [
    { garment_id: 'a', slot: 'top', layer: 2 },
    { garment_id: 'b', slot: 'bottom', layer: 3 },
    { garment_id: 'c', slot: 'shoes', layer: 4 },
  ],
  score: 0.8,
  score_breakdown: { color: 1, style: 1, novelty: 1, preference: 0, total: 0.8 },
  explanation,
});

const index = new Map([
  ['a', garment('a')],
  ['b', garment('b', { category: 'bottom', subcategory: 'vaquero', formality: 3 })],
  ['c', garment('c', { category: 'shoes', subcategory: null, img_cutout: null })],
]);

describe('toLookProposal', () => {
  it('maps slots, names, images and colours, with no match percentage and no name', () => {
    const look = toLookProposal(proposal(), index);

    expect(look?.pieces.map((piece) => [piece.garmentId, piece.role, piece.name])).toEqual([
      ['a', 'top', 'Camiseta blanca'],
      ['b', 'bottom', 'Vaquero blanco'],
      ['c', 'shoes', 'Calzado blanco'],
    ]);
    expect(look?.pieces[0]).toMatchObject({
      imageUri: 'http://localhost:8000/images/cutout/a.png',
      color: '#FFFFFF',
    });
    // No cutout: the thumbnail is the picture.
    expect(look?.pieces[2].imageUri).toBe('http://localhost:8000/images/thumb/c.webp');
    expect(look?.matchPercent).toBeUndefined();
    expect(look?.name).toBeUndefined();
  });

  it('is null while a garment is not known yet', () => {
    const partial = new Map([['a', garment('a')]]);
    expect(toLookProposal(proposal(), partial)).toBeNull();
    expect(toAltLook('1', proposal(), partial)).toBeNull();
  });
});

describe('formalityLabel', () => {
  it('joins the commonest style and the mean formality', () => {
    expect(formalityLabel([garment('a'), garment('b', { formality: 3 })])).toBe(
      'Casual · Formalidad 3/5',
    );
  });

  it('skips what the garments do not have', () => {
    expect(formalityLabel([garment('a', { formality: null, style_tags: [] })])).toBeUndefined();
    expect(formalityLabel([garment('a', { style_tags: null })])).toBe('Formalidad 2/5');
  });
});

describe('reasonsOf', () => {
  it('turns each sentence of the explanation into a line, inventing nothing', () => {
    expect(
      reasonsOf('Marino y camel: neutros clásicos. Hace 3 semanas que no usas tu camisa.').map(
        (reason) => [reason.title, reason.text],
      ),
    ).toEqual([
      ['Marino y camel: neutros clásicos.', ''],
      ['Hace 3 semanas que no usas tu camisa.', ''],
    ]);
  });
});

describe('toAltLook', () => {
  it('titles the card by its two lead pieces', () => {
    expect(toAltLook('2', proposal(), index)).toMatchObject({
      id: '2',
      name: 'Camiseta blanca y vaquero blanco',
    });
  });
});
