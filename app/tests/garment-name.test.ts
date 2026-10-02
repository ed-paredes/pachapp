import { garmentName } from '@/lib/garment-name';

const blue = [{ name: 'azul' }];

describe('garmentName', () => {
  it('composes subcategory, dominant colour and material', () => {
    expect(
      garmentName({ category: 'top', subcategory: 'camiseta', colors: blue, material: 'algodón' }),
    ).toBe('Camiseta azul de algodón');
  });

  it('falls back to the category label without a subcategory', () => {
    expect(garmentName({ category: 'shoes', colors: [{ name: 'negro' }] })).toBe('Calzado negro');
  });

  it('uses a generic noun when neither category nor subcategory exist', () => {
    expect(garmentName({ category: null })).toBe('Prenda');
  });

  it('skips missing colour and material', () => {
    expect(garmentName({ category: 'outerwear', subcategory: 'abrigo', colors: null })).toBe(
      'Abrigo',
    );
    expect(garmentName({ category: 'top', subcategory: 'camisa', colors: [] })).toBe('Camisa');
  });

  it('uses the first (dominant) colour only', () => {
    expect(
      garmentName({
        category: 'top',
        subcategory: 'jersey',
        colors: [{ name: 'gris' }, { name: 'rojo' }],
      }),
    ).toBe('Jersey gris');
  });

  it('makes the colour agree with a feminine noun', () => {
    expect(
      garmentName({ category: 'top', subcategory: 'camiseta', colors: [{ name: 'negro' }] }),
    ).toBe('Camiseta negra');
    expect(
      garmentName({ category: 'bottom', subcategory: 'falda midi', colors: [{ name: 'rojo' }] }),
    ).toBe('Falda midi roja');
  });

  it('pluralises the colour for plural nouns', () => {
    expect(
      garmentName({ category: 'shoes', subcategory: 'botas', colors: [{ name: 'marrón' }] }),
    ).toBe('Botas marrones');
    expect(
      garmentName({ category: 'shoes', subcategory: 'zapatillas', colors: [{ name: 'negro' }] }),
    ).toBe('Zapatillas negras');
  });

  it('pluralises colours without gender too', () => {
    expect(
      garmentName({ category: 'bottom', subcategory: 'bermudas', colors: [{ name: 'gris' }] }),
    ).toBe('Bermudas grises');
    expect(
      garmentName({ category: 'bottom', subcategory: 'vaqueros', colors: [{ name: 'azul' }] }),
    ).toBe('Vaqueros azules');
    expect(
      garmentName({ category: 'bottom', subcategory: 'pantalón', colors: [{ name: 'gris' }] }),
    ).toBe('Pantalón gris');
  });

  it('keeps invariable colours invariable in the plural', () => {
    for (const name of ['camel', 'beige', 'burdeos', 'denim', 'marino']) {
      expect(garmentName({ category: 'bottom', subcategory: 'bermudas', colors: [{ name }] })).toBe(
        `Bermudas ${name}`,
      );
    }
  });

  it('agrees gender and number together for -o colours', () => {
    expect(
      garmentName({ category: 'bottom', subcategory: 'bermudas', colors: [{ name: 'rojo' }] }),
    ).toBe('Bermudas rojas');
    expect(
      garmentName({ category: 'shoes', subcategory: 'zapatos', colors: [{ name: 'blanco' }] }),
    ).toBe('Zapatos blancos');
  });

  it('leaves invariable colours alone', () => {
    expect(
      garmentName({ category: 'top', subcategory: 'camiseta', colors: [{ name: 'beige' }] }),
    ).toBe('Camiseta beige');
  });
});
