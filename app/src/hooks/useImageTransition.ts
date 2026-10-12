import { useReducedMotion } from '@/hooks/useReducedMotion';

const FADE_MS = 160;

/** Short cross-fade for loading images; no animation when the OS asks for reduced motion (live). */
export function useImageTransition(): number {
  return useReducedMotion() ? 0 : FADE_MS;
}
