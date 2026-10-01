/**
 * Propuesta de tokens para el tema "Probador".
 * NO sustituir src/theme a ciegas: fusionar con la estructura existente
 * (mantener nombres/exports actuales y añadir o ajustar valores).
 */

export const colors = {
  bg: '#F6F3EE', // lino — fondo de pantalla
  surface: '#FFFFFF', // tarjetas
  surface2: '#EFEAE2', // arena — chips, pistas de meter, botones secundarios
  surface3: '#E7E0D5',
  ink: '#1F1B16', // texto principal, botón primario, nav
  ink2: '#6B6359', // texto secundario
  ink3: '#A39A8E', // placeholders, contadores
  line: '#E4DDD2', // bordes y separadores
  accent: '#B5562F', // terracota — acento, botón Añadir, enlaces
  accentSoft: '#F4E3D9',
  ok: '#4F7A5A',
  okSoft: '#E3EEE5',
  info: '#3E6A8A',
  infoSoft: '#E1EBF2',
  warn: '#A3741F',
  warnSoft: '#F6ECD6',
  danger: '#B23A30',
  tintBase: '#F1ECE4', // base sobre la que se tiñe el fondo de cada prenda
} as const;

export const radius = {
  sm: 12,
  md: 18,
  lg: 28,
  pill: 999,
} as const;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  xxl: 28,
  screen: 16, // margen lateral
} as const;

// RN >= 0.76 soporta la prop de estilo `boxShadow` (también en web).
export const shadow = {
  card: '0px 1px 2px rgba(31,27,22,0.04), 0px 8px 24px rgba(31,27,22,0.06)',
  raised: '0px 2px 4px rgba(31,27,22,0.05), 0px 20px 50px rgba(31,27,22,0.12)',
} as const;

export const fonts = {
  // Nombres según @expo-google-fonts; ajustar a los que ya se carguen en la app.
  display: 'Fraunces_400Regular',
  displayItalic: 'Fraunces_400Regular_Italic',
  displayBold: 'Fraunces_600SemiBold',
  body: 'Manrope_400Regular',
  bodyMedium: 'Manrope_500Medium',
  bodySemibold: 'Manrope_600SemiBold',
} as const;

export const type = {
  hero: { fontFamily: fonts.display, fontSize: 44, lineHeight: 46, letterSpacing: -0.9 },
  title: { fontFamily: fonts.display, fontSize: 34, lineHeight: 37, letterSpacing: -0.6 },
  section: { fontFamily: fonts.displayBold, fontSize: 20, lineHeight: 26 },
  stat: { fontFamily: fonts.display, fontSize: 28, lineHeight: 30 },
  eyebrow: { fontFamily: fonts.bodyMedium, fontSize: 12, letterSpacing: 1.4, textTransform: 'uppercase' as const },
  body: { fontFamily: fonts.body, fontSize: 15, lineHeight: 22 },
  label: { fontFamily: fonts.bodyMedium, fontSize: 13.5 },
  caption: { fontFamily: fonts.body, fontSize: 12.5, lineHeight: 17 },
} as const;

export const breakpoints = {
  twoColumns: 880, // Hoy y Detalle pasan a 2 columnas
} as const;

/**
 * Fondo teñido para una prenda: mezcla su color dominante con `tintBase`.
 * Sustituye a CSS `color-mix(in srgb, <color> 16%, #F1ECE4)` de la maqueta.
 */
export function tint(hex: string, amount = 0.16, base: string = colors.tintBase): string {
  const parse = (h: string) => {
    const n = parseInt(h.replace('#', '').padEnd(6, '0').slice(0, 6), 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255] as const;
  };
  const [r1, g1, b1] = parse(hex);
  const [r2, g2, b2] = parse(base);
  const mix = (a: number, b: number) => Math.round(a * amount + b * (1 - amount));
  return `rgb(${mix(r1, r2)}, ${mix(g1, g2)}, ${mix(b1, b2)})`;
}
