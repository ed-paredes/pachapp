import { useLocalSearchParams, useRouter } from 'expo-router';
import { useEffect, useRef, useState, type MutableRefObject, type ReactNode } from 'react';
import {
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  useWindowDimensions,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { ApiError } from '@/api-client/errors';
import type { components } from '@/api-client/schema';
import { Chip } from '@/components/Chip';
import { BackButton, GarmentHero } from '@/components/GarmentHero';
import { HeroImage } from '@/components/GarmentImage';
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';
import { LoadingState } from '@/components/LoadingState';
import { StateShell, useGoBack } from '@/components/StateShell';
import { Button, Card, ColorDots, ColorSwatch, Eyebrow, Pill, Title } from '@/components/ui';
import { FORMALITY_LABELS } from '@/components/ui/FormalityMeter';
import { pressFeedback } from '@/components/ui/feedback';
import { IconSymbol } from '@/components/IconSymbol';
import { useCompleteReview, usePatchGarment, type GarmentPatch } from '@/hooks/useGarmentMutations';
import { useGarment } from '@/hooks/useGarments';
import { useSettings } from '@/hooks/useSettings';
import { garmentName } from '@/lib/garment-name';
import { imageUrl } from '@/lib/image-url';
import {
  categoryLabel,
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
import {
  colors,
  fontFamilies,
  radii,
  shadows,
  spacing,
  TWO_COLUMNS,
  CONTENT_MAX_WIDTH,
} from '@/theme';

type Garment = components['schemas']['GarmentDetail'];

const DEFAULT_NEEDS_REVIEW_THRESHOLD = 0.7;
const DEFAULT_COLOR_REVIEW_THRESHOLD = 0.7;
const MAX_STYLE_TAGS = 3;
const LEVELS = [1, 2, 3, 4, 5];
/** On phones the image spends less of the window so the fields to check fit above the fold. */
const REVIEW_HERO_HEIGHT_RATIO = 0.24;
/** Tint of the hero when the garment has no colour yet. */
const NEUTRAL_HERO = '#A39A8E';
/** The fields column never grows past this on wide screens. */
const FIELDS_MAX_WIDTH = 560;
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

/** Spoken in row labels; on screen an empty value is a dashed "+ Añadir" chip. */
const EMPTY_SUMMARY = 'sin definir';

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
    return <StateShell state={<LoadingState />} />;
  }
  if (garment.isError && !garment.data) {
    if (garment.error instanceof ApiError && garment.error.status === 404) {
      return (
        <StateShell
          state={
            <EmptyState
              title="No encontramos esta prenda"
              description="Puede que se haya eliminado. Vuelve al armario."
            />
          }
        />
      );
    }
    return (
      <StateShell
        state={
          <ErrorState message={garment.error.message} onRetry={() => void garment.refetch()} />
        }
      />
    );
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
  // Every mounted free-text field registers here so typed-but-unsaved text can be committed on
  // demand (two fields can be open at once when both are doubtful).
  const flushers = useRef(new Set<FlushText>());
  const flushText = async () =>
    (await Promise.all([...flushers.current].map((flush) => flush()))).every(Boolean);

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
    if (!(await flushText())) return;
    try {
      await complete.mutateAsync();
      router.replace('/(tabs)/wardrobe');
    } catch {
      setCompleteError('No se pudo terminar la revisión. Inténtalo de nuevo.');
    }
  };

  const goBack = useGoBack();
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();
  const twoColumns = width >= TWO_COLUMNS;
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
    <View style={styles.levels}>
      <View style={styles.levelRow}>
        {LEVELS.map((level) => (
          <Chip
            key={level}
            grow
            group={group}
            label={String(level)}
            selected={current === level}
            onPress={() => current !== level && void save(field, { [field]: level }, level)}
          />
        ))}
      </View>
      {field === 'formality' && current ? (
        <Text style={styles.levelCaption}>{FORMALITY_LABELS[current - 1]}</Text>
      ) : null}
    </View>
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
            placeholder="Por ejemplo, camiseta"
            value={(value('subcategory') as string | null) ?? ''}
            flushers={flushers}
            onSave={(text) => save('subcategory', { subcategory: text }, text)}
          />
        );
      case 'colors':
        return (
          <>
            <View style={styles.swatchList} testID="color-swatches">
              {(garmentColors ?? []).map((entry) => (
                <ColorSwatch
                  key={entry.name}
                  color={entry.hex}
                  label={`${entry.name} ${Math.round(entry.proportion * 100)} %`}
                />
              ))}
              {!garmentColors?.length ? <EmptyValue /> : null}
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
                        style={(state) => [
                          styles.paletteChip,
                          selected && styles.paletteChipSelected,
                          (selected && colorNames.length === 1) ||
                          (!selected && colorNames.length >= MAX_COLORS)
                            ? styles.paletteChipDisabled
                            : null,
                          pressFeedback(state),
                        ]}
                      >
                        <View
                          style={[styles.swatchDot, { backgroundColor: paletteHex(paletteName) }]}
                        />
                        <Text style={[styles.chipLabel, selected && styles.chipLabelSelected]}>
                          {paletteName}
                        </Text>
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
              placeholder="Por ejemplo, algodón"
              value={(value('material') as string | null) ?? ''}
              flushers={flushers}
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
  const dominant = garment.colors?.[0]?.hex ?? NEUTRAL_HERO;
  const name = garmentName({
    category,
    subcategory: value('subcategory') as string | null,
    colors: garmentColors,
    material: value('material') as string | null,
  });

  const heading = (
    <View style={styles.head}>
      <Eyebrow>{categoryLabel(category)}</Eyebrow>
      <Title>{name}</Title>
      {garment.needs_review ? (
        <Pill label="Pendiente de revisión" tone="warn" testID="review-badge" />
      ) : null}
    </View>
  );

  const fields = (
    <View style={styles.fields}>
      {reviewFields.length || garment.needs_review ? (
        <Text style={styles.sectionTitle} accessibilityRole="header">
          {reviewFields.length ? 'Por revisar' : 'Ficha de la prenda'}
        </Text>
      ) : null}

      {reviewFields.length ? (
        <Card style={styles.reviewCard}>
          {reviewFields.map((field, index) => (
            <View
              key={field}
              testID={`field-${field}`}
              style={[styles.reviewField, index > 0 && styles.reviewSeparator]}
            >
              <View style={styles.fieldHeader}>
                <Text style={styles.reviewLabel}>{FIELD_LABELS[field]}</Text>
                <Pill label="Revisar" tone="warn" testID={`highlight-${field}`} />
              </View>
              {FIELD_HINTS[field] ? <Text style={styles.hint}>{FIELD_HINTS[field]}</Text> : null}
              {editor(field)}
              {errorText(field)}
            </View>
          ))}
        </Card>
      ) : null}

      {otherFields.length ? (
        <>
          {reviewFields.length ? <Text style={styles.sectionTitle}>Resto de la ficha</Text> : null}
          <Card>
            {otherFields.map((field, index) => {
              const open = expanded === field;
              const empty = summary(field) === EMPTY_SUMMARY;
              return (
                <View
                  key={field}
                  testID={`field-${field}`}
                  style={[styles.row, index > 0 && styles.rowSeparator]}
                >
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel={`${FIELD_LABELS[field]}, ${summary(field)}`}
                    accessibilityState={{ expanded: open }}
                    onPress={() => {
                      void flushText();
                      setExpanded(open ? null : field);
                      if (field === 'colors') setChoosingColors(false);
                    }}
                    style={(state) => [styles.rowHeader, pressFeedback(state)]}
                  >
                    <Text style={styles.rowLabel}>{FIELD_LABELS[field]}</Text>
                    <View style={styles.rowValueBox}>
                      {empty ? (
                        <EmptyValue />
                      ) : (
                        <>
                          {field === 'colors' && !open ? (
                            <ColorDots
                              colors={(garmentColors ?? []).map((entry) => entry.hex)}
                              ringColor={colors.surface}
                            />
                          ) : null}
                          <Text style={styles.rowValue} numberOfLines={1}>
                            {summary(field)}
                          </Text>
                        </>
                      )}
                    </View>
                    <View style={open ? styles.chevronOpen : undefined}>
                      <IconSymbol name={CHEVRON} size={18} color={colors.ink2} />
                    </View>
                  </Pressable>
                  {open ? (
                    <View style={styles.rowEditor}>
                      {FIELD_HINTS[field] ? (
                        <Text style={styles.hint}>{FIELD_HINTS[field]}</Text>
                      ) : null}
                      {editor(field)}
                    </View>
                  ) : null}
                  {errorText(field)}
                </View>
              );
            })}
          </Card>
        </>
      ) : null}
    </View>
  );

  return (
    <View style={styles.screen}>
      <ScrollView
        style={styles.scroll}
        testID="review-scroll"
        contentContainerStyle={[
          styles.container,
          { paddingTop: insets.top + (twoColumns ? spacing.xxl : spacing.md) },
        ]}
        keyboardShouldPersistTaps="handled"
      >
        {twoColumns ? (
          <View style={styles.pageTwo}>
            <View style={styles.heroColumn}>
              <GarmentHero
                uri={uri}
                color={dominant}
                onBack={goBack}
                analyzed={!!garment.img_cutout}
                sticky
                testID="review-image"
              />
            </View>
            <View style={styles.fieldsColumn}>
              {heading}
              {fields}
            </View>
          </View>
        ) : (
          <View style={styles.page}>
            <View style={styles.back}>
              <BackButton onPress={goBack} />
            </View>
            {uri ? (
              <HeroImage
                uri={uri}
                tintColor={dominant}
                testID="review-image"
                maxHeightRatio={REVIEW_HERO_HEIGHT_RATIO}
                compact
              />
            ) : null}
            {heading}
            {fields}
          </View>
        )}
      </ScrollView>

      <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.md }]}>
        <View style={[styles.footerInner, twoColumns && styles.pageTwo]}>
          {twoColumns ? <View style={styles.heroColumn} /> : null}
          <View style={twoColumns ? styles.fieldsColumn : styles.footerAction}>
            {completeError ? (
              <Text style={styles.error} testID="complete-error" accessibilityRole="alert">
                {completeError}
              </Text>
            ) : null}
            <Button label="Revisión terminada" onPress={() => void finish()} />
          </View>
        </View>
      </View>
    </View>
  );
}

function ChipRow({ children }: { children: ReactNode }) {
  return <View style={styles.chipRow}>{children}</View>;
}

/** Dashed stand-in for a value nobody has set yet (never "Sin definir"). */
function EmptyValue() {
  return (
    <View style={styles.empty}>
      <Text style={styles.emptyText}>+ Añadir</Text>
    </View>
  );
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
 * registers in `flushers` so the screen can commit it before finishing or collapsing a row.
 */
function TextField({
  label,
  placeholder,
  value,
  onSave,
  flushers,
}: {
  label: string;
  placeholder: string;
  value: string;
  onSave: (text: string) => Promise<boolean>;
  flushers: MutableRefObject<Set<FlushText>>;
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
    const registry = flushers.current;
    registry.add(commit);
    return () => {
      registry.delete(commit);
    };
  });

  return (
    <TextInput
      accessibilityLabel={label}
      value={edit ?? value}
      onChangeText={setEdit}
      onBlur={() => void commit()}
      onSubmitEditing={() => void commit()}
      placeholder={placeholder}
      placeholderTextColor={colors.ink3Text}
      style={styles.input}
    />
  );
}

const CHEVRON = { ios: 'chevron.right', android: 'chevron_right', web: 'chevron_right' } as const;

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  scroll: { flex: 1 },
  container: {
    width: '100%',
    maxWidth: CONTENT_MAX_WIDTH,
    alignSelf: 'center',
    paddingHorizontal: spacing.screen,
    paddingBottom: spacing.xxl,
  },
  page: { gap: spacing.lg },
  back: { alignItems: 'flex-start' },
  pageTwo: { flexDirection: 'row', alignItems: 'flex-start', gap: 48 },
  heroColumn: { flex: 1 },
  fieldsColumn: { flex: 1, maxWidth: FIELDS_MAX_WIDTH, gap: spacing.xl },
  head: { gap: 10 },
  fields: { gap: spacing.md },
  sectionTitle: {
    marginTop: spacing.xs,
    fontFamily: fontFamilies.display,
    fontSize: 20,
    lineHeight: 26,
    color: colors.ink,
  },
  reviewCard: { paddingHorizontal: 18 },
  reviewField: { gap: spacing.sm, paddingVertical: spacing.lg },
  reviewSeparator: { borderTopWidth: 1, borderTopColor: colors.line },
  fieldHeader: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  reviewLabel: {
    fontFamily: fontFamilies.bodySemiBold,
    fontSize: 15,
    lineHeight: 22,
    color: colors.ink,
  },
  row: { paddingHorizontal: 18 },
  rowSeparator: { borderTopWidth: 1, borderTopColor: colors.line },
  rowHeader: {
    minHeight: 56,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingVertical: spacing.sm,
  },
  rowLabel: { width: 108, fontFamily: fontFamilies.body, fontSize: 14, color: colors.ink2 },
  rowValueBox: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'flex-end',
    gap: spacing.sm,
  },
  rowValue: {
    flexShrink: 1,
    textAlign: 'right',
    fontFamily: fontFamilies.bodyMedium,
    fontSize: 14,
    color: colors.ink,
  },
  chevronOpen: { transform: [{ rotate: '90deg' }] },
  rowEditor: { gap: spacing.sm, paddingBottom: spacing.lg },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  levels: { gap: spacing.sm },
  levelRow: { flexDirection: 'row', gap: spacing.sm },
  levelCaption: { fontFamily: fontFamilies.bodySemiBold, fontSize: 13.5, color: colors.ink },
  swatchList: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  swatchDot: {
    width: 18,
    height: 18,
    borderRadius: 9,
    boxShadow: 'inset 0 0 0 1px rgba(0,0,0,0.12)',
  },
  hint: { fontFamily: fontFamilies.body, fontSize: 13, lineHeight: 18, color: colors.ink2 },
  paletteChip: {
    minHeight: 44,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingHorizontal: 14,
    borderRadius: radii.pill,
    borderWidth: 1,
    borderColor: colors.lineStrong,
    backgroundColor: colors.surface,
  },
  paletteChipSelected: { backgroundColor: colors.ink, borderColor: colors.ink },
  paletteChipDisabled: { opacity: 0.45 },
  chipLabel: { fontFamily: fontFamilies.bodyMedium, fontSize: 14, color: colors.ink },
  chipLabelSelected: { color: colors.onInk },
  link: { alignSelf: 'flex-start', minHeight: 44, justifyContent: 'center' },
  linkText: {
    fontFamily: fontFamilies.bodySemiBold,
    fontSize: 14,
    color: colors.accentText,
    textDecorationLine: 'underline',
  },
  input: {
    minHeight: 48,
    borderWidth: 1,
    borderColor: colors.lineStrong,
    borderRadius: radii.sm,
    backgroundColor: colors.surface,
    paddingHorizontal: spacing.lg,
    fontFamily: fontFamilies.body,
    fontSize: 16,
    color: colors.ink,
  },
  empty: {
    minHeight: 32,
    justifyContent: 'center',
    paddingHorizontal: 12,
    borderRadius: radii.pill,
    borderWidth: 1.5,
    borderStyle: 'dashed',
    borderColor: colors.lineStrong,
  },
  emptyText: { fontFamily: fontFamilies.bodyMedium, fontSize: 13, color: colors.ink3Text },
  error: { fontFamily: fontFamilies.body, fontSize: 14, lineHeight: 20, color: colors.danger },
  footer: {
    paddingTop: spacing.md,
    paddingHorizontal: spacing.screen,
    borderTopWidth: 1,
    borderTopColor: colors.line,
    backgroundColor: colors.bg,
    boxShadow: shadows.card,
  },
  footerInner: {
    width: '100%',
    // Same width as the content above (its side margins are the footer's padding here).
    maxWidth: CONTENT_MAX_WIDTH - spacing.screen * 2,
    alignSelf: 'center',
  },
  footerAction: { gap: spacing.sm },
});
