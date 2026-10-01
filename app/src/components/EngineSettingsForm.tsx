import { useState } from 'react';
import { StyleSheet, Text, TextInput, View } from 'react-native';

import { Button } from '@/components/ui';

import { usePatchSettings, type SettingsPatch } from '@/hooks/useSettings';
import {
  fieldsFromSettings,
  formatWeight,
  validateEngineFields,
  weightSum,
  type EngineFields,
  type EngineSettings,
} from '@/lib/engine-settings';
import { colors, fontFamilies, radii, spacing } from '@/theme';

const FIELDS: { key: keyof EngineFields; label: string; hint?: string }[] = [
  { key: 'weight_color', label: 'Peso de color', hint: '0 a 1' },
  { key: 'weight_style', label: 'Peso de estilo', hint: '0 a 1' },
  { key: 'weight_novelty', label: 'Peso de novedad', hint: '0 a 1' },
  { key: 'weight_preference', label: 'Peso de preferencia', hint: '0 a 1' },
  {
    key: 'no_repeat_days',
    label: 'Días sin repetir',
    hint: 'Días antes de volver a usar una prenda',
  },
  { key: 'max_accessories', label: 'Máximo de complementos', hint: 'Complementos por outfit' },
];

const WEIGHT_KEYS = FIELDS.slice(0, 4).map((field) => field.key);

/**
 * Editable engine settings (Ajustes): the four scoring weights, days before a
 * garment repeats and the maximum number of accessories (API-REQ-014/015).
 * Cheap checks run client-side; the server stays the authority and its
 * `INVALID_WEIGHTS` message is shown inline.
 */
export function EngineSettingsForm({ settings }: { settings: EngineSettings }) {
  const patch = usePatchSettings();
  const [fields, setFields] = useState<EngineFields>(() => fieldsFromSettings(settings));
  const [errors, setErrors] = useState<Partial<Record<keyof EngineFields | 'form', string>>>({});
  const [saved, setSaved] = useState(false);

  const change = (key: keyof EngineFields, value: string) => {
    setFields((current) => ({ ...current, [key]: value }));
    // A corrected field drops its own error and the cross-field sum error;
    // the remaining errors stay until the next "Guardar".
    setErrors(({ [key]: _field, form: _form, ...rest }) => rest);
    setSaved(false);
    patch.reset();
  };

  const save = () => {
    const result = validateEngineFields(fields);
    setErrors(result.errors);
    if (!result.values) return;
    setSaved(false);
    patch.mutate(result.values satisfies SettingsPatch, {
      onSuccess: (data) => {
        setFields(fieldsFromSettings(data));
        setSaved(true);
      },
    });
  };

  const sum = weightSum(fields);

  return (
    <View style={styles.form}>
      <View style={styles.grid}>
        {FIELDS.map(({ key, label, hint }) => (
          <View key={key} style={styles.field}>
            <Text style={styles.label}>{label}</Text>
            <TextInput
              accessibilityLabel={label}
              value={fields[key]}
              onChangeText={(value) => change(key, value)}
              keyboardType={WEIGHT_KEYS.includes(key) ? 'decimal-pad' : 'number-pad'}
              style={[styles.input, errors[key] ? styles.inputError : null]}
            />
            {errors[key] ? (
              <Text style={styles.error}>{errors[key]}</Text>
            ) : hint ? (
              <Text style={styles.hint}>{hint}</Text>
            ) : null}
          </View>
        ))}
      </View>
      <Text style={styles.sum} testID="weight-sum">
        {sum === null ? 'Suma de pesos: —' : `Suma de pesos: ${formatWeight(sum)} (debe ser 1,00)`}
      </Text>
      {errors.form ? <Text style={styles.error}>{errors.form}</Text> : null}
      {patch.isError ? (
        <Text style={styles.error} accessibilityRole="alert">
          {patch.error.message}
        </Text>
      ) : null}
      {saved ? <Text style={styles.ok}>Ajustes guardados</Text> : null}
      <View style={styles.action}>
        <Button
          label={patch.isPending ? 'Guardando…' : 'Guardar'}
          accessibilityLabel="Guardar"
          disabled={patch.isPending}
          onPress={save}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  form: { gap: spacing.lg },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.lg },
  field: { flexGrow: 1, flexBasis: 240, gap: 6 },
  label: { fontFamily: fontFamilies.bodySemiBold, fontSize: 14, color: colors.ink },
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
  inputError: { borderColor: colors.danger, borderWidth: 2 },
  hint: { fontFamily: fontFamilies.body, fontSize: 13, lineHeight: 18, color: colors.ink2 },
  sum: { fontFamily: fontFamilies.bodyMedium, fontSize: 13.5, color: colors.ink2 },
  error: { fontFamily: fontFamilies.body, fontSize: 13.5, lineHeight: 19, color: colors.danger },
  ok: { fontFamily: fontFamilies.bodySemiBold, fontSize: 14, color: colors.okText },
  action: { alignSelf: 'flex-start' },
});
