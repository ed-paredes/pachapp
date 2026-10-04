import { useRouter } from 'expo-router';

import { OFFLINE_NOTE } from '@/components/OfflineBanner';
import { useToast } from '@/components/ui';
import { TodayView, type TodayProblem, type TodayTip } from '@/components/today/TodayView';
import { useGarments } from '@/hooks/useGarments';
import { useNow } from '@/hooks/useNow';
import { useTodayLooks } from '@/hooks/useTodayLooks';
import { garmentName } from '@/lib/garment-name';
import { formatToday, greeting } from '@/lib/format-date';
import { LAUNDRY_FILTERS, LAUNDRY_NAMES, USAGE_FILTERS } from '@/lib/wardrobe-filters';
import { wardrobeUsage } from '@/lib/wardrobe-usage';

type NamedGarment = Parameters<typeof garmentName>[0];

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
 * Hoy: the look of the day (the best of the day's generated proposals), the other proposals as
 * "Otras opciones", "Me lo pongo" / "Otra sugerencia", and two notices derived from the wardrobe.
 * `weather` stays unset until the API has it.
 */
export default function TodayScreen() {
  const router = useRouter();
  const now = useNow();
  const toast = useToast();

  const laundry = useGarments(LAUNDRY_FILTERS);
  const active = useGarments(USAGE_FILTERS);

  // Wardrobe size reuses the two queries above: the no-proposal state must not flash the wrong copy.
  // Data wins over an error, so a failed refetch (backend offline) keeps showing what was saved.
  const wardrobeSize: number | 'loading' | 'unknown' =
    laundry.data && active.data
      ? laundry.data.total + active.data.total
      : laundry.isError || active.isError
        ? 'unknown'
        : 'loading';

  const looks = useTodayLooks({ now, wardrobeSize, notify: toast.show });
  const problem: TodayProblem | undefined =
    looks.status === 'error'
      ? looks.offline
        ? {
            title: 'Aún no hay un look guardado',
            text: 'Sin conexión no podemos prepararlo. Lo tendrás cuando vuelva la conexión.',
          }
        : {
            title: 'No pudimos preparar tu look',
            text: 'No hemos podido hablar con tu armario. Inténtalo de nuevo en un momento.',
            onRetry: looks.retry,
          }
      : undefined;
  const actionNote = looks.offline
    ? [OFFLINE_NOTE, looks.shuffleNote].filter(Boolean).join(' ')
    : looks.shuffleNote;

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
      proposal={looks.proposal}
      alternatives={looks.alternatives}
      generating={looks.status === 'loading'}
      problem={problem}
      savedNote={looks.savedFromBefore ? 'Mostrando el último look que guardamos.' : undefined}
      onOpenPiece={(id) => router.push(`/garments/${id}`)}
      onOpenAlternative={looks.openAlternative}
      onWear={looks.wear}
      onShuffle={() => void looks.shuffle()}
      wearDisabled={looks.offline || looks.wearing || looks.conflict}
      shuffleDisabled={looks.shuffleDisabled}
      actionNote={actionNote}
      replaceQuestion={
        looks.conflict
          ? { busy: looks.wearing, onConfirm: looks.confirmReplace, onCancel: looks.cancelReplace }
          : undefined
      }
      laundryTip={laundryTip}
      usageTip={usageTip}
      wardrobeSize={wardrobeSize}
      onAddGarment={() => router.push('/(tabs)/add')}
      onOpenWardrobe={() => router.push('/(tabs)/wardrobe')}
    />
  );
}
