import { useRouter } from 'expo-router';

import type { LookProposal } from '@/components/today/types';
import { TodayView, type TodayTip } from '@/components/today/TodayView';
import { useGarments } from '@/hooks/useGarments';
import { useNow } from '@/hooks/useNow';
import { garmentName } from '@/lib/garment-name';
import { formatToday, greeting } from '@/lib/format-date';
import { USAGE_PAGE_SIZE, wardrobeUsage } from '@/lib/wardrobe-usage';

type NamedGarment = Parameters<typeof garmentName>[0];

const LAUNDRY_NAMES = 2;

function plural(count: number, one: string, many: string) {
  return `${count} ${count === 1 ? one : many}`;
}

function laundryText(items: NamedGarment[], total: number): string | undefined {
  const names = items.slice(0, LAUNDRY_NAMES).map((item, index) => {
    const name = garmentName(item);
    return index === 0 ? name : name.charAt(0).toLowerCase() + name.slice(1);
  });
  if (!names.length) return undefined;
  const rest = total - names.length;
  if (rest > 0) return `${names.join(', ')} y ${plural(rest, 'más', 'más')}.`;
  return `${names.join(' y ')}.`;
}

/**
 * Hoy: the look of the day and two notices derived from the wardrobe. The outfit engine has no
 * endpoint yet, so `proposal` is always undefined and the empty state shows. To connect it, call
 * the future proposal hook here and pass `proposal`, `alternatives`, `onWear`, `onShuffle` (and
 * `weather` once the API has it) to `TodayView`.
 */
export default function TodayScreen() {
  const router = useRouter();
  const now = useNow();
  const proposal: LookProposal | undefined = undefined;

  const laundry = useGarments({ status: ['laundry'], page_size: LAUNDRY_NAMES });
  const active = useGarments({
    status: ['active'],
    sort: 'wear_count',
    order: 'desc',
    page_size: USAGE_PAGE_SIZE,
  });

  // Wardrobe size reuses the two queries above: the no-proposal state must not flash the wrong copy.
  // Data wins over an error, so a failed refetch (backend offline) keeps showing what was saved.
  const wardrobeSize: number | 'loading' | 'unknown' =
    laundry.data && active.data
      ? laundry.data.total + active.data.total
      : laundry.isError || active.isError
        ? 'unknown'
        : 'loading';

  const laundryTotal = laundry.data?.total ?? 0;
  const laundryTip: TodayTip | undefined =
    laundryTotal > 0
      ? {
          title: `${plural(laundryTotal, 'prenda', 'prendas')} en el cesto`,
          text: laundryText(laundry.data?.items ?? [], laundryTotal),
          onPress: () => router.push('/(tabs)/wardrobe'),
        }
      : undefined;

  const measured = active.data ? wardrobeUsage(active.data.items, active.data.total) : null;
  // "0% of your wardrobe" says nothing useful: show the notice once something has been worn.
  const usage = measured && measured.worn > 0 ? measured : null;
  const usageTip: TodayTip | undefined = usage
    ? {
        title: `Has usado el ${usage.percent}% de tu armario`,
        text: `${usage.worn} de ${plural(usage.total, 'prenda activa', 'prendas activas')} se han puesto alguna vez.`,
        onPress: () => router.push('/(tabs)/history'),
      }
    : undefined;

  return (
    <TodayView
      dateLabel={formatToday(now)}
      greeting={greeting(now)}
      proposal={proposal}
      laundryTip={laundryTip}
      usageTip={usageTip}
      wardrobeSize={wardrobeSize}
      onAddGarment={() => router.push('/(tabs)/add')}
      onOpenWardrobe={() => router.push('/(tabs)/wardrobe')}
    />
  );
}
