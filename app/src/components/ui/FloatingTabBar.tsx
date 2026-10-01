import { BlurView } from 'expo-blur';
import type { BottomTabBarProps } from 'expo-router/js-tabs';
import { useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import Animated, { useAnimatedStyle, useSharedValue, withTiming } from 'react-native-reanimated';

import { useReducedMotion } from '@/hooks/useReducedMotion';
import { colors, fontFamilies, radii, shadows } from '@/theme';

import type { PressState } from './feedback';
import { TAB_BAR_BOTTOM_GAP } from './tab-bar-metrics';

const EXPAND_MS = 280;
/** Route that renders as the round accent button instead of an icon tab. */
const ADD_ROUTE = 'add';

type ItemProps = {
  title: string;
  accessibilityLabel: string;
  focused: boolean;
  onPress: () => void;
  renderIcon: (color: string) => React.ReactNode;
};

/** Icon tab; when active it grows into a linen pill that also shows its label. */
function TabItem({ title, accessibilityLabel, focused, onPress, renderIcon }: ItemProps) {
  const reduced = useReducedMotion();
  const [labelWidth, setLabelWidth] = useState(0);
  const width = useSharedValue(0);

  useEffect(() => {
    // +8 for the gap between the icon and the label.
    const target = focused ? labelWidth + 8 : 0;
    width.value = reduced ? target : withTiming(target, { duration: EXPAND_MS });
  }, [focused, labelWidth, reduced, width]);

  const labelStyle = useAnimatedStyle(() => ({ width: width.value }));

  return (
    <Pressable
      accessibilityRole="tab"
      accessibilityLabel={accessibilityLabel}
      accessibilityState={{ selected: focused }}
      onPress={onPress}
      style={({ hovered, pressed }: PressState) => [
        styles.item,
        focused && styles.itemOn,
        pressed && styles.itemPressed,
        hovered && !focused && styles.itemHover,
      ]}
    >
      {renderIcon(focused ? colors.ink : colors.navInactive)}
      <Animated.View style={[styles.labelClip, labelStyle]}>
        {/* Fixed-width box so the label keeps its natural width inside the clipped parent;
            its layout drives the expand animation (and re-measures once the font is ready). */}
        <View style={styles.labelBox}>
          <Text
            numberOfLines={1}
            style={styles.label}
            onLayout={(e) => setLabelWidth(Math.ceil(e.nativeEvent.layout.width))}
          >
            {title}
          </Text>
        </View>
      </Animated.View>
    </Pressable>
  );
}

/**
 * Floating pill nav, passed to `<Tabs tabBar>`: Hoy, Armario, a round "Añadir" button, Historial.
 * Keeps the accessible name "<title>, tab, N of M" so tab semantics match the default bar.
 */
export function FloatingTabBar({ state, descriptors, navigation, insets }: BottomTabBarProps) {
  return (
    <View
      pointerEvents="box-none"
      style={[styles.layer, { bottom: TAB_BAR_BOTTOM_GAP + insets.bottom }]}
    >
      <View style={styles.bar}>
        <BlurView intensity={30} tint="dark" style={StyleSheet.absoluteFill} />
        {state.routes.map((route, index) => {
          const { options } = descriptors[route.key];
          const title = options.title ?? route.name;
          const focused = state.index === index;
          const accessibilityLabel =
            options.tabBarAccessibilityLabel ??
            `${title}, tab, ${index + 1} of ${state.routes.length}`;

          const onPress = () => {
            const event = navigation.emit({
              type: 'tabPress',
              target: route.key,
              canPreventDefault: true,
            });
            if (!focused && !event.defaultPrevented) navigation.navigate(route.name, route.params);
          };
          const renderIcon = (color: string) =>
            options.tabBarIcon?.({ focused, color, size: 20 }) ?? null;

          if (route.name === ADD_ROUTE) {
            return (
              <Pressable
                key={route.key}
                accessibilityRole="tab"
                accessibilityLabel={accessibilityLabel}
                accessibilityState={{ selected: focused }}
                onPress={onPress}
                style={({ pressed }) => [
                  styles.add,
                  focused && styles.addOn,
                  pressed && styles.itemPressed,
                ]}
              >
                {renderIcon(colors.onInk)}
              </Pressable>
            );
          }
          return (
            <TabItem
              key={route.key}
              title={title}
              accessibilityLabel={accessibilityLabel}
              focused={focused}
              onPress={onPress}
              renderIcon={renderIcon}
            />
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  layer: { position: 'absolute', left: 0, right: 0, alignItems: 'center' },
  bar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    padding: 6,
    borderRadius: radii.pill,
    // Translucent ink over the blur; stays legible where blur is unsupported.
    backgroundColor: 'rgba(31,27,22,0.92)',
    overflow: 'hidden',
    boxShadow: shadows.raised,
  },
  item: {
    minHeight: 44,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    borderRadius: radii.pill,
  },
  itemOn: { backgroundColor: colors.bg },
  itemHover: { backgroundColor: 'rgba(255,255,255,0.08)' },
  itemPressed: { transform: [{ scale: 0.98 }] },
  labelClip: { overflow: 'hidden', justifyContent: 'center' },
  labelBox: { width: 200, flexShrink: 0 },
  label: {
    alignSelf: 'flex-start',
    marginLeft: 8,
    fontFamily: fontFamilies.bodyMedium,
    fontSize: 13.5,
    color: colors.ink,
  },
  add: {
    width: 44,
    height: 44,
    marginHorizontal: 4,
    borderRadius: radii.pill,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.accent,
  },
  addOn: { boxShadow: '0 0 0 3px rgba(181,86,47,0.35)' },
});
