import { useLocalSearchParams, useRouter } from 'expo-router';
import { useEffect, useRef, useState, type MutableRefObject, type ReactNode } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import { ApiError } from '@/api-client/errors';
import { centeredContentStyle } from '@/components/ContentContainer';
import type { components } from '@/api-client/schema';
import { Chip } from '@/components/Chip';
import { HeroImage } from '@/components/GarmentImage';
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';
import { LoadingState } from '@/components/LoadingState';
import { useCompleteReview, usePatchGarment, type GarmentPatch } from '@/hooks/useGarmentMutations';
import { useGarment } from '@/hooks/useGarments';
import { useSettings } from '@/hooks/useSettings';
import { imageUrl } from '@/lib/image-url';
import {
  CATEGORY_LABELS,
  CATEGORY_ORDER,
  MATERIAL_SUGGESTIONS,
  PATTERN_LABELS,
  PATTERN_ORDER,
  SEASON_LABELS,
  SEASON_ORDER,
  STYLE_LABELS,
  STYLE_ORDER,
} from '@/lib/labels';
import { buildColors, MAX_COLORS, PALETTE_NAMES, paletteHex } from '@/lib/palette';
import { colors as theme, fontFamilies, fontSizes, lineHeights, radii, spacing } from '@/theme';

type Garment = components['schemas']['GarmentDetail'];

const DEFAULT_NEEDS_REVIEW_THRESHOLD = 0.7;
const DEFAULT_COLOR_REVIEW_THRESHOLD = 0.7;
const MAX_STYLE_TAGS = 3;
const LEVELS = [1, 2, 3, 4, 5];
/** The review screen spends less of the window on the image so the fields to check fit above the fold. */
const REVIEW_HERO_HEIGHT_RATIO = 0.24;
const SAVE_ERROR = 'No se pudo guardar el cambio. Inténtalo de nuevo.';

type FieldName =
  | 'category'
  | 'subcategory'
  | 'colors'
  | 'pattern'
  | 'formality'
  | 'style_tags'
  | 'seasons'
  | 'warmth'
  | 'material';

const AI_FIELDS: Exclude<FieldName, 'colors'>[] = [
  'category',
  'subcategory',
  'pattern',
  'formality',
  'style_tags',
  'seasons',
  'warmth',
  'material',
];

/** Order in which the fields are listed, both under "Por revisar" and in the summary rows. */
const FIELD_ORDER: FieldName[] = [
  'category',
  'subcategory',
  'colors',
  'pattern',
  'formality',
  'style_tags',
  'seasons',
  'warmth',
  'material',
];

const FIELD_LABELS: Record<FieldName, string> = {
  category: 'Categoría',
  subcategory: 'Subcategoría',
  colors: 'Colores',
  pattern: 'Estampado',
  formality: 'Formalidad',
  style_tags: 'Estilos',
  seasons: 'Temporadas',
  warmth: 'Abrigo',
  material: 'Material',
};

/** Hints shown inside the editor when the label alone is not enough. */
const FIELD_HINTS: Partial<Record<FieldName, string>> = {
  formality: '1 = informal, 5 = formal',
  style_tags: `Hasta ${MAX_STYLE_TAGS}`,
  warmth: '1 = fresco, 5 = muy abrigado',
};

/** Fields that close their row once one value is saved (single choice or free text). */
const COLLAPSE_AFTER_SAVE = new Set<FieldName>([
  'category',
  'subcategory',
  'pattern',
  'formality',
  'warmth',
  'material',
]);

const EMPTY_SUMMARY = 'Sin definir';

function isEmpty(value: unknown): boolean {
  return (
    value === null || value === undefined || value === '' || (Array.isArray(value) && !value.length)
  );
}

/**
 * Fields to highlight as doubtful (UI-REQ-021). Computed once from the garment
 * as it was when the screen opened: an attribute is doubtful when its
 * `ai_confidence` is under `needs_review_threshold`, or when it has no value
 * while the garment is pending review; colours use `color_confidence` and
 * `color_review_threshold`.
 */
function computeHighlights(
  garment: Garment,
  needsReviewThreshold: number,
  colorReviewThreshold: number,
): Set<FieldName> {
  const highlighted = new Set<FieldName>();
  for (const field of AI_FIELDS) {
    const confidence = garment.ai_confidence?.[field]?.confidence;
    const low = confidence !== undefined && confidence < needsReviewThreshold;
    if (low || (garment.needs_review && isEmpty(garment[field]))) {
      highlighted.add(field);
    }
  }
  const colorLow =
    garment.color_confidence !== null && garment.color_confidence < colorReviewThreshold;
  if (colorLow || (garment.needs_review && isEmpty(garment.colors))) {
    highlighted.add('colors');
  }
  return highlighted;
}

/**
 * Revisión (Review): cutout, the doubtful fields expanded under "Por revisar", every other
 * field as a one-line summary that expands in place, and the single sticky
 * "Revisión terminada" button (UI-REQ-021, D19).
 */
export default function ReviewScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const garment = useGarment(id);
  const settings = useSettings();

  if (garment.isPending || (settings.isPending && !settings.isError)) {
    return <LoadingState />;
  }
  if (garment.isError && !garment.data) {
    if (garment.error instanceof ApiError && garment.error.status === 404) {
      return (
        <EmptyState
          title="No encontramos esta prenda"
          description="Puede que se haya eliminado. Vuelve al armario."
        />
      );
    }
    return <ErrorState message={garment.error.message} onRetry={() => void garment.refetch()} />;
  }
  return (
    <ReviewForm
      key={garment.data?.id}
      garment={garment.data as Garment}
      needsReviewThreshold={settings.data?.needs_review_threshold ?? DEFAULT_NEEDS_REVIEW_THRESHOLD}
      colorReviewThreshold={settings.data?.color_review_threshold ?? DEFAULT_COLOR_REVIEW_THRESHOLD}
    />
  );
}

type Draft = Partial<Pick<Garment, Exclude<FieldName, 'colors'>>> & {
  colors?: Garment['colors'];
};

function ReviewForm({
  garment,
  needsReviewThreshold,
  colorReviewThreshold,
}: {
  garment: Garment;
  needsReviewThreshold: number;
  colorReviewThreshold: number;
}) {
  const router = useRouter();
  const patch = usePatchGarment(garment.id);
  const complete = useCompleteReview(garment.id);
  // Frozen on first render: editing never clears the highlight, only "Revisión terminada".
  const [highlights] = useState(() =>
    computeHighlights(garment, needsReviewThreshold, colorReviewThreshold),
  );
  const [draft, setDraft] = useState<Draft>({});
  const [errors, setErrors] = useState<Partial<Record<FieldName, string>>>({});
  const [completeError, setCompleteError] = useState<string | null>(null);
  // Only one collapsed-by-default row is open at a time; doubtful fields are always open.
  const [expanded, setExpanded] = useState<FieldName | null>(null);
  const [choosingColors, setChoosingColors] = useState(false);
  // The open free-text field registers here so typed-but-unsaved text can be committed on demand.
  const flushText = useRef<FlushText | null>(null);

  const value = <K extends keyof Draft>(field: K): Garment[K & keyof Garment] =>
    (field in draft ? draft[field] : garment[field as keyof Garment]) as Garment[K & keyof Garment];

  /** Saves right away; shows the value optimistically and reverts it on failure. */
  const save = async <K extends FieldName>(
    field: K,
    body: GarmentPatch,
    shown: Draft[K],
  ): Promise<boolean> => {
    setErrors((current) => ({ ...current, [field]: undefined }));
    setDraft((current) => ({ ...current, [field]: shown }));
    try {
      await patch.mutateAsync(body);
      if (COLLAPSE_AFTER_SAVE.has(field)) {
        setExpanded((current) => (current === field ? null : current));
      }
      return true;
    } catch {
      setErrors((current) => ({ ...current, [field]: SAVE_ERROR }));
      return false;
    } finally {
      setDraft((current) => {
        const { [field]: _dropped, ...rest } = current;
        return rest;
      });
    }
  };

  const finish = async () => {
    setCompleteError(null);
    // Text still being typed is saved first; if that fails the review stays open with its error.
    if (!(await (flushText.current?.() ?? true))) return;
    try {
      await complete.mutateAsync();
      router.replace('/(tabs)/wardrobe');
    } catch {
      setCompleteError('No se pudo terminar la revisión. Inténtalo de nuevo.');
    }
  };

  const uri = imageUrl(garment.img_cutout) ?? imageUrl(garment.img_thumb);
  const category = value('category');
  const pattern = value('pattern');
  const formality = value('formality');
  const warmth = value('warmth');
  const styleTags = (value('style_tags') ?? []) as string[];
  const seasons = (value('seasons') ?? []) as string[];
  const garmentColors = value('colors');
  const colorNames = (garmentColors ?? []).map((entry) => entry.name);

  const toggleColor = (name: string) => {
    const next = colorNames.includes(name)
      ? colorNames.filter((n) => n !== name)
      : [...colorNames, name];
    const built = buildColors(next, garment.colors);
    void save('colors', { colors: built }, built);
  };
  const toggleIn = (list: string[], item: string) =>
    list.includes(item) ? list.filter((v) => v !== item) : [...list, item];

  /** One-line text for a collapsed row. */
  const summary = (name: FieldName): string => {
    const join = (items: string[]) => (items.length ? items.join(', ') : EMPTY_SUMMARY);
    switch (name) {
      case 'category':
        return category ? CATEGORY_LABELS[category] : EMPTY_SUMMARY;
      case 'subcategory':
        return (value('subcategory') as string | null) || EMPTY_SUMMARY;
      case 'colors':
        return join(colorNames);
      case 'pattern':
        return pattern ? PATTERN_LABELS[pattern] : EMPTY_SUMMARY;
      case 'formality':
        return formality ? `${formality} de 5` : EMPTY_SUMMARY;
      case 'style_tags':
        return join(styleTags.map((tag) => STYLE_LABELS[tag as keyof typeof STYLE_LABELS] ?? tag));
      case 'seasons':
        return join(
          seasons.map((season) => SEASON_LABELS[season as keyof typeof SEASON_LABELS] ?? season),
        );
      case 'warmth':
        return warmth ? `${warmth} de 5` : EMPTY_SUMMARY;
      case 'material':
        return (value('material') as string | null) || EMPTY_SUMMARY;
    }
  };

  const levels = (
    group: string,
    current: number | null | undefined,
    field: 'formality' | 'warmth',
  ) => (
    <ChipRow>
      {LEVELS.map((level) => (
        <Chip
          key={level}
          group={group}
          label={String(level)}
          selected={current === level}
          onPress={() => current !== level && void save(field, { [field]: level }, level)}
        />
      ))}
    </ChipRow>
  );

  const editor = (name: FieldName): ReactNode => {
    switch (name) {
      case 'category':
        return (
          <ChipRow>
            {CATEGORY_ORDER.map((key) => (
              <Chip
                key={key}
                group="Categoría"
                label={CATEGORY_LABELS[key]}
                selected={category === key}
                onPress={() => category !== key && void save('category', { category: key }, key)}
              />
            ))}
          </ChipRow>
        );
      case 'subcategory':
        return (
          <TextField
            label="Subcategoría"
            value={(value('subcategory') as string | null) ?? ''}
            flushRef={flushText}
            onSave={(text) => save('subcategory', { subcategory: text }, text)}
          />
        );
      case 'colors':
        return (
          <>
            <View style={styles.swatchList} testID="color-swatches">
              {(garmentColors ?? []).map((entry) => (
                <View key={entry.name} style={styles.swatch}>
                  <View style={[styles.swatchDot, { backgroundColor: entry.hex }]} />
                  <Text style={styles.swatchText}>
                    {entry.name} {Math.round(entry.proportion * 100)} %
                  </Text>
                </View>
              ))}
              {!garmentColors?.length ? (
                <Text style={styles.swatchText}>{EMPTY_SUMMARY}</Text>
              ) : null}
            </View>
            {choosingColors ? (
              <>
                <Text style={styles.hint}>
                  Elige hasta {MAX_COLORS} colores; el primero es el dominante.
                </Text>
                <ChipRow>
                  {PALETTE_NAMES.map((paletteName) => {
                    const selected = colorNames.includes(paletteName);
                    return (
                      <Pressable
                        key={paletteName}
                        accessibilityRole="button"
                        accessibilityLabel={`Color: ${paletteName}`}
                        accessibilityState={{ selected }}
                        disabled={
                          (selected && colorNames.length === 1) ||
                          (!selected && colorNames.length >= MAX_COLORS)
                        }
                        onPress={() => toggleColor(paletteName)}
                        style={[styles.paletteChip, selected && styles.paletteChipSelected]}
                      >
                        <View
                          style={[styles.swatchDot, { backgroundColor: paletteHex(paletteName) }]}
                        />
                        <Text style={styles.chipLabel}>{paletteName}</Text>
                      </Pressable>
                    );
                  })}
                </ChipRow>
                <LinkButton
                  label="Listo con los colores"
                  onPress={() => setChoosingColors(false)}
                />
              </>
            ) : (
              <LinkButton label="Cambiar colores" onPress={() => setChoosingColors(true)} />
            )}
          </>
        );
      case 'pattern':
        return (
          <ChipRow>
            {PATTERN_ORDER.map((key) => (
              <Chip
                key={key}
                group="Estampado"
                label={PATTERN_LABELS[key]}
                selected={pattern === key}
                onPress={() => pattern !== key && void save('pattern', { pattern: key }, key)}
              />
            ))}
          </ChipRow>
        );
      case 'formality':
        return levels('Formalidad', formality, 'formality');
      case 'style_tags':
        return (
          <ChipRow>
            {STYLE_ORDER.map((key) => {
              const selected = styleTags.includes(key);
              const next = toggleIn(styleTags, key) as components['schemas']['StyleTag'][];
              return (
                <Chip
                  key={key}
                  group="Estilo"
                  label={STYLE_LABELS[key]}
                  selected={selected}
                  disabled={!selected && styleTags.length >= MAX_STYLE_TAGS}
                  onPress={() => void save('style_tags', { style_tags: next }, next)}
                />
              );
            })}
          </ChipRow>
        );
      case 'seasons':
        return (
          <ChipRow>
            {SEASON_ORDER.map((key) => {
              const next = toggleIn(seasons, key) as components['schemas']['Season'][];
              return (
                <Chip
                  key={key}
                  group="Temporada"
                  label={SEASON_LABELS[key]}
                  selected={seasons.includes(key)}
                  onPress={() => void save('seasons', { seasons: next }, next)}
                />
              );
            })}
          </ChipRow>
        );
      case 'warmth':
        return levels('Abrigo', warmth, 'warmth');
      case 'material':
        return (
          <>
            <TextField
              label="Material"
              value={(value('material') as string | null) ?? ''}
              flushRef={flushText}
              onSave={(text) => save('material', { material: text }, text)}
            />
            <ChipRow>
              {MATERIAL_SUGGESTIONS.map((suggestion) => (
                <Chip
                  key={suggestion}
                  group="Material"
                  label={suggestion}
                  selected={value('material') === suggestion}
                  onPress={() =>
                    value('material') !== suggestion &&
                    void save('material', { material: suggestion }, suggestion)
                  }
                />
              ))}
            </ChipRow>
          </>
        );
    }
  };

  const errorText = (name: FieldName) =>
    errors[name] ? (
      <Text style={styles.error} testID={`error-${name}`}>
        {errors[name]}
      </Text>
    ) : null;

  const reviewFields = FIELD_ORDER.filter((name) => highlights.has(name));
  const otherFields = FIELD_ORDER.filter((name) => !highlights.has(name));

  return (
    <View style={styles.screen}>
      <ScrollView
        style={styles.scroll}
        testID="review-scroll"
        contentContainerStyle={[styles.container, centeredContentStyle]}
        keyboardShouldPersistTaps="handled"
      >
        {uri ? (
          <HeroImage
            uri={uri}
            testID="review-image"
            maxHeightRatio={REVIEW_HERO_HEIGHT_RATIO}
            compact
          />
        ) : null}

        {reviewFields.length || garment.needs_review ? (
          <View style={styles.groupHeader}>
            <Text style={styles.groupTitle} accessibilityRole="header">
              {reviewFields.length ? 'Por revisar' : 'Ficha de la prenda'}
            </Text>
            {garment.needs_review ? (
              <View style={styles.badge} testID="review-badge">
                <Text style={styles.badgeText}>Pendiente de revisión</Text>
              </View>
            ) : null}
          </View>
        ) : null}

        {reviewFields.map((name) => (
          <View key={name} testID={`field-${name}`} style={styles.reviewField}>
            <View style={styles.fieldHeader}>
              <Text style={styles.reviewLabel}>{FIELD_LABELS[name]}</Text>
              <Text style={styles.doubt} testID={`highlight-${name}`}>
                Revisar
              </Text>
            </View>
            {FIELD_HINTS[name] ? <Text style={styles.hint}>{FIELD_HINTS[name]}</Text> : null}
            {editor(name)}
            {errorText(name)}
          </View>
        ))}

        {otherFields.length ? (
          <View style={styles.rows}>
            {reviewFields.length ? <Text style={styles.restTitle}>Resto de la ficha</Text> : null}
            {otherFields.map((name) => {
              const open = expanded === name;
              return (
                <View key={name} testID={`field-${name}`} style={styles.row}>
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel={`${FIELD_LABELS[name]}, ${summary(name)}`}
                    accessibilityState={{ expanded: open }}
                    onPress={() => {
                      void flushText.current?.();
                      setExpanded(open ? null : name);
                      if (name === 'colors') setChoosingColors(false);
                    }}
                    style={styles.rowHeader}
                  >
                    <Text style={styles.rowLabel}>{FIELD_LABELS[name]}</Text>
                    {name === 'colors' && !open ? (
                      <View style={styles.rowDots}>
                        {(garmentColors ?? []).map((entry) => (
                          <View
                            key={entry.name}
                            style={[styles.swatchDot, { backgroundColor: entry.hex }]}
                          />
                        ))}
                      </View>
                    ) : null}
                    <Text style={styles.rowValue} numberOfLines={1}>
                      {summary(name)}
                    </Text>
                    <Text style={[styles.chevron, open && styles.chevronOpen]}>›</Text>
                  </Pressable>
                  {open ? (
                    <View style={styles.rowEditor}>
                      {FIELD_HINTS[name] ? (
                        <Text style={styles.hint}>{FIELD_HINTS[name]}</Text>
                      ) : null}
                      {editor(name)}
                    </View>
                  ) : null}
                  {errorText(name)}
                </View>
              );
            })}
          </View>
        ) : null}
      </ScrollView>

      <View style={styles.footer}>
        <View style={[styles.footerInner, centeredContentStyle]}>
          {completeError ? (
            <Text style={styles.error} testID="complete-error">
              {completeError}
            </Text>
          ) : null}
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Revisión terminada"
            onPress={() => void finish()}
            style={({ pressed }) => [styles.done, pressed && styles.donePressed]}
          >
            <Text style={styles.doneText}>Revisión terminada</Text>
          </Pressable>
        </View>
      </View>
    </View>
  );
}

function ChipRow({ children }: { children: ReactNode }) {
  return <View style={styles.chipRow}>{children}</View>;
}

function LinkButton({ label, onPress }: { label: string; onPress: () => void }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      hitSlop={8}
      style={styles.link}
    >
      <Text style={styles.linkText}>{label}</Text>
    </Pressable>
  );
}

/** Commits pending text; resolves false only when saving it failed. */
type FlushText = () => Promise<boolean>;

/**
 * Free-text control: saves on blur / submit when the text changed and is not empty. It also
 * registers `flushRef` so the screen can commit it before finishing or collapsing the row.
 */
function TextField({
  label,
  value,
  onSave,
  flushRef,
}: {
  label: string;
  value: string;
  onSave: (text: string) => Promise<boolean>;
  flushRef: MutableRefObject<FlushText | null>;
}) {
  // `null` = untouched: show the saved value; otherwise the text being typed.
  const [edit, setEdit] = useState<string | null>(null);

  const commit: FlushText = async () => {
    if (edit === null) return true;
    const trimmed = edit.trim();
    setEdit(null);
    return trimmed && trimmed !== value ? onSave(trimmed) : true;
  };

  useEffect(() => {
    flushRef.current = commit;
    return () => {
      if (flushRef.current === commit) flushRef.current = null;
    };
  });

  return (
    <TextInput
      accessibilityLabel={label}
      value={edit ?? value}
      onChangeText={setEdit}
      onBlur={() => void commit()}
      onSubmitEditing={() => void commit()}
      placeholder={EMPTY_SUMMARY}
      placeholderTextColor={theme.muted}
      style={styles.input}
    />
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: theme.stone },
  scroll: { flex: 1 },
  container: { padding: spacing.lg, gap: spacing.md },
  groupHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.md,
    marginTop: spacing.xs,
  },
  groupTitle: {
    fontFamily: fontFamilies.display,
    fontSize: fontSizes.title,
    lineHeight: lineHeights.title,
    color: theme.charcoal,
  },
  badge: {
    paddingVertical: 2,
    paddingHorizontal: spacing.md,
    borderRadius: radii.pill,
    backgroundColor: theme.brass,
  },
  badgeText: {
    color: theme.onBrass,
    fontFamily: fontFamilies.bodySemiBold,
    fontSize: fontSizes.caption,
    lineHeight: lineHeights.caption,
  },
  reviewField: {
    gap: spacing.sm,
    paddingLeft: spacing.md,
    paddingVertical: spacing.xs,
    borderLeftWidth: 3,
    borderLeftColor: theme.brass,
  },
  fieldHeader: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  reviewLabel: {
    fontFamily: fontFamilies.bodySemiBold,
    fontSize: fontSizes.body,
    lineHeight: lineHeights.body,
    color: theme.charcoal,
  },
  doubt: {
    fontFamily: fontFamilies.bodyMedium,
    fontSize: fontSizes.caption,
    color: theme.muted,
  },
  restTitle: {
    fontFamily: fontFamilies.bodyMedium,
    fontSize: fontSizes.small,
    color: theme.muted,
    marginTop: spacing.sm,
    marginBottom: spacing.xs,
  },
  rows: { borderTopWidth: 1, borderTopColor: theme.hairline },
  row: { borderBottomWidth: 1, borderBottomColor: theme.hairline },
  rowHeader: {
    minHeight: 48,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingVertical: spacing.sm,
  },
  rowLabel: {
    width: 112,
    fontFamily: fontFamilies.body,
    fontSize: fontSizes.small,
    color: theme.muted,
  },
  rowDots: { flexDirection: 'row', gap: 4 },
  rowValue: {
    flex: 1,
    textAlign: 'right',
    fontFamily: fontFamilies.bodyMedium,
    fontSize: fontSizes.small,
    color: theme.charcoal,
  },
  chevron: { fontSize: fontSizes.title, lineHeight: lineHeights.title, color: theme.muted },
  chevronOpen: { transform: [{ rotate: '90deg' }] },
  rowEditor: { gap: spacing.sm, paddingBottom: spacing.md },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  swatchList: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.md },
  swatch: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  swatchDot: {
    width: 16,
    height: 16,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: theme.hairline,
  },
  swatchText: {
    fontFamily: fontFamilies.body,
    fontSize: fontSizes.small,
    color: theme.charcoal,
  },
  hint: { fontFamily: fontFamilies.body, fontSize: fontSizes.caption, color: theme.muted },
  paletteChip: {
    minHeight: 36,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: spacing.md,
    borderRadius: radii.pill,
    borderWidth: 1,
    borderColor: theme.hairline,
    backgroundColor: theme.plinth,
  },
  paletteChipSelected: { borderColor: theme.olive, borderWidth: 2 },
  chipLabel: {
    fontFamily: fontFamilies.bodyMedium,
    fontSize: fontSizes.small,
    color: theme.charcoal,
  },
  link: { alignSelf: 'flex-start', minHeight: 32, justifyContent: 'center' },
  linkText: {
    fontFamily: fontFamilies.bodySemiBold,
    fontSize: fontSizes.small,
    color: theme.olive,
    textDecorationLine: 'underline',
  },
  input: {
    minHeight: 44,
    borderWidth: 1,
    borderColor: theme.hairline,
    borderRadius: radii.sm,
    backgroundColor: theme.plinth,
    paddingHorizontal: spacing.md,
    fontFamily: fontFamilies.body,
    fontSize: fontSizes.body,
    color: theme.charcoal,
  },
  error: {
    fontFamily: fontFamilies.body,
    fontSize: fontSizes.small,
    color: theme.error,
  },
  footer: {
    borderTopWidth: 1,
    borderTopColor: theme.hairline,
    backgroundColor: theme.stone,
  },
  footerInner: { padding: spacing.lg, gap: spacing.sm },
  done: {
    minHeight: 48,
    borderRadius: radii.sm,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: theme.olive,
  },
  donePressed: { opacity: 0.85 },
  doneText: {
    color: theme.onOlive,
    fontFamily: fontFamilies.bodySemiBold,
    fontSize: fontSizes.body,
  },
});
