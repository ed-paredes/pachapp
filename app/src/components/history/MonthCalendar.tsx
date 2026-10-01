import { Image } from 'expo-image';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { IconSymbol } from '@/components/IconSymbol';
import { Card } from '@/components/ui';
import { pressFeedback } from '@/components/ui/feedback';
import { colors, fontFamilies, radii, tint } from '@/theme';

export type CalendarDay = {
  /** Day of the month, 1-31. */
  day: number;
  /** Dominant colour (hex) of the outfit's main garment: tints the cell. */
  color: string;
  /** Cutout of that garment, drawn peeking out of the bottom-right corner. */
  garmentUri?: string | null;
};

type MonthCalendarProps = {
  /** Month to show; only its year and month matter. */
  month: Date;
  /** Days with a recorded outfit. */
  days?: CalendarDay[];
  /** Highlights today's cell when it falls in this month. */
  today?: Date;
  onPrevious?: () => void;
  onNext?: () => void;
  /** Called with the day of the month when a day with an outfit is pressed. */
  onSelectDay?: (day: number) => void;
};

const WEEKDAYS = ['L', 'M', 'X', 'J', 'V', 'S', 'D'];
const MONTH_NAMES = [
  'enero',
  'febrero',
  'marzo',
  'abril',
  'mayo',
  'junio',
  'julio',
  'agosto',
  'septiembre',
  'octubre',
  'noviembre',
  'diciembre',
];
const PREVIOUS = { ios: 'chevron.left', android: 'chevron_left', web: 'chevron_left' } as const;
const NEXT = { ios: 'chevron.right', android: 'chevron_right', web: 'chevron_right' } as const;

/** "Septiembre 2026". */
export function monthTitle(month: Date): string {
  const name = MONTH_NAMES[month.getMonth()];
  return `${name.charAt(0).toUpperCase()}${name.slice(1)} ${month.getFullYear()}`;
}

/** Cells of the grid: leading blanks (weeks start on Monday) then every day of the month. */
function gridCells(month: Date): (number | null)[] {
  const first = new Date(month.getFullYear(), month.getMonth(), 1);
  const length = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate();
  const blanks = (first.getDay() + 6) % 7;
  return [
    ...Array.from({ length: blanks }, () => null),
    ...Array.from({ length }, (_, index) => index + 1),
  ];
}

/**
 * Month calendar: square cells, days with an outfit tinted with the main garment peeking out of
 * the corner, today ringed in the accent colour. Purely presentational: there is no wear-log
 * endpoint yet, so Historial renders it only when it has days to show.
 */
export function MonthCalendar({
  month,
  days = [],
  today,
  onPrevious,
  onNext,
  onSelectDay,
}: MonthCalendarProps) {
  const byDay = new Map(days.map((entry) => [entry.day, entry]));
  const isToday = (day: number) =>
    !!today &&
    today.getFullYear() === month.getFullYear() &&
    today.getMonth() === month.getMonth() &&
    today.getDate() === day;
  const cells = gridCells(month);
  const rows = Array.from({ length: Math.ceil(cells.length / 7) }, (_, row) =>
    cells.slice(row * 7, row * 7 + 7),
  );

  return (
    <Card style={styles.card} testID="month-calendar">
      <View style={styles.head}>
        <NavButton label="Mes anterior" icon={PREVIOUS} onPress={onPrevious} />
        <Text accessibilityRole="header" style={styles.month}>
          {monthTitle(month)}
        </Text>
        <NavButton label="Mes siguiente" icon={NEXT} onPress={onNext} />
      </View>
      <View style={styles.row}>
        {WEEKDAYS.map((weekday) => (
          <Text key={weekday} style={styles.weekday}>
            {weekday}
          </Text>
        ))}
      </View>
      {rows.map((row, index) => (
        <View key={index} style={styles.row}>
          {Array.from({ length: 7 }, (_, column) => {
            const day = row[column] ?? null;
            if (day === null) return <View key={column} style={styles.slot} />;
            const entry = byDay.get(day);
            const label = `${day} de ${MONTH_NAMES[month.getMonth()]}${entry ? ', con outfit' : ''}`;
            const cell = (
              <View
                style={[
                  styles.day,
                  entry && { backgroundColor: tint(entry.color) },
                  isToday(day) && styles.today,
                ]}
              >
                <Text style={[styles.dayNumber, isToday(day) && styles.todayNumber]}>{day}</Text>
                {entry?.garmentUri ? (
                  <Image
                    source={{ uri: entry.garmentUri }}
                    style={styles.garment}
                    contentFit="contain"
                  />
                ) : null}
              </View>
            );
            return (
              <View key={column} style={styles.slot}>
                {entry && onSelectDay ? (
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel={label}
                    onPress={() => onSelectDay(day)}
                    style={(state) => [styles.fill, pressFeedback(state)]}
                  >
                    {cell}
                  </Pressable>
                ) : (
                  <View accessible accessibilityLabel={label} style={styles.fill}>
                    {cell}
                  </View>
                )}
              </View>
            );
          })}
        </View>
      ))}
    </Card>
  );
}

function NavButton({
  label,
  icon,
  onPress,
}: {
  label: string;
  icon: typeof PREVIOUS | typeof NEXT;
  onPress?: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled: !onPress }}
      disabled={!onPress}
      onPress={onPress}
      style={(state) => [styles.nav, !onPress && styles.navOff, pressFeedback(state)]}
    >
      <IconSymbol name={icon} size={20} color={colors.ink} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: { padding: 20, gap: 6 },
  head: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  month: { fontFamily: fontFamilies.display, fontSize: 20, lineHeight: 26, color: colors.ink },
  nav: {
    width: 44,
    height: 44,
    borderRadius: radii.pill,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surface2,
  },
  navOff: { opacity: 0.4 },
  row: { flexDirection: 'row', gap: 6 },
  weekday: {
    flex: 1,
    textAlign: 'center',
    paddingBottom: 4,
    fontFamily: fontFamilies.bodySemiBold,
    fontSize: 11.5,
    color: colors.ink3Text,
  },
  slot: { flex: 1, aspectRatio: 1 },
  fill: { flex: 1 },
  day: {
    flex: 1,
    borderRadius: radii.sm,
    overflow: 'hidden',
    paddingTop: 5,
    paddingLeft: 7,
    backgroundColor: colors.surface2,
  },
  today: { borderWidth: 2, borderColor: colors.accent },
  dayNumber: { fontFamily: fontFamilies.bodyMedium, fontSize: 11.5, color: colors.ink2 },
  todayNumber: { fontFamily: fontFamilies.bodySemiBold, color: colors.accentText },
  garment: { position: 'absolute', width: '62%', height: '62%', right: '-4%', bottom: '-6%' },
});
