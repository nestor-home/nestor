import { useQuery } from "@tanstack/react-query";
import { peopleQuery } from "@/api";
import {
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
} from "@/components/ui/combobox";
import { tr } from "@/i18n/runtime";

interface Option {
  value: string; // "" for the empty choice
  label: string;
}

/**
 * Choose a person of the household by typing part of their name. The empty value is the whole
 * household (or nobody, per `empty`).
 */
export function PersonPicker({
  id,
  value,
  onChange,
  empty,
  className,
  invalid,
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
  empty?: string;
  className?: string;
  invalid?: boolean;
}) {
  const { data: people = [] } = useQuery(peopleQuery);
  const options: Option[] = [
    { value: "", label: empty ?? tr("household-everyone-capital") },
    ...people.map((p) => ({ value: p.id, label: p.name })),
  ];
  const selected = options.find((o) => o.value === value) ?? options[0] ?? null;
  return (
    <Combobox<Option>
      items={options}
      value={selected}
      onValueChange={(option, details) => {
        // Escape in the closed input means "leave" (close the dialog around it), not "clear the
        // choice": Base UI would otherwise empty the value and swallow the key
        if (details.reason === "escape-key") {
          details.cancel();
          details.allowPropagation();
          return;
        }
        onChange(option?.value ?? "");
      }}
      itemToStringLabel={(option) => option.label}
      isItemEqualToValue={(a, b) => a.value === b.value}
      autoHighlight
    >
      <ComboboxInput
        id={id}
        placeholder={tr("action-choose")}
        className={className}
        aria-invalid={invalid || undefined}
      />
      <ComboboxContent>
        <ComboboxEmpty>{tr("person-picker-empty")}</ComboboxEmpty>
        <ComboboxList>
          {(option: Option) => (
            <ComboboxItem key={option.value || "none"} value={option}>
              {option.label}
            </ComboboxItem>
          )}
        </ComboboxList>
      </ComboboxContent>
    </Combobox>
  );
}
