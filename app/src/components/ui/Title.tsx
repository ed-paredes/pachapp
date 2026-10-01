import { StyleSheet, Text, type StyleProp, type TextStyle } from 'react-native';

import { colors, fontFamilies, textStyles } from '@/theme';

type TitleProps = {
  children: string;
  /** One word or phrase of `children` set in italic accent colour. */
  accent?: string;
  /** `hero` (44 dp) or the default page title (34 dp). */
  size?: 'hero' | 'page';
  style?: StyleProp<TextStyle>;
};

/** Page title in Fraunces; an optional accent phrase is set in italic terracotta. */
export function Title({ children, accent, size = 'page', style }: TitleProps) {
  const base = size === 'hero' ? textStyles.hero : textStyles.pageTitle;
  const at = accent ? children.indexOf(accent) : -1;
  return (
    <Text accessibilityRole="header" style={[base, styles.text, style]}>
      {at < 0 || !accent ? (
        children
      ) : (
        <>
          {children.slice(0, at)}
          <Text style={styles.accent}>{accent}</Text>
          {children.slice(at + accent.length)}
        </>
      )}
    </Text>
  );
}

const styles = StyleSheet.create({
  text: { color: colors.ink },
  accent: { fontFamily: fontFamilies.displayItalic, color: colors.accent },
});
