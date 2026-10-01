import { fireEvent, render, screen } from '@testing-library/react-native';

import { AddChip } from '@/components/ui/AddChip';
import { Button } from '@/components/ui/Button';
import { FilterChip } from '@/components/ui/FilterChip';
import { Pill } from '@/components/ui/Pill';
import { SeasonPicker } from '@/components/ui/SeasonPicker';
import { Title } from '@/components/ui/Title';
import { colors, fontFamilies } from '@/theme';

describe('Button', () => {
  it('uses the label as its accessible name and reports presses', async () => {
    const onPress = jest.fn();
    await render(<Button label="Me lo pongo" onPress={onPress} />);

    await fireEvent.press(screen.getByRole('button', { name: 'Me lo pongo' }));
    expect(onPress).toHaveBeenCalledTimes(1);
  });

  it('renders an icon-only button named by its accessibilityLabel', async () => {
    await render(
      <Button
        icon={{ ios: 'arrow.triangle.2.circlepath', android: 'refresh', web: 'refresh' }}
        accessibilityLabel="Otra sugerencia"
        variant="secondary"
        onPress={() => undefined}
      />,
    );

    expect(screen.getByRole('button', { name: 'Otra sugerencia' })).toBeTruthy();
  });

  it('does not fire when disabled', async () => {
    const onPress = jest.fn();
    await render(<Button label="Guardar" onPress={onPress} disabled />);

    await fireEvent.press(screen.getByRole('button', { name: 'Guardar' }));
    expect(onPress).not.toHaveBeenCalled();
  });
});

describe('Title', () => {
  it('sets the accent phrase in italic terracotta and keeps the rest', async () => {
    await render(<Title accent="armario">Añade a tu armario</Title>);

    const title = screen.getByRole('header');
    expect(title).toHaveTextContent('Añade a tu armario');
    const accent = screen.getByText('armario');
    expect(accent.props.style).toEqual(
      expect.objectContaining({ fontFamily: fontFamilies.displayItalic, color: colors.accent }),
    );
  });

  it('renders plain text when the accent phrase is absent', async () => {
    await render(<Title accent="nada">Tu armario</Title>);
    expect(screen.getByRole('header')).toHaveTextContent('Tu armario');
  });
});

describe('FilterChip', () => {
  it('shows the counter, exposes selected state and reports presses', async () => {
    const onPress = jest.fn();
    await render(<FilterChip label="Camisas" count={4} selected onPress={onPress} />);

    expect(screen.getByText('4')).toBeTruthy();
    const chip = screen.getByRole('button', { name: 'Camisas, 4' });
    expect(chip.props.accessibilityState).toEqual({ selected: true });
    await fireEvent.press(chip);
    expect(onPress).toHaveBeenCalledTimes(1);
  });
});

describe('Pill', () => {
  it('shows its label', async () => {
    await render(<Pill label="En el armario" tone="ok" dot />);
    expect(screen.getByText('En el armario')).toBeTruthy();
  });
});

describe('AddChip', () => {
  it('defaults to "+ Añadir" and reports presses', async () => {
    const onPress = jest.fn();
    await render(<AddChip onPress={onPress} accessibilityLabel="Añadir marca" />);

    await fireEvent.press(screen.getByRole('button', { name: 'Añadir marca' }));
    expect(screen.getByText('+ Añadir')).toBeTruthy();
    expect(onPress).toHaveBeenCalledTimes(1);
  });
});

describe('SeasonPicker', () => {
  it('is read-only without onChange', async () => {
    await render(<SeasonPicker value={['summer']} />);

    expect(screen.queryAllByRole('checkbox')).toHaveLength(0);
    expect(screen.getByLabelText('Verano, activa')).toBeTruthy();
  });

  it('toggles seasons when onChange is given', async () => {
    const onChange = jest.fn();
    await render(<SeasonPicker value={['summer']} onChange={onChange} />);

    await fireEvent.press(screen.getByRole('checkbox', { name: 'Invierno' }));
    expect(onChange).toHaveBeenLastCalledWith(['summer', 'winter']);
    await fireEvent.press(screen.getByRole('checkbox', { name: 'Verano' }));
    expect(onChange).toHaveBeenLastCalledWith([]);
  });
});
