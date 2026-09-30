import { useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { usePatchSettings, type SettingsPatch } from '@/hooks/useSettings';
import {
  fieldsFromSettings,
  formatWeight,
  validateEngineFields,
  weightSum,
  type EngineFields,
  type EngineSettings,
} from '@/lib/engine-settings';

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
      <Text style={styles.hint} testID="weight-sum">
        {sum === null ? 'Suma de pesos: —' : `Suma de pesos: ${formatWeight(sum)} (debe ser 1,00)`}
      </Text>
      {errors.form ? <Text style={styles.error}>{errors.form}</Text> : null}
      {patch.isError ? (
        <Text style={styles.error} accessibilityRole="alert">
          {patch.error.message}
        </Text>
      ) : null}
      {saved ? <Text style={styles.ok}>Ajustes guardados</Text> : null}
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Guardar"
        disabled={patch.isPending}
        onPress={save}
        style={[styles.button, patch.isPending ? styles.buttonDisabled : null]}
      >
        <Text style={styles.buttonText}>{patch.isPending ? 'Guardando…' : 'Guardar'}</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  form: { gap: 12 },
  field: { gap: 4 },
  label: { fontSize: 14, fontWeight: '600' },
  input: {
    borderWidth: 1,
    borderColor: '#D0D5DD',
    borderRadius: 8,
    paddingVertical: 8,
    paddingHorizontal: 12,
    fontSize: 16,
  },
  inputError: { borderColor: '#B42318' },
  hint: { fontSize: 12, opacity: 0.6 },
  error: { fontSize: 13, color: '#B42318' },
  ok: { fontSize: 14, color: '#1a7f37' },
  button: {
    alignSelf: 'flex-start',
    paddingVertical: 10,
    paddingHorizontal: 20,
    borderRadius: 8,
    backgroundColor: '#208AEF',
  },
  buttonDisabled: { opacity: 0.6 },
  buttonText: { color: '#fff', fontWeight: '600' },
});
