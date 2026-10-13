import type { ImageSourcePropType } from 'react-native';

/** The try-on model the settings screen can preview. */
export type ModelGender = 'woman' | 'man';

/**
 * The 12 bundled previews (gender x skin tone 1-6): the shipped dummy pipeline run once on the
 * same outfit (pink tee, black shorts) for each base. Metro needs literal `require` paths.
 */
const PREVIEWS: Record<ModelGender, Record<number, ImageSourcePropType>> = {
  woman: {
    1: require('../../assets/tryon-preview/woman-t1.webp'),
    2: require('../../assets/tryon-preview/woman-t2.webp'),
    3: require('../../assets/tryon-preview/woman-t3.webp'),
    4: require('../../assets/tryon-preview/woman-t4.webp'),
    5: require('../../assets/tryon-preview/woman-t5.webp'),
    6: require('../../assets/tryon-preview/woman-t6.webp'),
  },
  man: {
    1: require('../../assets/tryon-preview/man-t1.webp'),
    2: require('../../assets/tryon-preview/man-t2.webp'),
    3: require('../../assets/tryon-preview/man-t3.webp'),
    4: require('../../assets/tryon-preview/man-t4.webp'),
    5: require('../../assets/tryon-preview/man-t5.webp'),
    6: require('../../assets/tryon-preview/man-t6.webp'),
  },
};

/** The preview of a gender and tone id; an id outside 1-6 falls back to the first tone. */
export function tryOnPreview(gender: ModelGender, tone: number): ImageSourcePropType {
  return PREVIEWS[gender][tone] ?? PREVIEWS[gender][1];
}
