import { useLocalSearchParams, useRouter } from 'expo-router';
import { useState, type ReactNode } from 'react';
import { Image, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import { ApiError } from '@/api-client/errors';
import type { components } from '@/api-client/schema';
import { Chip } from '@/components/Chip';
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

type Garment = components['schemas']['GarmentDetail'];

const DEFAULT_NEEDS_REVIEW_THRESHOLD = 0.7;
const DEFAULT_COLOR_REVIEW_THRESHOLD = 0.7;
const MAX_STYLE_TAGS = 3;
const LEVELS = [1, 2, 3, 4, 5];
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
 * Revisión (Review): cutout + one editable control per attribute + the single
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

  const value = <K extends keyof Draft>(field: K): Garment[K & keyof Garment] =>
    (field in draft ? draft[field] : garment[field as keyof Garment]) as Garment[K & keyof Garment];

  /** Saves right away; shows the value optimistically and reverts it on failure. */
  const save = async <K extends FieldName>(field: K, body: GarmentPatch, shown: Draft[K]) => {
    setErrors((current) => ({ ...current, [field]: undefined }));
    setDraft((current) => ({ ...current, [field]: shown }));
    try {
      await patch.mutateAsync(body);
    } catch {
      setErrors((current) => ({ ...current, [field]: SAVE_ERROR }));
    } finally {
      setDraft((current) => {
        const { [field]: _dropped, ...rest } = current;
        return rest;
      });
    }
  };

  const finish = async () => {
    setCompleteError(null);
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
  const colors = value('colors');
  const colorNames = (colors ?? []).map((entry) => entry.name);

  const field = (name: FieldName, label: string, children: ReactNode) => (
    <Field name={name} label={label} highlighted={highlights.has(name)} error={errors[name]}>
      {children}
    </Field>
  );

  const toggleColor = (name: string) => {
    const next = colorNames.includes(name)
      ? colorNames.filter((n) => n !== name)
      : [...colorNames, name];
    const built = buildColors(next, garment.colors);
    void save('colors', { colors: built }, built);
  };
  const toggleIn = (list: string[], item: string) =>
    list.includes(item) ? list.filter((v) => v !== item) : [...list, item];

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <View style={styles.imageBox}>
        {uri ? (
          <Image source={{ uri }} style={styles.image} resizeMode="contain" testID="review-image" />
        ) : null}
      </View>
      {garment.needs_review ? (
        <View style={styles.badge} testID="review-badge">
          <Text style={styles.badgeText}>Pendiente de revisión</Text>
        </View>
      ) : null}

      {field(
        'category',
        'Categoría',
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
        </ChipRow>,
      )}

      {field(
        'subcategory',
        'Subcategoría',
        <TextField
          label="Subcategoría"
          value={(value('subcategory') as string | null) ?? ''}
          onSave={(text) => void save('subcategory', { subcategory: text }, text)}
        />,
      )}

      {field(
        'colors',
        'Colores',
        <>
          <View style={styles.swatchRow} testID="color-swatches">
            {(colors ?? []).map((entry) => (
              <View key={entry.name} style={styles.swatch}>
                <View style={[styles.swatchDot, { backgroundColor: entry.hex }]} />
                <Text style={styles.swatchText}>
                  {entry.name} {Math.round(entry.proportion * 100)}%
                </Text>
              </View>
            ))}
          </View>
          <Text style={styles.hint}>
            Elige hasta {MAX_COLORS} colores; el primero es el dominante.
          </Text>
          <ChipRow>
            {PALETTE_NAMES.map((name) => {
              const selected = colorNames.includes(name);
              return (
                <Pressable
                  key={name}
                  accessibilityRole="button"
                  accessibilityLabel={`Color: ${name}`}
                  accessibilityState={{ selected }}
                  disabled={
                    (selected && colorNames.length === 1) ||
                    (!selected && colorNames.length >= MAX_COLORS)
                  }
                  onPress={() => toggleColor(name)}
                  style={[styles.paletteChip, selected && styles.paletteChipSelected]}
                >
                  <View style={[styles.swatchDot, { backgroundColor: paletteHex(name) }]} />
                  <Text style={styles.chipLabel}>{name}</Text>
                </Pressable>
              );
            })}
          </ChipRow>
        </>,
      )}

      {field(
        'pattern',
        'Estampado',
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
        </ChipRow>,
      )}

      {field(
        'formality',
        'Formalidad (1 = informal, 5 = formal)',
        <ChipRow>
          {LEVELS.map((level) => (
            <Chip
              key={level}
              group="Formalidad"
              label={String(level)}
              selected={formality === level}
              onPress={() =>
                formality !== level && void save('formality', { formality: level }, level)
              }
            />
          ))}
        </ChipRow>,
      )}

      {field(
        'style_tags',
        `Estilos (máx. ${MAX_STYLE_TAGS})`,
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
        </ChipRow>,
      )}

      {field(
        'seasons',
        'Temporadas',
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
        </ChipRow>,
      )}

      {field(
        'warmth',
        'Abrigo (1 = fresco, 5 = muy abrigado)',
        <ChipRow>
          {LEVELS.map((level) => (
            <Chip
              key={level}
              group="Abrigo"
              label={String(level)}
              selected={warmth === level}
              onPress={() => warmth !== level && void save('warmth', { warmth: level }, level)}
            />
          ))}
        </ChipRow>,
      )}

      {field(
        'material',
        'Material',
        <>
          <TextField
            label="Material"
            value={(value('material') as string | null) ?? ''}
            onSave={(text) => void save('material', { material: text }, text)}
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
        </>,
      )}

      {completeError ? (
        <Text style={styles.error} testID="complete-error">
          {completeError}
        </Text>
      ) : null}
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Revisión terminada"
        onPress={() => void finish()}
        style={styles.done}
      >
        <Text style={styles.doneText}>Revisión terminada</Text>
      </Pressable>
    </ScrollView>
  );
}

function Field({
  name,
  label,
  highlighted,
  error,
  children,
}: {
  name: FieldName;
  label: string;
  highlighted: boolean;
  error?: string;
  children: ReactNode;
}) {
  return (
    <View testID={`field-${name}`} style={[styles.field, highlighted && styles.fieldHighlighted]}>
      <View style={styles.fieldHeader}>
        <Text style={styles.fieldLabel}>{label}</Text>
        {highlighted ? (
          <Text style={styles.doubt} testID={`highlight-${name}`}>
            Revisar
          </Text>
        ) : null}
      </View>
      {children}
      {error ? (
        <Text style={styles.error} testID={`error-${name}`}>
          {error}
        </Text>
      ) : null}
    </View>
  );
}

function ChipRow({ children }: { children: ReactNode }) {
  return <View style={styles.chipRow}>{children}</View>;
}

/** Free-text control: saves on blur / submit when the text changed and is not empty. */
function TextField({
  label,
  value,
  onSave,
}: {
  label: string;
  value: string;
  onSave: (text: string) => void;
}) {
  // `null` = untouched: show the saved value; otherwise the text being typed.
  const [edit, setEdit] = useState<string | null>(null);

  const commit = () => {
    if (edit === null) return;
    const trimmed = edit.trim();
    setEdit(null);
    if (trimmed && trimmed !== value) onSave(trimmed);
  };

  return (
    <TextInput
      accessibilityLabel={label}
      value={edit ?? value}
      onChangeText={setEdit}
      onBlur={commit}
      onSubmitEditing={commit}
      placeholder="Sin definir"
      style={styles.input}
    />
  );
}

const styles = StyleSheet.create({
  container: { padding: 16, gap: 12 },
  imageBox: { aspectRatio: 1, borderRadius: 10, backgroundColor: '#F1F5F9', overflow: 'hidden' },
  image: { width: '100%', height: '100%' },
  badge: {
    alignSelf: 'flex-start',
    paddingVertical: 2,
    paddingHorizontal: 10,
    borderRadius: 10,
    backgroundColor: '#F79009',
  },
  badgeText: { color: '#fff', fontSize: 12, fontWeight: '700' },
  field: { gap: 8, padding: 10, borderRadius: 10, borderWidth: 1, borderColor: 'transparent' },
  fieldHighlighted: { borderColor: '#F79009', backgroundColor: '#FFF7E6' },
  fieldHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  fieldLabel: { fontSize: 14, fontWeight: '600' },
  doubt: { fontSize: 12, fontWeight: '700', color: '#B54708' },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  swatchRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 12 },
  swatch: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  swatchDot: { width: 16, height: 16, borderRadius: 8, borderWidth: 1, borderColor: '#D0D5DD' },
  swatchText: { fontSize: 13 },
  hint: { fontSize: 12, opacity: 0.7 },
  paletteChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingVertical: 6,
    paddingHorizontal: 10,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: '#D0D5DD',
  },
  paletteChipSelected: { borderColor: '#208AEF', borderWidth: 2 },
  chipLabel: { fontSize: 13 },
  input: {
    borderWidth: 1,
    borderColor: '#D0D5DD',
    borderRadius: 8,
    paddingVertical: 8,
    paddingHorizontal: 10,
    fontSize: 15,
  },
  error: { fontSize: 13, color: '#B42318' },
  done: {
    marginTop: 8,
    paddingVertical: 14,
    borderRadius: 10,
    alignItems: 'center',
    backgroundColor: '#208AEF',
  },
  doneText: { color: '#fff', fontSize: 16, fontWeight: '700' },
});
